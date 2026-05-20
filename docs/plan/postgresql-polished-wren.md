# PostgreSQL 전환 — 코드 레벨 검토 문서 작성

## Context

기존 `skill/plan/db-stabilization-postgres-migration.md`는 4주 일정과 단계별 액션 위주의 **로드맵**이다. 시점 기준은 명확하지만, 막상 W2(5/21~5/27) PG 전환 작업에 들어갈 때 *어느 파일의 어느 라인이 깨질 수 있는지*, *마이그레이션 직전 어떤 SQL로 사전 검증해야 하는지*는 빠져있다.

ARIMA 도입(시연 후 sprint)을 앞두고 SQLite로는 한계가 분명한 상황에서, 전환 실패 → 시연일(D-31) 위협이 가장 큰 risk다. 본 plan은 **로드맵과 분리된 "코드 레벨 검토·체크리스트" 문서를 신설**해, 전환 당일 보면서 작업할 수 있는 단위로 위험 지점을 모두 적재하는 것이 목표다.

검토 결과 단순 호환성 문제가 아닌 **데이터 정합성 위험**(NaN/Inf, naive datetime, Boolean NULL 혼용, FK 고아, partial unique 위반, UniqueConstraint 중복)이 8건 식별됐다 — 이건 사전 검증 SQL 없이 진입하면 마이그레이션 도중 실패한다.

---

## 산출물

**신규 파일:** [postgres-migration-code-review.md](postgres-migration-code-review.md) (skill/plan/ 하위)

- 위치: 기존 plan 컨벤션([[plan-storage-convention]])과 동일하게 `skill/plan/` 하위
- 위상: `db-stabilization-postgres-migration.md`의 **W2 단계 진입 시 동반 체크리스트**로 참조
- 기존 plan의 W2 섹션에 한 줄 추가: `> 작업 시 [postgres-migration-code-review.md](postgres-migration-code-review.md) 체크리스트 동반 참조.`

---

## 검토 문서 골격 (작성할 내용)

### 1. 사전 검증 SQL 모음 (SQLite 상태에서 먼저 돌릴 것)

전환 전 SQLite에서 돌려서 데이터 정합성을 확보하는 SELECT 모음. 결과 0건이 되면 그 위험은 통과.

```sql
-- 1.1 power_data PowerData NaN/Infinity (PG에서 INSERT 실패)
SELECT COUNT(*) FROM power_data WHERE value != value OR value = 1e999 OR value = -1e999;

-- 1.2 gas_data 9개 가스 컬럼 NaN/Inf (co, h2s, ch4, co2, o2, no2, so2, hcn, h2)
SELECT COUNT(*) FROM gas_data
WHERE co != co OR h2s != h2s OR ch4 != ch4 OR co2 != co2 OR o2 != o2
   OR no2 != no2 OR so2 != so2 OR hcn != hcn OR h2 != h2;

-- 1.3 PowerData UniqueConstraint 위반 후보
SELECT power_device_id, channel, data_type, measured_at, COUNT(*) c
FROM power_data
GROUP BY power_device_id, channel, data_type, measured_at HAVING c > 1;

-- 1.4 Threshold UniqueConstraint
SELECT group_id, measurement_item, facility_id, COUNT(*) c
FROM facilities_threshold
GROUP BY group_id, measurement_item, facility_id HAVING c > 1;

-- 1.5 MLModel UniqueConstraint (sensor_type, version)
-- 1.6 DataRetentionPolicy UniqueConstraint (device_type, data_category)
-- 1.7 SafetyStatus UniqueConstraint (session, check_item)
-- 1.8 CustomUser email 부분 UNIQUE (email IS NOT NULL AND email != '')

-- 1.9 FK 고아 — PROTECT 모델 우선
SELECT COUNT(*) FROM power_data p
LEFT JOIN facilities_powerdevice d ON p.power_device_id = d.id WHERE d.id IS NULL;
-- gas_data, worker_position, event 등 동일 패턴

-- 1.10 partial UniqueConstraint 위반
-- vr_training_content: (target_type, target_facility) is_active=True 중복
-- safety_checklist_revision: (facility, is_active=True) 중복
```

→ 각 쿼리에 **위반 발견 시 처리 SOP**도 함께 적시 (행 삭제 / 데이터 보정 / 마이그 직전 임시 데이터 정리).

### 2. 코드 레벨 위험 카탈로그

탐색에서 찾은 모든 위험 지점을 한 표로:

| # | 영역 | 파일:라인 | 위험도 | 조치 |
|---|---|---|---|---|
| 1 | settings DATABASES OPTIONS | drf-server/config/settings.py:125-128 | 低 | 이미 ENGINE 분기 보호. 확인만. |
| 2 | SQLite PRAGMA 시그널 | drf-server/apps/core/sqlite_pragmas.py:19 | 低 | vendor 가드 있음, no-op 자동. |
| 3 | docker-compose DATABASE_URL 하드코딩 | docker-compose.yml:33,101,128 | 高 | sqlite:// 3곳 → `${DATABASE_URL}` 환경변수 참조로 통일. .env.docker만 수정해 양 DB 전환. |
| 4 | db.sqlite3 볼륨 마운트 | docker-compose.yml:46,113 | 中 | PG 사용 시 무해하지만 불필요. profile 분리 또는 조건부 마운트 검토. |
| 5 | Makefile db-pragma/db-counts | Makefile:205-245 | 中 | PG용 분기 추가 (pg_stat, pg_database_size) 또는 별도 타겟. |
| 6 | DateTimeField naive 혼재 | apps/monitoring/models/power_data.py:62-63 외 | 高 | dumpdata→loaddata는 자동 변환. 단, raw 이관 시 검증 SQL 추가. |
| 7 | BooleanField null=True | apps/facilities/models/devices.py:113,201 | 中 | SQLite의 -1/0/1 혼용 검증. |
| 8 | FloatField NaN/Inf | apps/monitoring/models/power_data.py:39, gas_data.py:42-50, alarm_record.py:99-101, ml_anomaly_result.py:49 | 高 | §1.1-1.2 SQL 먼저, 0건 확인 후 진행. |
| 9 | FK 고아 (PROTECT) | apps/monitoring/models/power_data.py:32, facilities/devices.py:31 | 高 | §1.9 SQL. PG는 항상 강제. |
| 10 | UniqueConstraint 중복 가능성 | §1.3-1.8 모델 6종 | 高 | 전수 검증 후 진행. |
| 11 | partial UniqueConstraint | training/vr_training_content.py, safety/safety_checklist_revision.py | 中 | §1.10 SQL. |
| 12 | JSONField 변환 | alerts/alert_policy.py:51-57, ml/ml_model.py:51-57 외 6곳 | 低 | SQLite TEXT → PG jsonb 자동. dumpdata→loaddata 통과 시 OK. 시연 후 jsonb 인덱스 도입 검토. |
| 13 | RunPython 마이그레이션 86개 | apps/*/migrations/ | 中 | 신규 PG DB는 `migrate` 1회로 모두 적용 — 큰 RunPython 없으므로 빠를 것. ml/0001만 새 환경에서 시간 측정. |
| 14 | Celery long-running tasks | apps/operations/tasks/data_retention_task.py | 中 | PG `statement_timeout` + `idle_in_transaction_session_timeout` 설정. CONN_MAX_AGE 명시. |
| 15 | celery worker concurrency=2 | docker-compose.yml:98 | 低 | PG는 multi-writer OK. 시연 전 그대로 유지, 시연 후 4로 증설 검토. |
| 16 | gunicorn workers=1 | docker-compose.yml:59 | 中 | 개발 핫리로드 유지 위해 1 고정. PG로 가도 변경 불필요 (threads=4로 충분). |
| 17 | psycopg 드라이버 | drf-server/requirements.txt | 低 | psycopg2-binary==2.9.11 기 설치. 시연 전 신규 추가 없으면 그대로. |
| 18 | FastAPI DB 접근 | fastapi-server/* | — | DRF REST로만 통신 → **PG 전환과 무관**. 변경 없음. |

### 3. 데이터 이관 범위 — **추천 안**

**옵션 A (영구 계층만 이관, Raw는 새로 쌓기)를 추천**한다. 이유:

1. **이관 비용 vs 가치 불균형**: power_data는 truncate 후 401K행. 14일 보존정책상 W2 종료(5/27) 후 W3~W4 동안 자연 갱신되어 이관해도 시연일까지 데이터가 거의 회전한다.
2. **사전 검증 SQL 부담 격감**: §1.1, 1.2, 1.3, 1.9의 검증 대상이 Raw 25M행이 아니라 영구 계층(AlarmRecord/Event 수만~수십만 행)으로 축소된다. 위반 발견 시 보정 작업도 가벼워진다.
3. **시연 시 "빈 차트" 우려 해소책**: 시연 D-3(6/11)부터 더미 송출 가동 → 시연 당일 시점 14일 보존 윈도우 안에 자연스러운 시계열 채워짐. 이건 ARIMA 학습 데이터 부족과는 별개 (학습 데이터는 parquet에서 로드).
4. **AlarmRecord/Event 이관은 필수**: 시연 시 "지난 N주 알람 이력 N건" 표시되어야 신뢰감 있음. 이건 영구 계층이라 이관 범위에 포함됨.

**이관 대상 (영구 계층):** AlarmRecord, AlarmEvent, Event, EventLog, IntegrationLog, AppLog, SystemLog, CustomUser, Company, Department, Facility, GasSensor, PowerDevice, Threshold, AlertPolicy, DataRetentionPolicy, MLModel, SafetyChecklist, VrTrainingContent (그 외 마스터성 테이블).

**이관 제외 (Raw):** PowerData, GasData, WorkerPosition, MLAnomalyResult(이건 검토 필요 — 운영자에게 "지난 이상탐지 결과 5건" 보이고 싶으면 포함).

**이관 방식:** `dumpdata --natural-foreign --natural-primary --exclude` 패턴. 큰 테이블 제외하고 JSON 덤프 → PG에 `loaddata`. M:N 중간 테이블은 자동 처리.

### 4. PG 컨테이너 설정 권장값 (WSL2 개발 환경 기준)

```yaml
postgres:
  image: postgres:16-alpine
  shm_size: 256mb
  environment:
    POSTGRES_DB: diconai
    POSTGRES_USER: diconai
    POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
  command:
    - postgres
    - -c shared_buffers=256MB
    - -c effective_cache_size=1GB
    - -c work_mem=16MB
    - -c maintenance_work_mem=128MB
    - -c statement_timeout=60s
    - -c idle_in_transaction_session_timeout=30s
    - -c max_connections=50
  volumes:
    - postgres_data:/var/lib/postgresql/data
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U diconai"]
    interval: 10s
```

**선정 근거 (검토 문서에 단락으로 작성):**
- shared_buffers 256MB: WSL2 가용 메모리 보수. 운영 시 RAM의 25%로 상향.
- statement_timeout 60s: retention의 대량 DELETE 보호 (현재 36.5ms 측정값 대비 충분히 여유).
- max_connections 50: gunicorn 4 thread × 1 worker + celery 2 + beat 1 + admin = 8 동시, 여유 6배.

### 5. 전환 당일 작업 순서 (Runbook)

W2 본 진입 시 이 문서 보면서 따라가도록 단계별 명령 + 검증 포인트 정리.

1. **D-1**: §1 SQL 전수 실행, 위반 0건 확인
2. **D-Day 09:00**: 컨테이너 정지 + SQLite 최종 백업 (`db.sqlite3.pg_switch_2026_05_21`)
3. **09:30**: postgres 서비스 추가, `.env.docker` DATABASE_URL 교체
4. **10:00**: `docker compose up -d postgres` → healthcheck 대기
5. **10:15**: `make migrate` 실행 (시간 측정)
6. **10:30**: `dumpdata --exclude=monitoring.powerdata --exclude=...` 출력
7. **10:45**: `loaddata` 적용 + rowcount 양쪽 비교
8. **11:00**: 더미 1종(전력만) 30분 송출, fastapi log timeout 0건 확인
9. **11:30**: 더미 3종 동시 송출, Grafana p99 < 500ms 확인
10. **12:00**: 시연 시나리오 1회 dry-run

각 단계 실패 시 롤백 명령(`.env.docker` DATABASE_URL을 sqlite:///로 복귀 → `docker compose restart drf celery-worker celery-beat`)을 같이 적시.

### 6. PG 전환 후 새로 켜지는 가능성 (시연 후 도입 후보)

- jsonb GIN 인덱스 (AlertPolicy.target_user_types, MLModel.params_json 쿼리 가속)
- timestamptz + 시계열 인덱스 (BRIN 검토)
- TimescaleDB hypertable (별도 plan 영역)
- pg_stat_statements + postgres_exporter (관찰성 강화)

→ 본 문서에는 "시연 후 검토" 섹션으로 정리만, 도입은 별도 plan.

---

## 검증 방법

1. **검토 문서 작성 후 사용자 1차 리뷰** — 빠진 코드 위험 있는지 확인
2. **§1 SQL을 실제 현재 SQLite에서 dry-run**해 위반 건수 측정 → 검토 문서에 "현재 위반 0건/N건" 부기
3. **데이터 이관 옵션 A의 dumpdata 출력 사이즈 사전 측정** (영구 계층만, 추정 ~50MB 이하)
4. **W2 진입 시 Runbook 한 번 dry-run** (PG 컨테이너만 띄워서 1~5단계까지)

---

## 기존 plan과의 연계

기존 [db-stabilization-postgres-migration.md](db-stabilization-postgres-migration.md) **3단계(W2) PostgreSQL 전환** 섹션에:

```markdown
> ⚠️ 본 단계 진입 시 [postgres-migration-code-review.md](postgres-migration-code-review.md) 동반 참조 — 코드 레벨 위험 카탈로그 18건 + 사전 검증 SQL + Runbook 포함.
```

한 줄 추가. 기존 plan의 일정·범위·트레이드오프 기술은 그대로 유지.

---

## 미해결 질문 (검토 문서 작성 중 확정 필요)

1. MLAnomalyResult 이관 여부 — 운영자에게 과거 이상탐지 결과 표시가 시연 시나리오에 포함되는지
2. PG 비밀번호 관리 — `.env.docker` 평문 vs Docker secret (시연 환경은 평문도 무방)
3. postgres_data 볼륨 백업 정책 — pg_dump 일일 cron vs WAL 아카이빙 (시연 전엔 일일 dump로 충분)
