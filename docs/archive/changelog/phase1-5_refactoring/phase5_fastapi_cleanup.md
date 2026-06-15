# 변경 기록서 — Phase5 fastapi-server 정리 + 양 서버 로거 통일

> 작성일: 2026-05-04
> 브랜치: feature/project_4_refactoring
> 작업 종류: refactor + feat
> 하위 호환성: **mostly non-breaking** — 외부 응답 형식 변경 1건(4xx/5xx → 표준 봉투). 기존 동작/스키마 유지. 단 `power_service.post_to_drf` → `post_power_to_drf` 이름 변경(외부 사용처 없음).

---

## 1. 변경 개요

- **목적(Why):** fastapi-server에 `print()` 15곳 잔존, `gas/power/positioning` service의 DRF httpx 호출 정책이 3가지로 갈라짐(raise / print 무시 / 무시), `broadcast.py`의 `build_broadcast_payload()` 1개 함수가 stale 판정·더미 생성·페이로드 조립·active_alarms 소비를 모두 담당, `app.py`에 전역 예외 핸들러·로깅 설정 부재, 더미 스크립트 URL/주기 하드코딩. drf-server에 통일한 로거 정책을 fastapi-server에도 적용해 양 서버 운영 가시성 통일.
- **결과(What):** (1) `core/logging.py` + `setup_logging()` 신설 — drf-server `LOGGING` dictConfig와 동일 포맷·정책. (2) `services/drf_client.py` 신설 — `gas/power/positioning` 3개 service의 중복 httpx 호출을 `post_to_drf(path, json, raise_on_error=...)` 1개 함수로 통합. (3) `app.py` 전역 예외 핸들러 3종(`HTTPException`, `RequestValidationError`, `Exception`)으로 응답 봉투 표준 적용. (4) `broadcast.py` 책임 분리 — `is_stale()`, `build_ai_dummy_fields()`, `build_broadcast_payload()` 3개 함수. (5) `print()` 15곳 → 컨벤션 포맷 `[CATEGORY] key=value` logger 호출. (6) `BROADCAST_INTERVAL_SEC`, `DUMMY_TARGET_HOST/PORT`, `DUMMY_RISK_PROBABILITY`, `DUMMY_SEND_INTERVAL_SEC`, `DATA_STALE_THRESHOLD_SEC` 등 Phase 1에서 정의한 settings 필드를 실제로 사용하기 시작.
- **영향 범위(Where):** fastapi-server 전반. drf-server 영향 없음 (Phase 4의 LOGGING dictConfig는 이미 적용됨).

## 2. Before / After 비교

| 구분 | Before | After |
|---|---|---|
| 로거 인프라 | 없음 — service들에 산발적 `logging.getLogger(__name__)` + `print()` 15곳 혼재 | `core/logging.py setup_logging(level)` + `app.py`에서 1회 호출. **모든 모듈 동일 포맷** `시간 LEVEL 모듈: [CATEGORY] key=value` |
| DRF 호출 | gas: raise / power: print 무시 / positioning: print 무시 (3가지 정책) | `services/drf_client.py post_to_drf(path, json, raise_on_error=bool)` **1개 진입점**. 호출자가 `raise_on_error`로 정책 선택 |
| 4xx/5xx 응답 | 처리되지 않은 예외는 raw FastAPI 기본 응답(`{detail: ...}` 또는 traceback) | `{error: {code, message, details?}}` **표준 봉투 자동 변환** (drf-server와 동일) |
| 미처리 예외 | 그대로 500 + traceback이 콘솔에만 (포맷 비통일) | `logger.exception([unhandled_exception] path={...} method={...} exc={...})` + 표준 500 봉투 |
| `broadcast.py` | `build_broadcast_payload()` 1개 함수가 stale 판정·더미 생성·페이로드 조립·active_alarms 소비 모두 담당 | 3개 함수로 분리: `is_stale()` / `build_ai_dummy_fields()` / `build_broadcast_payload()` — 단위 테스트 가능 |
| `BROADCAST_INTERVAL` | `ws_router.py` 모듈 상수 `5` | `settings.BROADCAST_INTERVAL_SEC` env로 제어 |
| `DATA_STALE_SEC` | `broadcast.py` 모듈 상수 `8` | `settings.DATA_STALE_THRESHOLD_SEC` env로 제어 |
| dummies URL | `http://localhost:8001` 3개 파일 하드코딩 | `f"http://{settings.DUMMY_TARGET_HOST}:{settings.DUMMY_TARGET_PORT}"` |
| `gas_dummy.py DANGER_EVENT_PROB` | `0.09` 코드 상수 | `settings.DUMMY_RISK_PROBABILITY` env (기본 0.1) |
| `print()` 잔존 | 15곳 (ws_router 7, power_service 3, position_service 3, position_router 1, gas_service 0) | **0건** (dummies는 CLI 출력이라 logging.basicConfig로 유지) |
| `except Exception: pass` 묵음 | ws_router 3곳 + position_router 1곳 | `logger.warning(...)` / `logger.exception(...)`로 가시화 |

### 코드 차이 예시

```python
# Before — gas_service.py: 자체 _forward_to_drf
async def _forward_to_drf(drf_payload: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(DRF_GAS_URL, json=drf_payload)
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="등록되지 않은 장치입니다.")
        if response.status_code >= 400:
            logger.error("DRF 저장 실패 | %s | %s", response.status_code, response.text)
            raise HTTPException(status_code=502, detail="데이터 저장에 실패했습니다.")
        return response.json()
    except httpx.ConnectError:
        logger.error("DRF 연결 실패 (%s)", DRF_GAS_URL)
        raise HTTPException(status_code=503, detail="DRF 서버에 연결할 수 없습니다.")
    except httpx.TimeoutException:
        logger.error("DRF 응답 시간 초과")
        raise HTTPException(status_code=504, detail="DRF 서버 응답 시간 초과.")

# After — drf_client.post_to_drf 사용 + 로컬 매핑
try:
    res = await post_to_drf(DRF_GAS_PATH, drf_payload, raise_on_error=True, log_category="gas_service")
except DrfClientError as exc:
    if exc.status is None:
        raise HTTPException(status_code=503, detail=exc.detail) from exc
    if exc.status == 404:
        raise HTTPException(status_code=404, detail="등록되지 않은 장치입니다.") from exc
    raise HTTPException(status_code=502, detail="데이터 저장에 실패했습니다.") from exc
```

```python
# Before — power_service.py: 자체 post_to_drf with print
async def post_to_drf(url: str, payload: dict) -> None:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.post(url, json=payload, headers=auth_headers())
            if res.status_code not in (200, 201):
                print(f"[DRF] 저장 실패 {res.status_code}: {res.text[:80]}")
    except httpx.TimeoutException:
        print("[DRF] 응답 타임아웃")
    except Exception as e:
        print(f"[DRF] 전송 오류: {e}")

# After — drf_client.post_to_drf 위임
async def post_power_to_drf(path: str, payload: dict) -> None:
    await post_to_drf(path, payload, raise_on_error=False, log_category="power_service")
```

## 3. 변경 파일 목록

### 신규 (3개)
| 파일 | 역할 |
|---|---|
| `fastapi-server/core/logging.py` | `build_logging_config(level)` + `setup_logging(level)` — drf-server LOGGING과 동일 정책 |
| `fastapi-server/services/__init__.py` | 새 패키지 초기화 |
| `fastapi-server/services/drf_client.py` | 공통 `post_to_drf(path, json, *, raise_on_error, log_category)` + `DrfClientError` |

### 수정 (10개)
| 파일 | 변경 요약 |
|---|---|
| `fastapi-server/app.py` | `setup_logging()` 호출, `lifespan` 시작/종료 logger.info, 전역 예외 핸들러 3종(`HTTPException`/`RequestValidationError`/`Exception`) 추가 |
| `fastapi-server/core/config.py` | `LOG_LEVEL: str = "INFO"` 필드 추가 |
| `fastapi-server/core/logging.py` | (신규로 위에 표시) |
| `fastapi-server/.env.example` | `LOG_LEVEL=INFO` 추가 |
| `fastapi-server/gas/services/gas_service.py` | `_forward_to_drf` 제거 → `services.drf_client.post_to_drf(raise_on_error=True)` + `DrfClientError` → `HTTPException` 매핑. logger 추가 |
| `fastapi-server/power/services/power_service.py` | `post_to_drf` → `post_power_to_drf` 1줄 래퍼로 단순화. `auth_headers()` 제거 (drf_client 내부로 이동). `DRF_POWER_*_URL` → `DRF_POWER_*_PATH`로 이름 변경. logger 추가 |
| `fastapi-server/positioning/services/position_service.py` | 자체 httpx 호출 → `post_to_drf(raise_on_error=False)`. print → logger.info |
| `fastapi-server/power/routers/power_router.py` | import 이름 변경 (`DRF_POWER_*_URL` → `_PATH`, `post_to_drf` → `post_power_to_drf`) |
| `fastapi-server/websocket/routers/ws_router.py` | print 7곳 → logger.info/warning. `_forward_to_drf` 자체 구현 → `services.drf_client.post_to_drf` 위임. `except Exception: pass` 묵음 → logger.warning/exception. `BROADCAST_INTERVAL` 모듈 상수 → `settings.BROADCAST_INTERVAL_SEC` |
| `fastapi-server/websocket/services/broadcast.py` | 책임 3분할: `is_stale()`, `build_ai_dummy_fields()`, `build_broadcast_payload()`. `DATA_STALE_SEC` 상수 → `settings.DATA_STALE_THRESHOLD_SEC` |
| `fastapi-server/positioning/routers/position_router.py` | print → logger.info |
| `fastapi-server/dummies/gas_dummy.py` | `FASTAPI_BASE_URL` settings, `DANGER_EVENT_PROB` → `settings.DUMMY_RISK_PROBABILITY`, `time.sleep(1)` → `settings.DUMMY_SEND_INTERVAL_SEC` |
| `fastapi-server/dummies/power_dummy.py` | `FASTAPI_BASE_URL` settings (주기는 도메인별 의도 보존) |
| `fastapi-server/dummies/position_dummy.py` | `FASTAPI_BASE_URL` settings (주기는 도메인별 의도 보존) |

### 삭제 (코드 블록)
- `gas_service.py`의 `_forward_to_drf()` (40+ 줄) — `drf_client`로 이동
- `power_service.py`의 `auth_headers()`, `post_to_drf()` — `drf_client`로 이동

## 4. API / 응답 / 인터페이스 변경

### Breaking — 4xx/5xx 응답 봉투 표준화

```diff
- HTTP 422
- {"detail": [{"type": "missing", "loc": ["body", "co"], ...}]}

+ HTTP 422
+ {"error": {
+    "code": "validation_failed",
+    "message": "요청 데이터 검증에 실패했습니다.",
+    "details": [{"type": "missing", "loc": ["body", "co"], ...}]
+ }}
```

drf-server와 동일 표준. 프론트가 fastapi 직접 호출하는 사례는 현재 없으므로(브라우저는 WebSocket만, IoT는 fastapi에 직접 송신) **사실상 영향 없음**. 단, dummies/외부 도구로 fastapi `/api/sensors/...` 직접 호출 시 응답 형식이 바뀜.

### Non-breaking — 200 응답 동일

라우터 응답 본문 형식, WebSocket 페이로드 형식 모두 변경 없음.

### Internal — 함수 이름 변경

- `power_service.post_to_drf` → `post_power_to_drf` (외부 사용처 없음, power_router만 import)
- `power_service.DRF_POWER_*_URL` → `*_PATH` (전체 URL 대신 path만 보관, settings.DRF_BASE_URL과 결합은 drf_client 내부)

## 5. 환경변수·설정 변경

| 변수 | 추가/사용 시작 | 기본값 | 설명 |
|---|---|---|---|
| `LOG_LEVEL` | 추가 | `INFO` | core.logging.setup_logging에 전달 |

Phase 1에서 정의만 하고 미사용이었던 다음 필드들이 본 Phase부터 **실제 사용 시작:**

| 필드 | 사용처 |
|---|---|
| `BROADCAST_INTERVAL_SEC` | `websocket/routers/ws_router.broadcast_loop` |
| `DATA_STALE_THRESHOLD_SEC` | `websocket/services/broadcast.is_stale` |
| `DRF_REQUEST_TIMEOUT_SEC` | `services/drf_client.post_to_drf` |
| `DUMMY_TARGET_HOST` / `DUMMY_TARGET_PORT` | `dummies/{gas,power,position}_dummy.py` |
| `DUMMY_SEND_INTERVAL_SEC` | `dummies/gas_dummy.py` (power/position는 도메인별 의도 보존) |
| `DUMMY_RISK_PROBABILITY` | `dummies/gas_dummy.py`, `websocket/services/broadcast.is_danger 더미` |

## 6. 마이그레이션 가이드

```bash
# 1. 풀 받기
git pull

# 2. fastapi .env에 LOG_LEVEL 추가 (선택, 기본 INFO)
cd fastapi-server
diff .env .env.example
# 신규 키만 .env에 복사

# 3. 의존성 변경 없음

# 4. 서버 재시작 — 로그 포맷이 즉시 통일됨
uvicorn app:app --reload --port 8001

# 5. 검증
curl http://localhost:8001/health/
curl http://localhost:8001/docs   # Swagger UI
curl -X POST http://localhost:8001/api/sensors/gas -H "Content-Type: application/json" -d '{}'
# 응답: {"error": {"code": "validation_failed", ...}}
```

## 7. 결정 근거 (ADR)

| 결정 | 채택안 | 검토했던 대안 | 근거 |
|---|---|---|---|
| DRF 통신 정책 분기 | **`raise_on_error` 옵션 1개로 호출자 선택** | 별도 함수(`post_strict`/`post_lenient`) | 정책이 2가지밖에 없어 함수 분리는 과한 추상화. opts 1개로 충분. |
| `post_to_drf` 반환값 | **`httpx.Response` 또는 `None`** | 정규화된 dict 반환 | 호출자(gas: status 코드 분기, power: 무시, positioning: saved 카운트 추출)마다 응답 처리가 달라 raw Response 반환이 가장 유연. |
| broadcast.py 분리 단위 | **3개 함수 (`is_stale`/`build_ai_dummy_fields`/`build_broadcast_payload`)** | 클래스 BroadcastBuilder | 함수 + 모듈 상태(`_prev_total_kw`)로 충분. 클래스는 instance 1개 싱글톤이라 의미 없음. Plan agent의 "클래스 X" 권고와 일치. |
| logger 호출 포맷 | **`f"[CATEGORY] key=value key=value"`** | structlog / 모듈 자체 컨텍스트 | dev_convention.md §6의 컨벤션 그대로. structlog는 외부 의존성 추가. |
| 전역 예외 핸들러 분리 | **`HTTPException` / `RequestValidationError` / `Exception` 3개로 분리** | `Exception` 단일 catch | FastAPI는 핸들러를 타입별로 매칭. 분리해야 422가 422로, 401이 401로 그대로 유지되며 봉투만 변환됨. 단일 `Exception`은 자동 매칭이 깨짐. |
| `power_service.post_to_drf` → `post_power_to_drf` 이름 변경 | **이름 변경** | `post_to_drf` 그대로 두고 내부에서 drf_client 호출 | 같은 이름으로 함수 시그니처가 다르면 혼동(전역 `post_to_drf` vs 도메인 `post_to_drf`). 도메인 prefix가 명시적. |
| dummies의 `time.sleep` | **gas만 env, power/position은 코드 상수 유지** | 모두 env화 | power_dummy의 `SEND_INTERVAL_SEC=3`은 다른 도메인과 다른 의도된 값. surgical changes — 동작 보존 우선. |
| `power_service.CHANNEL_TO_DEVICE` env화 | **보류** | env로 펴기 | 16채널 dict라 env가 부적합. 이미 코드 주석으로 "운영 환경에서는 DRF PowerDevice.channel_meta 조회로 교체 예정"이라고 명시됨 — Phase 5+ 작업. |
| 도메인 service에 logger 부착 | **모든 service에 logger = getLogger(__name__)** | 호출자만 로깅 | 어디서 로그가 나는지 모듈 단위로 추적해야 운영 편의. 컨벤션의 "모듈별 logger" 원칙 준수. |
| Pydantic 422 응답 | **표준 봉투 + details에 errors() 그대로** | 사람이 읽기 쉬운 형태로 변환 | DRF의 details와 일관. 클라이언트(개발 도구·테스트)가 필드별 오류를 그대로 처리 가능. |
| ws_router의 `except Exception: pass` 4곳 | **`logger.warning/exception`로 가시화** | 그대로 유지 | WebSocket의 disconnect는 이미 `WebSocketDisconnect`로 잡고 있음. 그 외 Exception은 진짜 오류 — 무음 처리는 디버깅을 막음. |

## 8. 검증 방법 / 결과

### 자동 검증 (실행 완료)

```bash
cd fastapi-server && source .venv/bin/activate

# (1) print 잔존 (dummies 외)
grep -rn "^\s*print(" --include="*.py" | grep -v "__pycache__\|dummies/"
# 결과: ✅ 0건

# (2) app import + route 수
python -c "from app import app; print('app loaded, routes:', len(app.routes))"
# 결과: ✅ app loaded, routes: 17

# (3) broadcast 책임 분리 함수 import
python -c "
from websocket.services.broadcast import build_broadcast_payload, is_stale, build_ai_dummy_fields
print('is_stale(None):', is_stale(None))
print('ai keys:', sorted(build_ai_dummy_fields(1500.0, [{'name':'x'}]).keys()))
"
# 결과:
# is_stale(None): True
# ai keys: ['ai_eta_min', 'ai_max_load_kw', 'ai_max_load_pct', 'ai_power_equipment']

# (4) drf_client + DrfClientError import
python -c "from services.drf_client import post_to_drf, DrfClientError; print('drf_client OK')"
# 결과: ✅ drf_client OK

# (5) logging dictConfig
python -c "
from core.logging import setup_logging
setup_logging('INFO')
import logging
logging.getLogger('test').info('[verify] action=ok')
"
# 결과: ✅ 2026-05-04 14:37:26 INFO    test: [verify] action=ok

# (6) uvicorn 부팅
uvicorn app:app --port 9876
# 결과: ✅ INFO    app: [app] action=startup log_level=INFO broadcast_interval=5.0s

# (7) /docs / /openapi.json
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:9876/docs        # 200
curl -s http://localhost:9876/openapi.json | jq '.paths | length'           # 9 paths

# (8) 표준 에러 봉투 (잘못된 payload)
curl -X POST http://localhost:9876/api/sensors/gas -H "Content-Type: application/json" -d '{}'
# 결과: HTTP 422
# {"error":{"code":"validation_failed","message":"요청 데이터 검증에 실패했습니다.","details":[...]}}
```

### 검증 미완 (통합/회귀 시점)

- [ ] **더미 3종 동시 송출 시 회귀** — gas/power/position dummy를 동시에 띄워도 정상 수신·broadcast
- [ ] **DRF 강제 종료 시 fastapi 살아남음** — `gas_service`는 raise라 센서에 5xx 응답, `power/positioning`은 fire-and-forget이라 broadcast 지속
- [ ] **stale 판정** — 9초 이상 데이터 없으면 페이로드의 `power_loading: true`, `gas_loading: true`
- [ ] **WebSocket 클라이언트** — 브라우저에서 `/ws/sensors/`, `/ws/positions/`, `/ws/worker/{id}/` 모두 정상 동작
- [ ] **drf-server와의 통신** — IoT 시뮬레이션으로 `/api/monitoring/{gas,power}/`에 정상 ingest
- [ ] **로그 레벨 .env 변경 동작** — `LOG_LEVEL=DEBUG`로 재시작 시 더 상세한 로그
- [ ] **`/internal/alarms/push/`** — Celery 태스크가 알람 push 후 `alarm_flush_loop`가 즉시 브로드캐스트

## 9. 하위 호환성 / 롤백

### Breaking 영역
- 422 등 4xx/5xx 응답이 `{detail: ...}` → `{error: {code, message, details?}}`. 외부 도구가 fastapi `/api/...`를 직접 호출하던 경우만 영향. 브라우저·WebSocket·내부 호출 모두 영향 없음.

### Non-breaking 영역
- WebSocket 페이로드 형식 동일.
- 200 응답 형식 동일.
- 더미 스크립트 송출 형식 동일.

### Internal 영역 (외부 영향 없음)
- `power_service.post_to_drf` → `post_power_to_drf` 이름 변경. import는 power_router 1곳뿐.
- `DRF_POWER_*_URL` → `_PATH` 이름 변경. 같은 1곳뿐.

### 롤백
- `git revert <SHA>`로 충분.
- 의존성·DB 변경 없음.

## 10. 후속 작업 / 참고

### 본 Phase에서 의도적으로 미룬 것
- **CHANNEL_TO_DEVICE 운영 데이터 연동** — 여전히 코드 상수. 운영 시 DRF `PowerDevice.channel_meta` 조회로 교체 예정 (별도 기능 작업).
- **서버-서버 ingest 보호** — drf-server 측 `monitoring/views/{gas_data,power_data}.py`의 무인증은 Phase 4에서 의도적 보존. fastapi 측에서 `DRF_SERVICE_TOKEN` 부착 가능하지만 양쪽 토큰 발급/검증 워크플로 추가 작업이라 본 Phase 범위 외 — 향후 작업.
- **drf-spectacular 같은 OpenAPI 보강** — fastapi는 `/openapi.json` 자동 생성이 이미 동작. 라우터마다 `response_model=` 명시는 안 함 (Phase 1 결정문서대로 "Pydantic 모델은 schemas/에 이미 있음"이라 라우터 호환만 검증). 점진적 보강 가능.
- **WebSocket 메시지 스키마** — broadcast.py의 페이로드 dict는 type-hinted 안 됨. 향후 TypedDict / Pydantic으로 강타입화 가능.
- **structlog / loguru 도입** — 표준 logging으로 충분. 운영 시 JSON 포맷이 필요하면 그때 검토.

### 관련 문서
- 응답 봉투 표준: `docs/api_response_convention.md`
- Phase 1/2/3/4 변경 기록: `docs/changelog/phase{1,2,3,4}_*.md`
- 마스터 검증 체크리스트: `docs/changelog/00_pr_verification_checklist.md`
- 변경기록 프롬프트: `skill/system_instruction_changelog.md`
