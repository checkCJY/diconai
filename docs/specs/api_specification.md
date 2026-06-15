# API 명세서 — diconai 산재 예방 통합 관제 시스템

> 마지막 갱신: 2026-06-15
> 버전: 1.1.0
> 대상 독자: 신규 합류 개발자 / 외부 평가자 / IoT 센서 벤더

---

## 0. 빠른 진입 (TL;DR)

API 명세는 **3가지 형태**로 제공됩니다 — 용도에 맞게 골라 보세요.

| 채널 | URL / 경로 | 용도 |
|---|---|---|
| **DRF Swagger UI** | `http://localhost:8000/api/schema/swagger-ui/` | 대화형 — "Try it out"으로 실제 호출 가능 |
| **DRF ReDoc** | `http://localhost:8000/api/schema/redoc/` | 읽기 전용 — 깔끔한 명세 페이지 |
| **DRF OpenAPI YAML** | [docs/api/openapi-drf.yaml](../api/openapi-drf.yaml) | 정적 스냅샷 — Postman/Stoplight import 용 |
| **DRF HTML (Redoc)** | [docs/api/drf-api.html](../api/drf-api.html) | 오프라인 단일 파일 — 서버 없이 브라우저로 열람 |
| **FastAPI Swagger** | `http://localhost:8001/docs` | 실시간 처리 서버 (IoT 인입·WS) 대화형 |
| **FastAPI ReDoc** | `http://localhost:8001/redoc` | 실시간 처리 서버 읽기 전용 |
| **FastAPI OpenAPI JSON** | [docs/api/openapi-fastapi.json](../api/openapi-fastapi.json) | 정적 스냅샷 |
| **FastAPI HTML (Redoc)** | [docs/api/fastapi-api.html](../api/fastapi-api.html) | 오프라인 단일 파일 — 서버 없이 브라우저로 열람 |
| **이 문서** | `docs/specs/api_specification.md` | 아키텍처·인증·WebSocket·IoT 통합 안내 (자동 생성으로는 표현 불가한 부분) |

**평가자/리뷰어 시연 흐름**:
1. DRF Swagger UI → `/api/auth/login/` "Try it out" → JWT 받기
2. 우상단 Authorize 버튼 → `Bearer {access}` 입력
3. `/api/geofences/` GET 등 인증 필요한 엔드포인트 시연
4. FastAPI Swagger → `/api/sensors/gas` 페이로드 예시 확인
5. 본 문서 §5 WebSocket 페이로드 / §6 IoT 통합 가이드 확인

---

## 1. 시스템 아키텍처

### 1.1 두 서버 역할 분담

```
┌─────────────────┐     ┌──────────────────────┐     ┌──────────────────┐
│  IoT 센서/디바이스 │     │  FastAPI :8001       │     │  DRF :8000        │
│  (가스/전력/위치)  │ ──▶ │  Realtime API        │ ──▶ │  Persistence·Auth │
│                 │ HTTP │  - 데이터 인입·검증     │ HTTP │  - DB 저장          │
└─────────────────┘     │  - WebSocket 브로드캐스트│     │  - JWT 인증         │
                        │  - Celery 알람 브리지    │     │  - 어드민 패널        │
                        └──────────┬───────────┘     └────────┬─────────┘
                                   │ WebSocket                │
                                   ▼                          │ Celery
                            ┌──────────────┐                 │ tasks
                            │  Browser     │ ◀───────────────┘
                            │  Dashboard   │
                            └──────────────┘
```

### 1.2 데이터 흐름 (실시간)

1. **IoT → FastAPI**: 센서가 1~5초 주기로 측정값을 HTTP POST
2. **FastAPI 내부**:
   - Pydantic 검증 + 임계치 기준 status 재계산
   - 공유 상태(메모리)에 즉시 반영
   - DRF로 영속화 요청 (BackgroundTask 비동기)
3. **DRF**: DB 저장 + 임계치 초과 시 Celery 태스크가 알람 생성
4. **Celery → FastAPI 브리지**: 생성된 알람을 `POST /internal/alarms/push/`로 FastAPI에 전달
5. **FastAPI → 브라우저**: WebSocket 브로드캐스트(`/ws/sensors/`, 5초 주기) + 즉시 알람 푸시

### 1.3 URL 컨벤션

- HTML 페이지: 루트 경로 (`/dashboard/`, `/admin-panel/...`)
- JSON API: `/api/` 프리픽스 (`/api/auth/login/`, `/api/sensors/gas`)
- WebSocket: `/ws/` 프리픽스 (`/ws/sensors/`, `/ws/positions/`)
- 내부 서비스 통신: `/internal/` 프리픽스, **localhost에서만 호출 가능**

전체 URL 표는 [docs/specs/url-structure.md](url-structure.md) 참조.

---

## 2. 인증 (Authentication)

### 2.1 JWT (Django + simplejwt)

**적용 범위**: DRF의 모든 `/api/...` 엔드포인트 (단 §2.3 예외 제외)

**플로우**:
```
POST /api/auth/login/
  body: { "username": "admin", "password": "..." }
  ↓
  200 OK
  { "access": "eyJ...", "refresh": "eyJ...", "username": "admin", "role": "super_admin" }

이후 모든 요청에 헤더 추가:
  Authorization: Bearer eyJ...

토큰 만료 시:
POST /api/auth/token/refresh/
  body: { "refresh": "eyJ..." }
```

**역할 (role)**:
- `worker` — 일반 작업자 (대쉬보드 + 본인 안전확인만)
- `facility_admin` — 공장 관리자 (소속 공장 데이터 관리)
- `super_admin` — 슈퍼 관리자 (전 시스템)
- `viewer` — 읽기 전용 열람자

### 2.2 권한 클래스

| 권한 | 적용 대상 | 의미 |
|---|---|---|
| `IsAuthenticated` | 기본 (글로벌) | JWT 유효 사용자 |
| `IsSuperAdmin` | `/api/admin/...`, 어드민 패널 API | super_admin 또는 facility_admin |
| `AllowAny` | §2.3 참조 | 인증 우회 |

### 2.3 인증 우회 엔드포인트 (의도적)

| 엔드포인트 | 사유 | 보호 방안 |
|---|---|---|
| `POST /api/auth/login/` | 로그인 자체 | 비밀번호 검증 + LoginLog 기록 |
| `POST /api/auth/token/refresh/` | 토큰 갱신 | refresh 토큰 검증 |
| `POST /api/monitoring/gas/` | FastAPI → DRF ingest | **현재: 무인증**. Phase 5+에서 `DRF_SERVICE_TOKEN` 또는 IP 화이트리스트 |
| `POST /api/monitoring/power/event/` | FastAPI → DRF ingest | 동일 |
| `POST /api/monitoring/power/data/` | FastAPI → DRF ingest | 동일 |
| `GET /api/monitoring/power/thresholds/`, `.../threshold-meta/`, `.../channel-meta/`, `/api/monitoring/gas/thresholds/` | 공개 상수·메타 | 보호 불필요 |
| `POST /api/positioning/receive/` | FastAPI → DRF ingest | 동일 |
| `POST /api/ml/anomaly-results/`, `GET /api/ml/models/active/` | FastAPI AI ↔ DRF | 동일 |
| `POST /api/internal/integration-logs/`, `GET /api/internal/workers/` | 내부 서비스 통신 | 사설망 한정 |
| `/api/schema/...` | 문서 | 보호 불필요 |
| `POST /internal/alarms/push/` (FastAPI) | Celery → FastAPI 브리지 | **localhost(127.0.0.1/::1)에서만 호출 가능** — 외부 호출 시 403 |

### 2.4 FastAPI 측 인증 정책

FastAPI는 IoT 디바이스의 인입 엔드포인트가 대다수라 **현재 무인증** 상태입니다. 이 서버는 **사설망 또는 reverse proxy 뒤에 배치**해 외부 직접 노출을 막아야 합니다. 향후 디바이스 등록·서명 검증 추가 시 별도 명세 추가 예정.

---

## 3. 응답 봉투 표준

### 3.1 성공 응답 (2xx)
- 단건: 리소스 본문 그대로 (`{ "id": 1, "name": "..." }`)
- 목록: 페이지네이션 봉투 (`{ "results": [...], "total": N, "page": 1, "page_size": 20, "has_next": false }`)
- 액션: 액션별 명시 (`{ "ok": true }`, `{ "received": true, "id": 1 }` 등)

### 3.2 에러 응답 (4xx/5xx) — 표준 봉투

```json
{
  "error": {
    "code": "validation_failed",
    "message": "요청 데이터 검증에 실패했습니다.",
    "details": [...]
  }
}
```

**code 매핑**:

| HTTP | code |
|---|---|
| 400 | `validation_failed` |
| 401 | `authentication_required` |
| 403 | `permission_denied` |
| 404 | `not_found` |
| 405 | `method_not_allowed` |
| 409 | `conflict` |
| 422 | `validation_failed` |
| 429 | `throttled` |
| 500 | `internal_error` |
| 502/503/504 | `upstream_unavailable` |

DRF 측 글로벌 변환은 [`apps/core/exceptions.py`](../../drf-server/apps/core/exceptions.py), FastAPI 측은 [`app.py`](../../fastapi-server/app.py)의 `exception_handler` 3종에서 수행.

상세 표준은 [docs/conventions/api_response_convention.md](../conventions/api_response_convention.md) 참조.

---

## 4. 엔드포인트 카탈로그

### 4.1 DRF 서버 (:8000)

도메인별 진입점 — 자세한 요청/응답 스키마는 Swagger UI 또는 [openapi-drf.yaml](api/openapi-drf.yaml)에서 확인.

| 도메인 | URL 프리픽스 | 주요 동작 |
|---|---|---|
| Auth | `/api/auth/...` | 로그인/로그아웃/내정보/프로필/비밀번호변경/토큰갱신 |
| Geofence | `/api/geofences/` | 지오펜스 CRUD (ViewSet) + `by_facility` |
| Monitoring | `/api/monitoring/...` | **FastAPI ingest 전용** + 임계치·채널메타 조회 (공개) |
| Facilities | `/api/facilities/`, `/api/equipments/`, `/api/gas-sensors/`, `/api/power-devices/` | 공장·설비·장비·센서 CRUD + 점검(inspections) |
| Positioning | `/api/positioning/...` | 작업자 위치 인입 (FastAPI → DRF) |
| Alerts | `/alerts/api/...` | 알람·이벤트 ViewSet (`catch-up`, `ack`, `update_status`, `anomaly-alarm-records`) |
| Dashboard | `/dashboard/api/...` | 메뉴/안전확인/이력/새로고침/VR진도·콘텐츠 |
| Safety | `/api/safety/...`, `/api/admin/safety/...` | 안전점검 체크리스트 — 섹션·아이템·리비전·발행 |
| ML | `/api/ml/...` | 활성 모델 조회 + 이상탐지 결과 인입 (FastAPI AI → DRF) |
| Admin · 계정/조직 | `/api/admin/accounts/`, `/api/admin/departments/`, `/api/admin/organizations/...` | 계정·부서·조직 트리 |
| Admin · 데이터 | `/api/admin/gas-data/`, `/api/admin/power-data/` | 센서 데이터 조회·CSV export |
| Admin · 알람 | `/api/admin/alerts/policies/`, `/api/admin/alerts/events/` | 알람 정책 CRUD + 이벤트 이력 |
| Admin · 임계치 | `/api/admin/threshold-groups/`, `/api/admin/thresholds/` | 임계치 그룹·항목 관리 |
| Admin · 공통코드 | `/api/admin/code-groups/`, `/api/admin/codes/` | 코드 그룹·공통코드 |
| Admin · 공지/교육 | `/api/admin/notices/`, `/api/admin/training/vr-training/` | 공지사항(첨부) + VR 교육 콘텐츠 |
| Admin · 운영 | `/api/admin/system-logs/`, `/api/admin/integration-logs/`, `/api/admin/activity-logs/`, `/api/admin/map-edit-logs/`, `/api/admin/retention-policies/`, `/api/admin/risk-standards/` | 로그 조회·보존정책·위험기준 |
| Internal | `/api/internal/...` | 내부 서비스 통신 (통합로그 인입, 작업자 목록) |

총 **132개 path** (HTTP method 합산 시 더 많음). 전체 표는 [url-structure.md](url-structure.md).

### 4.2 FastAPI 서버 (:8001)

| 태그 | 엔드포인트 | 메서드 | 용도 |
|---|---|---|---|
| sensors | `/api/sensors/info` | POST | 가스 센서 부팅 시 식별 정보 1회 |
| sensors | `/api/sensors/gas` | POST | 가스 9종 1초 주기 인입 |
| power | `/api/power/onoff` | POST | 16채널 ON/OFF 스냅샷 |
| power | `/api/power/current` | POST | 16채널 전류(A) |
| power | `/api/power/voltage` | POST | 16채널 전압(V) |
| power | `/api/power/watt` | POST | 16채널 전력(W) |
| positioning | `/api/positioning/receive` | POST | 작업자 좌표 배열 |
| internal | `/internal/alarms/push/` | POST | Celery → WS 브리지 (**localhost 전용**) |
| internal | `/internal/scenario/mode` | GET / POST | 시연 시나리오 모드 |
| ai | `/ai/predict` | POST | IF 이상탐지 추론 |
| ai | `/ai/reload` | POST | 모델 캐시 무효화(재로드) |
| health | `/health/` | GET | 헬스체크 |

총 **12개 path / 13개 operation**. WebSocket은 §5 별도, `/metrics`(Prometheus)는 스키마 비노출.

---

## 5. WebSocket 엔드포인트

OpenAPI 3.0은 WebSocket을 직접 표현하지 않으므로 본 섹션에서 페이로드 구조를 명시합니다.

### 5.1 `/ws/sensors/` — 브라우저용 통합 실시간 스트림 (5초 주기 broadcast)

서버 → 클라이언트 페이로드 (TypeScript 인터페이스):

```ts
interface SensorBroadcast {
  device_id: string;
  timestamp: string;                 // ISO 8601
  level: "위험" | "정상";              // 가스 전체 위험 상태

  // 가스 — 9종 측정값 + 가스별 위험도
  co: number; h2s: number; co2: number; o2: number;
  no2: number; so2: number; o3: number; nh3: number; voc: number;
  co_risk: "normal" | "warning" | "danger";
  h2s_risk: "normal" | "warning" | "danger";
  // ... 9개 가스 모두 동일 패턴

  // 전력 — null = 데이터 stale 상태
  total_power_kw: number | null;
  power_change_pct: number | null;
  power_loading: boolean;             // FastAPI 데이터 수신 대기 중
  gas_loading: boolean;
  equipment: Array<{
    name: string;
    watt: number; voltage: number; current: number;
    onoff: boolean;
    sensor_status: "ok" | "comm_failure";
    risk_level: "normal" | "warning" | "danger";
  }>;

  // AI 예측 (현재는 더미)
  ai_power_equipment?: string;
  ai_eta_min?: number;
  ai_max_load_kw?: number;
  ai_max_load_pct?: number;

  // 작업자 위치 (worker_id → position)
  worker_positions: Record<string, {
    x: number; y: number;
    facility_id: number;
    worker_name: string;
    movement_status: string;
    updated_at: string;
  }>;

  // 활성 알람 (최대 5개)
  alarms: Array<{
    alarm_type: string;
    risk_level: string;
    source_label: string;
    summary: string;
    is_new_event: boolean;
    event_id?: number;
    gas_type?: string;
    measured_value?: number;
    threshold_value?: number;
  }>;
}
```

브로드캐스트 주기: `BROADCAST_INTERVAL_SEC` 환경변수(기본 5초). 신규 알람 발생 시 `alarm_flush_loop`이 즉시 push.

### 5.2 `/ws/positions/` — 작업자 위치 전용 (1초 주기)

```ts
interface PositionBroadcast {
  worker_positions: Array<{
    worker_id: number;
    x: number; y: number;
    facility_id: number;
    worker_name: string;
    movement_status: string;
    updated_at: string;             // ISO 8601
  }>;
}
```

### 5.3 `/ws/worker/{user_id}/` — 개인 알림 채널

서버 → 특정 작업자: 지오펜스 진입 알람 등을 즉시 push.
```ts
interface WorkerAlert {
  type: "worker_alert";
  alarm_type: "geofence_intrusion" | string;
  risk_level: string;
  summary: string;
  // ... AlarmPayload 필드 spread
}
```

### 5.4 `/ws/position/` — IoT 위치 장비 인바운드 (서버 ← 디바이스)

디바이스가 JSON 프레임을 송신:
```json
{ "worker_id": 1, "facility_id": 1, "x": 150.0, "y": 120.0, "measured_at": "2026-05-06T17:00:00Z" }
```
서버 응답: `{ "status": "ok" }` 또는 `{ "status": "error", "detail": "..." }`

---

## 6. IoT 디바이스 통합 가이드

### 6.1 가스 센서 부팅 시퀀스

```
[부팅]
  ↓
POST http://<fastapi-host>:8001/api/sensors/info
  Content-Type: application/json
  {
    "device_id": "sensor_01",
    "device_name": "AA:BB:CC:DD:EE:FF",
    "software_version": "1.0.1",
    "location": { "x": 150.0, "y": 120.0 }
  }
  ↓
  200 OK { "received": true, "device_id": "sensor_01" }
  ↓
[1초 주기로 측정값 송신]
POST /api/sensors/gas
  {
    "timestamp": "2026-05-06T17:00:00Z",
    "device_id": "sensor_01",
    "device_name": "AA:BB:CC:DD:EE:FF",
    "location": { "x": 150.0, "y": 120.0 },
    "o2": 20.9, "co": 5.2, "co2": 800,
    "h2s": 0.5, "lel": 0,
    "no2": 0.1, "so2": 0.05, "o3": 0.02, "nh3": 1.0, "voc": 0.5,
    "status": "normal"  // 서버에서 재계산해 덮어씀
  }
  ↓
  200 OK { "received": true, "device_id": "sensor_01", "status": "normal", "co_risk": "normal", ... }
```

### 6.2 전력 센서 — 4종 분리 송신

전력은 측정 종류마다 다른 엔드포인트로 송신 (프로토콜 규정):
- `POST /api/power/onoff` — 16채널 ON/OFF (0/255 → bool)
- `POST /api/power/current` — 전류(A)
- `POST /api/power/voltage` — 전압(V)
- `POST /api/power/watt` — 전력(W)

페이로드 공통:
```json
{
  "device_id": "power_01",
  "slave01": 1500, "slave02": -1, "slave11": 1200, ...
}
```
- `-1` = 통신 불능 채널 (DB에 저장되지만 통계 쿼리는 제외)
- 응답: 201 Created `{ "status": "ok", "updated": "watt" }`

### 6.3 작업자 위치 센서

```
POST /api/positioning/receive
[
  { "worker_id": 1, "facility_id": 1, "x": 150.0, "y": 120.0,
    "movement_status": "moving", "measured_at": "2026-05-06T17:00:00Z",
    "worker_name": "홍길동" },
  ...
]
```

### 6.4 권장 재시도 정책

- 4xx (검증 실패): 페이로드 수정 후 재시도. 동일 페이로드로 재시도 금지.
- 502/503/504 (DRF 일시 장애): exponential backoff (1s → 2s → 4s, 최대 30s)
- 422 (validation_failed): `details` 배열을 로그에 남기고 페이로드 수정

---

## 7. 페이지네이션 (목록 조회)

DRF 어드민 목록은 모두 표준 봉투 사용:

```
GET /api/admin/accounts/?page=1&page_size=20

200 OK
{
  "results": [...],
  "total": 145,
  "page": 1,
  "page_size": 20,
  "has_next": true
}
```

검색·필터는 엔드포인트별 query parameter (Swagger에서 확인 가능).

---

## 8. 변경 이력

| 일자 | 내용 | 관련 변경기록 |
|---|---|---|
| 2026-05-04 | drf-spectacular 도입 + 글로벌 예외 핸들러 + 응답 봉투 표준 | [phase4_drf_layer_exceptions_swagger.md](changelog/phase4_drf_layer_exceptions_swagger.md) |
| 2026-05-04 | FastAPI 정리 + 양 서버 로거 통일 | [phase5_fastapi_cleanup.md](changelog/phase5_fastapi_cleanup.md) |
| 2026-05-06 | 본 명세서 작성 + Tier 1 `@extend_schema` + FastAPI `response_model` 보강 | (별도 변경기록 작성 예정) |
| 2026-06-15 | OpenAPI 스냅샷 재생성 (DRF 78→132 path, FastAPI 10→12 path: `ai` 태그 추가). 카탈로그·인증우회 목록 갱신 | — |

자세한 변경 이력은 [docs/changelog/](changelog/) 참조.

---

## 9. 참고 문서

- [docs/specs/url-structure.md](url-structure.md) — 전체 URL 표 (페이지 + API + 어드민)
- [docs/conventions/api_response_convention.md](../conventions/api_response_convention.md) — 응답 봉투 / 페이지네이션 표준
- [docs/conventions/dev_convention.md](../conventions/dev_convention.md) — 개발 컨벤션
- [docs/specs/directory-structure.md](directory-structure.md) — 디렉토리 구조
- [docs/api/openapi-drf.yaml](../api/openapi-drf.yaml) — DRF OpenAPI 3.0 스냅샷
- [docs/api/openapi-fastapi.json](../api/openapi-fastapi.json) — FastAPI OpenAPI 3.0 스냅샷

OpenAPI YAML/JSON은 다음 명령으로 재생성 (런타임은 Docker Compose이므로 컨테이너에서 생성):
```bash
# DRF — 실행 중 컨테이너에서 spectacular 관리 명령
docker exec diconai-drf-1 python manage.py spectacular --format openapi --file /tmp/openapi-drf.yaml
docker cp diconai-drf-1:/tmp/openapi-drf.yaml docs/api/openapi-drf.yaml

# FastAPI — 실행 중 서버의 /openapi.json (2-space indent, 한글 보존)
curl -s localhost:8001/openapi.json | python3 -c \
  "import json,sys; d=json.load(sys.stdin); open('docs/api/openapi-fastapi.json','w').write(json.dumps(d,indent=2,ensure_ascii=False)+'\n')"
```

오프라인 HTML(Redoc 단일 파일)은 다음으로 재생성:
```bash
npx @redocly/cli build-docs docs/api/openapi-drf.yaml     -o docs/api/drf-api.html
npx @redocly/cli build-docs docs/api/openapi-fastapi.json -o docs/api/fastapi-api.html
```
