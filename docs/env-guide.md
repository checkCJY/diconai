# 환경변수 가이드

> Compose 전체 서비스(12종: redis · postgres · drf · fastapi · celery-worker-alarm ·
> celery-worker-metric · celery-beat · redis_exporter · postgres_exporter · node_exporter ·
> prometheus · grafana)가 공유하는 환경변수 정리.
> 실제 예시 파일: [.env.docker.example](../.env.docker.example) — 신규 머신 진입 시 `cp .env.docker.example .env.docker` 후 값 채움.

---

## 원칙

- 실제 `.env.docker`는 **git에 올리지 않는다** (.gitignore 등록됨)
- 예시값만 [.env.docker.example](../.env.docker.example)에 작성
- 두 서버(drf, fastapi)와 celery 모두 **단일 .env.docker**에서 주입받음
- `REDIS_URL`, `FASTAPI_INTERNAL_URL`, `DRF_BASE_URL`은 docker-compose.yml의 `environment` 블록에서 서비스명 기반으로 직접 주입 — `.env.docker`에 작성 X

## settings 분기 (PR #93)

| 파일 | 적용 시점 |
|---|---|
| [drf-server/config/settings/base.py](../drf-server/config/settings/base.py) | 공통 |
| [drf-server/config/settings/dev.py](../drf-server/config/settings/dev.py) | `DJANGO_DEBUG=True` 시 |
| [drf-server/config/settings/prod.py](../drf-server/config/settings/prod.py) | `DJANGO_DEBUG=False` 시 |

`base.py`가 `os.environ`을 읽고, dev/prod에서 추가 분기.

## 환경변수 카테고리

### 1. Django Core

| 변수 | 예시값 | 의미 |
|---|---|---|
| `DJANGO_SECRET_KEY` | `secrets.token_urlsafe(50)` 결과 | Django 시크릿. **모든 환경 서로 다르게** |
| `DJANGO_DEBUG` | `False` (운영) / `True` (개발) | settings 분기 |
| `DJANGO_ALLOWED_HOSTS` | `drf,localhost,127.0.0.1` | 컨테이너 호스트명 포함 필수 |
| `DJANGO_LOG_LEVEL` | `INFO` | 로그 레벨 |

### 2. 서비스 간 인증 ⚠️

| 변수 | 의미 |
|---|---|
| `INTERNAL_SERVICE_TOKEN` | drf가 검증하는 값 (drf/fastapi 양쪽 동일) |
| `DRF_SERVICE_TOKEN` | fastapi → drf 호출 시 헤더에 부착 |
| `JWT_SIGNING_KEY` | WebSocket JWT 검증 (drf SimpleJWT ↔ fastapi WS 공유). 위 토큰과 별개 시크릿 |
| `JWT_ALGORITHM` | `HS256` |
| `DRF_REQUEST_TIMEOUT_SEC` | fastapi → drf 호출 timeout (초, 기본 `5.0`) |

⚠️ **`INTERNAL_SERVICE_TOKEN`과 `DRF_SERVICE_TOKEN`은 반드시 같은 값.** 다르면 fastapi 가스 더미가 모두 502 발생 (drf가 401 반환). 진단: [docs/troubleshooting.md §4](troubleshooting.md).

### 3. JWT 수명

| 변수 | 예시 | 의미 |
|---|---|---|
| `JWT_ACCESS_TOKEN_LIFETIME_HOURS` | `2` | access 토큰 수명 |
| `JWT_REFRESH_TOKEN_LIFETIME_DAYS` | `7` | refresh 토큰 수명 |

### 4. 프론트엔드 노출 URL

| 변수 | 예시 | 의미 |
|---|---|---|
| `FRONTEND_API_BASE_URL` | (빈 문자열) | same-origin 시 비움. 별도 도메인이면 명시 |
| `FRONTEND_WS_BASE_URL` | `ws://localhost:8001` | 브라우저가 host에서 접속하는 WS URL |

### 5. FastAPI 도메인 설정

| 변수 | 예시 | 의미 |
|---|---|---|
| `LOG_LEVEL` | `INFO` | FastAPI 로그 레벨 (drf의 `DJANGO_LOG_LEVEL`과 별개) |
| `BROADCAST_INTERVAL_SEC` | `5.0` | WS broadcast 주기 (참고: 알람은 즉시 push) |
| `DATA_STALE_THRESHOLD_SEC` | `8.0` | 센서 데이터 stale 판정 임계 |
| `POWER_THRESHOLD_CAUTION` | `2200` | 전력 경고 임계 (W) |
| `POWER_THRESHOLD_DANGER` | `2860` | 전력 위험 임계 (W) |

### 6. 더미 송출

| 변수 | 예시 | 의미 |
|---|---|---|
| `DUMMY_TARGET_HOST` | `fastapi` | 더미가 송출할 대상 |
| `DUMMY_TARGET_PORT` | `8001` | |
| `DUMMY_SEND_INTERVAL_SEC` | `1.0` | 송출 주기 |
| `DUMMY_RISK_PROBABILITY` | `0.1` | 위험값 발생 확률 (시연: 0, IF 학습: 0.005~0.1) |
| `DUMMY_SCENARIO_MODE` | `normal` | `normal`=시연 안전 / `mixed`=IF 학습용 |

**시연용 선택 override (미설정 시 코드 기본값):** `.env.docker.example`에 주석으로 제공.
- 가스 `co_leak`: `DEMO_CO_LEAK_RAMP_UP_TICKS` / `_HOLD_TICKS` / `_RAMP_DOWN_TICKS` (기본 5/30/5)
- 가스 AI: `DEMO_GAS_CP_PENALTY` (Change Point penalty, 기본 3.0 — 낮추면 부드러운 RAMP도 감지)
- 전력 `overload`: `DEMO_OVERLOAD_RAMP_UP_TICKS` / `_HOLD_TICKS` / `_RAMP_DOWN_TICKS` (기본 5/60/10)

### 7. PostgreSQL

| 변수 | 예시 | 의미 |
|---|---|---|
| `POSTGRES_DB` | `diconai` | DB 이름 |
| `POSTGRES_USER` | `diconai` | DB 사용자 |
| `POSTGRES_PASSWORD` | (팀장에게 문의) | 시연/개발 팀 공통값. 운영 진입 시 secrets 관리 |
| `POSTGRES_HOST` | `postgres` | 컨테이너 서비스명 |
| `POSTGRES_PORT` | `5432` | |

⚠️ 2026-05-22 PG 전환 후 `DATABASE_URL`은 사용하지 않음 — `POSTGRES_*` 분리 변수로 settings.py가 합성.

### 8. 기타

| 변수 | 예시 | 의미 |
|---|---|---|
| `ADMIN_BACKOFFICE_URL` | `/admin-panel/accounts-management/` | 어드민 진입 경로 |
| `NOTIFICATION_DELAY_THRESHOLD_MINUTES` | `5` | 알림 지연 임계 |
| `GRAFANA_PASSWORD` | `admin` | Grafana admin 비밀번호 (초기값) |

### 9. Discord 알람 연동

알람을 외부 Discord 채널로도 발송. `DISCORD_ALARM_ENABLED`가 `False`거나 webhook이 비면 미발송.

| 변수 | 예시 | 의미 |
|---|---|---|
| `DISCORD_ALARM_ENABLED` | `False` | Discord 발송 on/off |
| `DISCORD_WEBHOOK_ADMIN` | (빈 문자열) | 관리자 채널 webhook URL |
| `DISCORD_WEBHOOK_WORKER` | (빈 문자열) | 작업자 채널 webhook URL |

webhook URL 발급: Discord 채널 설정 → 연동 → 웹훅 → 새 웹훅 → URL 복사.
소비처: [drf-server/apps/notifications/services/discord_service.py](../drf-server/apps/notifications/services/discord_service.py).

## 작성 시 주의사항

- 실제 비밀번호, API Key, Secret은 GitHub에 올리지 않는다
- `.env.docker.example`에는 **어떤 변수가 필요한지** 알 수 있는 예시값만 작성
- 토큰 변경 시 Compose 전체 재기동 (`make down && make up`)

## 증빙자료 추천

| 증빙 | 위치 / 캡처 대상 | 추천 제목 |
|---|---|---|
| **`.env.docker.example` 전문** | [.env.docker.example](../.env.docker.example) 인용 | `[부록] .env.docker.example 예시` |
| **settings dev/prod 분기 코드** | [drf-server/config/settings/](../drf-server/config/settings/) 일부 | `[그림 1] settings 환경별 분기 구조` |
| **토큰 불일치 시 502 사례** | [docs/troubleshooting.md §4](troubleshooting.md) | `[그림 2] 서비스 간 토큰 불일치 진단` |

## 참고 문서

- 신규 환경 세팅: [docs/infra/docker_setup.md §8](infra/docker_setup.md)
- 배포·운영: [docs/deployment.md](deployment.md)
- 트러블슈팅: [docs/troubleshooting.md](troubleshooting.md)
