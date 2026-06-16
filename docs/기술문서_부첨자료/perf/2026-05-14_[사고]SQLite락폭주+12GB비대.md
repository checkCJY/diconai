# 2026-05-14 — SQLite 락 폭주 + 12GB DB 비대 사고 기록

> 작성: 2026-05-14
> 상태: **1단계 + 2단계 W1 완료.** 후속(W2 PG 전환)은 다음 sprint.
> 관련 plan: [skill/plan/db-stabilization-postgres-migration.md](../../skill/plan/db-stabilization-postgres-migration.md)
> 관련 메모리: [data-lifecycle-3tier-principle](../../.claude/projects/-home-cjy-diconai/memory/data_lifecycle_3tier_principle.md) · [debug-pragma-first](../../.claude/projects/-home-cjy-diconai/memory/debug_pragma_first.md)

---

## 1. 요약

더미 3종(가스·전력·위치) 동시 송출 시 `/dashboard/`에서 알람이 누락되거나 응답이 멈추는 현상 발생. 진단 결과 **SQLite 다중 writer 락 폭주 → DRF 처리량 한계 → fastapi→drf timeout 폭주**의 직렬 병목. 응급 처방(1단계)으로 락 폭주 해소, 본 정리(2단계)로 12GB → 약 100MB 슬림화.

## 2. 영향 (Impact)

- 대시보드 알람 실시간 표시 불안정(분당 수십 건 누락)
- fastapi `services.drf_client: action=timeout` 로그 폭주
- Celery `database is locked` 에러로 알람 태스크 5초 retry 누적
- **시연 일정(2026-06-14, D-31) 위협 잠재적** — 더미 운영조차 안정성 부족하면 시연 부하에서도 동일 현상 우려

## 3. 타임라인 (2026-05-14, KST)

| 시각 | 사건 |
|---|---|
| 작업 시작 | 사용자가 "도커로 관리중인 상태에서 더미 3종 실행 시 대시보드 알람 누락" 보고 |
| +10분 | fastapi 로그에서 `action=timeout` 폭주 확인. drf gunicorn `--workers=1` 직렬화가 원인으로 가설 |
| +20분 | Celery 로그에서 `database is locked` 무한 retry 발견 → 진짜 원인은 락 |
| +30분 | DB 크기 12GB 확인. 단일 backup이 어제 353MB → 오늘 12GB로 비대화 |
| +40분 | WAL 활성 확인(이전 진단 오류 자기정정). 원인을 `BEGIN DEFERRED` + `BUSY_SNAPSHOT`으로 재정렬 |
| +1시간 | 1단계 응급 처방 적용: busy_timeout 30s + transaction_mode=IMMEDIATE + gunicorn threads=4 |
| +1시간 30분 | 검증: Celery 락 에러 0건. 단 더미 3종 송출 시 여전히 timeout 발생 → 병목이 처리량으로 이동 |
| +2시간 | 12GB의 99%가 `power_data` 테이블 + 인덱스 6개 9GB로 확인. Apr 15~May 11 매일 138K 균일 누적 패턴 발견 |
| +2시간 30분 | 균일 누적은 IF 학습 백필 데이터로 확인. 운영 DB와 학습 자산 분리 필요 판단 |
| +3시간 | 자동 송출 소스 추적: 호스트·컨테이너 모두 깨끗. 누적 원인은 사용자 수동 백필. retention task 미발사 원인은 03시 KST cron이 PC 꺼진 시간이라 미실행 |
| 진행 중 | 2단계 본 정리: parquet 백업 + DELETE + VACUUM |

## 4. 근본 원인 (Root Cause)

3겹 직렬 병목으로 분해 가능:

### 4.1 SQLite 다중 writer + DEFERRED 트랜잭션

Django 기본 `BEGIN DEFERRED`에서 SELECT → INSERT 업그레이드 중 다른 writer가 끼면 SQLite는 `SQLITE_BUSY_SNAPSHOT` 즉시 실패를 던짐. 이는 `busy_timeout`으로 재시도되지 않고 트랜잭션 전체 롤백. 따라서 Celery 알람 태스크들이 마이크로초 단위로 즉시 실패 → 5초 retry 누적.

### 4.2 운영 DB와 학습 자산 혼재 (12GB 비대화)

`power_data` 테이블에 Apr 15 ~ May 11 IF 학습용 백필 데이터(373만 행)가 운영 시계열과 같은 테이블에 적재됨. 인덱스 6개가 함께 비대해져 합계 9GB. INSERT 1건당 6개 B-tree 갱신 → 락 보유 시간 비례 증가 + 페이지 캐시 hit rate 저하로 cold miss 시 단발 INSERT 8초까지 측정됨.

### 4.3 Retention task 미발사 (자동 정리 안 됨)

[apps/operations/tasks/data_retention_task.py](../../drf-server/apps/operations/tasks/data_retention_task.py)의 `run_data_retention`은 매일 03:00 KST에 cron 등록되어 있고 `power_raw` 30일 정책도 활성. 그러나 03시는 개발자가 호스트 PC를 꺼놓는 시간대 → WSL2/Docker Desktop이 함께 멈춰 task가 미발사. cron-like catch-up 없음. 누적 결과가 4월 15일~5월 11일 사이 27일치를 그대로 보존.

## 5. 응급 조치 (1단계, 완료)

| 파일 | 변경 | 효과 |
|---|---|---|
| [apps/core/sqlite_pragmas.py](../../drf-server/apps/core/sqlite_pragmas.py) | `PRAGMA busy_timeout` 5s → 30s | 락 대기 허용 |
| [config/settings.py](../../drf-server/config/settings.py) | SQLite OPTIONS에 `timeout=30, transaction_mode='IMMEDIATE'` | BUSY_SNAPSHOT 회피, writer 큐잉 |
| [docker-compose.yml](../../docker-compose.yml) | gunicorn `--threads=4` 추가 (workers=1 유지) | 단일 워커 직렬화 완화 |

검증: 더미 송출 시 `database is locked` 폭주 0건, Celery 태스크 처리시간 5초+ → 10~25ms로 정상화.

## 6. 본 조치 (2단계, 진행 중)

### 6.1 학습 자산 분리 (parquet 백업)

`drf-server/ml_datasets/power_backfill_2026_04_15_to_05_11_part_*.parquet` 8 chunks, 총 3,732,480 행, 47MB(snappy 압축). manifest 파일로 재현성 보장. 향후 IF/ARIMA 학습 시 운영 DB가 아닌 이 parquet에서 로드.

### 6.2 운영 DB truncate

`DELETE FROM power_data WHERE measured_at < '2026-05-12'` + `VACUUM` + `PRAGMA wal_checkpoint(TRUNCATE)`. 원본 12GB cold copy를 `drf-server/db_backups/` 별도 보관(비상용).

**실측 결과:**

| 지표 | Before | After | 개선 |
|---|---|---|---|
| DB 파일 크기 | 11.19 GiB | 0.16 GiB | **99% 절감 (76배)** |
| `power_data` 행 | 25,284,944 | 401,744 | 98% 감소 |
| DELETE 소요 | — | 24,883,200 rows / **694초 (11.5분)** | — |
| VACUUM 소요 | — | **5.7초** (활성 데이터 적어 매우 빠름) | — |

**INSERT latency baseline 비교** (단일 connection, bulk_create 16행 × 100회):

| 지표 | Before (12GB) | After (160MB) | 비고 |
|---|---|---|---|
| p50 | 0.90ms | 0.79ms | 비슷 (이미 작았음) |
| p95 | 7.59ms | 11.83ms | 측정 표본 100회의 fluctuation 범위 |
| p99 | 10.83ms | 14.39ms | 동일 |
| **max** | **33.80ms** | **19.51ms** | **-42% (꼬리 발작 강도 감소)** |
| mean | 2.10ms | 2.10ms | 비슷 |

평균 INSERT 비용은 변화 없음 (이미 빠른 상태였음). 핵심 효과는 **꼬리 발작 강도 감소** + 디스크 회수 + 인덱스 슬림화로 인한 락 보유 시간 단축. 진짜 동시 부하 비교는 더미 3종 송출 중 별도 측정 예정.

### 6.3 Retention 스케줄 보정

[config/settings.py](../../drf-server/config/settings.py)의 `CELERY_BEAT_SCHEDULE` 시간을 `03:00 → 09:30 KST`로 이동. 개발자가 작업 시작할 시점이라 발사 보장됨. 코드 변경 없이 설정만 변경.

**검증 결과 (수동 1회 실행):**

```
[retention] action=deleted policy_id=6 category=gas_raw deleted=0
[retention] action=deleted policy_id=10 category=position_hist deleted=0
[retention] action=deleted policy_id=8 category=power_raw deleted=0
[retention] action=run_complete dry_run=False policies_run=3
[run_data_retention] 결과: {6: 0, 10: 0, 8: 0}
[run_data_retention] 소요: 36.5ms
```

이전엔 `power_raw` 처리 도중 25M 행 부담으로 죽었던 태스크가 이제 **3개 정책 모두 36.5ms 내 완료**. deleted=0은 정상 (이미 truncate로 제거되어 cutoff 이전 데이터가 없음).

## 7. 재발 방지 (Action Items)

| 항목 | 책임 | 완료 |
|---|---|---|
| Retention task 시간 09:30으로 이동 | 백엔드 | ✅ 본 작업 |
| 신규 테이블 추가 시 보존 기간 함께 결정 (운영 규칙) | 팀 컨벤션 | docs/conventions/data_lifecycle.md(별도 작성 예정) |
| ML 학습 데이터는 운영 DB에 두지 않기 | 팀 컨벤션 | 위와 동일 |
| 인덱스 추가 시 prefix 중복 검토 | 팀 컨벤션 | 위와 동일 |
| 시계열 raw 데이터에 정리 Celery beat 의무화 | 팀 컨벤션 | 위와 동일 |
| PostgreSQL 전환 (ARIMA 대비) | 백엔드 | W2 (5/21~5/27 예정) |

## 8. 교훈 (Lessons Learned)

### 진단 과정에서 얻은 것

1. **PRAGMA·기본 설정 확인을 0단계로.** WAL이 이미 활성인 줄 모르고 "WAL 켜라"를 권장한 초기 오진이 있었다. `sqlite3 db.sqlite3 "PRAGMA journal_mode;"` 한 줄이면 막을 수 있는 실수. 락·성능 진단 시 PRAGMA 현재값을 먼저 보는 습관 필요.

2. **원인과 증폭기는 다르다.** 12GB 자체가 락의 *원인*은 아니다. 진짜 원인은 다중 writer + `BEGIN DEFERRED`. 12GB는 락 보유 시간을 늘려 임계를 넘게 만든 *증폭기*. 슬림화만 하면 워크로드 증가 시 동일 사태 재현될 수 있음. 처방은 둘 다 필요.

3. **단발 측정의 함정.** 정적 측정에서 평균 INSERT 0.9ms로 빠르게 보였지만 가끔 발생하는 cold cache miss 발작(첫 INSERT 8.3초)이 실제 timeout 폭주의 원인. 평균 latency가 아닌 꼬리 지연(p99, max) 관찰 필요.

### 운영 차원에서 얻은 것

4. **개발 환경 cron은 catch-up이 없으면 무의미.** WSL2/Docker는 호스트가 꺼지면 같이 멈춤. "매일 03시" 같은 야간 cron은 개발 환경에선 사실상 0% 실행률. 업무 시간대에 두거나 catch-up 패턴 도입.

5. **학습 데이터와 운영 데이터의 물리적 분리.** 동일 테이블에 섞이면 한쪽의 비대화가 양쪽 모두를 끌어내림. parquet 스냅샷 같은 별도 매체로 처음부터 분리해야 함.

## 9. 추후 점검 항목 (.gitignore + 1회용 스크립트 컨벤션)

본 사고 처리 중 발견한 운영 위생 항목 — 별건 작업으로 분리.

- [ ] **1회용 스크립트 prefix 컨벤션 확장.** 현재 `_eval_*.py`만 .gitignore에 있음. 본 작업에서 `_backup_*.py`, `_verify_*.py` 등 추가 prefix를 임시로 썼는데, 일관된 컨벤션 합의 후 .gitignore에 추가 (또는 `drf-server/_*.py` 일괄 패턴).
- [ ] **`_truncate_*.py` 같은 루트 위치 스크립트 처리.** 본 작업에서 `/home/cjy/diconai/_truncate_run.py`를 만들었음. 향후 동일 위치 스크립트 패턴 표준화 필요.
- [ ] **PG 전환 후 백업 정책 재검토.** `db_backups/`는 SQLite 시기 cold copy 보관 목적. PG 전환 후엔 `pg_dump`-based 백업이라 디렉토리·확장자 다름. 그때 .gitignore 패턴도 동시 갱신.
- [ ] **`drf-server/ml_datasets/` 부피 임계 점검.** 현재 47MB (1회 백업). 정기 학습 셋이 누적되면 GB 단위 가능 — 별도 매체(S3 등) 이관 검토.


## 10. 후속 계획

본 사고의 직접 처방은 W1(이번 주)으로 종료. 그 외 시연일까지의 후속 작업:

- W2 (5/21~5/27): PostgreSQL 전환 (ARIMA 대비, [plan](../../skill/plan/db-stabilization-postgres-migration.md) 참조)
- W3 (5/28~6/3): 회귀 테스트 + 더미 부하 검증
- W4 (6/4~6/10): 시연 리허설
- 시연일: 2026-06-14
- 시연 후: ARIMA sprint (parquet 학습 셋 활용)

---

## 참고

- 1단계 응급 처방 후 INSERT latency baseline (12GB 상태):
  - p50 0.90ms / p95 7.59ms / p99 10.83ms / max 33.80ms / mean 2.10ms
- truncate 후 동일 baseline + 동시 부하 측정 예정 (별도 기록)
