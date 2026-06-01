# diconai 인프라 가이드 (팀 온보딩용)

> **이 문서의 목적**
> 우리 팀은 Docker·Kubernetes·모니터링을 "AI 도움으로 일단 도입"한 상태입니다.
> 이 문서는 **각 구성요소가 무엇이고, 무엇을 담당하며, 왜 필요한지**를
> 코드를 열어보지 않고도 이해할 수 있게 정리한 것입니다.
> (설정 검토 결과는 맨 아래 [§7 검토 결과](#7-검토-결과-2026-06-01)에 있습니다.)
>
> **관련 문서:** 실제 환경 세팅·일상 워크플로우는 `docs/infra/docker_setup.md`(§8 신규 환경 세팅, §9 워크플로우),
> 모든 단축 명령은 터미널에서 `make help`. 이 문서는 그 위에 얹는 **"개념 지도"**입니다.

작성일: 2026-06-01 · 대상: 팀 전원 · 난이도: 입문

---

## 1. 30초 요약

- 우리 시스템은 **두 개의 백엔드 서버**(Django/DRF, FastAPI)와
  그를 받쳐주는 **인프라 서비스 8종**(DB·캐시·작업큐 3종·모니터링 3종)으로 구성됩니다. (총 10개 컨테이너)
- 이걸 **두 가지 방법**으로 띄울 수 있습니다.
  - **Docker Compose** → 평소 개발·시연용 (간단, 노트북 한 대에서 전부).
  - **Kubernetes(k8s)** → "확장 가능한 운영 환경은 이렇게 생겼다"를 보여주는 학습/시연용.
- **두 방법은 똑같은 구성을 다른 도구로 표현**한 것뿐입니다. 서비스·포트·이미지가 1:1로 대응됩니다.
- 핵심 제약 하나만 기억: **FastAPI는 반드시 1개 프로세스(`workers=1`/`replicas=1`)로만 돌립니다.**
  이유는 [§5](#5-가장-중요한-제약-fastapi는-1개만)에서 설명합니다.

---

## 2. 전체 그림 (데이터가 흐르는 길)

```
            ┌──────────────┐
   IoT 센서  │  더미/장비    │  (가스·전력·작업자 위치 데이터 생성)
   (또는     └──────┬───────┘
   dummies/*.py)    │  ① 센서값 POST
                    ▼
            ┌──────────────┐        ④ WebSocket 실시간 푸시
            │   FastAPI     │ ───────────────────────────►  브라우저(대시보드)
            │  (8001)       │
            │ 수신·검증·WS  │
            └──┬────────┬───┘
        ② 저장 │        │ ③ 알람 발생 시 Celery에 작업 의뢰
               ▼        ▼
        ┌──────────┐  ┌──────────┐
        │   DRF    │  │  Redis    │ ◄── 작업 큐(broker) + 공유 상태
        │ (8000)   │  │  (6379)   │
        │ 저장·API │  └────┬──────┘
        │ ·HTML    │       │ 큐에서 작업 꺼냄
        └────┬─────┘       ▼
             │        ┌──────────────────────────┐
             ▼        │ Celery 워커들 (백그라운드) │
        ┌──────────┐  │  - alarm  : 알람 생성·발송 │
        │ Postgres │  │  - metric : 주기적 메트릭   │
        │ (5432)   │  │  - beat   : 스케줄러         │
        │ 영속 DB  │  └──────────────────────────┘
        └──────────┘

   [모니터링 라인]  Prometheus(9090) ── 각 서비스 /metrics 수집 ──► Grafana(3000) 대시보드
                    redis_exporter(9121) ── Redis 상태를 Prometheus가 읽을 수 있게 변환
```

**한 줄 흐름:**
센서 → **FastAPI**(받아서 검증) → **DRF**(Postgres에 저장) / **Redis**(알람 작업 적재)
→ **Celery**(알람 생성) → 다시 Redis → FastAPI가 **WebSocket**으로 브라우저에 즉시 전달.

---

## 3. 구성요소 카드 — 각자 무엇을 맡는가

각 카드는 **무엇 / 담당 / 왜 필요 / 설정 위치** 4가지로 정리했습니다.

### 🟦 DRF 서버 (Django + DRF) — 포트 8000
- **무엇:** 우리 시스템의 "본체" 웹서버.
- **담당:** 로그인·인증, 어드민/대시보드 **HTML 화면 렌더링**, **REST API**, DB에 데이터 저장.
- **왜 필요:** 사용자가 실제로 보는 화면과, 데이터가 영구 보관되는 통로. 비즈니스 로직의 중심.
- **설정:** `drf-server/Dockerfile`, `docker-compose.yml`의 `drf` 서비스, `k8s/drf.yaml`
- **이미지 태그:** `diconai/drf:dev`

### 🟩 FastAPI 서버 — 포트 8001
- **무엇:** 센서 데이터 수신 전용 + 실시간 통신 서버.
- **담당:** IoT/더미가 보내는 **센서값 수신·검증**, **WebSocket으로 브라우저에 실시간 브로드캐스트**,
  알람을 Celery에 넘기는 다리(bridge) 역할.
- **왜 필요:** 초당 다수의 센서 수신과 실시간 푸시는 비동기에 강한 FastAPI가 적합.
  무거운 DRF 본체와 분리해 부하를 나눔.
- **설정:** `fastapi-server/Dockerfile`, `docker-compose.yml`의 `fastapi`, `k8s/fastapi.yaml`
- **이미지 태그:** `diconai/fastapi:dev`
- ⚠ **반드시 1개 프로세스만** ([§5](#5-가장-중요한-제약-fastapi는-1개만) 참고)

### 🟥 Postgres — 포트 5432
- **무엇:** 관계형 데이터베이스 (PostgreSQL 16).
- **담당:** 센서 기록·알람 이력·사용자 등 **모든 영속 데이터**의 최종 보관소.
- **왜 필요:** 기존 SQLite는 동시 쓰기·대용량에서 한계 → 2026-05-22 PG로 전환.
- **설정:** `docker-compose.yml`의 `postgres`(`postgres:16-alpine`), `k8s/postgres.yaml`(StatefulSet)
- **메모:** dev에서는 `127.0.0.1:5432`로만 노출(DBeaver 등 GUI 접속용, 외부 차단).

### 🟨 Redis — 포트 6379
- **무엇:** 인메모리 키-값 저장소.
- **담당:** ① Celery **작업 큐(broker)** ② Celery **결과 저장** ③ 알람 **공유 상태 큐**.
- **왜 필요:** "알람 작업을 쌓아두고 워커가 꺼내 처리"하는 구조의 중심. 빠른 휘발성 저장.
- **설정:** `docker-compose.yml`의 `redis`(`redis:7-alpine`), `k8s/redis.yaml`

### 🟪 Celery 워커 3종 (백그라운드 작업자)
> Celery는 "시간이 걸리거나 나중에 해도 되는 일"을 웹서버 대신 처리하는 일꾼입니다.
> DRF와 **같은 이미지(`diconai/drf:dev`)**를 쓰되 실행 명령만 다릅니다.

| 워커 | 담당 | 왜 분리했나 |
|---|---|---|
| **celery-alarm** | 알람 생성·발송 (`-Q alarm`) | 알람은 지연되면 안 됨 → 전용 워커로 즉시 처리 |
| **celery-metric** | 주기적 메트릭 수집 (`-Q metric`) | 무거운 집계가 알람을 막지 않도록 큐 분리 |
| **celery-beat** | 스케줄러 (정해진 시각에 작업 트리거) | "매 N초마다 실행"을 담당. **항상 1개만** 떠야 중복 실행 방지 |

- **설정:** `docker-compose.yml`의 `celery-worker-alarm`/`celery-worker-metric`/`celery-beat`,
  `k8s/celery-alarm.yaml`·`celery-metric.yaml`·`celery-beat.yaml`

### 🟫 모니터링 3종 (Prometheus + Grafana + redis_exporter)
| 서비스 | 포트 | 담당 | 왜 필요 |
|---|---|---|---|
| **Prometheus** | 9090 | 각 서비스의 `/metrics`를 주기적으로 긁어 시계열로 저장 | "지금 시스템이 어떤 상태인가"의 원천 데이터 |
| **Grafana** | 3000 | Prometheus 데이터를 **대시보드 그래프**로 시각화 | 사람이 보기 쉬운 모니터링 화면 (5종 구성) |
| **redis_exporter** | 9121 | Redis 내부 상태를 Prometheus가 읽을 수 있는 형식으로 변환 | Redis는 자체 `/metrics`가 없어 통역기가 필요 |

- **설정:** `docker/prometheus/prometheus.yml`, `docker/grafana/provisioning/**`,
  k8s는 `k8s/prometheus.yaml`·`grafana.yaml`·`grafana-cm.yaml`·`redis-exporter.yaml`
- **Grafana 대시보드 5종:** overview / sensor / alarm / power-ai / db-redis
  (`docker/grafana/provisioning/dashboards/*.json`)

---

## 4. 두 가지 실행 환경 — 언제 무엇을 쓰나

| | **Docker Compose** | **Kubernetes (k8s)** |
|---|---|---|
| 용도 | 평소 개발·시연 | 운영급 확장 구조 학습/시연 |
| 정의 파일 | `docker-compose.yml` (1개) | `k8s/*.yaml` (14개) |
| 띄우는 곳 | 노트북 1대 | minikube (로컬 단일 노드 클러스터) |
| 외부 접근 | 포트 직접 발행(`8000:8000` 등) | Service `NodePort` |
| 난이도 | 낮음 | 높음 |

> **헷갈리지 말 것:** 둘은 경쟁 관계가 아니라 **같은 시스템의 두 표현**입니다.
> 서비스 이름·포트·이미지가 1:1로 대응되며, 검토 결과 양쪽이 서로 일치합니다.
> **평소엔 Compose를 쓰고, k8s는 "확장 가능한 형태는 이렇다"를 보여줄 때 사용**하면 됩니다.

### 실행 (Docker Compose — `make` 단축 명령)
> 전체 명령 목록은 `make help`. 신규 환경 세팅 절차는 `docs/infra/docker_setup.md §8`.

```bash
# 최초 1회
cp .env.docker.example .env.docker   # 비밀값 채우기
make build && make up                # 빌드 + 전체 기동
make ps && make health               # 상태/생존 확인

# 일상
make logs s=fastapi                  # 특정 서비스 로그
make rebuild s=drf && make up        # 코드 변경 후 재빌드
make down                            # 종료 (데이터는 유지)
```
접속: 대시보드 `http://localhost:8000` · Grafana `http://localhost:3000` · Prometheus `http://localhost:9090`

**데이터 흘려보내기** (띄운 직후엔 대시보드가 비어 있음):
```bash
make seed                # 기준 데이터 시드 (작업자/센서/장비)
make dummies-start       # 가스·전력·위치 더미 송출 시작 (s=gas|power|position 로 개별)
make demo-cycle          # 가스+전력 통합 시연 1사이클 (~2분 30초)
```

**Kubernetes (minikube):**
```bash
minikube start
eval $(minikube docker-env)          # 이미지를 minikube 안에서 빌드되게 설정
docker build -t diconai/drf:dev ./drf-server
docker build -t diconai/fastapi:dev ./fastapi-server
kubectl apply -f k8s/                # 전체 매니페스트 적용
kubectl get pods -n diconai          # 상태 확인
```

---

## 5. 가장 중요한 제약: FastAPI는 1개만

**FastAPI 서버는 절대 여러 개로 늘리지 마세요** (`--workers 2` 금지, `replicas: 2` 금지).

- **이유:** 실시간 브로드캐스트에 필요한 "누가 접속 중인지" 정보가
  **FastAPI 프로세스의 메모리 안**에 들어있습니다 (`fastapi-server/websocket/state.py`).
- 프로세스를 2개로 늘리면 메모리가 2개로 쪼개져서:
  - 센서 데이터는 A 프로세스로 들어가는데
  - 브라우저는 B 프로세스에 붙어 있으면 → **화면이 비어 보임**.
  - 알람도 한 워커만 큐에서 꺼내가서 → **일부 사용자에게 누락**.
- 현재 설정은 이를 정확히 반영해 `workers=1` / `replicas=1`로 고정돼 있습니다. (올바름)
- **언제 풀 수 있나:** Redis pub/sub으로 상태를 밖으로 빼면 그때 확장 가능.
  자세한 내용은 `docs/infra/websocket-scaling-guide.md`,
  `docs/infra/multi-replica-scaling-검토.md` 참고. (지금 당장 할 필요 없음)

---

## 6. 설정 파일 지도 — 무엇을 고치려면 어디를 보나

| 하고 싶은 것 | 봐야 할 파일 |
|---|---|
| Compose로 전체 띄우기 | `docker-compose.yml` |
| DRF/FastAPI 이미지 빌드 방법 | `drf-server/Dockerfile`, `fastapi-server/Dockerfile` |
| 환경변수(접속정보·토큰 등) | `.env.docker` (예시: `.env.docker.example`) |
| k8s로 띄우기 | `k8s/*.yaml` |
| k8s 환경변수 | `k8s/configmap.yaml` (일반값) + `k8s/secret.yaml` (비밀값) |
| Prometheus가 무엇을 수집하나 | `docker/prometheus/prometheus.yml` (Compose) / `k8s/prometheus.yaml` (k8s) |
| Grafana 대시보드·데이터소스 | `docker/grafana/provisioning/**` / `k8s/grafana-cm.yaml` |
| 단축 실행 명령 | `make help` (`Makefile`) |
| 환경 세팅·워크플로우 절차 | `docs/infra/docker_setup.md` |

> ⚠ **`.env.docker`와 `k8s/secret.yaml`은 비밀값**이라 git에 올리지 않습니다(.gitignore 처리됨).
> 새로 합류한 팀원은 `*.example` 파일을 복사해 직접 값을 채워야 합니다.

---

## 7. 검토 결과 (2026-06-01)

설정 전반을 점검한 결과입니다.

### ✅ 정상 — 빌드·기동을 막는 문제 없음
- Docker/Compose 설정 전부 git에 커밋되어 있고, 두 Dockerfile 모두 정상 동작.
- YAML 18개 전부 문법 OK. 빌드에 필요한 파일(entrypoint·requirements·gunicorn 설정) 모두 존재.
- **Compose ↔ k8s가 서로 일치**: 이미지 태그·포트·셀렉터·ConfigMap/Secret 키·네임스페이스 정합.
- 모니터링 연결 정상: Prometheus가 drf:8000 / fastapi:8001 수집, Grafana 데이터소스 `http://prometheus:9090`.
- 핵심 제약(FastAPI 1개)이 양쪽에 올바르게 박혀 있음.

### ⚠ 알아둘 점 (결함 아님 — 배포 환경에 따른 주의)
1. **WS 주소가 `ws://localhost:8001`로 고정** (`k8s/configmap.yaml`, `.env.docker`).
   Compose/로컬은 OK. 실제 k8s 외부 배포 시엔 NodePort/Ingress 주소로 바꿔야 브라우저가 실시간 연결 가능.
2. **WebSocket 실제 경로는 `/ws/sensors/`** (일부 문서의 `/api/sensors/ws`는 옛 표기).
   나중에 nginx/Ingress를 붙이면 `/ws/` 경로를 Upgrade 헤더와 함께 프록시해야 함.
3. **리버스 프록시(nginx) 없음.** 지금은 포트를 직접 노출. 로컬·시연엔 무방, 실서비스엔 앞단(프록시+TLS) 필요.
4. **더미/IoT 데이터 생성기가 Compose·k8s의 컨테이너로는 포함돼 있지 않음.**
   띄운 직후엔 대시보드가 비어 있음. 단 **`make seed` + `make dummies-start`** 단축 명령이 있어
   수동 실행은 간단함. (k8s 환경에선 이 더미 송출 경로가 별도 정리되어 있지 않으니 확인 필요.)
5. **Prometheus 설정이 2벌**(Compose용/k8s용)이고 redis exporter 이름이
   `redis_exporter`(언더스코어) vs `redis-exporter`(하이픈)로 다름. **각 환경엔 맞음.**
   한쪽 고칠 때 다른 쪽을 따라 고치면 깨지니 주의.
6. **`k8s/secret.yaml`에 평문 자격증명**이 들어있음(git 제외됨). 값이 dev 전용 throwaway인지 확인 권장.

### 결론
**지금 당장 고쳐야 할 블로커는 없습니다.** 위 ⚠ 항목은 "로컬/시연" 범위를 벗어나 실배포할 때
챙기면 되는 것들입니다. 우선순위 하나만 꼽으면 **#4(더미 실행을 README에 명시)** 가 신규 팀원 혼란을 가장 잘 줄여줍니다.

---

## 부록: 용어 빠른 사전
- **이미지(image):** 실행 가능한 앱을 통째로 담은 "설치 패키지". `Dockerfile`로 만듦.
- **컨테이너(container):** 이미지를 실제로 돌린 "실행 중인 인스턴스".
- **Compose:** 여러 컨테이너를 파일 하나로 묶어 한 번에 띄우는 도구.
- **k8s/Pod/Deployment:** Pod=컨테이너 묶음 / Deployment=Pod를 몇 개 어떻게 유지할지 정의 / Service=네트워크 진입점.
- **broker(브로커):** 작업을 쌓아두는 큐. 여기선 Redis가 담당.
- **exporter:** 어떤 서비스의 상태를 Prometheus가 읽을 수 있는 형식으로 변환해주는 통역기.
