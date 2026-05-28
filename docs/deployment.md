# 배포 · 운영 가이드

> 신규 팀원/평가자가 환경 세팅 → 실행 → 모니터링 → 백업까지 따라할 수 있는 매뉴얼.
> 상세 단계별 가이드: [docs/infra/docker_setup.md](infra/docker_setup.md) (546줄)

---

## 무엇을 수행하는가

Docker Compose 기반 7-서비스 구조로 drf-server / fastapi-server / postgres / redis / celery (alarm·metric·beat) / prometheus / grafana를 통합 실행·관찰·복구합니다.

## 왜 Compose 구조인가

| 결정 | 이유 |
|---|---|
| **Docker Compose 통합 환경** | 2026-05-11 결정. 로컬·시연·운영 환경 동일성 보장. 7-서비스 단일 명령으로 기동 |
| **settings dev/prod 분리** | PR #93 — `config/settings/{base,dev,prod}.py` 분기. `DJANGO_DEBUG` 값에 따라 자동 선택 |
| **K8s manifest 미적용** | 5개월차 팀 위험관리. 다중 인스턴스 시점에 도입 (현재 시연·운영 Compose로 충분) |

## 1. 환경 세팅 (신규 머신)

상세는 [docs/infra/docker_setup.md §8](infra/docker_setup.md)에 있습니다. 요약:

```bash
# 1-1. 저장소 받기
git clone <repo-url> diconai
cd diconai

# 1-2. 환경변수 채우기
cp .env.docker.example .env.docker
# 편집 — 자세히: docs/env-guide.md

# 1-3. Bind mount 디렉토리 생성 (drf-server/logs 등)
# docs/infra/docker_setup.md §8-3 참조

# 1-4. 빌드 + 기동
make up   # 또는: docker compose up -d

# 1-5. 마이그레이션 + 슈퍼유저
make migrate
make super

# 1-6. 검증
make health   # 7-서비스 healthy 확인
make ps
```

## 2. 일상 워크플로우

`make help`로 전체 명령 확인. 자주 쓰는 것:

```bash
make up          # 전체 기동
make down        # 전체 중지
make ps          # 상태 확인
make logs s=drf  # 특정 서비스 로그 follow
make sh s=drf    # 컨테이너 shell
make test        # drf + fastapi 테스트
make migrate     # makemigrations + migrate
make dummies-start  # 더미 센서 송출 시작
```

신규 환경변수·마이그레이션·Celery 태스크 추가 절차는 [docs/infra/docker_setup.md §9](infra/docker_setup.md).

## 3. 배포 구조

### 현행 (Compose)

```
host
 └─ docker-compose.yml (302줄)
     ├─ drf (8000)         — Django + gunicorn
     ├─ fastapi (8001)     — uvicorn
     ├─ postgres (5432)    — PG16, shared_buffers 256MB
     ├─ redis (6379)       — appendonly, brocker + List 큐
     ├─ celery-worker-alarm   (-Q alarm,    concurrency=2)
     ├─ celery-worker-metric  (-Q metric,   concurrency=1)
     ├─ celery-beat
     ├─ prometheus (9090)
     └─ grafana (3000)
```

### Phase 2 (K8s)

manifest는 [docs/roadmap-phase2.md](roadmap-phase2.md) (작성 예정) 참조. 진입 조건: 다중 인스턴스가 필요한 시점.

## 4. 모니터링

| 화면 | URL | 용도 |
|---|---|---|
| Prometheus targets | http://localhost:9090/targets | 메트릭 수집 대상 UP 여부 |
| Grafana | http://localhost:3000 (admin/admin) | 대시보드 시각화 |

Grafana 대시보드 5종 (자동 프로비저닝, [docker/grafana/provisioning/dashboards/](../docker/grafana/provisioning/dashboards/)):
- `diconai-overview.json` — 시스템 전반
- `diconai-sensor.json` — 센서 데이터 수신 / 처리
- `diconai-alarm.json` — 알람 발생 / 처리
- `diconai-power-ai.json` — AI 분석 처리 시간 / 성공률
- `diconai-db-redis.json` — DB · Redis 상태

전용 로그 명령:
```bash
make logs-err      # 에러만
make logs-alarm    # 알람 워커
make logs-ai       # AI 분석
make logs-retention  # 보존 정책 실행
```

## 5. 백업 절차

> **현재 자동화 미구현** — 수동 절차. 정기 백업은 Phase 2 항목.

PG 덤프:
```bash
docker compose exec postgres pg_dump -U diconai diconai > backup_$(date +%Y%m%d).sql
```

복원:
```bash
docker compose exec -T postgres psql -U diconai diconai < backup_YYYYMMDD.sql
```

기존 백업 파일: [backup/data_dump_2026_05_22_v2_clean.json](../backup/) (SQLite 시절 마지막 덤프).

## 6. 장애 대응 Runbook

상세 사례: [docs/troubleshooting.md](troubleshooting.md). 핵심 시나리오 3개:

| 증상 | 확인 명령 | 1차 조치 |
|---|---|---|
| **Redis 죽음** | `make ps` → redis Down · `redis-cli ping` 실패 | `docker compose restart redis` — List 큐 데이터는 appendonly로 유지 |
| **DB 응답 없음** | `pg_isready` 실패 · drf 500 | `docker compose logs postgres` → 락/디스크 확인. PRAGMA 진단부터 |
| **Celery 적체** | `celery inspect ping` 응답 지연 · Grafana 대기 작업 증가 | 워커 재시작 `make restart s=celery-worker-alarm`, 알람/메트릭 큐 분리 확인 |

## 어떻게 구현했는가

- **핫리로드**: 소스 볼륨 마운트 + gunicorn `--reload` + DEBUG WhiteNoise 3단 결합 (docker-compose.yml 주석 참조)
- **헬스체크 의존성**: `service_healthy` 그래프로 drf→fastapi→celery 순차 기동 보장
- **메트릭 격리**: `prometheus_multiproc/{drf,celery-alarm,celery-metric}` 서브디렉토리로 worker 파일 충돌 방지

## 증빙자료 추천

| 증빙 | 위치 / 캡처 대상 | 추천 제목 |
|---|---|---|
| **`docker compose ps`** | 7-서비스 모두 healthy 상태 출력 | `[그림 1] Docker Compose 기반 서비스 실행 결과` |
| **`make help`** | 명령어 카탈로그 일부 캡처 | `[그림 2] Makefile 단축 명령어` |
| **Grafana 대시보드 5종** | 각 대시보드 메인 화면 | `[그림 3~7] Grafana 운영 대시보드` |
| **Prometheus targets UP** | http://localhost:9090/targets 캡처 | `[그림 8] 메트릭 수집 대상 상태` |
| **헬스체크 의존성 다이어그램** | docker-compose.yml 주석 기반 작성 | `[그림 9] 서비스 의존성 그래프` |
| **백업 실행 로그** | `pg_dump` 명령 + 결과 파일 크기 | `[그림 10] PG 백업 절차 실행 결과` |

## 참고 문서

- 환경 세팅 단계별: [docs/infra/docker_setup.md](infra/docker_setup.md)
- 환경변수 상세: [docs/env-guide.md](env-guide.md)
- Redis/Celery 운영: [docs/infra/redis-celery-guide.md](infra/redis-celery-guide.md)
- 장애 대응: [docs/troubleshooting.md](troubleshooting.md)
