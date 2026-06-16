# 99. 보안 종합 (Cross-cutting Security Summary)

01~09 도메인 리뷰에서 식별한 보안 관련 항목을 OWASP Top 10 관점으로 재정렬.
이 문서는 **종합표**이며, 각 항목의 상세는 본문 도메인 파일을 참조.

## 0. 핵심 요약 (Top 10 보안 우선순위)

| # | 항목 | 도메인 | 영향 | 시급도 |
|---|---|---|---|---|
| 1 | `/ws/worker/{user_id}/` 인증 부재 — 임의 user_id로 타인 알람 가로채기 | 04, 07, 09 | 정보 누출·산업 안전 | 🔴 즉시 |
| 2 | `/ws/position/` IoT 무인증 — 가짜 위치 주입 가능 | 07, 09 | 위변조·안전 사고 | 🔴 즉시 |
| 3 | `/api/monitoring/{gas,power}/` 무인증 ingest (외부 노출 시) | 06 | 측정값 위변조·알람 폭주/누락 | 🔴 즉시 |
| 4 | `/internal/alarms/push/` localhost 검증만 — 호스트 내 위변조 | 04 | 가짜 알람 / 알람 무력화 | 🟠 1주 내 |
| 5 | JWT 블랙리스트 미설정 — 탈취 토큰 30일 노출 | 01 | 탈취 시 무력 대응 | 🟠 1주 내 |
| 6 | ACCESS_TOKEN_LIFETIME 24h — 일반 web app 기준 매우 김 | 01 | XSS·탈취 노출 시간 | 🟠 1주 내 |
| 7 | localStorage에 access·refresh 저장 — XSS에 취약 | 01, 08 | 토큰 탈취 | 🟠 다층 방어 |
| 8 | `auth.js._refresh` 동시성 미보호 — race로 강제 로그아웃 가능 | 01, 08 | 가용성·UX | 🟡 다음 sprint |
| 9 | check-connection SSRF — 임의 호스트 ping 가능 | 05 | 내부 망 정찰 | 🟡 다음 sprint |
| 10 | print() 사용 (positioning) — 운영 로그 누락 | 07 | 운영 가시성 | 🟢 즉시 (1줄) |

## 1. OWASP Top 10 매핑

### A01:2021 — Broken Access Control
- **WS 인증 부재** (위 #1, #2): /ws/worker/{user_id}/와 /ws/position/. 모든 WS는 JWT 검증 표준화 필요 (09 I4).
- **VR/안전 API AllowAny + 세션 키** (03 C2): 같은 브라우저로 여러 사용자가 로그인하면 진도/체크리스트가 섞임.
- **본인 계정 lock 차단 부재** (02 B8): super_admin이 본인을 잠그면 시스템 락아웃 가능.
- **facility_admin 데이터 범위 검증 부재** (03 C9): worker_id 파라미터로 자기 공장 외부 작업자 이력 조회 가능.
- **사용자 도메인 SystemLog 누락** (02 B3): 사용자 lock/unlock/deactivate가 감사 로그에 안 남음 → 감사 트레일 결손.
- **클라이언트 측 권한 모달 (UX only)** (02 4.2): _showAccessDenied가 보안 경계 아님 — 의도 명시 필요.

### A02:2021 — Cryptographic Failures
- **JWT 블랙리스트 미설정** (#5, 01 A1): rotate/blacklist 미사용 → 탈취 토큰 무력화 불가.
- **ACCESS_TOKEN_LIFETIME 24h** (#6, 01 A2): 노출 시간 길다.
- **localStorage 토큰 보관** (#7, 01·08): XSS 한 번이면 양쪽 토큰 탈취. CSP·DOMPurify 등 다층 방어 시급.
- **장비 인증 부재** (06 F2, 07 G2): IoT 장비별 secret/cert 없음 → 장비 위변조 가능.

### A03:2021 — Injection
- **SQL Injection: 현재 미감지** (사전 진단): raw SQL 미사용, ORM filter 사용 → 안전.
- **SSRF: check-connection** (#9, 05 E4): 사용자 입력 device 주소로 ping/HTTP 호출 가능 (내부 메타데이터 서비스 접근 등 우회).
- **XSS: innerHTML 패턴** (08 H3): 현재 백엔드 메뉴 데이터만 들어가지만, 향후 사용자 데이터 추가 시 위험. textContent 패턴 정착 필요.

### A04:2021 — Insecure Design
- **무인증 ingest를 reverse proxy 차단에 의존** (06 F1): 운영 환경에서 노출되면 즉시 위변조. Phase 5에서 토큰 도입 명시.
- **scenario_mode가 무인증 POST** (08·09): 시연 모드를 외부에서 변경 가능 → 운영 사용자에게 더미 데이터 표시.
- **device_id 위변조** (06): fastapi가 받은 device_id를 그대로 DRF에 전달 → 임의 ID로 데이터 주입.
- **알람 폭주 보호 부재** (04 D8): is_new_event=true 알람이 1초에 다수 도착 시 팝업 폭주 → DoS-like UX.
- **응답 봉투 일관성 결여** (04 D3): 클라이언트가 두 가지 패턴을 모두 처리해야 함 → 에러 처리 누락 가능.

### A05:2021 — Security Misconfiguration
- **CORS allow_origins 정합성**: app.py의 CORS는 localhost:8000만 — 개발 OK, 운영 시 도메인 추가 필요. allow_methods가 GET/POST만이라 PUT/DELETE 호출 시 silent fail.
- **CSP 헤더 부재** (08): XSS 다층 방어 누락.
- **세션과 JWT 혼용** (01 LogoutView, 03 VRProgressView): 정책 불명확. 세션을 쓰지 않는다면 SESSION_COOKIE_SAMESITE 등 보강.
- **debug logging 가능성** (각 도메인): except Exception 후 로깅 부재 — 보안 이슈 발생 시 흔적 누락.

### A06:2021 — Vulnerable and Outdated Components
- (이번 리뷰 범위에선 의존성 버전 점검 안 함) — `pip-audit`, `npm audit` 정기 실행 권장.

### A07:2021 — Identification and Authentication Failures
- **JWT 블랙리스트 미설정** (#5, 01 A1)
- **비밀번호 변경 후 기존 토큰 유효** (01 3.3)
- **응답 시간 차이로 username enumeration 가능성** (01 3.3): 존재하는 username과 없는 username의 응답 시간 차이 — `record_failed_login`이 한쪽만 실행됨.
- **X-Forwarded-For 신뢰 가정** (01 A6, 02 B6): 프록시 앞단 없으면 IP 위조 → 감사 로그 신뢰 불가.
- **password 정책 클라/서버 듀얼 메인테넌스** (01 A7): 한쪽 변경 누락 시 정책 우회 가능.

### A08:2021 — Software and Data Integrity Failures
- **AlarmPayload `extra="allow"`** (04 D5): 미정의 필드를 통과시킴 → 다운스트림 안전성 저하.
- **broadcast의 random `level`/`ai_*`** (09 I1): 운영 페이로드에 더미 값 섞임 → 사용자 신뢰 침해. **데이터 무결성 이슈**.
- **부분 실패 silent drop**: 구성원 일괄 작업 (02 B7), map-editor save (05 E5), positioning receive (07 G4) 모두 부분 실패가 silent. 트랜잭션 + 부분 실패 응답 표준화 필요.
- **active_alarms 5개 drop** (09 I5): silent drop은 알람 누락처럼 오인 가능.

### A09:2021 — Security Logging and Monitoring Failures
- **사용자 도메인 SystemLog 부재** (02 B3): 잠금/해제/비활성화 추적 불가.
- **광범위 except로 예외 묻힘** (01·03·04 등 다수): try-except Exception에서 logging 부재 → 보안 사고 흔적 누락.
- **print() 사용** (07 G3): 운영 로그 시스템 누락.
- **e2e 알람 흐름 통합 테스트 4종 (PR-H)** ⭐ — 모범. 보안 변경 시 회귀 검증 가능.
- **헬스체크 부재 (DRF 측)**: fastapi에는 `/health/` 있으나 DRF는 ?. 운영 모니터링 시 필요.

### A10:2021 — Server-Side Request Forgery (SSRF)
- **check-connection** (#9, 05 E4): 명시적 SSRF 가능 지점.
- **fastapi → DRF 호출**: 환경변수 기반 URL이라 사용자 입력 영향 없음 — 안전.

## 2. WS 인증 통합 마스터 플랜

여러 도메인의 WS 인증 이슈가 하나로 통합:

```
모든 WS endpoint → fastapi/websocket/auth.py 의존:

@app.websocket("/ws/sensors/")
async def sensor_stream(
    websocket: WebSocket,
    user: User = Depends(get_current_user_from_ws_token),
):
    ...

@app.websocket("/ws/worker/{user_id}/")
async def worker_stream(
    websocket: WebSocket,
    user_id: int,
    user: User = Depends(get_current_user_from_ws_token),
):
    if user.id != user_id:
        await websocket.close(code=1008, reason="forbidden")
        return
    ...

@app.websocket("/ws/position/")
async def position_stream(
    websocket: WebSocket,
    device: Device = Depends(get_current_device_from_ws_token),
):
    ...
```

**클라이언트 측 변경**:
- ws-client.js의 `attachToken: true` 일관 적용 (08 H5).
- 토큰은 query (`?token=...`)로 전송 — WebSocket 표준은 헤더 못 보냄.

**테스트**:
- PR-H의 4종 e2e 테스트가 토큰 발급/주입 fixture를 동반해야 함.

## 3. 인증/인가 매트릭스

엔드포인트 × 권한 (요약):

| 카테고리 | 권한 정책 | 비고 |
|---|---|---|
| `/api/auth/*` | 로그인은 AllowAny, 그 외 IsAuthenticated | A1·A2 시급 |
| `/api/admin/*` (사용자/조직) | IsSuperAdmin | A07/A09 (감사 로그 누락) |
| `/api/admin/*` (시설/장치/지오펜스/데이터) | IsSuperAdmin | E4 SSRF, E5 트랜잭션 |
| `/dashboard/*` 페이지 | (서버 무인증) — 클라이언트 redirect | C4 인증 통일 |
| `/dashboard/api/menu/`, `safety-history/`, `workers-list/`, `refresh/` | IsAuthenticated | C9 facility 범위 |
| `/dashboard/api/vr-progress/`, `safety-status/` | **AllowAny** | C2 시급 |
| `/alerts/api/*` | IsAuthenticated (worker-summary는 관리자 raise) | D4 권한 클래스화 |
| `/api/geofences/*`, `/api/positioning/receive/` | AllowAny (positioning) / IsAuthenticated (geofences) | F1 / G3 |
| `/api/monitoring/*` ingest | **무인증 (의도적)** | F1 시급 |
| `/api/monitoring/*` admin | IsSuperAdmin | F4 export 보호 |
| **fastapi** `/api/sensors/*`, `/api/power/*`, `/api/positioning/*` | (무인증) | F2 장비 인증 |
| **fastapi** `/internal/alarms/push/` | localhost only | D1 토큰 강화 |
| **fastapi** `/ws/sensors/`, `/ws/worker/{id}/`, `/ws/position/` | **인증 없음** | I4 통합 |

## 4. 민감정보 / 비밀 관리

- **DJANGO_SECRET_KEY, DATABASE_URL**: settings.py가 `environ.Env()` + `.env`. **OK**.
- **DRF_SERVICE_TOKEN, DRF_BASE_URL**: fastapi/core/config.py. fastapi → drf 호출에 Bearer로 사용. **양방향**으로 사용해야 (D1).
- **JWT 토큰 보관**: localStorage. XSS 위험 (#7).
- **로그에 password 노출 없는지**: LoginSerializer는 write_only=True 사용 — **OK**. except 블록에서 request.data 그대로 로깅 안 하는지 grep 필요.
- **`extra="allow"`** AlarmPayload (04 D5): 의도치 않은 정보 누출 가능.

## 5. 외부 통신 / 신뢰 경계

| 경계 | 인증/인가 | 검증 | 권장 |
|---|---|---|---|
| 브라우저 → drf | JWT (대부분) | DRF | A1·A2 |
| 브라우저 → fastapi WS | (없음) | (없음) | I4 통합 |
| IoT 장비 → fastapi HTTP/WS | (없음) | Pydantic 타입만 | F2/G2 장비 인증 |
| fastapi → drf | Bearer DRF_SERVICE_TOKEN | DRF auth | OK |
| Celery (drf) → fastapi `/internal/*` | localhost only | client.host 체크 | D1 토큰 추가 |

## 6. 동시성·가용성 보안

- **state.py 동시성** (09 I2): 다중 워커 시 100% 깨짐. 단일 워커 명시 또는 Redis.
- **slow client → broadcast 차단** (09 I3): DoS-like (서비스 장애).
- **_refresh race** (01 A3, 08): 토큰 회전 후 다중 401 시 일부 요청 강제 로그아웃.
- **부분 실패 silent** 다수 — 데이터 무결성 + 운영 가시성.

## 7. 개발 컨벤션 위반

- **print() 사용** (07 G3): CLAUDE.md 위반.
- **광범위 except Exception**: 01·03·04·07 등 다수.
- **함수 안 import** (03 C10): 순환 import 회피 임시.
- **inline_serializer 과다**: 01·03·04·05 등.

## 8. 권장 1주 내 작업 (보안 시급 묶음)

```
PR-S1 (1일) — 즉시 정합·로깅
  ✓ 07 G3: print → logger.exception
  ✓ 08 H1: levelLabel 정합 (또는 dead code 제거)
  ✓ 06 F1: ingest 토큰 보호 (Phase 5 명시 작업)
  ✓ 04 D5: AlarmPayload extra="ignore"
  ✓ 04 D1: /internal/alarms/push/ 토큰 검증

PR-S2 (3일) — JWT 보안
  ✓ 01 A2: ACCESS_TOKEN_LIFETIME 1h
  ✓ 01 A3: _refresh 동시성 가드
  ✓ 01 A1: token_blacklist + ROTATE/BLACKLIST_AFTER_ROTATION
  ✓ A1 도입 후 비밀번호 변경 시 refresh 블랙리스트

PR-S3 (5일) — WS 인증 통합 (09 I4)
  ✓ websocket/auth.py 신설
  ✓ /ws/sensors/, /ws/worker/{id}/, /ws/position/ 모두 적용
  ✓ ws-client.js attachToken 일관
  ✓ PR-H 4종 e2e 테스트에 토큰 fixture 추가

PR-S4 (3일) — 감사·정합
  ✓ 02 B3: 사용자 도메인 SystemLog 적용
  ✓ 02 B2: 트랜잭션 적용 (구성원 일괄 작업)
  ✓ 03 C2: VR/안전 API AllowAny → IsAuthenticated
```

이 후속 PR 4개로 보안 시급 항목 80% 해소 가능.

## 9. 장기 보안 로드맵 (다음 분기)

- **장비 인증 절차** (06 F2, 07 G2): 펌웨어 협업 필수. 큰 작업.
- **다중 워커 + Redis** (09 I2): 트래픽 증가 시점에 진행.
- **CSP·DOMPurify·SRI** (08): XSS 다층 방어.
- **의존성 정기 audit**: pip-audit, npm audit 자동화.
- **SSRF 정책 정착** (05 E4): IoT IP 화이트리스트 운영.
- **응답 봉투 표준 통일** (04 D3): drf 전반.
