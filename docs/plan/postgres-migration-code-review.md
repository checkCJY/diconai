# PostgreSQL 전환 — 코드 레벨 검토·체크리스트

> **위상:** [db-stabilization-postgres-migration.md](db-stabilization-postgres-migration.md) **W2 단계 동반 체크리스트**.
> **모체 plan:** [postgresql-polished-wren.md](postgresql-polished-wren.md) (산출물 정의).
> **작성:** 2026-05-22 (W2 진입 2일차) — 라인 번호는 매번 변하므로 `grep -n` 명령어를 함께 적었다. 라인은 참고용, 패턴 일치가 진실 공급원.

---

## 0. 사용법

W2 본 진입 시 이 문서를 펴놓고 다음 순서로 작업한다:
1. **§1 사전 검증 SQL** 전수 실행 → 위반 0건 확인 (전환 진입 게이트)
2. **§2 위험 카탈로그 18건** 영향도 확인 (이미 인지하고 있는지)
3. **§3 데이터 이관 범위** 옵션 (a)/(b) 중 선택
4. **§4 PG 컨테이너 설정** 적용
5. **§5 Runbook** 시간순 따라가기
6. **§6 시연 후 도입 후보** 별도 plan 화

각 SQL/명령에 **위반 발견 시 처리 SOP** 를 적어뒀다. 모르겠으면 그 줄을 따라 정리하면 된다.

---

## 1. 사전 검증 SQL 모음 (W2 진입 D-1 실행)

목표: 현재 SQLite 데이터가 PG로 옮겨가도 깨지지 않는지 사전 점검. 결과 **0건 확인 시 통과**, 1건이라도 나오면 SOP 따라 정정 후 재실행.

**실행 환경:** host 의 `sqlite3` 3.45.1 + read-only URI (`file:drf-server/db.sqlite3?mode=ro`). 활성 쓰기와 충돌 없음. 컨테이너 안에서 실행도 가능하나, host 가 더 빠르고 무해.

**테이블명 주의:** 본 프로젝트는 Django 기본 `<app>_<modelname>` 컨벤션을 따르지 않고 단순화된 단수형 테이블명을 사용한다 (`alarm_record`, `ml_model`, `threshold`, `custom_user`, `safety_status`, `data_retention_policy`, `vr_training_content`, `safety_checklist_revision`, `ml_anomaly_result` 등). 모델 정의의 `Meta.db_table` 참조.

### 2026-05-22 실측 결과 — 14건 전수 0건 통과 ✓

| # | 검증 | 위반 | 비고 |
|---|---|---|---|
| 1.1 | power_data NaN/Inf | 0 | |
| 1.2 | gas_data NaN/Inf (9종) | 0 | |
| 1.3 | power_data unique (4튜플) | 0 | unique constraint 보호 |
| 1.4 | threshold unique (group_id, measurement_item, facility_id) | 0 | |
| 1.5a | ml_model unique (sensor_type, algorithm, sensor_identifier, version) | 0 | |
| 1.5b | ml_model partial unique is_active (sensor_type, algorithm, sensor_identifier) | 0 | |
| 1.6 | data_retention_policy unique (device_type, data_category) | 0 | |
| 1.7 | safety_status unique (session_id, check_item_id) | 0 | |
| 1.8 | custom_user email partial unique | 0 | |
| 1.9a | power_data FK 고아 (power_device) | 0 | |
| 1.9b | gas_data FK 고아 (gas_sensor) | 0 | |
| 1.9c | worker_position FK 고아 (facility) | 0 | |
| 1.10a | vr_training_content partial unique is_active | 0 | |
| 1.10b | safety_checklist_revision partial unique is_active | 0 | |
| 1.11 | ml_anomaly_result 행수 | **424,949** | 옵션 c 검토용 |

**행수 스냅샷:** power_data 9,285,120 / gas_data 44,151 / alarm_record 29,362 / event 441 / worker_position 44,098 / ml_anomaly_result 424,949. SQLite 파일 5.3GB.

**총 소요 시간:** 64초 (43.7s + 20.6s, 9.2M GROUP BY 두 건 포함). PG 전환 직전 재실행해도 1분 부담.

---

### 1.1 power_data NaN / Infinity (PG INSERT 실패 원인)

```sql
SELECT COUNT(*) FROM power_data
WHERE value != value OR value = 1e999 OR value = -1e999;
```

- **2026-05-22 실측:** 0건 ✓
- **SOP:** 1건 이상이면 `DELETE FROM power_data WHERE value != value OR value = 1e999 OR value = -1e999;` 후 재실행.

### 1.2 gas_data NaN / Infinity (실제 가스 9종)

가스 컬럼은 `co, h2s, co2, o2, no2, so2, o3, nh3, voc` ([gas_data.py](../../drf-server/apps/monitoring/models/gas_data.py) FloatField). 모체 plan 의 `ch4/hcn/h2` 는 잘못된 명세였음.

```sql
SELECT COUNT(*) FROM gas_data
WHERE co != co OR h2s != h2s OR co2 != co2 OR o2 != o2 OR no2 != no2
   OR so2 != so2 OR o3 != o3 OR nh3 != nh3 OR voc != voc;
```

- **2026-05-22 실측:** 0건 ✓
- **SOP:** 위와 동일 DELETE 패턴.

### 1.3 power_data UniqueConstraint 위반 후보

```sql
SELECT COUNT(*) FROM (
  SELECT power_device_id, channel, data_type, measured_at, COUNT(*) c
  FROM power_data
  GROUP BY power_device_id, channel, data_type, measured_at HAVING c > 1
);
```

- **2026-05-22 실측:** 0건 ✓ (9.2M GROUP BY, 20.6초 소요. `uq_power_data_device_channel_type_time` 인덱스 활용)
- **SOP:** 중복 발견 시 `id MIN` 만 남기고 나머지 DELETE.

### 1.4 threshold UniqueConstraint

실제 unique = `(group_id, measurement_item, facility_id)`.

```sql
SELECT COUNT(*) FROM (
  SELECT group_id, measurement_item, facility_id, COUNT(*) c
  FROM threshold
  GROUP BY group_id, measurement_item, facility_id HAVING c > 1
);
```

- **2026-05-22 실측:** 0건 ✓
- **SOP:** 중복 발견 시 가장 최신 `updated_at` 1개만 남기고 삭제. 운영자가 의도적으로 갱신했을 가능성이 있어 단순 첫번째만 남기지 말 것.

### 1.5 ml_model UniqueConstraint (4튜플 + partial)

실제 제약 2개:
- 일반 unique: `(sensor_type, algorithm, sensor_identifier, version)` ← `uq_ml_model_sensor_alg_id_version`
- partial unique: `(sensor_type, algorithm, sensor_identifier)` WHERE `is_active` ← `uq_ml_model_active_per_match_unit`

```sql
-- 1.5a 4튜플 unique
SELECT COUNT(*) FROM (
  SELECT sensor_type, algorithm, sensor_identifier, version, COUNT(*) c
  FROM ml_model
  GROUP BY sensor_type, algorithm, sensor_identifier, version HAVING c > 1
);

-- 1.5b is_active=True partial unique
SELECT COUNT(*) FROM (
  SELECT sensor_type, algorithm, sensor_identifier, COUNT(*) c
  FROM ml_model WHERE is_active = 1
  GROUP BY sensor_type, algorithm, sensor_identifier HAVING c > 1
);
```

- **2026-05-22 실측:** a 0건 / b 0건 ✓
- **SOP:** 5a 위반 시 학습 재실행 흔적 → 최신 `trained_at` 만 유지. 5b 위반 시 가장 최근 `trained_at` 1개만 `is_active=True` 유지.

### 1.6 data_retention_policy UniqueConstraint `(device_type, data_category)`

```sql
SELECT COUNT(*) FROM (
  SELECT device_type, data_category, COUNT(*) c
  FROM data_retention_policy
  GROUP BY device_type, data_category HAVING c > 1
);
```

- **2026-05-22 실측:** 0건 ✓
- **SOP:** 운영 백오피스 입력값이라 충돌 가능성 낮음. 위반 시 가장 최신 `updated_at` 유지.

### 1.7 safety_status UniqueConstraint `(session_id, check_item_id)`

```sql
SELECT COUNT(*) FROM (
  SELECT session_id, check_item_id, COUNT(*) c
  FROM safety_status
  GROUP BY session_id, check_item_id HAVING c > 1
);
```

- **2026-05-22 실측:** 0건 ✓
- **SOP:** 동일 session 의 동일 check_item 이 2 row 인 경우 가장 최신 `checked_at` 유지.

### 1.8 custom_user email partial UNIQUE

실제 partial unique 인덱스 존재: `uq_user_email_notnull` ON `(email)` WHERE `(email IS NOT NULL AND NOT (email = ''))`.

```sql
SELECT COUNT(*) FROM (
  SELECT email, COUNT(*) c FROM custom_user
  WHERE email IS NOT NULL AND email != ''
  GROUP BY email HAVING c > 1
);
```

- **2026-05-22 실측:** 0건 ✓
- **SOP:** 충돌 시 운영자 수동 결정 (계정 보존 가치 판단).

### 1.9 FK 고아 — PROTECT 모델 우선

PG는 FK 위반을 SQLite 보다 엄격히 검사. SQLite 에서 FK off 로 삭제됐던 잔존 row 가 있을 수 있다.

```sql
-- 1.9a power_data → power_device
SELECT COUNT(*) FROM power_data p
LEFT JOIN power_device d ON p.power_device_id = d.id WHERE d.id IS NULL;

-- 1.9b gas_data → gas_sensor
SELECT COUNT(*) FROM gas_data g
LEFT JOIN gas_sensor s ON g.gas_sensor_id = s.id WHERE s.id IS NULL;

-- 1.9c worker_position → facility (NOT NULL FK)
SELECT COUNT(*) FROM worker_position w
LEFT JOIN facility f ON w.facility_id = f.id WHERE f.id IS NULL;
```

- **2026-05-22 실측:** a 0건 / b 0건 / c 0건 ✓
- **SOP:** 위반 시 해당 row 삭제. 부모 없는 시계열·위치는 UI 에서도 표시 불가.

### 1.10 Partial UniqueConstraint 위반

실제 partial unique 인덱스:
- `uq_vr_active_target` ON `vr_training_content (target_type, target_facility_id)` WHERE `is_active`
- `uq_revision_facility_active` ON `safety_checklist_revision (facility_id)` WHERE `is_active`

```sql
-- 1.10a vr_training_content
SELECT COUNT(*) FROM (
  SELECT target_type, target_facility_id, COUNT(*) c
  FROM vr_training_content WHERE is_active = 1
  GROUP BY target_type, target_facility_id HAVING c > 1
);

-- 1.10b safety_checklist_revision
SELECT COUNT(*) FROM (
  SELECT facility_id, COUNT(*) c
  FROM safety_checklist_revision WHERE is_active = 1
  GROUP BY facility_id HAVING c > 1
);
```

- **2026-05-22 실측:** a 0건 / b 0건 ✓
- **SOP:** 활성 row 가 둘 이상이면 가장 최신 `updated_at` 1개만 `is_active=True` 유지, 나머지는 `is_active=False` UPDATE. **삭제 금지** (이력 보존).

### 1.11 ml_anomaly_result 행수 카운트 (옵션 c 결정 보조)

```sql
SELECT COUNT(*) FROM ml_anomaly_result;
```

- **2026-05-22 실측:** **424,949 행**
- **해석:** dumpdata 추정 사이즈 ~200MB (~500 bytes/row × 424K). §3 옵션 c "일단 제외, SQLite 백업에서 추후 추가" 가 적정. 시연 D-7 까지 보관 의무는 SQLite 파일 백업으로 충족.

---

## 2. 코드 레벨 위험 카탈로그 18건

라인 번호는 grep 결과 기준. 파일 헤더 주석이 추가되면 ±5줄 이동할 수 있으므로 **패턴 검색이 진실 공급원**.

| # | 영역 | 위치 (grep 패턴) | 위험도 | 조치 |
|---|---|---|---|---|
| 1 | settings DATABASES OPTIONS | `drf-server/config/settings.py` ENGINE 분기 (`sqlite3` 가드 안 transaction_mode/timeout) | 低 | ENGINE 분기 보호되어 있어 PG 시 자동 skip. 확인만. |
| 2 | SQLite PRAGMA 시그널 | `drf-server/apps/core/sqlite_pragmas.py` (`connection.vendor != "sqlite": return`) | 低 | vendor 가드 있음, PG 시 no-op. |
| 3 | docker-compose DATABASE_URL 하드코딩 3곳 | `docker-compose.yml` 의 `DATABASE_URL: sqlite:////app/db.sqlite3` 3건 (drf / celery-worker / celery-beat) | 高 | 3곳 → `${DATABASE_URL}` 환경변수 참조로 통일. `.env.docker` 만 수정해 양 DB 전환 가능하게. |
| 4 | db.sqlite3 볼륨 마운트 2곳 | `docker-compose.yml` 의 `./drf-server/db.sqlite3:/app/db.sqlite3` | 中 | PG 사용 시 무해하지만 불필요. profile 분리(`--profile sqlite`) 또는 조건부 마운트 검토. |
| 5 | Makefile db-pragma / db-counts | `Makefile` 의 `db-pragma:` / `db-counts:` 타겟 (현재 SQLite PRAGMA / table_info 전용) | 中 | PG 분기 추가: `pg_stat_database`, `pg_database_size()`, `information_schema.tables`. 또는 `db-pragma-pg` 별도 타겟. |
| 6 | DateTimeField naive 혼재 | `monitoring/models/power_data.py` `measured_at = models.DateTimeField()` 외 다수 | 高 | `dumpdata→loaddata` 는 ISO 문자열을 자동 변환. raw INSERT 이관 시에만 timestamptz 강제 필요. **옵션 (a)/(b) 어느 쪽이든 자동 변환 신뢰 OK**. |
| 7 | BooleanField null=True | `facilities/models/devices.py` `connection_ok = models.BooleanField(null=True, blank=True)` (GasSensor, PowerDevice) | 中 | SQLite 의 -1/0/1 혼용 검증 SQL: `SELECT DISTINCT connection_ok FROM facilities_gassensor` → {NULL, 0, 1} 외 값 발견 시 정정. |
| 8 | FloatField NaN/Inf | `power_data.value`, `gas_data.{co,h2s,...}`, `alarm_record.value`, `ml_anomaly_result.score` 등 | 高 | §1.1~1.2 검증 SQL. **현재 0건 확인** ✓ |
| 9 | FK 고아 (PROTECT) | `power_data.power_device` (PROTECT), `gas_data.gas_sensor` (PROTECT) | 高 | §1.9 SQL. **power_data 0건 확인** ✓. 나머지 W2 D-1 실행. |
| 10 | UniqueConstraint 중복 | PowerData / Threshold / MLModel / DataRetentionPolicy / SafetyStatus / CustomUser email | 高 | §1.3~1.8 전수 검증. 위반 발견 시 SOP 따라 정정 후 재실행. |
| 11 | Partial UniqueConstraint | `vr_training_content.py` `is_active=True` 부분 unique, `safety_checklist_revision.py` 동일 | 中 | §1.10 SQL. 위반 발견 시 `is_active=False` UPDATE (DELETE 금지). |
| 12 | JSONField 변환 | `alerts/alert_policy.py` (target_*_ids, channels), `ml/ml_model.py` (feature_columns, params_json), `power_event.py` (snapshot, changed_channels), `ml_anomaly_result.py` (feature_snapshot_json), 외 | 低 | SQLite TEXT → PG `jsonb` 자동. `dumpdata→loaddata` 통과 시 OK. 시연 후 GIN 인덱스 도입 검토(§6). |
| 13 | RunPython 마이그레이션 | `apps/*/migrations/*.py` 중 RunPython 25개 (2026-05-22 기준, 모체 plan 의 86개는 추정 오류) | 中 | 신규 PG DB는 `migrate` 1회 모두 적용. ml/0001 데이터 시드 마이그레이션이 가장 무거움 — 새 환경에서 시간 측정. |
| 14 | Celery long-running tasks | `apps/operations/tasks/data_retention_task.py` (대량 DELETE), `queue_metrics_task.py` (LLEN) | 中 | PG `statement_timeout=60s` + `idle_in_transaction_session_timeout=30s`. DRF `CONN_MAX_AGE=60` 명시. |
| 15 | celery worker concurrency=2 | `docker-compose.yml` celery-worker `--concurrency=2` | 低 | PG 는 multi-writer OK. 시연 전 그대로, 시연 후 4로 증설 검토. |
| 16 | gunicorn workers=1 | `docker-compose.yml` drf `--workers=1 --threads=4` | 中 | 개발 핫리로드 유지 위해 1 고정. PG 로 가도 변경 불필요 (threads=4 로 동시성 확보). |
| 17 | psycopg2 드라이버 | `drf-server/requirements.txt` `psycopg2-binary==2.9.11` | 低 | 기 설치 확인 ✓. 시연 전 신규 추가 불필요. |
| 18 | FastAPI DB 접근 | `fastapi-server/*` 전체 | — | DRF REST 로만 통신, 직접 ORM 접근 없음 → **PG 전환과 무관**. 변경 없음. |

---

## 3. 데이터 이관 범위 — 옵션 (b) 확정

**2026-05-22 실측 결과 옵션 (b) "백업 후 Raw 이관 제외" 로 확정.** 이유: retention dry_run 측정 결과 삭제 예정 **0건** (현재 데이터 분포가 모두 보존 윈도우 30일 이내, 9.2M 행 전부 5/13~5/21 누적). 옵션 (a) 의 "retention 으로 데이터 축소" 전제가 무너졌으므로 (b) 가 사실상 유일한 합리적 경로.

### 옵션 (b) — SQLite 백업 후 Raw 이관 제외, PG 는 새로 쌓기

**절차:**
1. `cp drf-server/db.sqlite3 backup/db.sqlite3.pg_switch_2026_05_22` (파일 백업, 5.3GB)
2. (선택) `sqlite3 db.sqlite3 .dump > backup/db_dump_2026_05_22.sql` (SQL 형태 추가 백업, ARIMA 학습/감사 용도)
3. `dumpdata --natural-foreign --natural-primary --exclude=monitoring.powerdata --exclude=monitoring.gasdata --exclude=monitoring.workerposition --exclude=ml.mlanomalyresult` 로 영구 계층만 JSON 출력
4. PG 신규 DB 에 `loaddata` 적용
5. Raw 시계열은 PG 환경에서 더미·실측 송출로 자연 누적

**장점:** retention 실행 부담 없음. SQLite 파일 통째로 archive 보관 가능 (필요 시 복구·재학습 경로 유지). dumpdata 사이즈도 영구 계층만이라 작음 (~수십 MB 예상).

**단점:** PG 전환 직후 ~D-3 더미 송출 시점까지 raw 시계열 차트가 비어있음. 시연 D-23 여유로 시연일에는 자연 채워짐.

### 옵션 (a) — 폐기 (참고용)

원안: retention 1회 강제 실행 후 영구 계층만 이관. **무효:** retention dry_run 결과 삭제 0건. 보존정책(raw 30일) 단축이나 강제 cutoff 변경은 운영 정책 일시 변경이라 부적합.

### 공통: 이관 대상 / 제외

**이관 대상 (영구 계층):**
AlarmRecord, AlarmEvent, Event, EventLog, IntegrationLog, AppLog, SystemLog, CustomUser, Company, Department, Facility, GasSensor, PowerDevice, Threshold, AlertPolicy, DataRetentionPolicy, MLModel, SafetyChecklist, VrTrainingContent, 그 외 마스터성 테이블 일체.

**이관 제외 (Raw 시계열):**
PowerData, GasData, WorkerPosition.

**검토 필요:** MLAnomalyResult — 운영자에게 "지난 이상탐지 결과 N건" 보이고 싶으면 포함. 시연 시나리오에 포함되는지 시연 D-7 까지 확정.

---

## 4. PG 컨테이너 권장 설정 (WSL2 개발/시연 환경)

`docker-compose.yml` 에 추가할 서비스:

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
    - -c
    - shared_buffers=256MB
    - -c
    - effective_cache_size=1GB
    - -c
    - work_mem=16MB
    - -c
    - maintenance_work_mem=128MB
    - -c
    - statement_timeout=60s
    - -c
    - idle_in_transaction_session_timeout=30s
    - -c
    - max_connections=50
  volumes:
    - postgres_data:/var/lib/postgresql/data
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U diconai"]
    interval: 10s
    timeout: 5s
    retries: 5

volumes:
  postgres_data:
```

**`.env.docker` 변경:**
```
DATABASE_URL=postgres://diconai:${POSTGRES_PASSWORD}@postgres:5432/diconai
POSTGRES_PASSWORD=<dev_password>
```

**선정 근거:**
- `shared_buffers=256MB`: WSL2 가용 메모리 보수치. 운영 시 RAM 의 25% 로 상향.
- `statement_timeout=60s`: retention 대량 DELETE 보호. 현재 36.5ms 측정 대비 충분한 여유.
- `idle_in_transaction_session_timeout=30s`: Celery worker 가 transaction 열어둔 채 멈춤 방지.
- `max_connections=50`: gunicorn 4 thread × 1 worker + celery worker 2 + beat 1 + admin = 8 동시, 여유 6배. 시연 환경 충분.

**비밀번호 관리:** `.env.docker` 평문으로 충분 (시연·개발 환경 한정). 운영 진입 시 별도 secret 관리 plan.

---

## 5. 전환 당일 Runbook (W2 본 진입 시)

### D-1 (5/27 권장, retention 측정 후 결정)

| 시각 | 작업 | 검증 |
|---|---|---|
| 09:00 | §1.1~1.10 SQL 전수 실행 | 모두 0건 (위반 발견 시 SOP 따라 정정 후 재실행) |
| 10:00 | 옵션 (a) 선택 시 retention 강제 실행 | power_data 행수 14일 윈도우로 축소 |
| 10:30 | `dumpdata` dry-run (영구 계층만) | JSON 사이즈 ≤50MB 확인 |
| 11:00 | 옵션 (b) 선택 시 SQLite 파일 백업 | `backup/db.sqlite3.pg_switch_<date>` 생성 |

### D-Day

| 시각 | 작업 | 검증 / 롤백 |
|---|---|---|
| 09:00 | `docker compose down` + SQLite 최종 백업 | 백업 파일 존재 확인 |
| 09:30 | docker-compose.yml 에 postgres 서비스 추가, `DATABASE_URL` 3곳 환경변수화 (위험 #3) | `git diff` 로 변경 4곳 확인 |
| 09:40 | `.env.docker` `DATABASE_URL=postgres://...` 교체 | — |
| 10:00 | `docker compose up -d postgres` | healthcheck PASS 대기 |
| 10:15 | `docker compose run --rm drf python manage.py migrate` | 시간 측정 (예상 1~3분, ml/0001 가장 무거움) |
| 10:30 | `dumpdata` → `loaddata` 적용 | rowcount 양쪽 비교 (영구 계층 테이블별 차이 0) |
| 11:00 | 더미 1종(전력만) 30분 송출 | fastapi 로그 timeout 0건 |
| 11:30 | 더미 3종 동시 송출 | Grafana p99 < 500ms |
| 12:00 | 시연 시나리오 1회 dry-run | 알람·차트·이상탐지 정상 |

### 롤백 명령 (각 단계 실패 시)

```bash
# .env.docker DATABASE_URL 을 sqlite 로 복귀
sed -i 's|^DATABASE_URL=postgres://.*|DATABASE_URL=sqlite:////app/db.sqlite3|' .env.docker

# drf/celery 재시작
docker compose restart drf celery-worker celery-beat

# postgres 컨테이너만 정지 (볼륨 유지)
docker compose stop postgres
```

---

## 5b. 2026-05-22 D-Day 실측 결과

| 단계 | 측정 시간 | 비고 |
|---|---|---|
| SQLite 5.3GB 백업 (cp) | 7.4s | |
| dumpdata 영구 계층만 (448MB, 703K obj) | 1m44s | `--natural-foreign --natural-primary` |
| docker compose down | 4.6s | |
| PG image pull + healthy | 19s | postgres:16-alpine |
| migrate 1차 (0016 seed 충돌) | 17s | **시퀀스 reset 필요 (아래 §5c)** |
| 시퀀스 reset | 1s | |
| migrate 재실행 | 8.9s | |
| TRUNCATE RESTART IDENTITY CASCADE | 3min | application + 자연키 모델 |
| loaddata 448MB / 703K obj | **7m54s** | 가장 무거운 단계 |
| 시퀀스 reset (loaddata 후) | 1s | fixture PK 명시 모델의 sequence advance |
| 전체 서비스 up | 12.8s | |
| **합계** | **~13min** | |

### 5c. 시퀀스 reset 표준 패턴 (Django sqlsequencereset 동일)

`setval(seq, n)` 의 `is_called` 인자가 default `true` 라 빈 테이블에서 `setval(seq, 1)` 호출 시 다음 nextval=2 → **자연키 모델 PK 가 한 칸씩 shift** 됨 (initial D-Day 에 admin id=2 로 매겨졌던 원인). `false` 인자가 정답이지만, 데이터 있는 테이블에서는 `true` 여야 안전 → `MAX(id) IS NOT NULL` 로 동적 결정.

```sql
DO $$
DECLARE r RECORD;
DECLARE seq TEXT;
BEGIN
  FOR r IN SELECT tablename FROM pg_tables WHERE schemaname='public' LOOP
    BEGIN
      seq := pg_get_serial_sequence(format('public.%I', r.tablename), 'id');
      IF seq IS NOT NULL THEN
        EXECUTE format(
          'SELECT setval(%L, COALESCE((SELECT MAX(id) FROM %I), 1), (SELECT MAX(id) IS NOT NULL FROM %I))',
          seq, r.tablename, r.tablename
        );
      END IF;
    EXCEPTION WHEN OTHERS THEN NULL;  -- string PK 테이블 (django_session 등) skip
    END;
  END LOOP;
END $$;
```

호출 시점 2곳:
1. migrate 1차 실패 후 (0011 seed 가 만든 id=1, 2 의 sequence advance)
2. loaddata 직후 (fixture PK 명시 INSERT 후 sequence advance)

`TRUNCATE ... RESTART IDENTITY CASCADE` 직후엔 sequence 가 이미 1 로 reset 되어 있으므로 별도 호출 불필요 (호출하더라도 표준 패턴이면 빈 테이블 = `setval(1, false)` 로 무해).

검증 실패 위치를 commit 메시지에 남겨 다음 시도에서 우회 가능하게 한다.

---

## 6. 시연 후 도입 후보 (별도 plan)

PG 전환만 완료하고 시연 통과가 우선. 아래는 시연 후 별도 plan 으로 분리:

| 항목 | 가치 | 시점 |
|---|---|---|
| `jsonb` GIN 인덱스 (AlertPolicy.target_user_types, MLModel.params_json 쿼리 가속) | 中 | 시연 후 W+1 |
| `timestamptz` 명시 + 시계열 BRIN 인덱스 (Raw 테이블) | 高 (ARIMA 학습 쿼리 가속) | ARIMA 도입 직전 |
| TimescaleDB hypertable (power_data, gas_data) | 高 | 별도 plan, ARIMA 와 함께 |
| `pg_stat_statements` + postgres_exporter (관찰성) | 中 | 시연 후 W+2 |
| pg_dump 일일 cron / WAL 아카이빙 | 高 (운영 진입 전제) | 운영 진입 시 |

---

## 7. 미해결 질문 (W2 D-1 까지 확정)

1. **MLAnomalyResult 이관 여부** — 운영자에게 과거 이상탐지 결과 표시가 시연 시나리오에 포함되는지. 포함 시 §3 "이관 대상" 에 추가.
2. **옵션 (a) vs (b) 최종 선택** — D-1 retention 측정 시간 보고 결정. retention 30분 미만이면 (a), 그 이상이면 (b) 권장.
3. **PG 비밀번호** — `.env.docker` 평문 vs Docker secret. 시연 환경은 평문 무방, 운영 진입 시 재검토.

---

## 부록 A. SQLite ↔ PG 자동 변환 보장 (참고)

`dumpdata --natural-foreign --natural-primary` 흐름에서 다음은 Django ORM 이 자동으로 변환한다:

| SQLite 타입 | PG 타입 | 변환 책임 |
|---|---|---|
| TEXT (DateTime ISO 문자열) | timestamp / timestamptz | Django ORM (USE_TZ 설정에 따름) |
| TEXT (JSONField) | jsonb | Django JSONField serializer |
| INTEGER (BooleanField) | boolean | Django BooleanField (단 -1/0/1 혼용 검증은 §1 별도) |
| INTEGER (Decimal) | numeric | Django DecimalField |
| FLOAT (NaN/Inf 제외) | double precision | Django FloatField |

따라서 §1 SQL 통과 + `dumpdata→loaddata` 패턴이면 형 변환 위험 0에 가깝다. raw INSERT 이관 시에만 수동 캐스팅이 필요한데, 본 plan 의 옵션 (a)/(b) 모두 dumpdata 경로를 따르므로 해당 없음.
