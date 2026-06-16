# API 가이드

> 평가자/신규 팀원이 핵심 API 5분 안에 파악하기 위한 문서.
> 전체 endpoint·요청/응답 스펙: [docs/specs/api_specification.md](specs/api_specification.md) · URL 전체 표: [docs/specs/url-structure.md](specs/url-structure.md)

---

## URL 분리 원칙

- **페이지 (HTML 반환)**: 루트 경로 (`/dashboard/`, `/admin-panel/...`)
- **API (JSON 반환)**: **반드시 `/api/` 프리픽스** (`/api/sensors/`, `/api/auth/login/`)
- **어드민 패널**: `/admin-panel/` 프리픽스 (Django Admin과 별도)
- URL 경로 규칙: `kebab-case`, 복수형 (`/api/gas-data/`)

## 두 서버 API 책임 분리

| 서버 | 포트 | API 책임 |
|---|---|---|
| `drf-server` | 8000 | 인증, DB CRUD, 알람·이벤트 조회, 어드민 |
| `fastapi-server` | 8001 | 센서 수신 (외부 IoT), WebSocket, 내부 알람 push |

## 핵심 endpoint 그룹

### 1. 인증 (drf:8000)

| Method | Path | 역할 |
|---|---|---|
| POST | `/api/auth/login/` | JWT 발급 |
| POST | `/api/auth/token/refresh/` | 토큰 갱신 |
| POST | `/api/auth/logout/` | 토큰 폐기 |
| GET | `/api/auth/me/`, `/api/auth/profile/` | 내 정보·프로필 |

JWT는 SimpleJWT 기반. WebSocket 검증에도 동일 키 사용.

### 2. 센서 수신 (fastapi:8001 → drf 내부 전달)

| Method | Path | 역할 |
|---|---|---|
| POST | `/api/sensors/gas` | 유해가스 9종 JSON 수신 |
| POST | `/api/power/{onoff,current,voltage,watt}` | 전력 16채널 4종 분리 수신 |
| POST | `/api/positioning/receive` | 작업자 위치 배열 수신 |

수신 직후 검증 → DRF 내부 ingest(`/api/monitoring/...`, `/api/positioning/receive/`) 호출 → DB 저장 → 임계치 초과 시 알람 생성.

### 3. 데이터 조회 (drf:8000)

| Method | Path | 역할 |
|---|---|---|
| GET | `/api/admin/gas-data/` | 가스 시계열 조회 (filter: sensor, period) · `export/`로 CSV |
| GET | `/api/admin/power-data/` | 전력 시계열 조회 · `export/`로 CSV |
| GET | `/alerts/api/alarms/` | 알람 이력 (`summary/`, `catch-up/`) |
| GET | `/alerts/api/events/` | 위험 이벤트 (`{id}/ack/`, `{id}/update_status/`) |
| GET | `/api/ml/models/active/` | 활성 AI 모델 메타 |

### 4. 내부 API (서비스 간)

| Method | Path | 호출자 → 수신자 | 역할 |
|---|---|---|---|
| POST | `/internal/alarms/push/` (fastapi) | drf Celery → fastapi | 알람을 `active_alarms` 큐에 push (**localhost 전용**) |
| POST | `/api/monitoring/gas/` 등 (drf) | fastapi → drf | 수신 검증 후 영속 저장 |
| POST | `/api/ml/anomaly-results/` (drf) | fastapi AI → drf | 이상탐지 결과 영속 |
| GET | `/api/internal/workers/` (drf) | 내부 서비스 | 작업자 목록 조회 |

`/internal/alarms/push/`는 localhost(127.0.0.1/::1)에서만 호출 가능 — 외부 호출 시 403.

### 5. WebSocket (fastapi:8001)

| Path | 역할 |
|---|---|
| `/ws/sensors/` | 센서 데이터 + 활성 알람 통합 broadcast |
| `/ws/worker/{user_id}/` | 작업자 개인 알림 채널 |
| `/ws/positions/` | 작업자 위치 broadcast (1초 주기) |
| `/ws/position/` | IoT 위치 장비 인바운드 수신 |

JWT 쿼리스트링으로 인증. 알람은 별도 WS가 아니라 `/ws/sensors/` payload의 `alarms` 필드로 전달되며, `alarm_flush_loop`이 1초 간격으로 `active_alarms` 큐를 비워 broadcast.

### 6. 메트릭 (Prometheus 스크레이프 대상)

| Path | 서버 |
|---|---|
| `/metrics` | drf:8000 |
| `/metrics` | fastapi:8001 |

Celery worker 메트릭은 `prometheus_multiproc/celery-{alarm,metric}/` 하위 파일을 합산해 노출.

## 인증 흐름

```
Browser → POST /api/auth/login/ (id/pw)
         ↓ access + refresh JWT
Browser → GET /alerts/api/alarms/  (Authorization: Bearer <access>)
         ↓
Browser → WS /ws/sensors/?token=<access>
         ↓ broadcast 수신 (payload.alarms 포함)
```

## 증빙자료 추천

| 증빙 | 위치 / 캡처 대상 | 추천 제목 |
|---|---|---|
| **API 명세 전체** | [docs/specs/api_specification.md](specs/api_specification.md) | `[부록] 전체 API 명세서` |
| **JWT 발급 요청·응답** | Postman/Insomnia로 `/api/auth/login/` 호출 → access·refresh 토큰 캡처 | `[그림 1] JWT 발급 요청/응답` |
| **센서 수신 요청·응답** | `POST /api/sensors/gas`에 가스 JSON 전송 → 200 + DB row 캡처 | `[그림 2] 가스 데이터 수신 API` |
| **알람 조회 응답** | `GET /alerts/api/alarms/` 결과 | `[그림 3] 활성 알람 조회 응답` |
| **WebSocket 연결 로그** | 브라우저 DevTools Network → WS(`/ws/sensors/`) → Messages 탭 캡처 | `[그림 4] WebSocket 실시간 메시지 수신` |
| **내부 API 토큰 인증 실패 케이스** | 잘못된 토큰 → 401 응답 | `[그림 5] 내부 API 인증 검증 동작` |

## 참고 문서

- 전체 API 명세: [docs/specs/api_specification.md](specs/api_specification.md)
- URL 구조 전체: [docs/specs/url-structure.md](specs/url-structure.md)
- JSON 필드 명세: [docs/specs/json_fields_specification.md](specs/json_fields_specification.md)
