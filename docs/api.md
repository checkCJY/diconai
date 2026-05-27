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
| POST | `/api/auth/refresh/` | 토큰 갱신 |
| POST | `/api/auth/logout/` | 토큰 폐기 |

JWT는 SimpleJWT 기반, access 2h / refresh 7d. WebSocket 검증에도 동일 키 사용.

### 2. 센서 수신 (fastapi:8001 → drf 내부 전달)

| Method | Path | 역할 |
|---|---|---|
| POST | `/gas/` | 유해가스 JSON 수신 |
| POST | `/power/` | 전력 JSON 수신 |
| POST | `/position/` | 작업자 위치 수신 |

수신 직후 검증 → DRF 내부 API 호출 → DB 저장 → 임계치 초과 시 알람 생성.

### 3. 데이터 조회 (drf:8000)

| Method | Path | 역할 |
|---|---|---|
| GET | `/api/gas-data/` | 가스 시계열 조회 (filter: device, period) |
| GET | `/api/power-data/` | 전력 시계열 조회 |
| GET | `/api/alarms/` | 알람 이력 |
| GET | `/api/events/` | 위험 이벤트 |
| GET | `/api/ml-results/` | AI 분석 결과 |

### 4. 내부 API (서비스 간)

| Method | Path | 호출자 → 수신자 | 역할 |
|---|---|---|---|
| POST | `/internal/alarms/push/` | drf Celery → fastapi | 알람을 `active_alarms` 큐에 push |
| POST | drf 내부 sensor save | fastapi → drf | 수신 검증 후 영속 저장 |

내부 호출은 `INTERNAL_SERVICE_TOKEN` 헤더로 인증. drf와 fastapi가 같은 값 공유.

### 5. WebSocket (fastapi:8001)

| Path | 역할 |
|---|---|
| `/ws/sensors/` | 센서 데이터 실시간 broadcast |
| `/ws/alarms/` | 알람 실시간 push |

JWT 쿼리스트링으로 인증. `alarm_flush_loop`이 1초 간격으로 `active_alarms` 큐를 비워 broadcast.

### 6. 메트릭 (Prometheus 스크레이프 대상)

| Path | 서버 |
|---|---|
| `/metrics/` | drf:8000 |
| `/metrics` | fastapi:8001 |

Celery worker 메트릭은 `prometheus_multiproc/celery-{alarm,metric}/` 하위 파일을 합산해 노출.

## 인증 흐름

```
Browser → POST /api/auth/login/ (id/pw)
         ↓ access + refresh JWT
Browser → GET /api/alarms/  (Authorization: Bearer <access>)
         ↓
Browser → WS /ws/alarms/?token=<access>
         ↓ broadcast 수신
```

## 증빙자료 추천

| 증빙 | 위치 / 캡처 대상 | 추천 제목 |
|---|---|---|
| **API 명세 전체** | [docs/specs/api_specification.md](specs/api_specification.md) | `[부록] 전체 API 명세서` |
| **JWT 발급 요청·응답** | Postman/Insomnia로 `/api/auth/login/` 호출 → access·refresh 토큰 캡처 | `[그림 1] JWT 발급 요청/응답` |
| **센서 수신 요청·응답** | `POST /gas/`에 가스 JSON 전송 → 200 + DB row 캡처 | `[그림 2] 가스 데이터 수신 API` |
| **알람 조회 응답** | `GET /api/alarms/?status=ACTIVE` 결과 | `[그림 3] 활성 알람 조회 응답` |
| **WebSocket 연결 로그** | 브라우저 DevTools Network → WS → Messages 탭 캡처 | `[그림 4] WebSocket 실시간 메시지 수신` |
| **내부 API 토큰 인증 실패 케이스** | 잘못된 토큰 → 401 응답 | `[그림 5] 내부 API 인증 검증 동작` |

## 참고 문서

- 전체 API 명세: [docs/specs/api_specification.md](specs/api_specification.md)
- URL 구조 전체: [docs/specs/url-structure.md](specs/url-structure.md)
- JSON 필드 명세: [docs/specs/json_fields_specification.md](specs/json_fields_specification.md)
