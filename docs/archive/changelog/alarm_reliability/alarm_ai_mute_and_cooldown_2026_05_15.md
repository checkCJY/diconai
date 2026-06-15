# 알람 시스템 — AI 우선순위 mute + 룰 누락 해소 (Phase 2)

> **요약 한 줄**: PR #52 (AI 이상탐지 통합) 머지 이후 발생한 "AI/룰 알람 동시 발화 중복 + 룰 알람 1시간 누락 + Celery retry push 중복" 3중 회귀를 5개 commit 으로 해소.

**브랜치**: `feature/alarm-ai-mute-and-cooldown` (base: `feature/db-안정화-w1`)
**커밋**: 5개 (`cf3a62c`, `1041ff0`, `a862360`, `f9bf4e4`, `1c1551f`)
**시연 환경 검증 일자**: 2026-05-15
**상세 plan**: [.claude/plans/ai-polymorphic-cupcake.md](../../../.claude/plans/ai-polymorphic-cupcake.md) (임시, 머지 후 `skill/plan/` 이동 예정)
**선행**: [if_alarm_binding_power_2026_05_14.md](../ml/if_alarm_binding_power_2026_05_14.md) (PR #52)

---

## 왜 이 작업을 했나

### 사용자가 보고한 증상 (시연 D-31)

| 증상 | 빈도 | 추정 원인 |
|---|---|---|
| 같은 채널 `power_overload` + `power_anomaly_ai` 동시 발화 | 항상 | PR #52 가 AI 알람 추가하면서 룰 알람과 양립 제어 부재 |
| 한 번 뜨고 1시간 동안 같은 위험은 안 뜸 | 항상 | `try_transition` 의 `_CACHE_TTL=3600` 이 같은 상태 천이를 1시간 skip |
| 정상화 후 다시 위험으로 가도 두 번째 알람 누락 | 종종 | WARNING `task_key` 가 1시간 잔류 → `cache.add(SETNX)` 충돌 |
| (잠재) Celery retry 시 같은 payload 가 큐에 3번 적재 | 운영 누적 | `_push_to_ws` max_retries=3 + Redis 큐 dedup 부재 |

### 코드 검토에서 확인한 결함 5가지

| # | 문제 | 위치 | 영향 |
|---|---|---|---|
| 1 | `_push_to_ws` retry 가 같은 payload 를 fastapi `/internal/alarms/push/` 에 3번 전달 → Redis 큐 중복 | `fastapi/websocket/services/alarm_queue.py` | 브라우저가 같은 알람 3회 수신 |
| 2 | `_CACHE_TTL=3600` 으로 `try_transition` 이 1시간 동안 같은 상태 천이 skip | `monitoring/services/gas_alarm.py` / `power_alarm.py` | 위험 지속 시 첫 1번만 알람, 1시간 정적 |
| 3 | WARNING `task_key` 가 동일 `_CACHE_TTL` 로 1시간 잔류, 정상 종료 시 정리 안 됨 | 같은 두 파일 + `alerts/tasks.py` | 다음 WARNING 타이머 시작 불가 |
| 4 | AI/룰 알람 양립 제어 부재 — `POWER_ANOMALY_AI` 와 `POWER_OVERLOAD` 가 다른 `event_type` 이라 Event 도 분리 발화 | `monitoring/services/power_alarm.py` + `event_service.py` | 같은 채널 카드 2개 동시 노출 |
| 5 | (회귀) fastapi 가 IoT raw id 로 mute 키 set, DRF 는 PK 로 read → 키 mismatch | `fastapi/services/ai_mute.py` ↔ `drf/apps/monitoring/services/power_alarm.py` | AI mute 가드 무력화 (시연 검증 중 발견) |

---

## 무엇을 변경했나

### Commit 1 — `cf3a62c` Step 1: push fingerprint dedup
`fastapi/websocket/services/alarm_queue.py` `push_alarm` 에 SET NX EX idempotency 키 추가. 룰 알람은 `event_id+risk_level`, AI 알람은 `anomaly_meta.{device_id, channel}+risk_level` 조합으로 fingerprint. 첫 도착자만 LPUSH 하고 retry 도착분은 silently drop + Prometheus `alarm_push_dedup_hits_total` 증가.

→ **choke point 차단**: 생산자(Celery worker) 측 retry 폭주가 큐로 새지 않음.

### Commit 2 — `1041ff0` Step 2: AI/룰 매핑 상수 + observability 토대
`AI_TO_RULE_LEVEL: dict[str, str]` 을 DRF / fastapi 양쪽에 정의. AI 4단계(normal/caution/predict_warn/danger) → 룰 3단계(normal/warning/danger) 환산의 단일 진실 공급원. Prometheus `rule_fire_suppressed_by_ai_total{device_id, channel, level}` counter 신설.

→ **암묵 매핑 회귀 차단**: `predict_warn` 이 warning/danger 중 무엇인지 곳곳에 박히면 mute 키 충돌 + 격상 bypass 깨짐.

### Commit 3 — `a862360` Step 3·4·5: 룰 누락 해소 + AI mute 가드
- **Step 4** `_CACHE_TTL = 3600 → 300` (가스/전력) — 그 후 Commit 4 에서 다시 60s 로 단축.
- **Step 5** WARNING `task_key` TTL 을 `WARNING_DURATION_SEC + 5` 로 분리 + `fire_warning_alarm_task` / `fire_power_warning_task` 정상 종료 시 `cache.delete(task_key)`.
- **Step 3** `alarm_dedupe.py` 에 `mark_ai_recent` / `is_ai_mute_active` raw redis 헬퍼 + `power_alarm` DANGER/WARNING 분기 가드 + `fastapi/services/ai_mute.py` 신규. 키는 발화 level '이하' 분리(`ai_fired:{device}:{channel}:{rule_level}`)로 격상(AI=warning, 룰=danger) bypass 자연 표현.
- **§2 회귀 가드** DANGER 분기에서 mute 활성 시에도 pending WARNING task 를 가드 이전에 revoke (stale 타이머 발화 차단).

### Commit 4 — `f9bf4e4` tune: dedup cooldown 5분 → 1분
[5번 문서 §9](../../../../skill/AI/5️⃣%20알림%20고도화.md) "동일 작업자+센서+구역+위험단계 1분 내 1회" 권장 패턴 정렬. `_CACHE_TTL=60`, `RENOTIFY_COOLDOWN_MINUTES=1`, `PUSH_DEDUP_TTL_SEC=30` (race 마진). 산업 안전 도메인에서 위험 지속은 미대응 신호이므로 1분 cadence 가 자연 escalation 트리거.

### Commit 5 — `1c1551f` fix: AI mute 식별자 일치 (회귀 픽스)
시연 검증 중 발견 — Redis 키 `ai_fired:63200c3afd12:1:danger` 는 fastapi 가 IoT raw id 로 set, DRF 는 `ai_fired:1:1:danger` (PK) 로 read 해서 mismatch. `power_alarm` 의 mute 가드만 `device.device_id` (raw IoT) 로 변경, 다른 코드 경로(try_transition, fire_*_task)는 PK 그대로 사용.

---

## 시나리오 검증 결과 (2026-05-15)

### 검증 환경
- Docker Compose 7-서비스 ([[runtime_docker_environment]]) 기동
- 더미 시뮬레이터: `power_dummy` + `gas_dummy` + `position_dummy` (3종)
- 시나리오 모드: `/internal/scenario/mode` 로 `mixed/warning/normal/danger/overload` 등 전환
- 관찰: `make logs-celery|drf|fastapi`, Prometheus (`http://localhost:9090`), `redis-cli`

### 결과 표

| # | 시나리오 | 결과 | 근거 |
|---|---|---|---|
| **1** | 가스 단일 센서 계속 danger → 1분 간격 재발화 | ✅ | Celery 로그 — `DANGER 알람 푸시 sensor=1 gas=o2/co2/no2/so2/o3/nh3/voc new_event=False` 9개 가스 cooldown 통과 후 재푸시. counter `alarm_fired_total{alarm_type=gas_threshold, risk_level=danger}=180` 누적 |
| **2** | warning → normal → danger 시퀀스 → 두 번째 danger 정상 fire | ✅ | 시퀀스 흐름 정상 (mode 전환 사이 WARNING/clear/DANGER fire 모두 발화). `gas_threshold warning=85, danger=180` |
| **3** | 전력 CH1 watt AI 발화 → 같은 채널 룰 60s mute | ✅ | Redis `ai_fired:63200c3afd12:1:{normal,warning,danger}` raw IoT id 일치 set. counter `rule_fire_suppressed_by_ai_total{device_id=63200c3afd12, channel=1, level=warning}=27` 증가 (식별자 픽스 직후 baseline) |
| **4** | AI predict_warn → 룰 danger 격상 bypass | ✅ | unit test `test_escalation_bypass_warning_mark_does_not_block_danger` 통과. 시연 환경에선 더미 모드로 AI=warning + 룰=danger 동시 강제 어려워 단위 테스트로 대체 |
| **5** | fastapi 일시 5xx → Celery retry → fingerprint dedup | ✅ | counter `alarm_push_dedup_hits_total = 1095` 누적 — 시연 진행 중 자연 retry 가 모두 dedup 으로 차단됨 (의도된 docker pause 시나리오는 fire 타이밍 갭이 안 맞아 추가 hit 없었으나, baseline 자체가 픽스 작동 입증) |
| **6** | Prometheus 시계열 종합 | ✅ | `alarm_fired_total` 6 시계열 (gas/power/geofence × warning/danger) 모두 증가. `rule_fire_suppressed_by_ai_total`, `alarm_push_dedup_hits_total` 운영 누적 증가. |

### 자동 테스트
- DRF `pytest apps/alerts/ apps/monitoring/ apps/ml/` — 95/95 ✅
- fastapi `pytest tests/` — 74/74 ✅
- 신규 단위 테스트:
  - `apps/alerts/tests/test_ai_mute_guard.py` (10 종 — mark/check / 격상 bypass / TTL / `power_alarm` 통합 + 회귀 가드)
  - `fastapi/tests/test_push_alarm_dedup.py` (9 종 — fingerprint 분기 / dedup hit / TTL 인자화)
  - `fastapi/tests/test_ai_mute_marking.py` (8 종 — forward 통합 / silent fail / 격상 bypass 키 분리)

### 코드 리뷰 (review skill 셀프)
- 발견 후 즉시 해소된 회귀: 1건 (DANGER 분기 가드의 pending WARNING revoke 누락 — Commit 3 안에서 함께 픽스)
- 식별자 mismatch: 1건 (시연 검증 중 발견 → Commit 5 별도 픽스)
- 향후 정비 권장 (회귀 위험 없음): 코드 중복 3건, fixture 격리 1건 — 본 PR 외 백로그

---

## 별개 발견 사항 (본 PR 범위 외)

검증 과정에서 노출됐으나 본 PR 의 범위(알람 백엔드 흐름)와 다른 이슈들. 별도 PR 권장.

| # | 이슈 | 위치 | 영향 |
|---|---|---|---|
| 1 | 가스 AI 추론 실패: `X has 12 features, but IsolationForest is expecting 4 features as input` | `fastapi/gas/services/gas_service.py` IF feature builder | 가스 AI 자체 미작동 (다른 작업자 진행 중, [[ai_anomaly_scope_2026_05_11]]) |
| 2 | 브라우저 `/ws/worker/1/` 폭주: `action=forbidden token_user=1 path_user=1` | `fastapi/websocket/routers/ws_router.py` | log noise. 토큰 일치인데 forbidden — 권한 검증 로직 점검 필요 |
| 3 | `POST /api/internal/integration-logs/` 매번 403 | `drf/apps/operations/views/internal/integration_log.py` IP 화이트리스트 | docker 네트워크(172.18.0.x)는 localhost 가 아니라 거절. alarm_router 패턴 따라 `INTERNAL_SERVICE_TOKEN` Bearer 인증으로 통일 권장 |
| 4 | 프론트 알람 팝업 정책: "조치 완료 안 하면 새 알람 팝업 안 보이고 소리만" | `drf/static/js/dashboard/panels/` | 백엔드 push 는 정상. 프론트 측 활성 Event 검사 로직이 1분 cadence 와 부정합. 5번 문서 §3 "신규 강조 / 미확인 카운터" 와 묶어 별도 sprint |

---

## 향후 백로그

1. **Event 그룹 병합 (옵션 2B)** — "AI=관측 / 룰=판단을 같은 사건"으로 보는 구조적 답. `event_type` 의미 재설계 + UI + policy_matcher + 마이그레이션. 시연 후 RFC.
2. **AlertHistory 모델 + 외부 채널** — Slack/Discord 연동 sprint 와 묶어 도입. 5번 문서 §8.
3. **가스 AI 완성 후 가스 룰에 AI mute 가드** — Step 3 헬퍼 재사용. `gas_alarm.py` 에 가드만 추가.
4. **WARNING 카운트다운 비대칭** (가스 30s vs 전력 3s) — 별도 PR, 시연 후 재평가.
5. **운영 데이터 1~2주 후 cooldown 재평가** — `_CACHE_TTL=60` / `RENOTIFY_COOLDOWN_MINUTES=1` / `PUSH_DEDUP_TTL_SEC=30` 의 실제 alert fatigue / 누락 비율 측정. 위험 단계별 차등 (Critical 1m / Warning 3m) 필요 시 dict/함수 리팩토링.
6. **fixture 격리 보강** — `apps/alerts/tests/test_ai_mute_guard.py` 의 `clear_cache` 가 raw redis `ai_fired:*` 키도 명시 삭제하도록.

---

## 변경 파일 인덱스

### DRF
- [`apps/alerts/services/alarm_dedupe.py`](../../../../drf-server/apps/alerts/services/alarm_dedupe.py) — `mark_ai_recent` / `is_ai_mute_active` 추가
- [`apps/alerts/tasks.py`](../../../../drf-server/apps/alerts/tasks.py) — fire_warning_* 정상 종료 시 `cache.delete(task_key)`
- [`apps/alerts/tests/test_ai_mute_guard.py`](../../../../drf-server/apps/alerts/tests/test_ai_mute_guard.py) — 신규 (10 종)
- [`apps/core/constants.py`](../../../../drf-server/apps/core/constants.py) — `AI_TO_RULE_LEVEL`
- [`apps/core/metrics.py`](../../../../drf-server/apps/core/metrics.py) — `RULE_FIRE_SUPPRESSED_BY_AI_TOTAL`
- [`apps/alerts/services/event_service.py`](../../../../drf-server/apps/alerts/services/event_service.py) — `RENOTIFY_COOLDOWN_MINUTES = 1`
- [`apps/monitoring/services/gas_alarm.py`](../../../../drf-server/apps/monitoring/services/gas_alarm.py) — `_CACHE_TTL=60`, `_TASK_KEY_TTL`
- [`apps/monitoring/services/power_alarm.py`](../../../../drf-server/apps/monitoring/services/power_alarm.py) — `_CACHE_TTL=60`, `_TASK_KEY_TTL`, mute 가드 (`device.device_id`), §2 회귀 가드

### fastapi
- [`core/constants.py`](../../../../fastapi-server/core/constants.py) — 신규, `AI_TO_RULE_LEVEL`
- [`services/ai_mute.py`](../../../../fastapi-server/services/ai_mute.py) — 신규, Redis 직접 마킹
- [`services/anomaly_alarm.py`](../../../../fastapi-server/services/anomaly_alarm.py) — `forward_inference_e2e` 안 `mark_ai_recent` fire-and-forget 호출
- [`websocket/services/alarm_queue.py`](../../../../fastapi-server/websocket/services/alarm_queue.py) — fingerprint dedup, `PUSH_DEDUP_TTL_SEC=30`, `push_alarm_dedup_hits_total`
- [`tests/test_push_alarm_dedup.py`](../../../../fastapi-server/tests/test_push_alarm_dedup.py) — 신규 (9 종)
- [`tests/test_ai_mute_marking.py`](../../../../fastapi-server/tests/test_ai_mute_marking.py) — 신규 (8 종)
