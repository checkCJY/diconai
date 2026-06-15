# diconai — 산재 예방 통합 관제 시스템

> IoT 가스·전력·위치 센서로 현장을 실시간 감지하고 자동 알람으로 **사고 발생 전 개입**을 목표하는 산업재해 예방 통합 관제 플랫폼.

> **프로젝트 성격** — 실 IoT 하드웨어 대신 **더미 송출로 센서를 시뮬레이션**하는 PoC(미배포)입니다. 단일 공장(`Facility(id=1)`) 기준이며, 이상탐지는 **룰 기반 임계가 1차 판정 · AI(IF·ARIMA·Change Point)는 보조·실험 단계**입니다. 데모/포트폴리오 목적의 통합 구현에 초점을 맞췄습니다.

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-6.0-092E20?logo=django&logoColor=white)
![DRF](https://img.shields.io/badge/DRF-3.17-A30000)
![FastAPI](https://img.shields.io/badge/FastAPI-0.135-009688?logo=fastapi&logoColor=white)
![Celery](https://img.shields.io/badge/Celery-5.4-37814A?logo=celery&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white)
![Prometheus](https://img.shields.io/badge/Prometheus-2.55-E6522C?logo=prometheus&logoColor=white)
![Grafana](https://img.shields.io/badge/Grafana-11.3-F46800?logo=grafana&logoColor=white)
---

## 목차

- [프로젝트 소개](#프로젝트-소개) · [기술 스택](#기술-스택) · [아키텍처](#아키텍처) · [주요 기능](#주요-기능) · [데모 화면](#데모-화면)
- [실행 방법](#실행-방법) · [Docker 통합 환경](#docker-통합-환경-대안) · [환경 변수](#환경-변수)
- [API 엔드포인트](#api-엔드포인트) · [DB 설계](#db-설계) · [프로젝트 구조](#프로젝트-구조)
- [테스트](#테스트) · [트러블슈팅](#트러블슈팅) · [향후 개선 포인트](#향후-개선-포인트) · [관련 문서](#관련-문서)

> 바로 띄워보려면 → [docs/QUICKSTART.md](docs/QUICKSTART.md) (Docker 한 경로, 클론→가동)

---

## 프로젝트 소개

### 왜 만들었는가

2026년 고용노동부 집계 기준, 제조업 현장에서 화재·폭발로 인한 산재 사망자는 전년 동기 10명에서 **20명으로 두 배** 늘었습니다. 지게차 충돌과 정비·점검 중 끼임 사고는 전년과 동일한 수준으로 반복되고 있고, 유해가스 누출 같은 산업 사고도 줄어들지 않고 있습니다. *(출처: [연합뉴스 2026.04.13](https://www.yna.co.kr/view/AKR20260413132900530))*

공통점은 하나입니다 — **감지가 늦었거나, 감지했어도 대응이 늦었습니다.**

**diconai project**는 IoT 가스·전력·위치 센서 데이터를 가정하여  현장을 실시간 모니터링하고 위험 상황을 자동 판정해 관리자·작업자에게 즉시 알람을 전달함으로써 **사고 발생 전 개입**을 목표로 하는 산업재해 예방 통합 플랫폼입니다. **유해가스 / 지오펜스(가상 위험구역) / 전력 이상** 세 가지 감지 축으로 현장 위험을 종합적으로 커버합니다.

### 기술 구조

동기 ORM 호출이 이벤트 루프를 막는 문제를 해결하기 위해 **DRF**(영속성·인증·비즈니스 로직)와 **FastAPI**(IoT 수신·실시간 스트림) 두 서버로 책임을 분리하고, **Celery + Redis** 비동기 파이프라인으로 알람 처리를 묶었습니다. 데이터 흐름은 단방향입니다 — `IoT → FastAPI → DRF (저장)`. 센서 통합 데이터는 주기적으로 브라우저에 브로드캐스트되고, **알람은 `Celery → Redis → FastAPI 내부 엔드포인트 → WebSocket → 브라우저` 순으로 이벤트 기반 즉시 전달**됩니다.

#### 데이터 주기 (코드 기준)

| 구간 | 현재 주기 | 코드 근거 · 설정값 |
|---|---|---|
| IoT 수신 (서버 인입) | 이벤트성 (패킷마다) | POST 수신 즉시 처리 |
| 더미 송출 — 가스·전력·위치 공통 | 1초 | `DUMMY_SEND_INTERVAL_SEC` — 3종 더미가 **단일 변수 공유** (코드 default 3.0 → `.env`에서 1.0으로 override) |
| 센서 통합 → 브라우저 broadcast | 5초 | `BROADCAST_INTERVAL_SEC=5.0` — 코드 주석 *"너무 짧으면 클라이언트 부하 증가"* (렌더링 부하). 다음 단계 목표 3초 |
| 작업자 위치 → 브라우저 stream | 1초 | WS 루프 `asyncio.sleep(1)` |

> 송출 주기는 가스·전력·위치가 현재 모두 동일(1초)하며 `DUMMY_SEND_INTERVAL_SEC` 하나로 조정됩니다. 안전과 밀접한 가스·위치는 짧게, 데이터가 크고(16채널×3종) 변화가 느린 전력은 길게 잡는 식의 **도메인별 차등은 이 값을 분리하면 적용 가능**합니다(현재는 미분리).

---

## 기술 스택

| Layer | Stack |
|---|---|
| **Backend (DRF)** | Python 3.12, Django 6.0.4, DRF 3.17, simplejwt 5.5 (JWT), drf-spectacular (OpenAPI), gunicorn (WSGI), WhiteNoise (정적 파일), django-environ |
| **Realtime (FastAPI)** | FastAPI 0.135, Uvicorn 0.44 (uvloop), Pydantic 2.13, websockets 16, PyJWT (WS 인증) |
| **Async / Queue** | Celery 5.4, Redis 7 (서버) / redis-py 5.2 (클라이언트) |
| **Database** | PostgreSQL 16 (Docker 운영, psycopg2) / SQLite (로컬 개발 폴백) |
| **ML / 이상탐지** | scikit-learn 1.8 (IsolationForest), statsmodels 0.14 (ARIMA), ruptures 1.1 (Change Point), numpy · pandas · joblib |
| **Monitoring** | Prometheus 2.55, Grafana 11.3, exporters (node/postgres/redis), prometheus-client (직접 노출) |
| **Tooling** | uv, pre-commit (ruff + ruff-format) |

상세 의존성: [drf-server/requirements.txt](drf-server/requirements.txt), [fastapi-server/requirements.txt](fastapi-server/requirements.txt)

---

## 아키텍처

![시스템 구조도](docs/img/시스템구조도.png)

> 센서는 FastAPI로만 들어오고 영속성은 DRF가 책임진다. 센서 통합 데이터는 5초 주기로 브라우저에 송신되고, 알람은 `Celery → Redis → FastAPI 내부 엔드포인트 → WebSocket` 순으로 이벤트 즉시 전달된다.

**핵심 컴포넌트**

| 컴포넌트 | 역할 |
|---|---|
| **FastAPI :8001** | IoT 센서 수신·검증, WebSocket 브로드캐스트, AI 이상탐지(IsolationForest·ARIMA·Change Point) 추론 |
| **DRF :8000** | 인증(JWT), DB 영속성, REST API, HTML 렌더링, ML 모델 학습 커맨드 |
| **Celery 워커 (alarm 큐)** | 알람 비동기 처리·이벤트 변환·실시간 push |
| **Celery 워커 (metric 큐)** | 보관 정책·큐 길이·DB 상태 등 주기 메트릭 수집 |
| **Redis** | Celery 브로커 + 캐시 |
| **PostgreSQL 16** | 영속 저장소 (로컬 개발 시 SQLite 폴백) |
| **Prometheus** | 메트릭 수집·시계열 저장 (drf·fastapi·exporter 6개 타깃 scrape) |
| **Grafana** | 메트릭 시각화 대시보드 (`:3000`) |
| **Exporters** | node / postgres / redis exporter — 호스트·DB·캐시 메트릭 노출 |

---

## 주요 기능

- **다종 가스 모니터링** — CO·H2S·CO2·O2·NO2·SO2·O3·NH3·VOC 9종을 1초 주기로 수신, 임계치별 위험도(NORMAL/WARNING/DANGER) 자동 산정
- **전력 이상 감지** — 16채널 × 전류·전압·전력 측정, **정격 대비 % 임계**로 위험도(WARNING/DANGER) 판정 + AI 5축 시나리오 분류(과부하·저전압·결상·열화·모터정지)
- **AI 이상탐지** — IsolationForest(이상치) + ARIMA(임계 돌파 예측) + Change Point(급변 감지)를 가스·전력 양 도메인에 적용, 결과는 `MLAnomalyResult`로 영속
- **위험구역(Geofence)** — Ray casting 기반 다각형 내포 판정, 작업자 진입 시 즉시 푸시
- **작업자 실시간 위치** — 1초 주기 WebSocket 스트림, `measured_at` vs `received_at` 분리로 통신 지연 측정
- **알람 영속화 + 즉시 전파** — Celery로 DB 저장과 브로드캐스트 분리, `AlarmRecord`는 *불변* 모델로 감사 추적 보장
- **Discord 알림 미러링** — 알람을 Discord 채널로 미러: 관리자 채널 broadcast / 작업자 채널은 DANGER `@here` 대피·지오펜스 개인 멘션 (`DISCORD_ALARM_ENABLED` 토글)
- **JWT 인증 + 4단계 권한** — SUPER_ADMIN / FACILITY_ADMIN / WORKER / VIEWER
- **실시간 관측** — Prometheus 메트릭 수집 + Grafana 대시보드 (HTTP·Celery 큐·DB 상태)
- **자동 OpenAPI 문서** — drf-spectacular Swagger UI + FastAPI `/docs`

---

## 데모 화면

> 직접 캡처한 이미지를 `docs/img/`에 저장한 뒤 아래 주석(`<!-- -->`)을 해제하면 렌더링됩니다.

| 슬롯 | 캡처할 화면 |
|---|---|
| **메인 대시보드** | 공장 도면 위 가스·전력 센서 상태 + 작업자 실시간 위치 마커가 보이는 전체 관제 화면 |
| **위험 알람 팝업** | 가스/전력 DANGER 발생 시 뜨는 알람 모달 (위험도·위치·발생시각) |
| **지오펜스 진입** | 작업자 마커가 위험구역(다각형) 안으로 들어가 알람이 뜬 순간 |
| **Grafana 대시보드** | HTTP·Celery 큐·DB 메트릭 패널 (관측 스택 증빙) |

<!-- 캡처 후 아래 주석을 해제하세요
![메인 대시보드](docs/img/demo-dashboard.png)
![위험 알람 팝업](docs/img/demo-alarm.png)
![지오펜스 진입](docs/img/demo-geofence.png)
![Grafana 대시보드](docs/img/demo-grafana.png)
-->

---

## 실행 방법

> **처음이라면 → [docs/QUICKSTART.md](docs/QUICKSTART.md)** — 클론부터 가동까지 Docker 한 경로로 정리한 빠른 시작 가이드.
> 아래는 로컬(uv) 개발 방식이며, Docker 통합 환경은 하단 `Docker 통합 환경 (대안)` 절을 참고.

### Prerequisites

- Python 3.12
- [uv](https://docs.astral.sh/uv/) (패키지 매니저)
- Redis 6+ (Celery 브로커)
- PostgreSQL 16 *(선택 — `POSTGRES_HOST` 미설정 시 SQLite로 폴백)*

### 1. Clone & 루트 설치

```bash
git clone https://github.com/checkCJY/diconai.git
cd diconai
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt
pre-commit install
```

### 2. DRF 서버 (:8000)

```bash
cd drf-server
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt
cp .env.example .env.dev      # manage.py 기본값(config.settings.dev)이 .env.dev를 읽음 — 아래 섹션 참고
python manage.py migrate
python manage.py runserver
```

### 3. FastAPI 서버 (:8001)

```bash
cd fastapi-server
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt
cp .env.example .env          # 환경변수 작성 (아래 섹션 참고)
uvicorn app:app --reload --port 8001
```

### 4. Celery 워커 *(알람 비동기 처리용 — 필수)*

알람 영속화·이벤트 변환·실시간 push가 모두 Celery 태스크로 처리되므로 워커가 떠 있지 않으면 알람 흐름이 동작하지 않습니다. Celery는 Redis를 브로커로 사용하므로 **Redis가 설치되어 있고 서버가 실행 중**이어야 합니다.

```bash
# 1) Redis 설치 (한 번만)
sudo apt install redis-server   # Ubuntu / WSL
# brew install redis            # macOS

# 2) Redis 서버 실행 (별도 터미널)
redis-server                    # 또는 sudo service redis-server start

# 3) Celery 워커 실행 (알람 태스크는 alarm 큐, 주기 메트릭은 metric 큐로 라우팅됨)
cd drf-server
celery -A config worker -Q alarm,metric -l info
```

> 태스크가 `alarm`/`metric` 큐로 라우팅되므로(`config/settings/base.py`의 `CELERY_TASK_ROUTES`), 큐를 지정하지 않은 워커는 알람을 소비하지 못합니다. Docker 환경은 두 큐를 별도 워커(`celery-worker-alarm`/`celery-worker-metric`)로 분리합니다. 주기 메트릭·보관 정책 스케줄을 쓰려면 `celery -A config beat -l info`도 함께 띄우세요.

### 5. 마스터 데이터 시드 *(더미·센서 연동 시 필수)*

DRF는 수신된 `device_id`로 `GasSensor` / `PowerDevice` 마스터를 조회하므로, **마스터가 등록되지 않은 device_id의 데이터는 404로 거부됩니다.** 위치 더미도 `worker_id=1~4`에 해당하는 `CustomUser`가 사전에 존재해야 합니다.

아래 명령이 더미 송출에 필요한 마스터 데이터를 한 번에 생성합니다 (재실행 안전).

> **`createsuperuser`는 반드시 시드 이후에 실행하세요.** 시드가 worker `id=1~4`를 먼저 점유해야 슈퍼유저가 `id=5` 이상으로 부여되어 위치 더미와 충돌하지 않습니다.

```bash
cd drf-server
python manage.py seed_dummy_data        # Facility, Worker × 4, GasSensor, PowerDevice 생성
python manage.py createsuperuser        # 슈퍼유저 (id=5+ 자동 부여)
```

생성 항목:

| 항목 | 값 |
|---|---|
| `Facility(id=1)` | 도면 1290×590 |
| `CustomUser × 4` | `id=1~4` (`worker_a~d`, user_type=WORKER, 비밀번호 `worker1234!`) |
| `GasSensor` | `device_id="63200c3afd12"` |
| `PowerDevice` | `device_id="63200c3afd12"`, 16채널 |

> 부서/직급 13종은 마이그레이션이 자동으로 채워줍니다 ([accounts/migrations/0005_seed_department_position.py](drf-server/apps/accounts/migrations/0005_seed_department_position.py)). 시드 명령 본체는 [apps/core/management/commands/seed_dummy_data.py](drf-server/apps/core/management/commands/seed_dummy_data.py).

### 6. 더미 데이터 송출 *(개발·시연용 — 선택)*

```bash
cd fastapi-server   # FastAPI 가상환경 활성화 상태에서
python -m dummies.gas_dummy        # 가스 9종 (DEVICE_ID="63200c3afd12")
python -m dummies.power_dummy      # 전력 16채널 (DEVICE_ID="63200c3afd12")
python -m dummies.position_dummy   # 작업자 4명 위치 (worker_id=1~4)
```

각각 별도 터미널에서 실행. 송출 주기·위험 발생 확률 등은 `fastapi-server/.env`의 `DUMMY_*` 변수로 조절합니다.

### 접속

| 페이지 | URL |
|---|---|
| 대시보드 | http://localhost:8000/dashboard/ |
| 어드민 | http://localhost:8000/admin-panel/ |
| DRF Swagger UI | http://localhost:8000/api/schema/swagger-ui/ |
| FastAPI Docs | http://localhost:8001/docs |

> 전체 명령어 모음은 [docs/conventions/COMMANDS.md](docs/conventions/COMMANDS.md) 참고.

---

## Docker 통합 환경 (대안)

위 1~6번을 한 번에 띄우는 Docker Compose 환경입니다. 12개 서비스(`postgres` + `redis` + `drf` + `fastapi` + `celery-worker-alarm` + `celery-worker-metric` + `celery-beat` + `prometheus` + `grafana` + `redis_exporter` + `postgres_exporter` + `node_exporter`)가 함께 기동됩니다. **DB는 PostgreSQL 16**(`postgres:16-alpine`)을 사용하며 데이터는 `postgres_data` 명명 볼륨에 영속됩니다. (로컬 수동 실행 시에는 `POSTGRES_HOST` 미설정으로 SQLite로 폴백합니다.)

### 사전 요구사항

- Docker Engine 24+ / Docker Compose v2
- WSL2: Docker Desktop의 **Settings → Resources → WSL Integration**에서 현재 배포 토글 ON
- 호스트에 빈 디렉토리 미리 생성 (bind mount 자동 생성 시 root 소유 문제 방지):
  ```bash
  mkdir -p drf-server/media
  ```

### 첫 실행

```bash
# 1) 환경변수 작성
cp .env.docker.example .env.docker
python -c "import secrets; print(secrets.token_urlsafe(50))"   # DJANGO_SECRET_KEY 용
python -c "import secrets; print(secrets.token_urlsafe(32))"   # INTERNAL_SERVICE_TOKEN 용
python -c "import secrets; print(secrets.token_urlsafe(32))"   # JWT_SIGNING_KEY 용
# .env.docker 에 위 값들 채워넣기 (DRF_SERVICE_TOKEN = INTERNAL_SERVICE_TOKEN 동일 값 권장)

# 2) 빌드 + 기동
docker compose build
docker compose up -d

# 3) 상태 확인
docker compose ps
docker compose logs -f drf fastapi
```

기동되면 마이그레이션 + collectstatic이 `drf` 컨테이너 entrypoint에서 자동 실행됩니다 (`celery-worker-alarm`/`celery-worker-metric`/`celery-beat`는 `RUN_MIGRATIONS=0`로 중복 방지).

### 접속

| 서비스 | URL | 비고 |
|---|---|---|
| 대시보드 (DRF) | http://localhost:8000/dashboard/ | |
| FastAPI Docs | http://localhost:8001/docs | |
| WebSocket | `ws://localhost:8001/ws/worker/{user_id}/` | 브라우저 직접 연결 |
| DRF `/metrics` | http://localhost:8000/metrics | prometheus-client (커스텀 미들웨어 + 멀티프로세스 합산) |
| FastAPI `/metrics` | http://localhost:8001/metrics | prometheus-client (직접 노출, 외부 instrumentator 미사용) |
| Prometheus | http://localhost:9090 | targets 모두 UP 확인 |
| Grafana | http://localhost:3000 | id `admin` / pw `.env.docker`의 `GRAFANA_PASSWORD` |
| PostgreSQL | `127.0.0.1:5432` | DBeaver 등 GUI 클라이언트 접속용 (호스트 바인딩, 외부 노출 차단) |
| node_exporter | http://localhost:9100/metrics | 호스트 자원 메트릭 |
| postgres_exporter | http://localhost:9187/metrics | PostgreSQL 메트릭 |
| redis_exporter | http://localhost:9121/metrics | Redis 메트릭 |

> 위 12개 서비스는 `docker compose ps`에서 모두 `Up (healthy)`로 확인됩니다. Redis(6379)·Celery 워커(8000)는 호스트로 포트를 노출하지 않고 컨테이너 네트워크 내부에서만 통신합니다.

### 자주 쓰는 명령

```bash
# Django 명령 (시드, createsuperuser 등)
docker compose exec drf python manage.py seed_dummy_data
docker compose exec drf python manage.py createsuperuser
docker compose exec drf python manage.py showmigrations

# 테스트
docker compose exec drf pytest -q
docker compose exec fastapi pytest -q

# 한 서비스만 재기동 (코드 수정 후)
docker compose build drf && docker compose up -d drf

# 로그 모니터링 (stdout — 휘발성)
docker compose logs -f celery-worker-alarm
docker compose logs -f --tail=50 fastapi

# 영속 파일 로그 (RotatingFileHandler) — 시연·사고 추적용
make logs-err-all                # 양 서버 ERROR 실시간 (1순위)
make logs-stat                   # 파일 크기·회전 백업 확인
# 상세: docs/conventions/COMMANDS.md "파일 로그 보기" 절

# 정리
docker compose down              # 컨테이너만 제거 (볼륨 유지)
docker compose down -v           # 볼륨까지 제거 (Redis/Prometheus/Grafana 데이터 삭제)
```

### 검증 체크리스트

```bash
curl -fsS http://localhost:8000/health/ && echo OK
curl -fsS http://localhost:8001/health/ && echo OK
curl -s http://localhost:8000/metrics | head -5
curl -s http://localhost:8001/metrics | head -5
# Prometheus targets — 모두 state="up"
curl -s http://localhost:9090/api/v1/targets | python -m json.tool | grep -E '"job"|"health"'
```

> DB는 PostgreSQL 16 컨테이너로 운영되며 다중 컨테이너(drf·celery 워커들)가 `postgres` 서비스를 공유합니다. PG 연결은 `CONN_MAX_AGE=60`으로 재사용됩니다.

> 도커 도입 배경 · 서비스 구조 · 서버별 일상 워크플로우 · 트러블슈팅 · 남은 과제는 [docs/infra/docker_setup.md](docs/infra/docker_setup.md) 에 정리되어 있습니다. 명령어 모음은 [docs/conventions/COMMANDS.md](docs/conventions/COMMANDS.md).

---

## 환경 변수

> **설정 구조 요약**
> - 로컬 개발: `drf-server/.env.dev` 작성 → `manage.py`가 `config.settings.dev` 자동 로드
> - Docker 운영: `.env.docker` 작성 → `docker-compose.yml`이 컨테이너에 주입, `config.settings.prod` 고정
> - `DEBUG` 값은 환경변수로 조정하지 않음 — `dev.py`=`True`, `prod.py`=`False` 하드코딩
> - 실제 비밀값이 담긴 `.env*` 파일은 `.gitignore`로 git 추적 차단. git에는 `.env.example`(placeholder)만 포함.

> **처음이라면 이 5개만 설정하면 동작합니다** — `DJANGO_SECRET_KEY` · `POSTGRES_PASSWORD` · `INTERNAL_SERVICE_TOKEN`(= `DRF_SERVICE_TOKEN` 동일 값) · `JWT_SIGNING_KEY` · `DJANGO_ALLOWED_HOSTS`. 나머지는 기본값으로 동작합니다.
> Docker 전체 변수 상세는 [docs/env-guide.md](docs/env-guide.md), 로컬·FastAPI 변수는 각 `.env.example` 주석을 참고하세요. 아래는 자주 쓰는 변수만 추린 표입니다.

---

### 로컬 개발 — `drf-server/.env.dev`

```bash
cp drf-server/.env.example drf-server/.env.dev
```

| 변수 | 예시 | 비고 |
|---|---|---|
| `DJANGO_SECRET_KEY` | `django-insecure-...` | **필수** — 로컬은 임의값 가능 |
| `DJANGO_ALLOWED_HOSTS` | `*` | 로컬은 `*` 허용 |
| `DJANGO_LOG_LEVEL` | `INFO` | DEBUG/INFO/WARNING/ERROR |
| `REDIS_URL` | `redis://localhost:6379/0` | Celery 브로커 + 캐시 |
| `JWT_ACCESS_TOKEN_LIFETIME_HOURS` | `1` | JWT 액세스 토큰 만료 |
| `JWT_REFRESH_TOKEN_LIFETIME_DAYS` | `30` | JWT 리프레시 토큰 만료 |
| `JWT_SIGNING_KEY` | (빈 문자열) | 빈 값 = `SECRET_KEY` 폴백 |
| `INTERNAL_SERVICE_TOKEN` | (빈 문자열) | drf ↔ fastapi 서비스 간 인증 토큰 |
| `FASTAPI_INTERNAL_URL` | `http://127.0.0.1:8001` | Celery → FastAPI 알람 브리지 |
| `FRONTEND_WS_BASE_URL` | `ws://127.0.0.1:8001` | 브라우저 WebSocket 접속 URL |
| `ALARM_REPOPUP_COOLDOWN_SEC` | `15` | 시연용 — 운영은 `60` |
| `DISCORD_ALARM_ENABLED` | `False` | Discord 미러 발송 토글 (`True` 시 아래 webhook 필요) |
| `DISCORD_WEBHOOK_ADMIN` | (빈 문자열) | 관리자 채널 webhook URL |
| `DISCORD_WEBHOOK_WORKER` | (빈 문자열) | 작업자 채널 webhook URL (DANGER `@here` 대피용) |

---

### Docker 운영 — `.env.docker`

```bash
cp .env.docker.example .env.docker
# 아래 명령으로 각 키 값 생성 후 .env.docker에 기입
python -c "import secrets; print(secrets.token_urlsafe(50))"  # DJANGO_SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(32))"  # INTERNAL_SERVICE_TOKEN, JWT_SIGNING_KEY
```

| 변수 | 예시 | 비고 |
|---|---|---|
| `DJANGO_SECRET_KEY` | (긴 랜덤 문자열) | **필수** — 운영은 반드시 랜덤값 |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | **필수** — 미설정 시 서버 기동 실패 |
| `POSTGRES_DB` | `diconai` | PostgreSQL DB명 |
| `POSTGRES_USER` | `diconai` | PostgreSQL 사용자 |
| `POSTGRES_PASSWORD` | (랜덤값) | **필수** |
| `POSTGRES_HOST` | `postgres` | docker-compose 서비스명 |
| `POSTGRES_PORT` | `5432` | 기본값 |
| `JWT_SIGNING_KEY` | (랜덤값) | 빈 값 = `SECRET_KEY` 폴백 (비권장) |
| `INTERNAL_SERVICE_TOKEN` | (랜덤값) | drf ↔ fastapi 서비스 간 인증 토큰 |
| `DRF_SERVICE_TOKEN` | (랜덤값) | **`INTERNAL_SERVICE_TOKEN`과 반드시 동일 값** — 다르면 가스 더미가 전부 502 |
| `GRAFANA_PASSWORD` | (임의값) | Grafana admin 비밀번호 |

> `REDIS_URL` · `FASTAPI_INTERNAL_URL` · `DRF_BASE_URL`은 `.env.docker`가 아니라 [docker-compose.yml](docker-compose.yml)의 `environment` 블록이 서비스명 기반으로 직접 주입합니다 — `.env.docker`에 적지 않아도 됩니다. `ALARM_REPOPUP_COOLDOWN_SEC`는 미설정 시 코드 기본값(`60`)이 적용됩니다.

---

### FastAPI — `fastapi-server/.env`

```bash
cp fastapi-server/.env.example fastapi-server/.env
```

| 변수 | 예시 | 비고 |
|---|---|---|
| `LOG_LEVEL` | `INFO` | DEBUG/INFO/WARNING/ERROR |
| `DRF_BASE_URL` | `http://localhost:8000` | DRF 호출용 (Docker: `http://drf:8000`) |
| `DRF_SERVICE_TOKEN` | (빈 문자열) | fastapi → drf 인증 토큰. `INTERNAL_SERVICE_TOKEN`과 동일 값 |
| `INTERNAL_SERVICE_TOKEN` | (빈 문자열) | drf가 보내는 헤더 검증용. drf와 동일 값 |
| `JWT_SIGNING_KEY` | (빈 문자열) | WS JWT 검증용. drf와 동일 값 |
| `DRF_REQUEST_TIMEOUT_SEC` | `5.0` | fastapi → drf 호출 타임아웃 (초) |
| `BROADCAST_INTERVAL_SEC` | `5.0` | 센서 WebSocket 브로드캐스트 주기 |
| `DATA_STALE_THRESHOLD_SEC` | `8.0` | 데이터 미수신 판정 임계 |
| `DUMMY_TARGET_HOST` | `127.0.0.1` | 더미 송출 대상 호스트 |
| `DUMMY_TARGET_PORT` | `8001` | 더미 송출 대상 포트 |
| `DUMMY_SEND_INTERVAL_SEC` | `1.0` | 더미 송출 주기 (초) |
| `DUMMY_RISK_PROBABILITY` | `0.1` | 더미 위험 발생 확률 (0~1) |

---

## API 엔드포인트

### DRF (:8000) — 영속성·인증

| Method | Path | 설명 |
|---|---|---|
| POST | `/api/auth/login/` | JWT 로그인 |
| POST | `/api/auth/token/refresh/` | 액세스 토큰 갱신 |
| GET | `/alerts/api/alarms/` | 알람 목록 |
| GET | `/alerts/api/events/` | 이벤트 목록 |
| POST | `/api/monitoring/gas/` | 가스 데이터 저장 *(FastAPI 호출용)* |
| POST | `/api/monitoring/power/data/` | 전력 측정값 저장 |
| GET/POST | `/api/geofences/` | 위험구역 CRUD |
| GET/POST | `/api/gas-sensors/` | 가스 센서 마스터 관리 |
| GET/POST | `/api/power-devices/` | 전력 장비 마스터 관리 |
| GET | `/api/ml/models/active/` | active 이상탐지 모델 메타 조회 *(FastAPI 호출용)* |
| POST | `/api/ml/anomaly-results/` | AI 추론 결과 저장 *(FastAPI 호출용)* |

### FastAPI (:8001) — IoT 수신·실시간

| Method | Path | 설명 |
|---|---|---|
| POST | `/api/sensors/gas` | 가스 9종 측정값 수신 (1초 주기) |
| POST | `/api/power/watt` | 전력 16채널 측정값 |
| POST | `/api/positioning/receive` | 작업자 위치 수신 |
| WS | `/ws/sensors/` | 센서·알람 통합 스트림 |
| WS | `/ws/positions/` | 작업자 위치 스트림 (1초 주기) |
| WS | `/ws/worker/{user_id}/` | 개인 작업자 푸시 |

> 전체 엔드포인트는 [docs/specs/api_specification.md](docs/specs/api_specification.md) 문서, 또는 서버 실행 후 다음 두 곳에서 확인할 수 있습니다.
>
> - **DRF Swagger UI** — http://localhost:8000/api/schema/swagger-ui/
> - **FastAPI Docs** — http://localhost:8001/docs

---

## DB 설계

![ERD 다이어그램](docs/img/ERD%20일부분.png)

### 핵심 테이블

| 도메인 | 테이블 | 핵심 관계 |
|---|---|---|
| 계정 | `CustomUser` | → `Facility`(소속), → `Position` |
| 시설/장비 | `Facility`, `GasSensor`, `PowerDevice`, `GeoFence` | Facility 1:N 모든 장비/구역 |
| 측정 | `GasData`, `PowerData`, `PowerEvent` | GasSensor 1:N GasData |
| 알람 | `AlarmRecord`, `Event`, `EventLog` | AlarmRecord N:1 Event, Event 1:N EventLog |
| 위치 | `WorkerPosition` | CustomUser 1:N, GeoFence FK (캐시) |

### 설계 포인트

- **`GasData`** — wide 구조: 9종 컬럼(`co`/`h2s`/`co2`/`o2`/`no2`/`so2`/`o3`/`nh3`/`voc`) + `max_risk_level` 캐시 컬럼으로 조회 최적화
- **`AlarmRecord`** — *불변 모델*. `save()` 오버라이드로 update 차단 → 감사 추적 보장
- **`WorkerPosition`** — `measured_at`(센서 측정 시각) vs `received_at`(서버 수신 시각) 분리 → 통신 지연 측정 가능
- **`GeoFence`** — `polygon` JSONField + `contains_point(x, y)` (Ray casting) → 외부 의존성 없이 다각형 내포 판정

> 모델 상세는 [drf-server/apps/](drf-server/apps/) 각 앱 `models/` 참고.

---

## 프로젝트 구조

```
diconai/
├── drf-server/             # Django :8000 — 인증, DB, REST API
│   ├── config/             # settings, urls, celery
│   └── apps/               # accounts, alerts, facilities, monitoring,
│                           # geofence, positioning, ml(AI 이상탐지) ...
├── fastapi-server/         # FastAPI :8001 — IoT 수신, WebSocket
│   ├── gas/                # 가스 라우터/스키마/서비스
│   ├── power/              # 전력 라우터/스키마/서비스
│   ├── positioning/        # 위치 라우터/스키마/서비스
│   ├── ai/                 # IF·ARIMA 추론 + 위험도 결합(risk_combine)
│   ├── ml_models/          # 학습된 .pkl 모델 로딩 디렉토리
│   ├── websocket/          # /ws/* 엔드포인트, 공유 상태
│   └── internal/           # Celery → WS 브리지
└── docs/                   # 컨벤션, API 명세, URL 맵, changelog
```

### Django 앱 레이어 구조

```
apps/<app>/
├── models/        # DB 스키마
├── selectors/     # 읽기 전용 조회
├── services/      # 비즈니스 로직·트랜잭션
├── serializers/   # API 입출력 변환·검증
└── views/         # 요청 → 서비스 호출 → 응답 (로직 금지)
```

### AI 이상탐지 레이어 구조

학습은 DRF, 실시간 추론은 FastAPI로 분리합니다 — DRF가 모델 메타의 **단일 진실 공급원(SoT)**이며, FastAPI는 active 모델 메타를 조회해 `.pkl`을 로드한 뒤 추론합니다 ([ml/views.py](drf-server/apps/ml/views.py) docstring 기준).

```
drf-server/apps/ml/        # 학습 · 메타 · 추론 결과 영속 (SoT)
├── models/                # MLModel(학습 메타), MLAnomalyResult(추론 결과)
├── services/              # feature_service · dataset_service (피처·학습셋 생성)
├── management/commands/   # train_anomaly_model · train_arima_model (모델 학습)
└── views.py               # 모델 메타 조회 + 추론 결과 저장 API

fastapi-server/ai/         # 실시간 추론
├── router.py              # active 모델 .pkl 로드 → IsolationForest · ARIMA 추론
└── risk_combine.py        # 룰 위험도 + AI 위험도 결합 (combine_risk)
```

> 디렉토리 상세는 [docs/specs/directory-structure.md](docs/specs/directory-structure.md),
> 코딩 컨벤션은 [docs/conventions/dev_convention.md](docs/conventions/dev_convention.md) 참고.

---

## 테스트

```bash
# Docker (권장)
docker compose exec drf pytest -q
docker compose exec fastapi pytest -q

# 로컬 — 각 서버 venv 활성화 후
cd drf-server && pytest -q
cd fastapi-server && pytest -q
```

pytest 설정: [drf-server/pytest.ini](drf-server/pytest.ini) · [fastapi-server/pytest.ini](fastapi-server/pytest.ini)

---

## 트러블슈팅

주요 이슈와 해결 과정은 [docs/changelog/](docs/changelog/)에 페이즈별로 정리되어 있습니다.

- **알람 실시간 전파 지연** — Celery DB 저장 후에야 broadcast → 내부 push 엔드포인트(`/internal/alarms/push/`) + `alarm_flush_loop` 도입으로 즉시 전송 ([7a0f390](https://github.com/checkCJY/diconai/commit/7a0f390))
- **전력 임계치 양쪽 하드코딩** — DRF/JS 동기화 깨짐 → DRF `/api/monitoring/power/thresholds/` 단일 출처 API로 통일 ([34e808c](https://github.com/checkCJY/diconai/commit/34e808c))
- **DRF 레이어 책임 혼재** — view에 비즈니스 로직 섞임, 예외 응답 형식 제각각 → service/selector 분리 + 글로벌 예외 핸들러 도입 ([Phase 4](docs/changelog/phase4_drf_layer_exceptions_swagger.md))
- **프론트 HTTP·WebSocket 호출 분산** — 페이지마다 fetch/ws URL 하드코딩 → 단일 클라이언트 모듈로 통일, 인증 헤더 중앙 처리 ([Phase 3](docs/changelog/phase3_frontend_http_ws_unification.md))

---

## 향후 개선 포인트

### 브로드캐스트 주기 단축 (5초 → 3초)

현재 `BROADCAST_INTERVAL_SEC = 5.0`으로 운영합니다. 코드 주석대로 **브로드캐스트가 너무 짧으면 클라이언트 렌더링 부하가 커지기** 때문에 5초로 잡았으며, **다음 단계 목표는 3초 주기**입니다 (주기·근거 전체는 위 [데이터 주기](#기술-구조) 표 참고).

| 단계 | 주기 | 상태 |
|---|---|---|
| v1 (현재) | **5초** | 안정 운영 |
| v2 (목표) | **3초** | 개선 예정 |

**개선 방향**

- DRF 저장 경로 비동기화 (Celery 큐 단계 정리, 배치 INSERT 도입)
- WebSocket 페이로드 슬림화 (변경분만 전송 / diff 프로토콜)
- PostgreSQL 인덱스·쿼리 플랜 튜닝 (DB 운영 전환은 완료 — `postgres:16-alpine`)
- FastAPI ↔ DRF 내부 호출의 connection pool 재사용

### 그 외 로드맵

- **FastAPI 수평 확장(멀티 레플리카)** — WebSocket 공유 상태를 프로세스 메모리 → Redis로 이관해 replica ≥ 2 지원
- **AI 이상탐지 고도화** — 임계 돌파 조기예측 리드타임 개선 (현재는 룰 기반이 1차 판정, AI는 보조)
- **실 IoT 하드웨어 연동** — 현재 더미 송출을 실제 센서 수신으로 대체
- **다중 공장 지원** — 단일 `Facility(id=1)` → 멀티 테넌시 확장

---

## 관련 문서

- [docs/QUICKSTART.md](docs/QUICKSTART.md) — **빠른 시작** (클론→가동 한 경로)
- [docs/specs/api_specification.md](docs/specs/api_specification.md) — API 상세 명세
- [docs/specs/url-structure.md](docs/specs/url-structure.md) — 전체 URL 맵
- [docs/conventions/dev_convention.md](docs/conventions/dev_convention.md) — 코딩 컨벤션
- [docs/conventions/github_convention.md](docs/conventions/github_convention.md) — 이슈/PR/커밋 컨벤션
- [docs/changelog/](docs/changelog/) — 페이즈별 변경 이력
- [docs/refactor/waves/2026_05_09/CHANGES_REVIEW.md](docs/refactor/waves/2026_05_09/CHANGES_REVIEW.md) — **이번 브랜치 종합 변경 인벤토리** (5 카테고리 + 리뷰어 체크리스트)
- [docs/refactor/waves/2026_05_09/TEAM_BRIEF.md](docs/refactor/waves/2026_05_09/TEAM_BRIEF.md) — 이번 브랜치 팀 공유용 진입 문서 (5분 cheatsheet 포함)
- [docs/refactor/waves/2026_05_09/MIGRATION_GUIDE.md](docs/refactor/waves/2026_05_09/MIGRATION_GUIDE.md) — 머지·적용 5단계 + 트러블슈팅
