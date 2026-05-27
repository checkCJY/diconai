# 트러블슈팅 · 사후 보완 가이드

> 개발·운영 중 발생한 실제 사례와 해결 과정. 신규 팀원이 같은 문제를 만났을 때 1차 진단 경로.

---

## 진단 원칙

1. **DB 문제는 PRAGMA부터** — 락·성능 권장조치 내기 전에 `journal_mode` / `busy_timeout` / 파일 크기 확인 (2026-05-14 WAL 미확인 자기정정 사례에서 도출)
2. **알람 흐름은 코드가 truth source** — `skill/알람*.md`의 WS broadcast 섹션은 옛 5초 폴링 설계. 현재는 Redis BRPOP 즉시
3. **동작 중인 시스템에 갭 분석 금지** — 인접 시스템이 잘 돌면 거기서 멈춤 (2026-05-27 retention 벌집 사례)

## 실제 사례

### 1. SQLite 락 + 12GB 파일 폭증 (2026-05-14)

**증상**: drf 500 응답, 쓰기 대기, db.sqlite3 12GB 도달
**원인**: SQLite 단일 라이터 락 + raw 데이터 무제한 누적
**조치**:
1. 임시: `journal_mode=WAL` + `busy_timeout` 조정
2. 항구: PG16 컨테이너 전환 (2026-05-22 완료)
3. 보존정책: 3계층 (Raw 7~14일 / Event 영구 / ML 별도)

상세: [docs/incidents/2026_05_14_sqlite_lock_and_db_bloat.md](incidents/2026_05_14_sqlite_lock_and_db_bloat.md) · [docs/migration/2026-05-22-postgres.md](migration/2026-05-22-postgres.md)

### 2. 시연 알람 안정화 + cooldown bypass (PR #94)

**증상**: 위험도 격상 시 첫 알람 후 cooldown으로 후속 알람 차단
**원인**: 단일 cooldown 규칙이 risk_level 변화를 무시
**조치**: 위험도 격상(WARNING→DANGER)에 한해 cooldown bypass. 60s TTL 단축으로 `_AckStore` 가설 해소

세션 상세: [docs/refactor/2026_05_26_alarm_demo_session.md](refactor/2026_05_26_alarm_demo_session.md)

### 3. 알람 팝업 Docker 환경 깨짐

**증상**: 로컬 dev에서는 보였던 알람 팝업이 컨테이너에서 미표시
**원인**: WebSocket URL의 host 분기 누락 (컨테이너 내부 vs 브라우저)
**조치**: `FRONTEND_WS_BASE_URL`을 host 기준 `ws://localhost:8001`로 분리

상세: [docs/infra/troubleshooting_alarm_popup_docker.md](infra/troubleshooting_alarm_popup_docker.md)

### 4. INTERNAL_SERVICE_TOKEN 불일치로 가스 더미 502

**증상**: fastapi 가스 더미가 모두 HTTP 502, drf 401 Unauthorized
**원인**: `.env.docker`의 `INTERNAL_SERVICE_TOKEN`과 `DRF_SERVICE_TOKEN`을 다르게 채움
**조치**: 두 값을 반드시 동일하게. 자세히: [docs/infra/docker_setup.md §10 ⑥](infra/docker_setup.md)

### 5. Docker DB 마이그레이션 30글자 초과 (commit 6a0ea47)

**증상**: 마이그레이션 실행 시 인덱스명 길이 제한 초과로 에러
**원인**: Event 인덱스 자동 생성명이 PG 식별자 제한(63자) 근접 + 마이그레이션 직접 명명 미설정
**조치**: 마이그레이션 이름 명시적으로 단축

## 구간별 사후 보완 기준표

| 장애 구간 | 관찰 지표 | 확인 자료 | 보완 방향 |
|---|---|---|---|
| API 수신 | 요청 수, 에러율 | fastapi 로그, Grafana sensor 대시보드 | endpoint, payload, 인증 토큰 확인 |
| DB 저장 | 저장 건수 | `make logs s=drf`, Admin · DBeaver | validation, 필드명, DB 연결 |
| Celery 작업 | 작업 성공/실패 | `make logs-alarm`, `make logs-ai` | Redis 연결, worker 실행 상태 |
| AI 분석 | MLAnomalyResult 생성 여부 | `MLAnomalyResult` 테이블 | feature 생성, 모델 입력값 포맷 |
| 알람 생성 | AlarmRecord 생성 여부 | `AlarmRecord` 테이블, alarm 워커 로그 | risk_level 기준, cooldown 규칙 |
| WS 반영 | broadcast 메시지 | 브라우저 Network → WS Messages | `alarm_flush_loop` 동작, JWT 검증 |
| 처리 지연 | Grafana 응답 시간 | overview · db-redis 대시보드 | 비동기 분리, DB 인덱스, 큐 분산 |

## 시연 직전 점검

[docs/templates/self-check.md](templates/self-check.md) 사용 — 시연 1~2일 전에 항목별 체크.

## 증빙자료 추천

| 증빙 | 위치 / 캡처 대상 | 추천 제목 |
|---|---|---|
| **SQLite 사고 보고서** | [docs/incidents/2026_05_14_sqlite_lock_and_db_bloat.md](incidents/2026_05_14_sqlite_lock_and_db_bloat.md) | `[그림 1] SQLite 락·폭증 사고 분석` |
| **PG 전환 비교표** | [docs/migration/2026-05-22-postgres.md](migration/2026-05-22-postgres.md) 의 Before/After 표 | `[표 1] DB 전환 전후 성능 비교` |
| **알람 시연 안정화 commit** | git log — 7ff6c94, 1517642, 6a0ea47 등 | `[그림 2] 핵심 트러블슈팅 commit 이력` |
| **에러 로그 샘플** | `make logs-err` 결과 | `[그림 3] 운영 중 에러 로그 발췌` |
| **사후 보완표** | 본 문서 "구간별 사후 보완 기준표" | `[표 2] 장애 구간별 보완 가이드` |
| **개선 전후 비교** | 동기 → Celery 분리 / SQLite → PG / 5초 폴링 → BRPOP | `[표 3] 구조 개선 전후 비교` |

## 참고 문서

- 사고 이력: [docs/incidents/](incidents/)
- 코드리뷰 결과: [docs/codereviews/](codereviews/)
- 단일 기능 변경 이력: [docs/changelog/single_features/](changelog/single_features/)
- 시연 안정화 세션: [docs/refactor/2026_05_26_alarm_demo_session.md](refactor/2026_05_26_alarm_demo_session.md)
