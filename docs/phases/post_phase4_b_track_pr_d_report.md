# B 운영 트랙 PR-D — AppLog Celery + IntegrationLog 비동기 INSERT

> 작업일: 2026-05-09
> 브랜치: `feature/0508_refactory`
> 부모 plan: [`~/.claude/plans/b-cozy-panda.md`](../../../home/cjy/.claude/plans/b-cozy-panda.md) §3 PR-D
> 직전 PR: [post_phase4_b_track_pr_c_report.md](post_phase4_b_track_pr_c_report.md) (`81e70de`)

---

## 1. 작업 목적

운영 진입 시 web pod의 응답 latency를 보호하기 위해 두 로그 모델의 INSERT를 Celery worker 비동기로 전환:
- **B-2 AppLog Celery 큐 + graceful fallback**: DBLogHandler.emit()이 Celery delay() 호출, broker 다운 시 동기 fallback
- **B-3 IntegrationLog 비동기 INSERT**: alerts/tasks.py의 _push_to_ws 후처리를 Celery task로 분리

Docker/K8s 도입 예정 — Celery worker pod 분리로 web latency 보호 + broker(Redis) 인프라 일관 (사용자 결정 1).

---

## 2. 검증 결과

| 항목 | 명령 | 결과 |
|---|---|---|
| Django 시스템 검사 | `manage.py check` | ✅ 통과 |
| 마이그 일관성 | `makemigrations --dry-run --check` | ✅ "No changes detected" |
| pytest 회귀 | `.venv/bin/pytest` | ✅ **56 passed** |
| pre-commit | `pre-commit run --files <변경파일>` | ✅ Passed |

---

## 3. 변경 파일

### 3-1. 신규 (2개)

| 파일 | 역할 |
|---|---|
| [apps/operations/tasks/applog_task.py](../../drf-server/apps/operations/tasks/applog_task.py) | `applog_create_task` Celery 태스크 — `@shared_task(max_retries=0, ignore_result=True)` |
| [apps/operations/tasks/integration_log_task.py](../../drf-server/apps/operations/tasks/integration_log_task.py) | `integration_log_create_task` Celery 태스크 — 동일 패턴 |

### 3-2. 기존 수정 (4개)

| 파일 | 변경 |
|---|---|
| [apps/operations/tasks/__init__.py](../../drf-server/apps/operations/tasks/__init__.py) | `applog_create_task`, `integration_log_create_task` re-export |
| [apps/operations/logging/db_handler.py](../../drf-server/apps/operations/logging/db_handler.py) | `emit()`이 `applog_create_task.delay()` 호출. broker 예외 시 `_sync_insert()` graceful fallback. `settings.APPLOG_FORCE_SYNC=True`로 동기 모드 강제 가능 (테스트용) |
| [apps/alerts/tasks.py](../../drf-server/apps/alerts/tasks.py) | `_push_to_ws()`의 `IntegrationLog.objects.create()` → `integration_log_create_task.delay()` |
| [fastapi-server/services/drf_client.py](../../fastapi-server/services/drf_client.py) | docstring 갱신: fastapi 측 이미 async fire-and-forget이라 변경 불필요. PR-D 변경 명시 + 운영 진입 시 batch endpoint 도입 검토 후속 메모 |

---

## 4. 사용자 결정 사항 (B-track plan §2 결정 1)

| 항목 | 채택 | 본 PR 반영 |
|---|---|---|
| AppLog 비동기 방식 | (b) Celery 큐 + graceful fallback | ✅ Celery task + broker 다운 시 동기 fallback |
| Docker/K8s 인프라 일관 | 기존 Celery worker (Phase 4 PR3 DataRetention) 재사용 | ✅ `@shared_task` 패턴 동일 |

---

## 5. 발견 사항 / 주의

### 5-1. plan §3 PR-D B-3 vs 본 구현 — 단순화

plan §3은 "in-memory queue + 5초/10건 flush" 권장이었으나, in-memory queue는 K8s/Docker pod 재시작 시 **데이터 손실 위험**이 있어 동일 패턴(Celery 큐 비동기 INSERT)으로 단순화. 효과는 본질적으로 동일 (web pod의 latency 0). 단순화 사유:
- 운영 호환: pod 재시작에 안전
- AppLog Celery 패턴과 일관 (worker 인프라 재사용)
- broker 의존성 단일화 (Redis 1개)

batch flush의 가치(다건 통합 INSERT)는 향후 fastapi → DRF 호출 빈도가 큰 경우에만 유의미. 본 PR에선 Celery task 비동기로 web latency 우선 해소. **운영 진입 후 호출 빈도 측정 + DRF batch endpoint 도입은 후속 트랙**.

### 5-2. fastapi 측은 변경 없음

[fastapi-server/services/drf_client.py:_record_integration_log](../../fastapi-server/services/drf_client.py)는 이미 `httpx.AsyncClient` + fire-and-forget BackgroundTask 패턴 — fastapi 응답 latency 영향 0. docstring만 갱신해 PR-D 변경 사실 + batch endpoint 후속 메모 명시.

### 5-3. broker fallback 동작

```python
# DBLogHandler.emit()
try:
    applog_create_task.delay(**payload)  # broker 정상 → 비동기 INSERT
except Exception:
    self._sync_insert(payload)           # broker 다운 → 동기 fallback
```

학습 환경에서 broker 미가동도 허용 (Phase 4 PR3 Celery worker 미시작 상태에서도 logger.error 호출이 silent fail 없이 동기 INSERT). thread-local 재귀 가드는 sync/async 모두 유지 (logger 자기 호출 차단).

### 5-4. Celery worker 가동 권장

본 PR 적용 후 **Celery worker가 가동된 환경에서 실제 비동기 효과**가 발생:
```bash
celery -A config worker -l info  # broker 연결 후 task 처리
```
worker 미가동 시 broker는 task를 큐에 적재 (메모리 사용량 증가). graceful fallback 유지하되 worker 가동 모니터링 필요.

### 5-5. Step 3 회귀 테스트 영향 0

본 PR은 호출 패턴만 변경 (ORM create → Celery delay). 테스트 환경에서는 Celery 미가동이라 broker fallback이 동작 → 동기 INSERT. 결과 동일.

---

## 6. 다음 단계

PR-E (GasTypeChoices.LEL dead code 제거) 진입.

---

## 7. 누적 결과

| PR | commit | 변경 |
|---|---|---|
| PR-A | `f4b50d0` | fixture 시드 마이그 historical apps 패턴 |
| PR-B | `7207a4c` | BaseModel 컨벤션 10개 모델 |
| PR-C | `81e70de` | DataRetentionPolicy + AlertPolicy 시드 |
| **PR-D** | (본 commit) | AppLog/IntegrationLog Celery 비동기 INSERT |
