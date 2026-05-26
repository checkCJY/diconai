# 📒 diconai — 명령어 모음

> diconai 개발에서 자주 쓰는 명령을 한 곳에 모았습니다.
> 처음 환경 구축은 [README.md](../../README.md), Docker 상세는 [docs/infra/docker_setup.md](../infra/docker_setup.md).

---

## 🛠 로컬 개발 (Docker 없이)

### 가상환경

```bash
# 서버별 .venv (드라이버 직접 설치 환경에서만)
uv venv && source .venv/bin/activate
deactivate

# pre-commit (한 번만)
pre-commit install
pre-commit run --all-files
```

### 서버 실행 (각 터미널)

```bash
# DRF (:8000)
cd drf-server
uv pip install -r requirements.txt
python manage.py migrate
python manage.py runserver

# FastAPI (:8001)
cd fastapi-server
uv pip install -r requirements.txt
uvicorn app:app --reload --port 8001

# Celery worker (Redis가 떠 있어야 함)
cd drf-server
celery -A config worker -l info

# Celery beat (선택, 매일 새벽 3시 데이터 보관 배치)
cd drf-server
celery -A config beat -l info

# Redis (한 번만 설치)
sudo apt install redis-server   # Ubuntu/WSL
sudo service redis-server start
```

---

## 🐳 Docker (원형 명령)

> 보통은 ⚡ Makefile 단축을 쓰세요. 아래는 무엇이 일어나는지 알기 위한 원형.

### 빌드 / 기동 / 정지

```bash
docker compose build                    # 7개 이미지 빌드 (캐시 사용)
docker compose build --no-cache         # 캐시 무시 (의존성 충돌 의심 시)
docker compose build drf                # 한 서비스만 재빌드
docker compose up -d                    # 백그라운드 기동
docker compose stop                     # 정지 (제거 안 함)
docker compose start                    # 재기동
docker compose restart drf              # 한 서비스만 재기동
docker compose down                     # 컨테이너 제거 (볼륨 유지)
docker compose down -v                  # 볼륨까지 제거 (데이터 삭제!)
```

### 상태 / 로그 / 진입

```bash
docker compose ps                       # 7개 상태 (healthy/Up)
docker compose logs -f drf              # drf 로그 실시간
docker compose logs --tail=50 fastapi   # fastapi 최근 50줄
docker compose exec drf sh              # drf 컨테이너 쉘 진입
docker compose exec drf python manage.py shell    # Django shell
```

---

## ⚡ Makefile 단축

`make help`로 전체 타깃 + 자주 쓰는 시나리오 자동 노출. 서비스명 인자: `make logs s=drf`.

### 🐳 빌드 / 기동

| 타깃 | 동작 | 인자 |
|---|---|---|
| `make help` | 전체 타깃 + 시나리오 출력 | — |
| `make up` | 7-서비스 전체 기동 (백그라운드) | — |
| `make down` | 컨테이너 제거 (볼륨 유지) | — |
| `make start` | 정지된 컨테이너 재기동 | `s=` |
| `make stop` | 컨테이너 정지 | `s=` |
| `make restart` | 재기동 | `s=` |
| `make ps` | 서비스 상태 | — |
| `make build` | 이미지 빌드 (캐시 사용) | `s=` |
| `make rebuild` | 이미지 빌드 (캐시 무시) | `s=` |

### 📋 서비스별 로그 (stdout — 휘발성)

| 타깃 | 동작 | 인자 |
|---|---|---|
| `make logs` | 전체 또는 한 서비스 stdout | `s=` |
| `make logs-drf` | drf 단독 (gunicorn + Django) | — |
| `make logs-fastapi` | fastapi 단독 (uvicorn + IoT + WS) | — |
| `make logs-celery` | celery-worker 단독 | — |
| `make logs-beat` | celery-beat 단독 | — |
| `make logs-all` | drf + fastapi + celery 4개 통합 | — |

### 📁 파일 로그 (영속 — RotatingFileHandler)

> 배경·결정 근거: [skill/study/2026-05-26_파일_로깅_도입_배경.md](../../skill/study/2026-05-26_파일_로깅_도입_배경.md)

| 타깃 | 동작 | 인자 |
|---|---|---|
| `make logs-err` | drf error.log 실시간 (ERROR 전용) | — |
| `make logs-err-fastapi` | fastapi error.log 실시간 | — |
| `make logs-err-all` | **양 서버 error.log 합쳐 보기 — 시연·사고 추적 1순위** | — |
| `make logs-app` | drf app.log 실시간 (INFO+; retention·AI·임계치 변경) | — |
| `make logs-app-fastapi` | fastapi app.log 실시간 (IoT 페이로드 파싱 등) | — |
| `make logs-stat` | 파일 크기·회전 백업 현황 (운영 점검) | — |

### 🔍 로그 필터 (이슈 추적·트러블슈팅)

| 타깃 | 동작 | 인자 |
|---|---|---|
| `make logs-locks` | celery `database is locked` 감시 | — |
| `make logs-timeouts` | fastapi `action=timeout` 감시 | — |
| `make logs-errors` | DRF 4xx/5xx + ERROR + Forbidden 감시 | — |
| `make logs-ai` | AI 추론 로그 (`anomaly_inference`) 감시 | — |
| `make logs-retention` | retention task 발사·실행 로그 | — |

### 🐚 컨테이너 안 실행

| 타깃 | 동작 | 인자 |
|---|---|---|
| `make sh` | 컨테이너 쉘 진입 | `s=` 필수 |
| `make exec` | 임의 명령 실행 | `s= cmd="..."` |
| `make test` | drf + fastapi pytest 일괄 | — |
| `make test-drf` | drf만 | — |
| `make test-fastapi` | fastapi만 | — |
| `make shell-drf` | Django shell 진입 | — |

### 🗄 Django DB 작업

| 타깃 | 동작 | 인자 |
|---|---|---|
| `make migrate` | `manage.py migrate` | — |
| `make showmigrations` | 마이그레이션 적용 상태 | — |
| `make super` | 슈퍼유저 생성 (대화형) | — |
| `make seed` | 더미 데이터 시드 | — |

### ✅ 정상 동작 검증

| 타깃 | 동작 | 인자 |
|---|---|---|
| `make health` | 양 서버 `/health/` 호출 | — |
| `make metrics` | `/metrics` 샘플 5줄씩 | — |
| `make targets` | Prometheus targets 상태 | — |

### 🎭 더미 송출 (개발·시연 부하)

| 타깃 | 동작 | 인자 |
|---|---|---|
| `make dummies-start` | 더미 시작 (미지정 시 gas/power/position 3종 전체) | `s=gas\|power\|position` |
| `make dummies-stop` | 더미 정상 종료 (SIGINT) | `s=` |
| `make dummies-list` | 실행 중 더미 프로세스 확인 | — |
| `make dummies-restart` | 더미 재기동 (stop → 2초 → start) | `s=` |

### 💾 DB 상태 진단

| 타깃 | 동작 | 인자 |
|---|---|---|
| `make db-size` | DB 파일 + WAL/SHM 크기 (12GB 비대화 감지) | — |
| `make db-pragma` | PRAGMA 설정 (`busy_timeout`/`journal_mode`) | — |
| `make db-counts` | 주요 테이블 row count + 시간 범위 | — |

### 🧹 정리

| 타깃 | 동작 | 인자 |
|---|---|---|
| `make clean` | `down -v` ⚠️ Redis/Prometheus/Grafana 데이터 삭제 | — |
| `make prune` | 댕글링 이미지/볼륨 정리 ⚠️ 전역 | — |

---

## ✅ 자주 쓰는 검증

```bash
# 헬스 한 줄 확인
make health
# 또는 직접
curl -fsS http://localhost:8000/health/
curl -fsS http://localhost:8001/health/

# 메트릭 노출 확인
make metrics
curl -s http://localhost:8000/metrics | grep '^http_requests_total' | head

# Prometheus scrape 정상 여부
make targets
curl -s 'http://localhost:9090/api/v1/targets?state=active' | python3 -m json.tool | grep -E '"job"|"health"'

# Grafana 접속
# http://localhost:3000   (id: admin / pw: .env.docker의 GRAFANA_PASSWORD)
```

### 빠르게 트래픽 발생시켜 대시보드 채우기

```bash
for i in {1..50}; do
  curl -s http://localhost:8000/health/ > /dev/null
  curl -s http://localhost:8001/health/ > /dev/null
  sleep 0.2
done
```

---

## 📁 파일 로그 보기 (RotatingFileHandler)

`make logs`(stdout)는 컨테이너 재시작 시 휘발. 영속 로그는 `*/logs/*.log` 파일에서 본다.

| 시나리오 | 명령 |
|---|---|
| **시연 중 에러 즉시 확인 (1순위)** | `make logs-err-all` |
| 특정 알람만 추적 | `tail -f drf-server/logs/error.log \| grep alarm` |
| IoT 페이로드 파싱 실패 원본 | `tail -f fastapi-server/logs/app.log \| grep parse_fail` |
| Celery beat 09:30 retention 동작 여부 | `grep "retention" drf-server/logs/app.log \| tail` |
| 로그 회전 동작 확인 | `make logs-stat` |
| 시연 직전 로그 초기화 | `: > drf-server/logs/error.log && : > fastapi-server/logs/error.log` |

> **정책**: `error.log` = ERROR 전용 (100MB × 10 = 1GB 캡), `app.log` = INFO+ (50MB × 5 = 250MB 캡). 두 파일 모두 자동 회전.
> 배경·결정 근거: [skill/study/2026-05-26_파일_로깅_도입_배경.md](../../skill/study/2026-05-26_파일_로깅_도입_배경.md)

---

## 🗄 DB · 시드 · 슈퍼유저

### Docker 환경

```bash
make showmigrations              # 53개 모두 [X] 인지
make migrate                     # 미적용분 수동 실행 (entrypoint가 자동 처리하지만 명시적으로)
make super                       # 슈퍼유저 생성
make seed                        # Worker × 4, GasSensor, PowerDevice 더미 마스터
make exec s=drf cmd="python manage.py dbshell"   # SQLite CLI
make exec s=drf cmd="python manage.py dumpdata --natural-foreign --natural-primary --exclude=contenttypes --exclude=auth.permission > /app/dump.json"
```

### 로컬 환경

```bash
cd drf-server
python manage.py migrate
python manage.py seed_dummy_data
python manage.py createsuperuser
```

> ⚠️ `createsuperuser`는 반드시 `seed_dummy_data` 이후 실행. 시드가 worker `id=1~4`를 먼저 점유해야 슈퍼유저가 `id=5` 이상으로 부여됨.

---

## 🐛 트러블슈팅 한 줄 명령

```bash
# 포트 점유 확인 (8000 이미 사용 중인지)
sudo lsof -i :8000
sudo ss -ltnp | grep -E ':8000|:8001|:9090|:3000'

# 컨테이너 강제 재생성 (이미지 재사용, env/volume 다시 마운트)
docker compose up -d --force-recreate drf

# 특정 에러만 로그에서 grep
docker compose logs --tail=200 fastapi | grep -i -E 'error|exception|traceback'

# 한 서비스만 처음부터 (이미지 재빌드 + 컨테이너 재생성)
docker compose build --no-cache fastapi && docker compose up -d --force-recreate fastapi

# .env.docker 가 컨테이너에 들어갔는지 확인
docker compose exec drf env | grep DJANGO_SECRET_KEY

# 볼륨 목록
docker volume ls | grep diconai

# 디스크 사용량 (이미지 + 볼륨)
docker system df

# WSL Docker 통합 OFF 시 (Windows Docker Desktop 설정에서 통합 ON 후)
wsl --shutdown   # PowerShell에서. 재시작 후 docker --version 확인
```

### 흔한 실수와 해결

| 증상 | 원인 | 해결 |
|---|---|---|
| `make`가 없다고 함 | WSL에 build-essential 미설치 | `sudo apt install build-essential` |
| `docker` 명령 없음 | Docker Desktop WSL 통합 OFF | Settings → Resources → WSL Integration ON |
| `make build` 의존성 충돌 | requirements.txt에 transitive 박힘 | 직접 의존성만 남기고 재빌드 |
| Grafana "No data" | datasource UID 불일치 | `docker/grafana/.../prometheus.yml`에 `uid: prometheus` 명시 |
| `/metrics` 빈 응답 (FastAPI) | mount 미작동 | `@app.get("/metrics")` GET 엔드포인트로 변경 |
| bind mount 폴더가 root 소유 | 컨테이너가 자동 생성한 빈 폴더 | `sudo rm -rf` 후 호스트에서 mkdir |

---

## 참고

- 도커 도입 배경·구조·트러블슈팅: [docs/infra/docker_setup.md](../infra/docker_setup.md)
- 개발 컨벤션: [docs/conventions/dev_convention.md](dev_convention.md)
- 커밋·브랜치 규칙: [docs/conventions/github_convention.md](github_convention.md)
- API 응답 규약: [docs/conventions/api_response_convention.md](api_response_convention.md)
