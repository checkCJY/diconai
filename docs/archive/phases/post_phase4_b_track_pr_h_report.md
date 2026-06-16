# B 운영 트랙 PR-H — e2e 알람 흐름 통합 테스트 4종

> 작업일: 2026-05-09
> 브랜치: `feature/0508_refactory`
> 부모 plan: [`~/.claude/plans/b-cozy-panda.md`](../../../home/cjy/.claude/plans/b-cozy-panda.md) §3 PR-H
> 직전 PR: [post_phase4_b_track_pr_g_report.md](post_phase4_b_track_pr_g_report.md) (`6acd681`)

---

## 1. 작업 목적

회귀 점검 Step 3의 5종 단위/통합 테스트는 GasData.save / get_threshold / WorkerPosition.received_node / mark_checked 등 **개별 모델/서비스 레이어**만 검증. 알람 task → AlarmRecord/Event/policy 매칭 흐름은 미검증.

PR-C AlertPolicy 9종 시드 + PR-G facility 우선순위가 적용된 후, **fire_*_alarm_task → create_alarm_and_event → match_policy → AlarmRecord/Event 생성** 흐름의 e2e 회귀 보호 추가.

---

## 2. 검증 결과

| 항목 | 명령 | 결과 |
|---|---|---|
| pytest 신규 e2e (4건) | `pytest apps/alerts/tests/test_alarm_e2e.py -v` | ✅ 4 passed |
| pytest 회귀 + 신규 (전체) | `.venv/bin/pytest` | ✅ **62 passed** (drf-server) |
| pytest 회귀 (fastapi-server) | `cd fastapi-server && .venv/bin/pytest` | ✅ 22 passed (영향 0) |
| pre-commit | `pre-commit run --files <변경파일>` | ✅ Passed |

### 누적 결과
- drf-server: **62 tests** (Step 3 회귀 27 + 기존 단위 29 + PR-G 신규 2 + PR-H 신규 4)
- fastapi-server: **22 tests** (PR-F)
- 총합: **84 tests**

---

## 3. 변경 파일 (신규 1개)

| 파일 | 테스트 수 | 회귀 커버 |
|---|---|---|
| [apps/alerts/tests/test_alarm_e2e.py](../../../drf-server/apps/alerts/tests/test_alarm_e2e.py) | 4 | 가스/전력/지오펜스/체크리스트 흐름 |

### 3-1. 4개 e2e 테스트

| 테스트 | 흐름 |
|---|---|
| `test_gas_alarm_e2e_creates_event_with_policy` | `fire_danger_alarm_task.apply()` → AlarmRecord(co=250) + Event + Event.policy = 가스 임계치 전사 알림 (PR-C 시드) |
| `test_power_alarm_e2e_creates_event_with_policy` | `fire_power_danger_task.apply()` → AlarmRecord + Event + Event.policy = 전력 과부하 전사 알림 (PR-C 시드) |
| `test_geofence_alarm_e2e_creates_event_with_policy` | `fire_geofence_alarm_task.apply()` → AlarmRecord + Event + Event.policy = 위험구역 진입 전사 알림 (PR-C 시드) |
| `test_safety_check_normal_flow_no_alarm` | check_service.check_item() 정상 흐름 → 알람 발생 0건 (회귀 가드) |

---

## 4. 사용자 결정 사항 (B-track plan §2 결정 5)

| 항목 | 채택 | 본 PR 반영 |
|---|---|---|
| e2e 알람 흐름 테스트 (B-10) | (b) 본 plan 포함 | ✅ PR-H로 진입 |
| Celery eager 인프라 | `task.apply()` 동기 실행 (worker 미가동 OK) | ✅ pytest-celery 미도입, 단순 |
| WS broadcast mock | `unittest.mock.patch("apps.alerts.tasks._push_to_ws")` | ✅ autouse fixture로 모든 e2e 적용 |

---

## 5. 발견 사항 / 주의

### 5-1. `task.apply()` vs `pytest-celery`
plan §3 PR-H는 `pytest-celery` 또는 `CELERY_TASK_ALWAYS_EAGER=True` 권장이었으나, `task.apply(kwargs=...)`로 동기 실행해도 동일 효과 — 단순화. 추가 dep 도입 없음.

### 5-2. mock 범위 — `_push_to_ws`만
WS broadcast는 알람 task의 fire-and-forget 후처리. e2e 검증의 핵심은 AlarmRecord/Event/Notification 생성이므로 WS는 mock으로 차단. 본 mock이 IntegrationLog Celery delay() 호출도 같이 무력화 (broker 미가동 환경 호환).

### 5-3. `notify_event_created` 검증 미포함
[apps/notifications/services/notification_service.py:notify_event_created](../../../drf-server/apps/notifications/services/notification_service.py)는 알람 task에서 자동 호출 안 됨 — 별도 호출자가 처리. 알람 task의 e2e는 AlarmRecord/Event/policy 매칭까지만 검증. Notification 생성/메시지 렌더 e2e는 향후 별도 트랙 (`notify_event_created` 직접 호출 단위 테스트로 충분).

### 5-4. 안전 체크리스트는 알람 0건 흐름
체크리스트 미완료 알람(`safety_check_pending`)은 별도 task에서 트리거. 본 PR의 e2e는 정상 체크 흐름이 알람 미발생함을 검증 (회귀 가드). Step 3 `test_check_item_flow.py` 5건이 체크리스트 자체 흐름 검증 완료.

### 5-5. fastapi-server 영향 0
본 PR은 drf-server e2e 테스트만 추가. fastapi-server pytest 22 tests 영향 0 확인.

---

## 6. 본 plan 종료

PR-H가 본 plan의 마지막 PR. 8 PR 모두 완료.

---

## 7. 누적 결과 (B 운영 트랙 plan 종료)

| PR | commit | 변경 | tests 영향 |
|---|---|---|---|
| PR-A | `f4b50d0` | fixture 시드 마이그 historical apps 패턴 (4건) | 56 (Step 3 회귀 유지) |
| PR-B | `7207a4c` | BaseModel 컨벤션 10개 모델 (마이그 6건 자동) | 56 |
| PR-C | `81e70de` | DataRetentionPolicy 5종 + AlertPolicy 9종 시드 | 56 |
| PR-D | `cdbeddd` | AppLog/IntegrationLog Celery 비동기 INSERT | 56 |
| PR-E | `af80d69` | GasTypeChoices.LEL dead code 제거 | 56 |
| PR-F | `f647d93` | fastapi-server pytest 인프라 + 스모크 22종 | 56 + 22 |
| PR-G | `6acd681` | Threshold.facility FK + 우선순위 + gas_facility_default | 58 + 22 |
| **PR-H** | (본 commit) | e2e 알람 흐름 통합 테스트 4종 | 62 + 22 = **84 tests** |

### 누적 효과
- **단일 진실 공급원 정책**: DRF 측 100% (Threshold + facility 우선순위)
- **컨벤션 정합**: BaseModel 10개 + fixture 시드 4건 + LEL 제거
- **운영 진입 즉시 동작**: AlertPolicy 9종 + DataRetentionPolicy 5종 시드
- **운영 안정성**: AppLog/IntegrationLog Celery 비동기 (web latency 0)
- **회귀 보호**: 84 tests (단위 + 통합 + e2e)
- **양측 서버 검증**: drf-server 62 + fastapi-server 22

---

## 8. 본 plan 외 / 후속 트랙

| 항목 | 진행 시점 |
|---|---|
| **B-11 POWER_THRESHOLDS FastAPI 자동 동기화** | K8s 배포 시점 결정 후 별도 plan |
| **A 화면 구현 트랙** | 사용자 화면 명세 수령 후 별도 plan |
| **외부 합의** | 펌웨어 node_id 페이로드, 피그마 CH4/온도 컬럼 협의 |
| **fastapi-server 추가 통합 테스트** | 운영 진입 시 호출 빈도 측정 + DRF mock 인프라 |
| **IntegrationLog batch endpoint** | 운영 진입 후 호출 빈도 측정 → DRF batch endpoint 도입 검토 |

---

## 9. End-to-End 검증 시나리오 (B-track plan §8 충족 확인)

| 시나리오 | 검증 위치 | 결과 |
|---|---|---|
| fresh setup migrate → 모든 시드 자동 | 마이그 reverse + re-apply 7회 검증 | ✅ |
| 알람 e2e: 페이로드 → GasData → 위험도 재계산 → 알람 task → policy 매칭 | PR-G 단위 + PR-H e2e | ✅ |
| 로그 흐름: logger.error → AppLog Celery 큐 + broker fallback | PR-D + 56 tests 회귀 | ✅ |
| 데이터 보관: Celery beat → DataRetentionPolicy 5종 순회 | PR-C 시드 + 기존 test_data_retention 10건 | ✅ |
| fastapi pytest 스모크 | PR-F 22 tests | ✅ |
| drf-server 누적 회귀 | 84 tests 통과 | ✅ |
