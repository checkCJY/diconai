# 시스템 아키텍처

> 평가자/신규 팀원이 1페이지로 전체 구조를 파악하기 위한 문서.
> 상세는 [docs/specs/directory-structure.md](specs/directory-structure.md) · [docs/infra/docker_setup.md](infra/docker_setup.md) 참조.

---

## 무엇을 수행하는가

산재 예방 통합 관제 시스템 — 가스/전력/작업자 위치 센서 데이터를 실시간으로 수집·저장·분석하고, 임계치 초과·이상 패턴 감지 시 알람을 즉시 운영자 화면에 전달합니다.

데이터 흐름:

```
IoT 센서
   ↓ HTTP POST
fastapi-server (수신 · 검증)
   ↓ 내부 API
drf-server (DB 영속성 · 위험 판단 · 알람 생성)
   ↓ Celery task
AI 분석 (IF / ARIMA / Z-score / Change Point)
   ↓ 결과 저장
PostgreSQL ← → Redis (브로커 · 알람 큐)
   ↓ Celery → fastapi /internal/alarms/push/
fastapi WebSocket broadcast
   ↓
브라우저 대시보드
   ↑
Prometheus / Grafana ← 양 서버 /metrics
```

## 왜 이 구조인가

| 결정 | 이유 |
|---|---|
| **DRF + FastAPI 2서버 분리** | DRF는 인증·DB 영속성·HTML 렌더링 (동기 모델 최적), FastAPI는 센서 수신·WebSocket broadcast (async 최적). 책임 분리로 한쪽 부하가 다른쪽에 전이되지 않음 |
| **Redis Stream(XADD / replica별 독립 XREAD 커서, fan-out)** | Pub/Sub는 구독자 없을 때 메시지 유실 — Stream은 fastapi 재시작 중에도 알람이 적체. BRPOP은 경쟁 소비라 다중 replica fan-out 불가 — replica별 독립 XREAD 커서로 모든 replica가 모든 알람 수신. 상세: [docs/infra/redis-celery-guide.md](infra/redis-celery-guide.md) |
| **Celery 큐 alarm/metric 분리** | 알람 태스크가 주기적 메트릭 수집과 같은 워커를 쓰면 알람 지연 발생. 큐 분리로 알람 우선순위 보장. 실제 분리 코드: [docker-compose.yml:154-220](../docker-compose.yml#L154-L220) |
| **PostgreSQL (SQLite 폐기)** | 2026-05-14 SQLite 락 + 12GB 폭증 사고. PG16 컨테이너로 전환. 상세: [docs/migration/2026-05-22-postgres.md](migration/2026-05-22-postgres.md) |
| **K8s manifest 미적용** | 5개월차 팀의 위험 관리 — 다중 인스턴스가 필요한 시점에 도입. Compose로 시연·운영 충분. 설계 자료는 별도 보관 |

## 어떻게 구현했는가

Docker Compose 구조 (10 컨테이너):

| 서비스 | 포트 | 책임 |
|---|---|---|
| `drf` | 8000 | Django + DRF — 인증, 대시보드 HTML, REST API, 알람 생성 |
| `fastapi` | 8001 | 센서 수신, WebSocket broadcast, 알람 push 엔드포인트 |
| `postgres` | 5432 | 영속 저장소 (PG16, shared_buffers 256MB) |
| `redis` | 6379 | Celery 브로커 + WS 알람 Stream(`diconai:ws:alarms`, XADD/XREAD) |
| `redis_exporter` | 9121 | Redis 메트릭 익스포터 (Prometheus scrape) |
| `celery-worker-alarm` | - | alarm 큐 전용 (`-Q alarm`, concurrency=2) |
| `celery-worker-metric` | - | metric 큐 전용 (`-Q metric`, concurrency=1) |
| `celery-beat` | - | 주기 스케줄러 |
| `prometheus` / `grafana` | 9090 / 3000 | 메트릭 수집 + 6개 대시보드 |

Django 앱 레이어 ([drf-server/apps/](../drf-server/apps/)):
- `models/` — DB 스키마
- `selectors/` — 읽기 전용 조회
- `services/` — 비즈니스 로직 · 트랜잭션
- `serializers/` — API I/O 변환·검증
- `views/` — service 호출만, 로직 금지

핵심 앱:
- `monitoring` — 가스/전력 데이터 수신·저장
- `alerts` — 알람 생성·이력 (`AlarmRecord`, `Event`, `EventLog`, `EventAcknowledgement`)
- `ml` — AI 분석 모델·결과 (`MLModel`, `MLAnomalyResult`)
- `positioning` — 작업자 위치
- `facilities` — 설비·디바이스
- `accounts` — 사용자·권한·로그인 로그

## 증빙자료 추천

> 본 문서에 첨부 / 또는 `docs/img/`에 PNG 추가 후 참조.

| 증빙 | 위치 / 캡처 대상 | 추천 제목 |
|---|---|---|
| **전체 아키텍처 다이어그램** | [docs/img/시스템구조도.png](img/시스템구조도.png) — 기존 파일 활용 | `[그림 1] 디코나이 통합 관제 플랫폼 전체 아키텍처` |
| **Docker Compose 실행 결과** | `docker compose ps` 출력 (7-서비스 모두 healthy) | `[그림 2] Docker Compose 기반 서비스 실행 결과` |
| **데이터 흐름 시퀀스** | 본 문서 상단 흐름도 → Mermaid 또는 Lucidchart 변환 | `[그림 3] 센서 → DB → AI → 알람 → 대시보드 시퀀스` |
| **Celery worker 로그** | `make logs s=celery-worker-alarm` 결과 캡처 | `[그림 4] Celery alarm 큐 처리 로그` |
| **Prometheus target 화면** | http://localhost:9090/targets (모든 target UP) | `[그림 5] Prometheus 메트릭 수집 상태` |
| **Grafana overview 대시보드** | [docker/grafana/provisioning/dashboards/diconai-overview.json](../docker/grafana/provisioning/dashboards/diconai-overview.json) 자동 프로비저닝 화면 | `[그림 6] Grafana overview 대시보드` |

## 참고 문서

- 디렉토리 구조 전체: [docs/specs/directory-structure.md](specs/directory-structure.md)
- URL 전체 표: [docs/specs/url-structure.md](specs/url-structure.md)
- Redis/Celery 상세: [docs/infra/redis-celery-guide.md](infra/redis-celery-guide.md)
- Docker 운영: [docs/infra/docker_setup.md](infra/docker_setup.md)
