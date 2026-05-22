# DB 안정화 + PostgreSQL 전환 4주 로드맵

> 작성: 2026-05-14
> 시연일: **2026-06-14** (D-31)
> 트리거: 2026-05-14 SQLite 락 폭주 + 12GB DB 비대 진단 — power_data 99.4% 점유, AI 백필 누적이 직접 원인
> 메모리: [[data-lifecycle-3tier-principle]] · [[debug-pragma-first]] · [[docker-infra-decision-2026-05-11]]

---

## Context

지난 1주일간 더미 3종 송출 시 대시보드 알람 누락·멈춤 현상 발생. 진단 결과 단계적 병목:

1. SQLite 다중 writer + `BEGIN DEFERRED` → `SQLITE_BUSY_SNAPSHOT` 즉시 실패 (해결 완료, 1단계)
2. power_data 테이블 25M 행 + 인덱스 6개 9GB → cold cache miss 시 단발 INSERT 8.3초 (해결 대기, 2단계)
3. 보존 정책 부재 → 1주일 단위로 동일 사태 재발 가능 (3단계)
4. ARIMA 도입 예정 → 시계열 학습/예측 데이터량 폭증 시 SQLite 한계 명확 (4단계)

본 plan은 1단계 완료 시점에서 시작해 시연 전까지 2~4단계를 직렬로 수행하는 4주 계획.

---

## 목표·범위

### 목표
1. 시연일(2026-06-14)에 더미·실데이터 동시 송출 시 **timeout 0건**, 알람 실시간 표시
2. ARIMA 도입 시점에 인프라(PostgreSQL + 데이터 수명 정책)가 이미 준비된 상태
3. 동일 사태 재발 방지 위한 **운영 규칙 + 자동화** 정착

### 범위
- ✅ power_data 데이터 정리 + 학습 자산 parquet 백업
- ✅ Raw 계층 보존 Celery beat 태스크 (14일)
- ✅ 인덱스 중복 제거 (6개 → 2~3개)
- ✅ PostgreSQL 전환 (Docker compose + 마이그레이션 + 데이터 이관)
- ✅ 회귀 테스트 + 더미 부하 검증
- ❌ TimescaleDB 도입 (시연 후 별도 plan)
- ❌ ARIMA 모델 자체 (별도 sprint)

### 비-목표 (의도적 제외)
- 시연 전 ARIMA 도입 — 인프라 안정화 후 별도 sprint
- 시계열 롤업 테이블 — 시연 후
- 실 IoT 펌웨어 연동 — 펌웨어 팀 작업과 별개

---

## 1단계 — 응급 처방 ✅ 완료 (2026-05-14)

| 변경 | 파일 | 효과 |
|---|---|---|
| `busy_timeout` 5s → 30s | [apps/core/sqlite_pragmas.py](../../drf-server/apps/core/sqlite_pragmas.py) | 락 대기 허용 |
| `transaction_mode='IMMEDIATE'` 추가 | [config/settings.py](../../drf-server/config/settings.py) | `BUSY_SNAPSHOT` 회피, writer 큐잉 |
| gunicorn `--threads=4` 추가 | [docker-compose.yml](../../docker-compose.yml) | 동시성 확보 |

검증: Celery `database is locked` 폭주 → 0건. 단 INSERT 처리량은 여전히 한계 (12GB DB cold cache).

---

## 2단계 — 데이터 정리 (W1, 5/14~5/20)

**의사결정 이유:** truncate 효과를 측정으로 입증 (단발 INSERT 8.3초 vs 평상 1ms — cold cache가 직접 원인). DB 슬림화 = 페이지 캐시 hit rate 향상 = 꼬리 지연 해소.

### 작업

1. **사전 확인**
   - 디스크 여유 12GB 이상 (`df -h`)
   - 자동 송출 소스 추적 + 중단 (Apr 15~May 11 138K/일 균일 누적의 출처)
   - 백업본 별도 보관 (`db.sqlite3.before_truncate_<date>`)

2. **학습 자산 parquet 스냅샷**
   ```python
   # drf-server/ml_datasets/power_backfill_2026_05_11.parquet
   PowerData.objects.filter(
       measured_at__gte='2026-04-15', measured_at__lt='2026-05-12'
   ).to_dataframe().to_parquet(...)
   ```
   → IF 학습 시 재로딩으로 모델 재현성 보장. 운영 DB와 분리.

3. **운영 DB truncate**
   - 컨테이너 정지: `docker compose stop drf celery-worker celery-beat`
   - `DELETE FROM power_data WHERE measured_at < <오늘-14일>`
   - `VACUUM` (30~60분, +12GB 임시 공간)
   - `PRAGMA wal_checkpoint(TRUNCATE)`
   - 컨테이너 재기동
   - 결과 검증: 파일 크기 ~700MB, 평균 INSERT 시간 측정

4. **인덱스 중복 제거**
   - 현재 6개 (idx_pwr_device_ch_type_time / idx_pwr_risk_time / idx_pwr_device_ch_time / idx_pwr_anomaly_time / idx_pwr_time / power_data_power_device_id_*)
   - `idx_pwr_device_ch_time` ⊂ `idx_pwr_device_ch_type_time` 중복
   - 쿼리 분석 후 2~3개로 축소 — Django 마이그레이션
   - INSERT 비용 절반 이상 감소 예상

5. **보존 Celery beat 태스크 신설**
   - `apps/monitoring/tasks/cleanup_old_data.py` 신설
   - 매일 03:00 KST 14일 이전 power_data 삭제
   - 같은 패턴으로 gas_data, worker_position에도 적용
   - `apps.core.tasks` 또는 `apps.operations.tasks`에 배치 (기존 컨벤션 확인 후)

### 검증
- 더미 3종 동시 송출 30분간 fastapi action=timeout 0건
- 알람 평균 처리시간 < 50ms
- DB 파일 크기 < 1GB

---

## 3단계 — PostgreSQL 전환 (W2, 5/21~5/27)

**의사결정 이유:** ARIMA 도입 시점에 다중 writer/시계열 인덱싱 본격 필요. 시연 전 안정화 마치는 게 시연 후보다 risk 낮음 (시연 후엔 ARIMA 작업과 직렬 충돌).

<<<<<<< Updated upstream
=======
> ⚠️ 본 단계 진입 시 [postgres-migration-code-review.md](postgres-migration-code-review.md) 동반 참조 — 사전 검증 SQL 10건 + 코드 레벨 위험 카탈로그 18건 + Runbook 포함.

>>>>>>> Stashed changes
### 작업

1. **docker-compose.yml에 postgres 서비스 추가**
   - `postgres:16-alpine`
   - volume: `postgres_data:/var/lib/postgresql/data`
   - 기존 SQLite 볼륨 유지 (롤백 안전망)

2. **DATABASE_URL 환경변수 전환**
   - `.env.docker`: `DATABASE_URL=postgres://...`
   - django-environ가 자동 처리, settings.py 변경 거의 없음
   - SQLite-only OPTIONS는 `if ENGINE == 'sqlite3'` 분기로 보호 (이미 적용됨)

3. **마이그레이션 재실행**
   - `docker compose exec drf python manage.py migrate`
   - 픽스처 로드 (`apps/*/fixtures/*.json`)
   - 더미 누적분은 버림 (학습 자산은 이미 parquet)

4. **운영 데이터 이관** (선택)
   - AlarmRecord, Event, IntegrationLog 등 영구 계층만 이관
   - Raw 계층(power_data 등)은 이관 불필요 — 새로 쌓임
   - `dumpdata` + `loaddata` 또는 pgloader

5. **PostgreSQL 운영 도구 셋업**
   - `pg_dump` 백업 스크립트 (Makefile에 추가)
   - 기존 SQLite 백업 명령(`backup-db` 등) 폐기 또는 분기

### 검증
- 모든 단위 테스트 통과
- 더미 부하 30분간 무사고
- 동시 writer 처리량 SQLite 대비 10배 이상 (이론치)

### 롤백 전략
- `.env.docker`에서 `DATABASE_URL`만 sqlite로 되돌리면 즉시 복구
- postgres 컨테이너는 보존, SQLite 백업본도 보존

---

## 4단계 — 회귀 + 부하 검증 (W3, 5/28~6/3)

### 작업
1. 단위 테스트 전체 실행 (PG 환경)
2. 더미 3종 24시간 송출 + Grafana로 latency/throughput 추이
3. AI 스프린트 잔여작업 병행 (인프라가 안정화돼야 ML 검증도 신뢰 가능)
4. 시연 시나리오 1회 리허설

### 검증 지표 (Grafana 대시보드)
- `http_request_duration_seconds_bucket{le="0.5"}` p99 < 500ms
- `alarm_fired_total` 분당 정상 발생
- `alarm_ws_push_failed_total` 0건

---

## 5단계 — 시연 준비 (W4, 6/4~6/10)

### 작업
1. 시연 시나리오 최종 리허설 (3회 이상)
2. 학습 데이터 parquet ARIMA 입력 형식 점검 (ARIMA 본 sprint 직전 준비)
3. 운영 문서 갱신 — [docs/specs/](../../docs/specs/)
4. 비상시 SQLite 롤백 매뉴얼 출력본 준비

### 시연 당일 (6/14)
- 사전 컨테이너 재기동 (메모리 정리)
- 모니터링 화면 별도 띄워 부하 추이 실시간 확인

---

## 시연 이후 (장기 로드맵, 본 plan 범위 외)

| 시기 | 작업 | 목적 |
|---|---|---|
| 시연 직후 | ARIMA 도입 sprint | 시계열 모델 본격화 |
| ~3개월 | TimescaleDB 확장 | 시계열 인덱싱·연속 집계 자동화 |
| ~6개월 | 시계열 롤업 테이블 | 분/시간 집계, raw와 분리 |
| 시점 미정 | 실 IoT 펌웨어 연동 | 다중 device 동시성 검증 |

---

## 향후 적용 운영 원칙

본 사태에서 도출된 4가지 — 신규 작업 시 의무 적용:

1. **신규 테이블 = 보존 기간 함께 결정.** 영구 보관 가정 금지. [[data-lifecycle-3tier-principle]]
2. **ML 학습 데이터는 운영 DB에 두지 않는다.** parquet/csv 스냅샷으로 별도 보관.
3. **인덱스 추가 시 prefix 중복 검토.** 같은 컬럼 조합 인덱스 중복 → INSERT 비용 배수 증가.
4. **시계열 raw 데이터에 Celery beat 정리 태스크 동시 작성.** 영구 보관 절대 금지.

---

## 의사결정 트레이드오프 (기록용)

### "왜 시연 전에 PostgreSQL 전환하나?"
- 미루면 ARIMA 작업과 직렬 충돌 → ARIMA 일정에 같은 지연 발생
- 시연 후 전환은 ARIMA 데이터 누적 후라 전환 비용 더 큼
- 시연 전 4주 = 전환 + 안정화 + 회귀 검증에 충분
- 롤백 안전망(DATABASE_URL 분기)이 있어 위험 통제됨

### "왜 인덱스를 줄이나?"
- 6개 인덱스 = INSERT마다 6개 B-tree 갱신 = 락 보유 시간 6배
- 일부는 prefix 중복으로 실질 효용 없음
- PG로 가도 동일 — 인덱스 정리는 DB 엔진과 무관한 위생작업

### "왜 보존 14일인가?"
- 시연·디버깅 주기에 충분
- 14일 × 138K/일 ≈ 193만 행, ~700MB — 페이지 캐시에 충분히 들어감
- 7일은 디버깅 시 곤란, 30일은 캐시 한계 다시 접근

---

## 안전망

- 매 단계 진입 전 백업: `db.sqlite3.checkpoint_<date>` 별도 보관
- PG 전환은 DATABASE_URL 한 줄로 즉시 롤백 가능
- W3 회귀 실패 시 SQLite 유지 + 시연 진행 (1단계+2단계만으로도 단기 안정성 확보됨)
- 시연 당일 비상시 더미 송출 송신 빈도 즉시 조정 가능 (DUMMY_SEND_INTERVAL_SEC)

---

## 미해결 질문

1. 자동 송출 소스(Apr 15~May 11 138K/일 균일 누적) 출처 — W1 진입 전 추적 필요
2. Postgres 컨테이너 메모리 할당 (WSL2 환경에서 적정값) — W2 진입 시 결정
3. 인덱스 6개 중 실제 사용되는 것 — `EXPLAIN QUERY PLAN`으로 분석 필요
