# Docker 통합 환경 가이드

> 대상: diconai 개발팀 (Docker에 익숙하지 않은 팀원 포함)
> 작성일: 2026-05-11 / 작성 환경: WSL2 + Docker Desktop
> 짝꿍 문서: [README.md "🐳 Docker 통합 환경"](../../README.md) · [docs/conventions/COMMANDS.md](../conventions/COMMANDS.md)

이 문서 하나만 따라가면:
- 신규 팀원도 처음부터 환경 띄울 수 있다 (§8)
- 일상 개발에서 어떤 명령을 쳐야 하는지 안다 (§9)
- 문제가 생겼을 때 어디부터 보는지 안다 (§10)

---

## 1. 왜 도입했는가

| 동기 | 설명 |
|---|---|
| **개발 환경 일관성** | "내 PC에선 되는데" 차단. drf/fastapi/redis/celery 의존성과 버전을 컨테이너로 고정. |
| **AI/모니터링 추가 전 토대** | 다음 스프린트에 AI 시계열 컨테이너·Prometheus·Grafana가 추가되면 서비스가 6~8개로 늘어남. 토대가 없으면 그때 도커 도입 비용 + 누적된 환경 불일치 비용을 동시에 치러야 함. |
| **운영/시연 안정성** | 1초 안에 한 서비스만 재기동 가능. systemd 수동 관리에 비해 일관성↑. |
| **메트릭 자동 수집** | Prometheus가 컨테이너 네트워크에서 서비스명 기준으로 자동 scrape. 운영 상황을 숫자로 본다. |

> 결정 사유: 이전 결정 ("Docker는 다음 스프린트") 변경. 인프라 토대를 AI 작업 전에 깔기로 (2026-05-11). 자세한 사유는 메모리 `docker_infra_decision_2026_05_11.md`.

---

## 2. 무엇이 바뀌었는가

| 항목 | 이전 (수동) | 이후 (Docker) |
|---|---|---|
| Redis 시작 | `sudo service redis-server start` | `make up` (자동) |
| DRF 시작 | `cd drf-server && python manage.py runserver` | `make up` (자동, gunicorn 3-worker) |
| FastAPI 시작 | `cd fastapi-server && uvicorn app:app --port 8001` | `make up` (자동, uvicorn 2-worker) |
| Celery worker | 별도 터미널: `celery -A config worker` | `make up` (자동) |
| Celery beat | 거의 미실행 (배치 누락 위험) | `make up` (자동 시간 배치) |
| 마이그레이션 적용 | 수동 `python manage.py migrate` | drf 컨테이너 entrypoint 자동 |
| 정적파일 수집 | 거의 안 함 (admin 페이지 깨질 위험) | drf 컨테이너 entrypoint 자동 |
| 모니터링 | 없음 (장애 시 로그 grep) | Prometheus + Grafana 대시보드 자동 |
| 의존성 충돌 | 팀원 PC마다 환경 다름 | 이미지에 고정 |
| 멈출 때 | 터미널 4~5개 Ctrl+C | `make down` |

---

## 3. 이점 5가지

1. **재현성** — 누구나 같은 이미지로 같은 동작. WSL/macOS/Linux 어디서 띄워도 동일.
2. **격리** — 호스트 시스템에 Python·Redis·Postgres 안 깔아도 됨. 다른 프로젝트와 의존성 충돌 없음.
3. **헬스체크** — 컨테이너가 자기 상태를 알림. `make ps` 한 줄로 7개 모두 OK인지 확인.
4. **메트릭** — `http_requests_total`, p95 latency가 자동으로 Grafana에 차트로 그려짐. 장애 전조 감지.
5. **의존성 관리** — `depends_on: condition: service_healthy`로 fastapi는 drf가 healthy 된 후에만 뜸. 시작 순서 자동.

---

## 4. 7-서비스 구조

```
┌───────────────────────── 호스트 (WSL2) ──────────────────────────┐
│                                                                  │
│  브라우저 ──► localhost:8000 ──► drf (gunicorn:8000)             │
│             ╲     :8001 ────────► fastapi (uvicorn:8001)         │
│              ╲    :9090 ────────► prometheus                     │
│               ╲   :3000 ────────► grafana                        │
│                                                                  │
│  ┌─ Docker compose network (서비스명으로 통신) ────────────────┐ │
│  │                                                             │ │
│  │   drf ──HTTP──► fastapi   (FASTAPI_INTERNAL_URL=http://     │ │
│  │    │                                  fastapi:8001)         │ │
│  │    │                                                        │ │
│  │   celery-worker ──► fastapi (/internal/alarms/push/)        │ │
│  │   celery-beat   ──► drf DB (Django ORM)                     │ │
│  │   fastapi  ──HTTP──► drf  (DRF_BASE_URL=http://drf:8000)    │ │
│  │                                                             │ │
│  │   drf/celery×2 ──► redis  (REDIS_URL=redis://redis:6379)    │ │
│  │   prometheus  ──► drf:8000/metrics, fastapi:8001/metrics    │ │
│  │   grafana     ──► prometheus:9090                           │ │
│  │                                                             │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  bind mount: drf-server/db.sqlite3  ←→  drf/celery 컨테이너      │
│  bind mount: drf-server/media       ←→  drf 컨테이너             │
└──────────────────────────────────────────────────────────────────┘
```

| # | 서비스 | 이미지 | 역할 |
|---|---|---|---|
| 1 | `drf` | 자체 빌드 (Django + gunicorn) | REST API, 어드민, DB, 인증 |
| 2 | `fastapi` | 자체 빌드 (FastAPI + uvicorn) | 센서 수신, WebSocket 브로드캐스트 |
| 3 | `redis` | `redis:7-alpine` | Celery 브로커 + Django 캐시 |
| 4 | `celery-worker` | drf 이미지 재사용 | 알람 영속화, 알람 push 트리거 |
| 5 | `celery-beat` | drf 이미지 재사용 | 매일 새벽 3시 데이터 보관 배치 |
| 6 | `prometheus` | `prom/prometheus` | 15초마다 /metrics scrape |
| 7 | `grafana` | `grafana/grafana` | 시각화 + 알림 (예정) |

---

## 5. 환경변수 흐름

```
.env.docker  (호스트 파일, gitignore)
      │
      │  docker compose의 env_file: ./.env.docker
      ▼
컨테이너 OS env (KEY=VALUE)
      │
      │  Django:   environ.Env()  /  FastAPI: pydantic-settings
      ▼
앱 코드의 settings.SECRET_KEY  등
```

### 필수 시크릿 — 3번 생성, 4줄 채움

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"   # ① DJANGO_SECRET_KEY 용
python -c "import secrets; print(secrets.token_urlsafe(32))"   # ② INTERNAL_SERVICE_TOKEN 용 (★ DRF_SERVICE_TOKEN도 같은 값)
python -c "import secrets; print(secrets.token_urlsafe(32))"   # ③ JWT_SIGNING_KEY 용
```

`.env.docker`에서 **4줄을 다음과 같이 채웁니다**:

| 변수 | 채울 값 | 비고 |
|---|---|---|
| `DJANGO_SECRET_KEY` | ① | Django 자체 비밀키 |
| `INTERNAL_SERVICE_TOKEN` | ② | drf가 검증하는 서비스 토큰 |
| `DRF_SERVICE_TOKEN` | **②와 동일** | fastapi → drf 호출 시 헤더에 부착. 다르면 가스 ingest 401 → 502 |
| `JWT_SIGNING_KEY` | ③ | WebSocket JWT 검증용 (drf SimpleJWT ↔ fastapi WS 공유) |

> ⚠️ **`INTERNAL_SERVICE_TOKEN`과 `DRF_SERVICE_TOKEN`이 다르면** fastapi→drf 호출이 401로 거부되고 fastapi가 이를 502로 래핑합니다. 가장 흔한 함정 — §10⑥ 참조.

### 서비스명 기반 통신 (`docker-compose.yml`에서 직접 주입)

`.env.docker`에 *넣지 않고* compose 파일에 명시:

```yaml
drf:
  environment:
    DATABASE_URL: sqlite:////app/db.sqlite3
    REDIS_URL:    redis://redis:6379/0
    FASTAPI_INTERNAL_URL: http://fastapi:8001
```

→ 컨테이너 안에서 `redis:6379`가 정상 resolve됨 (Docker 내장 DNS).

---

## 6. 헬스체크와 의존성 그래프

각 Dockerfile 안에 `HEALTHCHECK` 명시:

```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:8000/health/ || exit 1
```

compose에서 `depends_on: condition: service_healthy` 사용:

```yaml
fastapi:
  depends_on:
    drf:
      condition: service_healthy   # ← drf의 HEALTHCHECK가 ok 되어야 fastapi 기동
```

기동 순서 (compose가 자동 정렬):

```
redis (healthy) → drf (migrate + collectstatic + gunicorn → healthy)
                ├─► fastapi (uvicorn → healthy)
                │     └─► celery-worker
                └─► celery-beat
prometheus, grafana는 drf/fastapi 시작과 무관하게 병행
```

> 헬스체크 확인: `make ps` (STATUS 열에 `(healthy)` 표시) 또는 `make health`

---

## 7. 메트릭 흐름

```
앱 코드 (Counter, Histogram)
   │  매 요청마다 .labels(...).inc() / .observe(elapsed)
   ▼
/metrics 엔드포인트  (Prometheus 텍스트 포맷)
   │
   │  prometheus.yml: 15초마다 scrape
   ▼
prometheus (시계열 DB, 15일 보관)
   │
   │  PromQL 쿼리
   ▼
grafana 대시보드 "diconai — Overview"
```

### 메트릭 이름은 양 서버 동일, 서버 구분은 `job` label로

| 메트릭 | 의미 |
|---|---|
| `http_requests_total{job="drf",method=...,path=...,status=...}` | 요청 카운터 |
| `http_request_duration_seconds_bucket{job="drf",...}` | 응답시간 히스토그램 |
| `up{job="drf"}` (Prometheus 내장) | 서비스 alive 여부 (0/1) |

PromQL 예시:

```promql
# DRF의 5분 평균 RPS
sum by (path) (rate(http_requests_total{job="drf"}[5m]))

# FastAPI의 5분 p95 응답시간
histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{job="fastapi"}[5m])))
```

---

## 8. 신규 환경 최초 세팅 (체크리스트)

### 8-1. Docker Desktop 설치 + WSL 통합

1. https://www.docker.com/products/docker-desktop/ 에서 Docker Desktop 설치
2. 실행 후 **Settings → Resources → WSL Integration** → 사용하는 WSL 배포 토글 ON
3. WSL 터미널에서 검증:
   ```bash
   docker --version           # → Docker version 24.x 이상
   docker compose version     # → Docker Compose version v2.x 이상
   ```
   `command not found`가 나오면 WSL 통합이 꺼진 상태.

### 8-2. 저장소 받기

```bash
git clone https://github.com/checkCJY/diconai.git
cd diconai
git checkout develop      # 또는 작업 브랜치
git pull origin develop
```

### 8-3. Bind mount 디렉토리 미리 생성

Docker가 없는 디렉토리를 자동 생성하면 root 소유가 됨 → 호스트에서 쓰기 권한 잃음.

```bash
mkdir -p drf-server/media
# db.sqlite3는 이미 있으므로 생략 (없는 환경이라면 touch drf-server/db.sqlite3)
```

### 8-4. 환경변수 채우기

```bash
cp .env.docker.example .env.docker
```

**3번 실행해서 값 3개를 메모해두세요** (출력값 그대로 복사):

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"   # → ① DJANGO_SECRET_KEY 용
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # → ② INTERNAL_SERVICE_TOKEN ★ DRF_SERVICE_TOKEN에도 같은 값
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # → ③ JWT_SIGNING_KEY 용
```

`nano .env.docker` (또는 `code .env.docker`)로 편집해 **4줄을 정확히** 채웁니다:

```ini
DJANGO_SECRET_KEY=<①>
INTERNAL_SERVICE_TOKEN=<②>
DRF_SERVICE_TOKEN=<②와 같은 값>     # ⚠️ ②와 반드시 동일! 다르면 가스 ingest 502
JWT_SIGNING_KEY=<③>
```

저장(nano: `Ctrl+O` → `Enter` → `Ctrl+X`).

**검증** (기동 후 §8-6에서 다시 봐도 OK):

```bash
# 4줄이 모두 같은 형태로 들어갔는지
grep -E "^(DJANGO_SECRET_KEY|INTERNAL_SERVICE_TOKEN|DRF_SERVICE_TOKEN|JWT_SIGNING_KEY)=" .env.docker
# INTERNAL_SERVICE_TOKEN과 DRF_SERVICE_TOKEN 값이 같은지 시각적으로 확인
```

> 자세한 토큰 역할: §5 환경변수 흐름.
> 만에 하나 토큰 둘이 달라서 가스 더미가 502 나면: §10 ⑥ 참조.

### 8-5. 빌드 + 기동

```bash
make build       # 첫 빌드는 5~10분 (이후 캐시로 1분 내외)
make up          # 백그라운드 기동
make ps          # 7개 모두 (healthy)/Up 인지
```

### 8-6. 검증

```bash
make health      # drf OK / fastapi OK
make metrics     # 메트릭 5줄씩
make targets     # job 3개 모두 health=up

# 브라우저
# http://localhost:8000/dashboard/    ← 대시보드
# http://localhost:8001/docs          ← FastAPI Swagger
# http://localhost:9090/targets       ← Prometheus 모두 UP
# http://localhost:3000               ← Grafana (id: admin / pw: .env.docker의 GRAFANA_PASSWORD)
```

### 8-7. (필요 시) 슈퍼유저 + 시드

```bash
make showmigrations    # 모두 [X] 인지
make super             # 대화형 슈퍼유저 생성
make seed              # 더미 데이터 (Worker × 4, GasSensor, PowerDevice)
```

---

## 9. 일상 개발 워크플로우

### 9-1. drf-server (Django)

#### 새 Python 패키지 추가

```bash
# 1) drf-server/requirements.txt 에 줄 추가 (alphabetical, 직접 의존성만)
echo "django-cors-headers==4.6.0" >> drf-server/requirements.txt

# 2) drf 이미지 재빌드 (celery×2도 같은 이미지 사용하므로 한 번에)
make rebuild s=drf

# 3) 기동
make up
```

> ⚠️ transitive 의존성은 명시 금지 (호환성 충돌 원인). 직접 import하는 패키지만 추가.

#### 새 마이그레이션

```bash
# 1) 모델 수정 후 makemigrations (컨테이너 안에서)
make exec s=drf cmd="python manage.py makemigrations"

# 2) 자동 적용은 drf 컨테이너 entrypoint가 처리. 수동으로 적용하려면:
make migrate
```

#### 새 환경변수 추가

```bash
# 1) drf-server/.env.example 에 변수 추가 (가이드)
# 2) .env.docker.example 에 변수 추가 (compose용)
# 3) .env.docker 에 실제 값 채움 (gitignore)
# 4) drf 컨테이너 재기동 (이미지 재빌드 불필요, env_file 다시 읽음)
make restart s=drf
```

#### 새 Celery 태스크

```bash
# 1) apps/<app>/tasks.py 에 @shared_task 추가
# 2) celery-worker만 재기동 (코드는 drf 이미지에 들어있으므로 재빌드 필요)
make rebuild s=drf      # 또는 모든 drf 기반 컨테이너
make up
# beat 스케줄 추가했다면 config/settings.py CELERY_BEAT_SCHEDULE 수정 후 같은 절차
```

#### 정적파일 변경

```bash
# 호스트의 drf-server/static/ 안 파일 수정 후
make exec s=drf cmd="python manage.py collectstatic --noinput"
# (또는 단순히 컨테이너 재기동하면 entrypoint가 자동 처리)
make restart s=drf
```

### 9-2. fastapi-server

#### 새 라우터 추가

```bash
# 1) fastapi-server/<domain>/routers/<name>_router.py 작성
# 2) app.py에 include_router 호출 추가
# 3) fastapi 이미지 재빌드 + 기동
make rebuild s=fastapi
make up
```

#### 새 환경변수

```bash
# 1) fastapi-server/.env.example 에 변수 추가
# 2) fastapi-server/core/config.py 에 pydantic-settings 필드 추가
# 3) .env.docker.example + .env.docker 에 추가
make restart s=fastapi
```

#### WebSocket 디버그

```bash
# 컨테이너 안에서 WS 연결 추적
make logs s=fastapi | grep -i "websocket\|connect\|disconnect"

# 호스트에서 직접 WS 연결 (wscat 필요: npm i -g wscat)
JWT=$(make exec s=drf cmd="python manage.py drf_test_token" 2>/dev/null | tail -1)
wscat -c "ws://localhost:8001/ws/worker/1/?token=$JWT"
```

### 9-3. 공통

#### 코드 변경 → 재기동

| 변경 종류 | 명령 |
|---|---|
| 환경변수만 수정 | `make restart s=<서비스>` |
| Python 코드 변경 | `make rebuild s=<서비스> && make up` |
| requirements.txt 변경 | `make rebuild s=<서비스> && make up` |
| docker-compose.yml 변경 | `make up`만 (compose가 변경 감지) |
| Dockerfile 변경 | `make rebuild s=<서비스>` |
| Prometheus/Grafana 설정 변경 | `make restart s=prometheus` 또는 `make restart s=grafana` |

#### 컨테이너 안에서 디버깅

```bash
make sh s=drf            # /bin/sh 진입
make shell-drf           # Django shell (manage.py shell)
make exec s=drf cmd="python manage.py dbshell"   # SQLite CLI
```

#### 로그 모니터링

```bash
make logs              # 7개 컨테이너 전체
make logs s=fastapi    # fastapi만
docker compose logs -f --since=10m fastapi | grep -i error   # 최근 10분 에러만
```

---

## 10. 트러블슈팅 (실제 만난 6건)

### ① `django-prometheus 2.4.1 ↔ django 6.0` 비호환

**증상**: `make build` 중
> Because django-prometheus==2.4.1 depends on django>=4.2,<6.0 and you require django==6.0.4, your requirements are unsatisfiable.

**원인**: django-prometheus가 django 6 미지원.

**해결**: `prometheus-client`만 사용해 직접 미들웨어 작성 → [drf-server/apps/core/prometheus.py](../../drf-server/apps/core/prometheus.py)

### ② `prometheus-fastapi-instrumentator ↔ starlette 1` 비호환

**증상**:
> Because prometheus-fastapi-instrumentator==7.1.0 depends on starlette>=0.30.0,<1.0.0 and you require starlette==1.0.0, your requirements are unsatisfiable.

**원인**: 의존성 핀 충돌. fastapi 0.135.3가 starlette 1.0을 가져오는데 instrumentator는 0.x 요구.

**해결**: 동일 패턴으로 직접 미들웨어 작성 → [fastapi-server/app.py](../../fastapi-server/app.py)의 `prometheus_metrics_middleware`

### ③ Grafana datasource UID 미명시 → "No data"

**증상**: Prometheus targets 모두 up, /metrics에도 데이터 있는데 Grafana 대시보드만 "No data".

**원인**: Grafana 11은 datasource에 UID를 자동 부여하는데, 대시보드 JSON이 `"uid": "prometheus"`로 하드코딩되어 매칭 실패.

**해결**: `docker/grafana/provisioning/datasources/prometheus.yml`에 `uid: prometheus` 추가 + `make restart s=grafana`.

### ④ FastAPI `app.mount("/metrics")` 미동작

**증상**: `curl http://localhost:8001/metrics`가 빈 응답.

**원인**: FastAPI에서 ASGI sub-app mount는 일반 미들웨어와 상호작용이 미묘. 메트릭이 등록되어도 mount된 sub-app에 전파 안 됨.

**해결**: `@app.get("/metrics")` 일반 GET 엔드포인트로 교체 (DRF처럼).

### ⑤ WSL에서 `docker` 명령 못 찾음

**증상**:
> The command 'docker' could not be found in this WSL 2 distro.

**해결**: Docker Desktop **Settings → Resources → WSL Integration** → 현재 배포 토글 ON 후 WSL 터미널 재시작.

### ⑥ 가스 더미만 HTTP 502 (전력·위치는 정상)

**증상**: `python -m dummies.gas_dummy` 실행 시 `[GAS] HTTP 502` 반복. 전력·위치 더미는 200/201 정상.

**로그 (fastapi)**:
```
POST http://drf:8000/api/monitoring/gas/ "HTTP/1.1 401 Unauthorized"
[gas_service] action=non_success status=401 body='{"error":{"code":"authentication_required","message":"유효하지 않은 서비스 토큰입니다."}}'
"POST /api/sensors/gas HTTP/1.1" 502
```

**원인**: `.env.docker`의 `DRF_SERVICE_TOKEN`(fastapi → drf 호출 시 헤더 값)과 `INTERNAL_SERVICE_TOKEN`(drf가 검증하는 값)이 **다른 값**으로 채워짐. fastapi가 jwt 시크릿 생성 시 따로 만든 값을 채워 넣었다면 발생. 전력·위치 라우터는 현재 토큰 검증 경로 없이 통과하므로 영향 없음 (옵트인 보안이 가스에만 적용됨 — 별도 일관성 이슈).

**진단**:
```bash
docker compose exec drf     env | grep INTERNAL_SERVICE_TOKEN
docker compose exec fastapi env | grep -E "INTERNAL_SERVICE_TOKEN|DRF_SERVICE_TOKEN"
# 세 줄의 값이 모두 동일해야 정상
```

**해결**: `.env.docker`에서 세 변수(`INTERNAL_SERVICE_TOKEN`·`DRF_SERVICE_TOKEN`·`JWT_SIGNING_KEY`는 별개로 둬도 OK이지만 토큰 두 개는 같은 값)를 같은 값으로 통일 → fastapi 재생성:

```bash
sed -i 's|^DRF_SERVICE_TOKEN=.*|DRF_SERVICE_TOKEN=<INTERNAL_SERVICE_TOKEN과 같은 값>|' .env.docker
docker compose up -d --force-recreate fastapi celery-worker
```

> `restart`는 env_file을 다시 안 읽는 경우가 있어 `--force-recreate` 권장. 또는 `down && up -d`.

---

## 11. 알려진 한계

- **SQLite 다중 writer**: drf + celery-worker + celery-beat가 같은 SQLite 파일에 접근. 부하 시 `SQLITE_BUSY` 가능. 다음 스프린트 Postgres 전환에서 해소.
- **단일 호스트**: 모든 서비스가 한 머신. 멀티 노드 필요 시 K8s 검토.
- **TLS 없음**: HTTP만. 도메인/공개 노출 시 nginx + Let's Encrypt 필요.
- **WSL 의존**: Windows 환경은 Docker Desktop + WSL2 필수. 사내 보안정책으로 Docker Desktop 사용 불가하면 Rancher Desktop 또는 podman 대안 검토.
- **시크릿 평문**: `.env.docker`는 평문 파일. 운영 환경에선 docker secret/vault 검토.

---

## 12. 📋 남은 과제

### Now (이번 PR 머지 직후, ≤1일)

- 팀원 1~2명이 §8 신규 환경 세팅을 그대로 따라 검증 (문서 갭 발견)
- README의 "🐳 Docker 통합 환경" 섹션 끝에 이 문서 링크 추가 (완료 시 체크)
- (선택) `feature/docker_test` 브랜치 push + develop 대상 PR 생성

### Next (다음 스프린트, 1~3주)

- **Postgres 전환** (트리거: SQLite 락 발생 시. 공수: 1~2일) — `DATABASE_URL` 교체, `docker-compose.yml`에 postgres 서비스 추가, 데이터 이전 절차 (`dumpdata` → `loaddata`)
- **AI 시계열 분석 컨테이너** (트리거: 메모리 `ai_anomaly_scope_2026_05_11.md` 범위. 공수: 1주) — 가스 STEP 1~4 + multivariate IF
- **nginx + TLS** (트리거: 도메인 도입 시. 공수: 1~2일) — 정적/미디어 서빙 + WS 프록시 + Let's Encrypt
- **dev/prod compose 분리** (트리거: 운영 환경 구분 필요 시. 공수: 반나절) — `docker-compose.dev.yml` (hot reload, DEBUG=True), `docker-compose.prod.yml` (replicas, restart=always)
- **헬스체크 강화** (트리거: 의존성 오작동 발견 시. 공수: 2시간) — drf는 DB ping까지 검사, fastapi는 redis 연결 검사

### Later (분기 단위, 트리거 발생 시)

- **이미지 사이즈 최적화** (트리거: 이미지 ≥1GB 시. 공수: 1일) — distroless 또는 alpine 검토
- **BuildKit 캐시 최적화** (트리거: 빌드 시간 ≥5분 시. 공수: 반나절) — uv pip layer 분리, `--mount=type=cache`
- **시크릿 관리** (트리거: 운영 진입 시. 공수: 2일) — docker secret 또는 HashiCorp Vault
- **로그 수집** (트리거: 멀티 서비스 로그 grep 비효율 시. 공수: 1주) — Loki + Promtail + Grafana Logs
- **Grafana 알림** (트리거: p95 SLO 정의 시. 공수: 1일) — Slack/Email contact point, alert rule
- **multi-platform 이미지** (트리거: arm64 호스트 도입 시. 공수: 반나절) — `docker buildx`
- **CVE 스캔** (트리거: 보안 감사 요구 시. 공수: 1일) — `trivy image` 자동화, 정기 베이스 이미지 업데이트
- **gunicorn 워커 튜닝** (트리거: 응답시간 SLO 미달 시) — `(2*CPU)+1` 규칙
- **백업 스크립트** (트리거: 데이터 손실 우려 시. 공수: 1일) — Prometheus retention 정책, Grafana dashboards export
- **CI/CD 통합** (트리거: PR 자동 검증 필요 시. 공수: 2일) — GitHub Actions에서 이미지 빌드 + push + 테스트
- **Kubernetes 검토** (트리거: 멀티 노드 / HA 필요 시) — Helm chart 또는 Kustomize
