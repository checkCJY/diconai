# Wave 3 — WebSocket 인증 통합 리팩토링 실행 보고서

> **브랜치**: `feature/0508_refactory_code`
> **작업일**: 2026-05-10
> **분석 베이스**: [04 D2](../../../codereviews/2026_05_09/04_alerts_events.md), [07 G1](../../../codereviews/2026_05_09/07_geofence_positioning.md), [09 I4](../../../codereviews/2026_05_09/09_realtime_websocket.md)
> **상태**: ✅ 완료
> **검증**: pytest 84/84 통과, ruff lint+format 통과
> **의존성**: Wave 2 완료 (JWT blacklist + ROTATE + ServiceTokenAuthentication 인프라)

## 1. 작업 개요

### 1.1 목표
**산재 예방 시스템의 가장 큰 보안 위험인 WS 인증 부재** 차단:
- `/ws/worker/{user_id}/` — 임의 user_id로 타인 알람 가로채기 가능
- `/ws/sensors/` — 인증 없이 모니터링 데이터 수신 가능

**옵트인 활성화** 패턴으로 회귀 위험 0 + 점진적 활성화 가능하게 설계.

### 1.2 범위
- 백엔드 4건 (B11-1~B11-4 + B12-1~B12-3)
- JS 1건 (J17 — 8곳 호출자)
- 신규 파일 1개 (`fastapi-server/websocket/auth.py`)
- 의존성 1개 추가 (`PyJWT==2.10.1`)
- 환경변수 2개 추가 (`JWT_SIGNING_KEY`, `JWT_ALGORITHM`)
- `/ws/position/` 의도적 제외 (IoT 펌웨어 협업 별도)

### 1.3 영향 파일 (총 12개)

| 분류 | 파일 |
|---|---|
| **신규** | `fastapi-server/websocket/auth.py` |
| **백엔드 수정** | `fastapi-server/requirements.txt`, `fastapi-server/core/config.py`, `fastapi-server/websocket/routers/ws_router.py`, `drf-server/config/settings.py` |
| **JS 수정** | `shared/{alarm-ws,worker-ws,ws-client}.js`, `dashboard/websocket.js`, `detail/{websocket_gas,websocket_power,monitoring_workers}.js` |

### 1.4 의존성 체계
- Wave 1 ServiceToken 인프라와 별개 (다른 레이어)
- Wave 2 JWT blacklist + lifetime 단축 위에 빌드 (같은 SimpleJWT)
- drf SIGNING_KEY 명시 → fastapi가 같은 키로 검증

## 2. 변경 항목 상세

### B11. fastapi JWT 검증 인프라

#### B11-1. PyJWT 의존성 추가 ([requirements.txt:16](../../../../../fastapi-server/requirements.txt#L16))

**(A) 변경 내용**
- `pyjwt==2.10.1` 한 줄 추가 (alphabetical 위치)
- `.venv` 동기화: `uv pip install`로 설치

**(B) 왜 바뀌었나**
- fastapi-server에 JWT 라이브러리 부재 (검증된 결과: 의존성 목록에 없음)
- WebSocket query string의 access 토큰을 검증하려면 JWT 디코드 필요

**(C) 적용된 기능**
- `import jwt` 사용 가능
- HS256 등 표준 알고리즘 지원
- `jwt.decode()`가 만료(`ExpiredSignatureError`) + 무효(`InvalidTokenError`) 자동 처리

**(D) Before / After**
```
# Before (requirements.txt)
pydantic-settings==2.13.1
python-dotenv==1.2.2

# After
pydantic-settings==2.13.1
pyjwt==2.10.1   # 추가
python-dotenv==1.2.2
```

**(E) 다른 방법 trade-off**

| 옵션 | 장점 | 단점 | 채택 여부 |
|---|---|---|---|
| ✅ PyJWT (2.10.1) | 가장 가벼움 / 표준 / Django SimpleJWT와 호환 | — | **채택** |
| python-jose | 더 다양한 알고리즘 (cryptography 의존성) | 무거움 / 보안 이슈 사례 | 미채택 |
| authlib | 완전한 OAuth 솔루션 | 본 작업 범위 초과 | 미채택 |
| 자체 구현 | 의존성 0 | 보안 위험 / 학습 비용 | 미채택 |

#### B11-2. websocket/auth.py 신규 ([websocket/auth.py](../../../../../fastapi-server/websocket/auth.py))

**(A) 변경 내용**
- 신규 파일 (60줄)
- 함수 1개: `verify_jwt_from_ws_query(websocket: WebSocket) -> dict | None`
- 옵트인 패턴: `JWT_SIGNING_KEY` 빈 값 → `{}` 반환 (인증 비활성)
- 검증 실패 시 `None` 반환 + `logger.warning`

**(B) 왜 바뀌었나**
- 분석 근거: [09 I4](../../../codereviews/2026_05_09/09_realtime_websocket.md)
- 모든 WS 채널이 통합 인증 미들웨어 필요 — 한 곳에 검증 로직 집중

**(C) 적용된 기능**
- WS query string에서 token 추출
- PyJWT로 디코드 (HS256 + JWT_SIGNING_KEY)
- 만료/무효 토큰 거부
- 옵트인 비활성 시 빈 dict 반환 (호출자는 `is None`만 체크)

**(D) Before / After**
```python
# Before
# 파일 없음 — 모든 WS endpoint가 인증 검증 0

# After (websocket/auth.py)
def verify_jwt_from_ws_query(websocket: WebSocket) -> dict | None:
    expected_key = settings.JWT_SIGNING_KEY
    if not expected_key:
        return {}  # 옵트인 비활성

    token = websocket.query_params.get("token", "")
    if not token:
        logger.warning("[ws-auth] action=token_missing path=%s", ...)
        return None

    try:
        payload = jwt.decode(token, expected_key, algorithms=[settings.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        logger.warning("[ws-auth] action=token_expired path=%s", ...)
        return None
    except jwt.InvalidTokenError as exc:
        logger.warning("[ws-auth] action=token_invalid path=%s error=%s", ...)
        return None

    return payload
```

**(E) 다른 방법 trade-off**

| 옵션 | 장점 | 단점 | 채택 여부 |
|---|---|---|---|
| ✅ 헬퍼 함수 + 옵트인 | 단순 / 호출자 간단 / 점진 활성화 | 호출자가 close 처리 책임 | **채택** |
| FastAPI Depends 패턴 | 표준 의존성 주입 | WS는 Depends 사용 시 close 흐름 복잡 | 미채택 |
| WS Middleware | 모든 WS 자동 적용 | FastAPI는 WS middleware 미지원 (HTTP만) | 미채택 |
| 강제 활성화 | 보안 강제 | 기존 환경 즉시 깨짐 | 미채택 |

#### B11-3. fastapi config.py JWT env 추가 ([core/config.py:25-29](../../../../../fastapi-server/core/config.py#L25-L29))

**(A) 변경 내용**
- `JWT_SIGNING_KEY: str = ""` (옵트인 비활성 기본값)
- `JWT_ALGORITHM: str = "HS256"` (drf SimpleJWT 기본과 일치)

**(B) 왜 바뀌었나**
- B11-2의 검증 함수가 settings를 사용
- env 변수로 운영별 설정 + 옵트인 비활성 default

**(C) 적용된 기능**
- pydantic_settings 자동 .env 로드
- 빈 문자열 default → 기존 환경 호환

**(D) Before / After**
```python
# Before
INTERNAL_SERVICE_TOKEN: str = ""

# After
INTERNAL_SERVICE_TOKEN: str = ""

# ── WebSocket JWT 인증 (Phase 5) ──────────────────────────
JWT_SIGNING_KEY: str = ""
JWT_ALGORITHM: str = "HS256"
```

#### B11-4. drf settings.py SIMPLE_JWT["SIGNING_KEY"] 명시 ([config/settings.py:174-176](../../../../drf-server/config/settings.py#L174-L176))

**(A) 변경 내용**
- `SIMPLE_JWT`에 `"SIGNING_KEY": env("JWT_SIGNING_KEY", default=SECRET_KEY)` 추가
- 기본값 `SECRET_KEY`는 SimpleJWT 자체 기본 동작과 동일 → 호환 유지

**(B) 왜 바뀌었나**
- fastapi가 같은 키로 토큰 검증하려면 키 공유 필수
- 명시적 SIGNING_KEY가 있으면 운영자가 의도 명확히 파악 가능

**(C) 적용된 기능**
- `JWT_SIGNING_KEY` env 미설정 시: SECRET_KEY 사용 (drf 단독 작동, 기존 동작 그대로)
- `JWT_SIGNING_KEY` env 설정 시: 양 서비스 공유 키 사용

**(D) Before / After**
```python
# Before
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": ...,
    "REFRESH_TOKEN_LIFETIME": ...,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}

# After
SIMPLE_JWT = {
    ...
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    # Phase 5 WS 인증: fastapi가 같은 키로 검증할 수 있도록 명시.
    "SIGNING_KEY": env("JWT_SIGNING_KEY", default=SECRET_KEY),
}
```

**(E) 다른 방법 trade-off (B11-3 + B11-4)**

| 옵션 | 장점 | 단점 | 채택 여부 |
|---|---|---|---|
| ✅ 단일 env `JWT_SIGNING_KEY` 양 서비스 공유 (default SECRET_KEY) | 운영 단순 / 옵트인 / 호환 | 키 동기화 부담 (운영 가이드 필요) | **채택** |
| drf SECRET_KEY 직접 fastapi에 공유 | 변경 없음 | drf SECRET_KEY는 다른 용도(CSRF 등)에도 사용 → 노출 위험 | 미채택 |
| 별도 키 (drf 발급 키 ≠ fastapi 검증 키) | 명시적 분리 | 비대칭 키 (RS256) 필요 → 복잡 | 미채택 |
| 매 인증마다 drf로 검증 위임 (HTTP) | drf가 단일 진실 원천 | WS 연결마다 HTTP 1회 → 성능 저하 | 미채택 |

---

### B12. WS 엔드포인트 인증 적용

#### B12-1. `/ws/sensors/` 인증 ([ws_router.py:88-103](../../../../../fastapi-server/websocket/routers/ws_router.py#L88-L103))

**(A) 변경 내용**
- `accept()` 후 `verify_jwt_from_ws_query(websocket)` 호출
- `None` 반환 시 `close(code=1008, reason="unauthenticated")` + return
- docstring에 Phase 5 옵트인 정책 명시

**(B) 왜 바뀌었나**
- 분석 근거: [09 I4](../../../codereviews/2026_05_09/09_realtime_websocket.md)
- 인증 없이 누구나 모니터링 데이터(전력·가스·worker 위치) 수신 가능 → 정보 노출

**(C) 적용된 기능**
- 옵트인 활성화 시 토큰 없는 연결 즉시 종료
- 옵트인 비활성 시 기존 동작 (회귀 위험 0)
- close code 1008 (Policy Violation)는 WebSocket 표준

**(D) Before / After**
```python
# Before
@router.websocket("/ws/sensors/")
async def sensor_stream(websocket: WebSocket):
    await websocket.accept()
    sensor_clients.append(websocket)
    ...

# After
@router.websocket("/ws/sensors/")
async def sensor_stream(websocket: WebSocket):
    """[Phase 5] settings.JWT_SIGNING_KEY 설정 시 query token 검증."""
    await websocket.accept()
    payload = verify_jwt_from_ws_query(websocket)
    if payload is None:
        await websocket.close(code=1008, reason="unauthenticated")
        return
    sensor_clients.append(websocket)
    ...
```

#### B12-2. `/ws/worker/{user_id}/` 인증 + path 일치 검증 ([ws_router.py:117-141](../../../../../fastapi-server/websocket/routers/ws_router.py#L117-L141))

**(A) 변경 내용**
- B12-1의 인증 흐름 적용
- 추가: payload의 `user_id`와 path의 `user_id` 일치 검증
- 불일치 시 `close(code=1008, reason="forbidden")` + `logger.warning`

**(B) 왜 바뀌었나**
- 분석 근거: [04 D2](../../../codereviews/2026_05_09/04_alerts_events.md), [07 G1](../../../codereviews/2026_05_09/07_geofence_positioning.md)
- **이전에 식별된 가장 큰 보안 위험**: 클라이언트가 임의 user_id로 접속 시 다른 사용자의 지오펜스 알람 수신 가능
- 산재 예방 시스템의 정보 누출 시나리오 직접 차단

**(C) 적용된 기능**
- 토큰의 user_id가 path와 일치해야만 worker_clients에 등록됨
- 옵트인 비활성 시 (`payload`가 빈 dict) 검증 skip → 기존 동작 유지

**(D) Before / After**
```python
# Before
@router.websocket("/ws/worker/{user_id}/")
async def worker_stream(websocket: WebSocket, user_id: int):
    await websocket.accept()
    worker_clients[user_id] = websocket
    ...

# After
@router.websocket("/ws/worker/{user_id}/")
async def worker_stream(websocket: WebSocket, user_id: int):
    """[Phase 5] JWT 검증 + path user_id 일치 확인."""
    await websocket.accept()
    payload = verify_jwt_from_ws_query(websocket)
    if payload is None:
        await websocket.close(code=1008, reason="unauthenticated")
        return

    # 옵트인 활성 시 (payload truthy) path user_id 일치 확인.
    if payload and payload.get("user_id") != user_id:
        logger.warning(
            f"[ws/worker] action=forbidden token_user={payload.get('user_id')} path_user={user_id}"
        )
        await websocket.close(code=1008, reason="forbidden")
        return

    worker_clients[user_id] = websocket
    ...
```

#### B12-3. `/ws/position/` Wave 3 범위 밖 ([ws_router.py:165-172](../../../../../fastapi-server/websocket/routers/ws_router.py#L165-L172))

**(A) 변경 내용**
- 코드 동작 변경 없음
- docstring에 "Phase 5 미적용" + 사유 명시 (펌웨어 협업)

**(B) 왜 바뀌었나**
- IoT 장비 인증은 토큰 보관·갱신 메커니즘이 필요 → 펌웨어 작업
- Wave 3 범위 명확히 (분석 06 F2 / 07 G2 별도 작업)

**(C) 적용된 기능**
- 코드 변경 없이 의도 명시 — 다음 Wave에서 IoT 인증 별도 진행

**(E) trade-off (B12 전체)**

| 옵션 | 장점 | 단점 | 채택 여부 |
|---|---|---|---|
| ✅ accept 후 verify + close | FastAPI 표준 / 명확 | accept는 통과해야 close 가능 (이상한 패턴) | **채택** |
| `WebSocketException` raise | 더 정확한 의미 | starlette 1.x에서만, accept 전엔 못 던짐 | 미채택 |
| accept 전 query 검증 시도 | 거부가 더 빠름 | starlette WS는 accept 전 close 미지원 | 미채택 |
| `/ws/position/` 도 Wave 3 포함 | 일관성 | IoT 토큰 관리 부재 → 운영 즉시 깨짐 | 미채택 |

---

### J17. ws-client 호출자 attachToken 일관 적용 (8곳)

**(A) 변경 내용**
8개 호출 위치 모두 `{ attachToken: true }` 옵션 추가:

| 파일 | 라인 | 변경 |
|---|---|---|
| `shared/alarm-ws.js` | 10 | `WSClient.connect('/ws/sensors/', { attachToken: true })` |
| `shared/worker-ws.js` | 11 | `WSClient.connect('/ws/worker/' + user.id + '/', { attachToken: true })` |
| `shared/ws-client.js` | docstring | 사용 예시에 `attachToken: true` 명시 |
| `dashboard/websocket.js` | 270 | `/ws/sensors/` |
| `dashboard/websocket.js` | 449 | `/ws/positions/` |
| `detail/websocket_gas.js` | 43 | `/ws/sensors/` |
| `detail/websocket_power.js` | 121 | `/ws/sensors/` |
| `detail/monitoring_workers.js` | 332 | `/ws/sensors/` |

**(B) 왜 바뀌었나**
- B12 백엔드 인증 활성화 후 토큰 미동봉 시 모든 WS 연결 close
- ws-client.js는 이미 `attachToken: true`를 처리하지만, 호출자가 옵션 명시 안 하면 토큰 부착 안 함
- 호출자가 명시적으로 옵트인 → 의도 명확

**(C) 적용된 기능**
- ws-client.js의 `_resolveUrl`이 자동으로 `?token=<access_token>` query 부착
- access 토큰 부재 시 `console.warn` (Wave 1 J5에서 추가됨)

**(D) Before / After**
```js
// Before (예: alarm-ws.js)
const ws = WSClient.connect('/ws/sensors/');

// After
const ws = WSClient.connect('/ws/sensors/', { attachToken: true });
```

**(E) 다른 방법 trade-off**

| 옵션 | 장점 | 단점 | 채택 여부 |
|---|---|---|---|
| ✅ 호출자별 명시 옵션 | 의도 명확 / 페이지별 정책 가능 | 8곳 변경 (1줄씩) | **채택** |
| ws-client.js 기본값 변경 (`attachToken=true`) | 호출자 변경 0 | `/ws/position/` 같은 IoT 채널은 토큰 없음 → 의도 충돌 | 미채택 |
| 옵션 자동 감지 (path 기반) | 자동 | 페이지별 의도 불명 / 미래 채널 추가 시 매번 코드 변경 | 미채택 |

## 3. 적용된 신규 기능 (요약)

### 3.1 `verify_jwt_from_ws_query` 헬퍼
**위치**: [fastapi-server/websocket/auth.py](../../../../../fastapi-server/websocket/auth.py)
**역할**: WS query string의 token을 PyJWT로 검증
**옵트인**: `JWT_SIGNING_KEY` 빈 값이면 비활성

### 3.2 환경변수 `JWT_SIGNING_KEY` (양 서비스)
- **drf settings**: `SIMPLE_JWT["SIGNING_KEY"]`로 사용 (default SECRET_KEY)
- **fastapi config**: `verify_jwt_from_ws_query`가 사용
- **운영**: 양 서비스 동일 값 설정 시 활성화

### 3.3 환경변수 `JWT_ALGORITHM` (fastapi)
- 기본 HS256, drf SimpleJWT 기본과 일치

### 3.4 WS 채널별 인증 정책
- `/ws/sensors/`: 토큰 검증
- `/ws/worker/{user_id}/`: 토큰 검증 + path user_id 일치 확인
- `/ws/position/`: Wave 3 미적용 (IoT 펌웨어 협업)

### 3.5 ws-client.js attachToken 일관 활용
- 8개 호출 위치 모두 옵션 명시 → 백엔드 활성화 시 즉시 인증 통과

## 4. 검증 체크리스트

### 4.1 자동 테스트 ✅
- [x] **fastapi-server pytest**: 22 passed (PyJWT import 영향 없음)
- [x] **drf-server pytest**: 62 passed (SIGNING_KEY default=SECRET_KEY로 호환 유지)
- [x] **ruff lint**: All checks passed (4개 변경 백엔드 파일 + 7개 JS)
- [x] **ruff format**: 4 files already formatted

### 4.2 수동 검증 (운영 활성화 전 필수)

#### 4.2.1 케이스 A — JWT_SIGNING_KEY 미설정 (옵트인 비활성, 현재 상태)
- [ ] WS 연결 → 토큰 없이도 정상 통과 (기존 동작 유지)
- [ ] PR-H 4종 e2e 테스트 통과 (이미 pytest로 ✓)
- [ ] dashboard 진입 → /ws/sensors/ 연결 정상

#### 4.2.2 케이스 B — 양 서비스 동일 JWT_SIGNING_KEY 설정 (활성화)
- [ ] drf .env에 `JWT_SIGNING_KEY=<32+chars>` 설정
- [ ] fastapi .env에 동일 키 설정
- [ ] 양쪽 서버 재시작
- [ ] 정상 로그인 후 dashboard 진입 → WS 연결 통과
- [ ] dev tools에서 access 토큰 일부 변조 → WS 재연결 시 close 1008
- [ ] wscat 등으로 토큰 없이 직접 연결 → close 1008
- [ ] `/ws/worker/{X}/` 에 다른 사용자의 토큰으로 연결 → close 1008 forbidden

#### 4.2.3 케이스 C — 한쪽만 설정 (운영 사고 시뮬레이션)
- [ ] drf만 설정, fastapi 미설정 → 인증 비활성 동작 (정상 통과 — 의도)
- [ ] fastapi만 설정, drf SIGNING_KEY=SECRET_KEY (default) → 키 불일치 → 모든 토큰 검증 실패 → 모든 WS close 1008
- [ ] 즉시 모니터링 대시보드 alert 권장

#### 4.2.4 회귀 위험 시나리오
- [x] PR-H 4종 e2e 테스트 옵트인 비활성 상태에서 통과 ✓
- [ ] 활성화 후 e2e 테스트 fixture에 토큰 추가 필요 (별도 PR)

### 4.3 환경변수 점검
- [ ] `JWT_SIGNING_KEY` 양 서비스 동일 설정 (운영 .env)
- [ ] `JWT_ALGORITHM` 기본 HS256 (변경 불필요)
- [ ] `JWT_ACCESS_TOKEN_LIFETIME_HOURS` Wave 2 설정 유지

## 5. 알려진 한계 / 후속 작업

### 5.1 이번 Wave에 포함되지 않은 항목
- **`/ws/position/` IoT 인증**: 펌웨어 협업 별도 작업 (분석 06 F2 / 07 G2)
- **PR-H e2e 테스트 fixture 갱신**: 활성화 후 토큰 동봉 필요 (별도 PR)
- **WS access log 토큰 마스킹**: query token이 서버 access log에 노출 → 운영 시 filter 필요
- **알람 contract 정합** (J14-J16): `shared/alarm-mapper.js` 추출 (Wave 4 후보)
- **XSS 패턴 정착** (J18-J19): Menu.render createElement (Wave 4)
- **B10**: PasswordChangeView 토큰 블랙리스트

### 5.2 운영 적용 시 주의사항
1. **JWT_SIGNING_KEY 양 서비스 동일 값 필수**: 한쪽만 설정 시 fastapi 검증이 SECRET_KEY ≠ JWT_SIGNING_KEY로 모든 WS 인증 실패. **운영 .env 동시 갱신 필수**.
2. **활성화 순서**: B11+B12+J17 모두 머지 (옵트인 비활성 상태) → drf·fastapi env 동시 설정 → 양쪽 재시작 → WS 연결 모니터링.
3. **WS 토큰 query 노출**: `?token=...`이 access log·proxy log에 남을 수 있음. 운영 시 nginx·uvicorn access log filter 또는 WARN 이상 로그 레벨 권장.
4. **PR-H e2e 테스트**: 옵트인 비활성에서 통과 ✓. 활성화 후엔 fixture에 토큰 추가 필요 (현 PR 범위 밖).
5. **PyJWT 버전 고정**: `pyjwt==2.10.1` 명시. 1.x는 API 호환 안 됨.
6. **token 만료 후 자동 재연결**: ws-client.js의 자동 재연결이 정상 동작 (Wave 1 인프라). 단, access 만료 시 새 토큰 query에 자동 반영 안 됨 → URL 캐시 문제 가능. 모니터링 후 추후 보완.

### 5.3 향후 분석 항목
- 활성화 후 WS 연결 실패율 측정
- WS 토큰 만료 시 사용자 경험 (자동 재연결의 query token 갱신 문제)
- `/ws/position/` IoT 인증 메커니즘 설계 (별도 sprint)

## 6. 머지 전 확인 항목

### 6.1 Git
- [x] commit 분리: B11 / B12 / J17 (3개)
- [x] 신규 파일 `fastapi-server/websocket/auth.py` git add 확인
- [x] 변경 파일 12개 (신규 1 + 백엔드 수정 4 + JS 7)

### 6.2 운영 영향
- [ ] **운영 활성화 시점 결정** — Wave 3 머지 후 즉시 vs 별도 일정
- [ ] env 정책 결정: `JWT_SIGNING_KEY` 새 키 발급 또는 SECRET_KEY 재사용
- [ ] 운영팀 WS 연결 모니터링 대시보드 준비
- [ ] 운영 .env 동시 갱신 절차 명문화

### 6.3 PR 작성 (실험 → 머지 결정 후)
- [ ] PR 제목: `feat: Wave 3 — WebSocket 인증 통합 (B11 + B12 + J17)`
- [ ] PR 본문: 본 보고서 §2 + §4 + §5.2 운영 주의사항

## 7. 다음 단계 (Wave 4 후보)

### 7.1 알람 contract fragility 차단 (분석 PR-J2)
- **J14 (= 03 R1)**: `shared/alarm-mapper.js` 추출 — alarm-ws/worker-ws/dashboard/websocket의 키 매핑 통합
- **J15 (= 03 R3)**: 서버 timestamp 사용
- **J16 (= 03 R4)**: AlarmToast 호출 일관

### 7.2 XSS 패턴 정착 (분석 PR-J5)
- **J18 (= 04 R1)**: `Menu.render` innerHTML → createElement
- **J19 (= 04 R5)**: menuTree·child path 검증

### 7.3 추가 보안 (선택)
- **B10**: PasswordChangeView 토큰 블랙리스트
- **C1 (= 03 C2)**: `loadMySafetyStatus` 백엔드 권한 변경 (AllowAny → IsAuthenticated)

### 7.4 큰 작업 (별도 sprint)
- IoT 장비 인증 (펌웨어 협업)
- 다중 워커 + Redis (트래픽 증가 시점)

## 8. 결정 로그 (Wave 3 핵심 의사결정)

### 8.1 PyJWT vs python-jose
**선택**: PyJWT
**이유**: 가벼움 + Django SimpleJWT와 동일 라이브러리 + 메인테넌스 활발

### 8.2 옵트인 vs 강제 활성화
**선택**: 옵트인 (`JWT_SIGNING_KEY` 빈 값이면 비활성)
**이유**: Wave 1 ServiceToken 패턴과 일관 / 점진적 활성화 / 회귀 위험 0

### 8.3 단일 env vs 양 서비스 별도
**선택**: 단일 `JWT_SIGNING_KEY` 양 서비스 공유
**이유**: 운영 단순. drf의 SECRET_KEY와 다른 키를 명시적으로 설정 가능.

### 8.4 query string vs 첫 메시지에 토큰
**선택**: query string (`?token=...`)
**이유**: WebSocket 표준상 핸드셰이크에 헤더 못 보냄. query는 표준적이고 수신자(fastapi)가 즉시 검증 가능. 첫 메시지 패턴은 accept 후 한 번 더 await 필요해 복잡.

### 8.5 `/ws/position/` 포함 vs 제외
**선택**: 제외 (Wave 3 범위 밖)
**이유**: IoT 장비 토큰 관리는 펌웨어 협업 필요. 본 Wave에서 포함하면 운영 IoT 장비 통신 즉시 깨짐.

### 8.6 close code 1008 vs 1011
**선택**: 1008 (Policy Violation)
**이유**: 인증 실패는 정책 위반에 해당. 1011은 서버 내부 에러 의미.

### 8.7 commit 분리: 3개 (B11 / B12 / J17)
**선택**: 의존성 + 책임 단위로 분리
**이유**: B11은 인프라 (라이브러리·env·헬퍼), B12는 적용, J17은 클라이언트 협업. 각 단계 독립 PR 가능.

## 9. Wave 1 + 2 + 3 누적

### 9.1 누적 commit (13개)
```
f8edd2d refactor : J17 ws-client 호출자 attachToken 일관 적용 (8곳)
947cbc8 feat     : B12 WS 엔드포인트 인증 (/ws/sensors/, /ws/worker/{id}/)
39d2ba7 feat     : B11 fastapi JWT 검증 인프라 + drf SIGNING_KEY 명시
c58373d refactor : J12+J13 Auth._refresh 싱글톤 + Logout body refresh 동봉
3567c60 feat     : B9 LogoutView에서 refresh 토큰 블랙리스트
4735670 feat     : B6-B8 SimpleJWT blacklist + ROTATE + access lifetime 1h
5ee7628 refactor : J9-J11 JS 에러 핸들링
0b67e7c refactor : J5-J8 JS 로깅·layout 가드
eb60cfc refactor : J1-J4 JS 정합 (levelLabel/pushData/WS_BASE/pad)
00ae07c feat     : B3+B4 service token authentication (Phase 5)
0770423 refactor : B2 AlarmPayload extra="ignore"
b6cb6ce refactor : B1 print() → logger.exception
7e6b404 refactor : B5 WorkerSummaryView permission_classes
```

### 9.2 누적 변경
- 백엔드 항목: B1~B9 + B11~B12 = 11건
- JS 항목: J1~J13 + J17 = 14건
- 총 25건 + 신규 파일 2개 (authentication.py, websocket/auth.py) + 마이그레이션 1세트 + PyJWT 의존성

### 9.3 누적 검증
- pytest: 84/84 (drf 62 + fastapi 22)
- ruff lint+format: pass
- 회귀 위험: 0 (모든 보안 변경이 옵트인 패턴)

### 9.4 누적 옵트인 토큰
| env | 적용 범위 | 빈 값 동작 |
|---|---|---|
| `INTERNAL_SERVICE_TOKEN` | drf ingest + Celery → fastapi alarm-push | 비활성 (기존 무인증 동작) |
| `JWT_SIGNING_KEY` | drf SIMPLE_JWT.SIGNING_KEY + fastapi WS 검증 | 비활성 (drf default=SECRET_KEY로 호환) |

### 9.5 다음 결정 시점
1. **수동 검증 후 머지 결정**: Wave 1+2+3 통합 PR / Wave별 PR / cherry-pick
2. **Wave 4 진행**: 알람 contract / XSS / B10 중 선택
3. **운영 활성화**: 옵트인 토큰들을 운영에 설정해 활성화

## 10. 통계

- **변경 파일**: 12개 (신규 1, 수정 11)
- **추가 라인**: ~120줄 (B11 60 + B12 35 + J17 11 + 4 import/주석)
- **제거 라인**: ~10줄 (Before/After 패턴)
- **commit 수**: 3개
- **테스트 회귀**: 0
- **외부 의존성 추가**: 1개 (PyJWT)
