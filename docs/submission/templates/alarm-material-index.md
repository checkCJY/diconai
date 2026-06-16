# 알람 시스템 자료 인덱스 — 시연 2026-06-14 제출용

> **목적**: 본인 담당 영역 **알람 시스템 (CM-07 알람 팝업 + MN-04 geofence 알람 + T1~T7 작업)** 의 자료를 한 자리에 모음.
> **짝 문서**: [기술문서-자료인덱스.md](기술문서-자료인덱스.md) 의 7장 / 6장 / 10장 부분을 본 문서로 깊게 보강. 작성 시 둘 다 참조.
> **본인 담당 영역**: 알람 시스템 (재설계 + T1~T7) + 전력 AI 추론 [(power-ai 인덱스는 별도)](기술문서-자료인덱스.md).

---

## 0. 큰 그림 — 알람 E2E 흐름

```
[센서 측 발화 신호]                                              [브라우저]
    │
    ├─ 가스: gas_service 임계치 + IF 추론 ───┐
    ├─ 전력: anomaly_inference 5축 + decide_alarm ──┼─► push_alarm (Redis LPUSH "diconai:ws:alarms")
    └─ geofence: 위치 + 가스 위험 매핑 ───┘              │
                                                          │ (dedup fingerprint NX EX 30s)
                                                          ▼
    Celery (DRF)                                       broadcast_loop (1s BRPOP)
      ├─ fire_danger_alarm_task                            │
      ├─ fire_warning_alarm_task                           ▼
      └─ fire_geofence_alarm_task                       sensor_clients[]
        │                                                  │  worker_clients[user_id]
        ├─ create_alarm_and_event (atomic)                ▼
        │     ├─ AlarmRecord 생성                      [alarm-popup.js / alarm-ws.js]
        │     ├─ Event 생성/병합                          ├─ 모달 (danger)
        │     └─ EventLog (CREATED)                       ├─ 토스트 (warning + 회색 처리)
        ├─ AI mute 체크 (ai_fired:* Redis 키)             └─ localStorage _AckStore / _DedupStore
        └─ POST /internal/alarms/push/ (localhost 전용)
```

**핵심 의사결정 4가지** (이 흐름에 녹아있음):
1. **AI vs rule 동시 발화 방지** — `ai_fired:*` Redis 키 + `alarm_dedupe.is_ai_mute_active`
2. **rate limit + dedup** — 같은 sensor_identifier 60s rate limit + push 단계 fingerprint dedup 30s
3. **자동 해제 + 수동 ack** — Event 활성 유지 + EventAcknowledgement 분리
4. **AI source vs static source 분기** — decide_alarm 매트릭스 6 cell (T4 D2 결정)

---

## 1. 알람 시스템 진화 타임라인 (2026-05-09 ~ 2026-05-21)

> 본 타임라인이 **10장 트러블슈팅** + **11장 결론** 의 핵심 회고 자료.

| 시점 | 작업 | 의사결정 | 산출물 |
|---|---|---|---|
| 2026-05-09 | 알람 코드리뷰 | 전체 alerts/events 영역 회고 | [docs/codereviews/2026_05_09/04_alerts_events.md](../../../docs/archive/codereviews/2026_05_09/04_alerts_events.md) |
| 2026-05-14 | IF + 알람 binding (전력) | AI 결과 → AlarmRecord 영속화 | [docs/changelog/ml/if_alarm_binding_power_2026_05_14.md](../../../docs/archive/changelog/ml/if_alarm_binding_power_2026_05_14.md) |
| 2026-05-15 | **알람 시스템 재설계 ★** | PR #57 — 3대 요구 + 회색지대 5건 결정 | [skill/plan/alarm-system-redesign.md](../../plan/alarm-system-redesign.md) · [drf-server/docs/refactoring/alarm-system-redesign-2026-05-15.md](../../../drf-server/docs/refactoring/alarm-system-redesign-2026-05-15.md) · [memory: alarm-system-redesign-2026-05-15](../../../../../.claude/projects/-home-cjy-diconai/memory/alarm_system_redesign_2026_05_15.md) |
| 2026-05-15 | **AI mute + cooldown** | `ai_fired:*` Redis 키 도입 — AI vs rule 중복 알람 차단 | [docs/changelog/alarm_reliability/alarm_ai_mute_and_cooldown_2026_05_15.md](../../../docs/archive/changelog/alarm_reliability/alarm_ai_mute_and_cooldown_2026_05_15.md) · [memory: alarm-popup-policy-followups-2026-05-15](../../../../../.claude/projects/-home-cjy-diconai/memory/alarm_popup_policy_followups_2026_05_15.md) |
| 2026-05-15 | 알람 흐름도 stale 인지 | 5초 폴링 → Redis BRPOP 즉시 전환. 문서 stale 만 정정 (코드 truth source) | [memory: alarm-flow-doc-stale-2026-05-15](../../../../../.claude/projects/-home-cjy-diconai/memory/alarm_flow_doc_stale_2026_05_15.md) |
| 2026-05-17 | **D 옵션 (도메인별 결정)** | 가스 = 격하 / 전력 = un-downgrade — 알람 algorithm_source 분기 출발 | [docs/codereviews/2026_05_17/alarm-d-option-flow.md](../../../docs/archive/codereviews/2026_05_17/alarm-d-option-flow.md) · [drf-server/docs/refactoring/alarm-d-option-2026-05-17.md](../../../drf-server/docs/refactoring/alarm-d-option-2026-05-17.md) |
| 2026-05-17 | **Phase 2 — UI refactor** | 알람 팝업 UI 정리 (모달 vs 토스트 분리) | [drf-server/docs/refactoring/alarm-phase2-completion-2026-05-17.md](../../../drf-server/docs/refactoring/alarm-phase2-completion-2026-05-17.md) · [docs/codereviews/2026_05_17/alarm-phase2-flow.md](../../../docs/archive/codereviews/2026_05_17/alarm-phase2-flow.md) · [docs/changelog/alarm_reliability/ui_refactor_phase2.md](../../../docs/archive/changelog/alarm_reliability/ui_refactor_phase2.md) |
| 2026-05-19 | **T1+T6 (정보 통일)** | 알람 message·summary·algorithm_source workspace 통일. ML 용어 제거 (운영자 톤) | [skill/plan/alarm-t1-t6-info-unification.md](../../plan/alarm-t1-t6-info-unification.md) · [drf-server/docs/refactoring/2026_05_19_alarm_t1_t6.md](../../../drf-server/docs/refactoring/2026_05_19_alarm_t1_t6.md) |
| 2026-05-19 | **T3 (dedup 통일)** | push_alarm fingerprint dedup (NX EX 30s) — Celery retry 중복 차단 | [skill/plan/alarm-t3-dedup-unification.md](../../plan/alarm-t3-dedup-unification.md) · [drf-server/docs/refactoring/2026_05_20_alarm_t3_troubleshooting.md](../../../drf-server/docs/refactoring/2026_05_20_alarm_t3_troubleshooting.md) |
| 2026-05-19 | 알람 현황 코드리뷰 | as-is 전체 정리 | [docs/codereviews/2026_05_19/alarm-business-logic-as-is.md](../../../docs/archive/codereviews/2026_05_19/alarm-business-logic-as-is.md) · [integrated-issues-triage.md](../../../docs/archive/codereviews/2026_05_19/integrated-issues-triage.md) |
| 2026-05-19 | 5축 정책 → 알람 흐름 | 전력 5축 결합 결과를 algorithm_source 로 → AlarmRecord 영속화 | [docs/codereviews/2026_05_19/power-5axis-policy-flow.md](../../../docs/archive/codereviews/2026_05_19/power-5axis-policy-flow.md) |
| 2026-05-20 | **T4 (AI vs 정적 계층화) ★** | decide_alarm 6 매트릭스 + AI state 5종 — fastapi 가 단일 결정자 | [skill/plan/alarm-t4-ai-static-hierarchy.md](../../plan/alarm-t4-ai-static-hierarchy.md) + T4 changelogs 5종 |
| 2026-05-20 | **알람 3대 증상 진단** | `_AckStore` 24h 영구 차단 가설 + ack/RESOLVED 멘탈 모델 충돌 진단 | [docs/codereviews/2026_05_20/alarm-symptom-bottleneck-diagnosis.md](../../../docs/archive/codereviews/2026_05_20/alarm-symptom-bottleneck-diagnosis.md) · [memory: alarm-symptom-diagnosis-2026-05-20](../../../../../.claude/projects/-home-cjy-diconai/memory/alarm_symptom_diagnosis_2026_05_20.md) |
| 2026-05-20 | 외부 리뷰 피드백 | a/c path 충돌 가능성 — AI 알람 시 시그널 누락 위험 | [memory: alarm-dataflow-review-2026-05-20](../../../../../.claude/projects/-home-cjy-diconai/memory/alarm_dataflow_review_2026_05_20.md) |
| 2026-05-20 | **T1+T3 완료** | feature/0519_alarm_business_logic 10 commit 완료. 시연 전 적용 끝 | [memory: alarm-t1-t3-pause-2026-05-20](../../../../../.claude/projects/-home-cjy-diconai/memory/alarm_t1_t3_pause_2026_05_20.md) |
| 2026-05-20 | T4 진입 전 검증 | 12-step 코드 매핑 + source 5종 직교 도입 확정 | [memory: alarm-t4-pre-entry-verified-2026-05-20](../../../../../.claude/projects/-home-cjy-diconai/memory/alarm_t4_pre_entry_verified_2026_05_20.md) |

---

## 2. 핵심 컴포넌트 (8개 영역)

### 2.1 decide_alarm 6 매트릭스 (T4 D2)

| 자료 | 인용 |
|---|---|
| [fastapi-server/power/services/decide_alarm.py](../../../fastapi-server/power/services/decide_alarm.py) | 6 매트릭스 (AI state 5종 × static_risk → source 결정) — 순수 함수 |
| [skill/alarm/t4-d2-implementation-spec.md](../../alarm/t4-d2-implementation-spec.md) | T4 D2 구현 spec |
| [skill/alarm/t4-d2-changelog.md](../../alarm/t4-d2-changelog.md) | D2 적용 결과 |

```
| AI 상태             | 정적 결과 | source                       |
|---------------------|-----------|------------------------------|
| FIRED               | *         | "ai"                         |
| INFERRED_NORMAL     | fired     | "static_cover_miss"          |
| INFERRED_FAILED     | fired     | "static_cover_inference_fail"|
| DISABLED            | fired     | "static_no_ai_available"     |
| WARMING_UP          | fired     | "static_cover_warmup"        |
| None (Redis 장애)   | fired     | "static_no_ai_available"     |
| *                   | not fired | None (알람 없음)              |
```

### 2.2 push_alarm + fingerprint dedup (T3)

| 자료 | 인용 |
|---|---|
| [fastapi-server/websocket/services/alarm_queue.py](../../../fastapi-server/websocket/services/alarm_queue.py) | `push_alarm` + `_payload_fingerprint` (event_id / ai_meta / clear / cover 4 분기) |
| [drf-server/apps/alerts/services/alarm_dedupe.py](../../../drf-server/apps/alerts/services/alarm_dedupe.py) | DRF 측 dedupe + AI mute 가드 |
| [docs/changelog/alarm_reliability/alarm_reliability_phase1.md](../../../docs/archive/changelog/alarm_reliability/alarm_reliability_phase1.md) | Phase 1 신뢰성 작업 |

**dedup fingerprint 4 종**:
1. 룰 알람 — `event:{event_id}:{risk_level}` (RESOLVED 신호는 `:resolved` 별 suffix)
2. AI 알람 — `ai:{alarm_type}:{device_id}:{channel}:{risk_level}`
3. 정상화 — `clear:{alarm_type}:{source_label}`
4. 정적 cover — `cover:{source}:{source_label}:{risk_level}`

### 2.3 AI mute (ai_fired:*) — AI vs rule 중복 방지

| 자료 | 인용 |
|---|---|
| [fastapi-server/services/ai_mute.py](../../../fastapi-server/services/ai_mute.py) | `mark_ai_recent` / `mark_ai_state` / `AIInferenceState` 5종 |
| [drf-server/apps/alerts/services/alarm_dedupe.py:60-132](../../../drf-server/apps/alerts/services/alarm_dedupe.py) | `is_ai_mute_active` 가드 |
| [docs/changelog/alarm_reliability/alarm_ai_mute_and_cooldown_2026_05_15.md](../../../docs/archive/changelog/alarm_reliability/alarm_ai_mute_and_cooldown_2026_05_15.md) | AI mute + cooldown 도입 |
| [skill/study/power-ai-종합문서 §4.4](../../study/power-ai-종합문서-2026-05-21.md) | rate limit (60s) + AI mute 동기 |

**의도**: AI 가 발화하면 Redis 에 `ai_fired:{device_id}:{channel}` 키 60s TTL → DRF Celery 의 rule 알람이 이 키 보고 mute. **운영자에게 같은 채널 알람 중복 표시 차단**.

### 2.4 rate limit (60s, sensor_identifier 단위)

| 자료 | 인용 |
|---|---|
| [fastapi-server/power/services/anomaly_inference.py:416-440](../../../fastapi-server/power/services/anomaly_inference.py#L416-L440) | `_last_fired_at` dict + RATE_LIMIT_SEC=60 |
| [skill/study/power-ai-종합문서 §4.4.2 30s vs 60s 검토](../../study/power-ai-종합문서-2026-05-21.md) | "폭주 회피 > 시연 가시성" 결정 |

### 2.5 Event lifecycle (create / merge / acknowledge / resolve)

| 자료 | 인용 |
|---|---|
| [drf-server/apps/alerts/services/event_service.py](../../../drf-server/apps/alerts/services/event_service.py) | `create_alarm_and_event` (atomic + select_for_update) |
| [drf-server/apps/alerts/services/merge_policy.py](../../../drf-server/apps/alerts/services/merge_policy.py) | 동일 이벤트 중복 병합 정책 |
| [skill/DB/alerts/event.py.md](../../DB/alerts/event.py.md) | Event 모델 |
| [skill/DB/alerts/event_acknowledgement.py.md](../../DB/alerts/event_acknowledgement.py.md) | EventAcknowledgement (`_AckStore` 와 연계) |
| [skill/DB/alerts/event_log.py.md](../../DB/alerts/event_log.py.md) | EventLog (CREATED / ACK / RESOLVED) |
| [skill/plan/alarm-record-integration.md](../../plan/alarm-record-integration.md) | AlarmRecord ↔ Event 통합 plan |

### 2.6 algorithm_source 6 종 + 운영자 워딩 (T1+T6)

| 자료 | 인용 |
|---|---|
| [drf-server/apps/core/constants.py `ALGORITHM_SOURCE_PHRASE`](../../../drf-server/apps/core/constants.py) | 6 라벨 한글 워딩 (운영자 톤 통일) |
| [fastapi-server/power/services/anomaly_inference.py `_ALGORITHM_SOURCE_PHRASE`](../../../fastapi-server/power/services/anomaly_inference.py) | fastapi 측 동일 (단일 동기) |
| [skill/alarm/t4-source-message-spec.md](../../alarm/t4-source-message-spec.md) | source 별 메시지 패턴 spec |
| [skill/plan/alarm-t1-t6-info-unification.md](../../plan/alarm-t1-t6-info-unification.md) | T1+T6 통일 plan |
| [drf-server/docs/refactoring/2026_05_19_alarm_t1_t6.md](../../../drf-server/docs/refactoring/2026_05_19_alarm_t1_t6.md) | T1+T6 적용 보고 |
| [memory: operator-mental-model-simplicity](../../../../../.claude/projects/-home-cjy-diconai/memory/operator_mental_model_simplicity.md) | "운영자 멘탈 모델 단순함 우선 — AI/ML 출처는 엔지니어 채널로" — T1 칩 제거 사례 |

| algorithm_source | 운영자 워딩 |
|---|---|
| `isolation_forest` | 이상 수치 탐지 |
| `arima` | 이상 패턴 탐지 |
| `combined` | 이상 수치·패턴 동시 탐지 |
| `zscore` | 통계 이상 수치 |
| `change_point` | 패턴 변화 탐지 |
| `night_abnormal` | 야간 이상 가동 |

### 2.7 geofence 알람 (MN-04)

| 자료 | 인용 |
|---|---|
| [docs/features/cjy_MN-04_geofence_alarm.md](../../../docs/features/cjy_MN-04_geofence_alarm.md) | geofence 알람 기능정의서 (본인) |
| [skill/지오펜스 알람 경로에 대해서.md](../../지오펜스%20알람%20경로에%20대해서.md) | geofence 알람 경로 정리 (본인) |
| [skill/알람 시나리오 관련 파일과 흐름도.md](../../알람%20시나리오%20관련%20파일과%20흐름도.md) | 위치 → 지오펜스 진입 → 알람 발화 시나리오 (본인) |
| [drf-server/apps/positioning/services/position_service.py](../../../drf-server/apps/positioning/services/position_service.py) | 핵심 오케스트레이터 (`update_geofence_cache` + `_get_dangerous_sensors_in_geofence`) |
| [drf-server/apps/geofence/models/geofence.py](../../../drf-server/apps/geofence/models/geofence.py) | `contains_point` Ray Casting 알고리즘 |
| [drf-server/apps/alerts/tasks.py `fire_geofence_alarm_task`](../../../drf-server/apps/alerts/tasks.py) | geofence 알람 발화 Celery 태스크 |

### 2.8 알람 팝업 UI (CM-07)

| 자료 | 인용 |
|---|---|
| [docs/features/cjy_CM-07_알람팝업개선_기능정의서.md](../../../docs/features/cjy_CM-07_알람팝업개선_기능정의서.md) | 알람 팝업 기능정의서 (본인) |
| [drf-server/static/js/shared/alarm-popup.js](../../../drf-server/static/js/shared/alarm-popup.js) | AlarmPopup 컨트롤러 |
| [drf-server/static/js/shared/alarm-popup.css](../../../drf-server/static/js/shared/alarm-popup.css) | 색상 토큰 + 토스트/모달 스타일 |
| [drf-server/static/js/dashboard/websocket.js](../../../drf-server/static/js/dashboard/websocket.js) | WS 수신 → `AlarmPopup.show()` |
| [drf-server/docs/refactoring/alarm-phase2-completion-2026-05-17.md](../../../drf-server/docs/refactoring/alarm-phase2-completion-2026-05-17.md) | UI Phase 2 refactor |

---

## 3. 데이터 흐름 (E2E, 도메인별 차이)

### 3.1 가스 알람 흐름

```
gas_dummy → POST /api/sensors/gas → gas_router → process_gas_data
  ├ 임계치 비교 (core/gas_thresholds.py)
  ├ IF 추론 (sensor_type="gas", 15피처 다변량)
  └ 위험 시 Celery 트리거: fire_danger_alarm_task / fire_warning_alarm_task
     ├ create_alarm_and_event (atomic): AlarmRecord + Event (ACTIVE)
     │   ├ 활성 Event 있으면 merge_policy → AlarmRecord 만 추가
     │   └ 없으면 새 Event 생성 + EventLog(CREATED)
     └ POST /internal/alarms/push/ (localhost 전용)
        └ push_alarm → Redis LPUSH "diconai:ws:alarms"
            └ broadcast_loop BRPOP → sensor_clients[] broadcast
                └ alarm-popup.js: 모달(danger) / 토스트(warning)
```

### 3.2 전력 알람 흐름 (5축 + decide_alarm)

```
power_dummy (watt) → POST /api/power/watt → power_router → process_anomaly_inference
  ├ 채널 16개 루프
  │   ├ quality_guard (comm_failure/overflow/stuck) skip
  │   ├ 정적 임계 평가 (모든 채널 공통)
  │   ├ AI 활성 여부 (4채널만)
  │   │   ├ 비활성 → DISABLED → decide_alarm
  │   │   ├ 윈도우 < 30 → WARMING_UP → decide_alarm
  │   │   └ 윈도우 ≥ 30 → 5축 추론 (IF / ARIMA / Z / CP / threshold)
  │   │       ├ combine_risk_5axis → combined + escalation_source
  │   │       ├ night_abnormal 시각 격상
  │   │       ├ algorithm_source priority 6단계 결정
  │   │       ├ rate limit (60s) + AI mute 마킹
  │   │       └ decide_alarm → source (ai vs static_*)
  │   └ push_alarm (Redis LPUSH) + forward_inference_e2e (DRF MLAnomalyResult + AlarmRecord)
  │       └ broadcast_loop → 브라우저
```

**가스 vs 전력 차이**:
- 가스: **1 단계 흐름** (IF + 임계치만 → Celery 직접 발화)
- 전력: **5 단계 흐름** (quality_guard → AI state + 5축 → decide_alarm → push) + AI source 분리

### 3.3 geofence 알람 흐름

```
position_dummy → POST /api/positioning/receive → position_router
  └ position_service (FastAPI) → 비동기 DRF 전달
     └ WorkerPositionReceiveView → position_service (DRF)
        ├ update_geofence_cache → 현재 지오펜스 갱신
        ├ _get_dangerous_sensors_in_geofence → 가스 위험 매핑
        └ fire_geofence_alarm_task (Celery)
           ├ create_alarm_and_event → AlarmRecord + Event
           └ /internal/alarms/push/ → worker_clients[user_id] 개인 전송 (sensor_clients[] 전체 X)
```

**geofence 차이**: 개인 작업자 알람 → `worker_clients[user_id]` 매핑으로 본인에게만 송신 (sensor_clients 브로드캐스트와 분리).

---

## 4. DB 스키마 (alerts 앱 7 모델)

| 모델 | 자료 | 핵심 필드 |
|---|---|---|
| **AlarmRecord** | [skill/DB/alerts/alarm_record.py.md](../../DB/alerts/alarm_record.py.md) | event(FK), risk_level, source, source_device_id, channel, **algorithm_source**, summary, measured_value, detected_at |
| **Event** | [skill/DB/alerts/event.py.md](../../DB/alerts/event.py.md) | facility(FK), alarm_type, status(ACTIVE/RESOLVED), opened_at, resolved_at — 중복 발화는 같은 활성 Event 에 AlarmRecord 만 추가 |
| **EventAcknowledgement** | [skill/DB/alerts/event_acknowledgement.py.md](../../DB/alerts/event_acknowledgement.py.md) | event(FK), user(FK), acknowledged_at — 다중 관리자 환경의 "확인 중" 시그널 |
| **EventLog** | [skill/DB/alerts/event_log.py.md](../../DB/alerts/event_log.py.md) | event(FK), log_type(CREATED/ACK/RESOLVED), timestamp — APPEND-ONLY |
| **HazardType** | [skill/DB/alerts/hazard_type.py.md](../../DB/alerts/hazard_type.py.md) | 알람 type 분류 (gas_danger / power_overload / power_anomaly_ai / geofence 등) |
| **HazardTypeGroup** | [skill/DB/alerts/hazard_type_group.py.md](../../DB/alerts/hazard_type_group.py.md) | 알람 type 카테고리 그룹 |
| **AlertPolicy** | [skill/DB/alerts/alert_policy.py.md](../../DB/alerts/alert_policy.py.md) | 알람 정책 (자동 해제 vs 수동 해제 등) |

**연관 모델**:
- [MLAnomalyResult](../../DB/ml/ml_anomaly_result.py.md) — AI 추론 결과 영속화 (AlarmRecord 와 ml_id FK 연계)
- [SystemLog](../../DB/core/system_log.py.md) — 알람 lifecycle 감사 로그 (APPEND-ONLY)
- [Notification](../../DB/notifications/notification.py.md) — 채널별 알림 발송 이력

---

## 5. 의사결정·트레이드오프

### 5.1 알람 시스템 재설계 3대 요구 (2026-05-15)

[memory: alarm-system-redesign-2026-05-15](../../../../../.claude/projects/-home-cjy-diconai/memory/alarm_system_redesign_2026_05_15.md) 가 명시:

| 요구 | 결정 |
|---|---|
| **시각화 단순화** | 모달(danger) + 토스트(warning) 분리. 같은 채널 중복 1줄 표시 |
| **운영자 ack 추적** | EventAcknowledgement 모델 분리. _AckStore localStorage 와 sync |
| **자동 해제 + 수동 해제 정책** | 자동 (상태 전이) + 관리자 ack (수동) — `critical` 등급은 수동 강제 (4차) |

### 5.2 의사결정 매트릭스

| # | 결정 | 채택 | 회피 | 정당화 |
|---|---|---|---|---|
| 1 | **알람 결정자** | fastapi 단일 (T4 D2) | DRF Celery 와 fastapi 양쪽 | fastapi 가 5축 + 정적 평가 모두 가짐 → 단일 결정자가 race 없음 |
| 2 | **AI vs rule 중복** | `ai_fired:*` Redis TTL 60s + alarm_dedupe.is_ai_mute_active | event_id 기반 매칭 | TTL 단순 + 다른 시스템 (geofence/static cover) 도 같은 패턴 재활용 가능 |
| 3 | **dedup 위치** | push_alarm 진입부 fingerprint NX EX 30s | Celery task 안 dedup | choke point 차단 — Celery retry 도 막힘 |
| 4 | **rate limit 단위** | sensor_identifier (60s) | facility / event_id / alarm_type | 같은 센서 폭주 회피 + 다른 센서는 영향 X |
| 5 | **algorithm_source 라벨** | 6 종 (priority 매트릭스) | "AI 발화" 단일 라벨 | 운영자 추적 가능 ("어느 축이 잡았나") + 시연 가치 |
| 6 | **algorithm_source 워딩 (T1+T6)** | 운영자 한글 ("이상 수치 탐지" 등) | 코드 라벨 그대로 ("isolation_forest") | 운영자 멘탈 모델 우선 — AI/ML 출처는 엔지니어 채널로 |
| 7 | **AI source 분리 (T4)** | `source=ai` vs `source=static_*` 6 매트릭스 | 단일 source | AI 침묵 시 정적이 cover 한다는 framing 명시 + 운영 추적 |
| 8 | **Event merge 정책** | 같은 facility + 같은 alarm_type 의 활성 Event 에 AlarmRecord 만 추가 | 매번 새 Event | 운영자 view 단순 (한 사건당 한 Event) |
| 9 | **WS broadcast 단위** | sensor_clients[] (가스/전력) vs worker_clients[user_id] (geofence) | 단일 broadcast | 개인 알람은 본인만 봄 — 권한·집중도 |
| 10 | **모달 vs 토스트** | danger=모달 / warning=토스트 (회색 처리 옵션 보류) | 둘 다 토스트 | 위험도별 사용자 주의 차등 |

### 5.3 보류된 결정 (시연 후 결정)

| 항목 | 보류 사유 | 결정 시점 |
|---|---|---|
| 정상화 → 회색 처리 디자인 | UX 결정 미완 | 시연 후 |
| 작업자 디바이스 종류·UX | 모바일 vs 웨어러블 미정 | Phase 3 (시연 후) |
| `_AckStore` 24h TTL → 영구 ack 분리 | 멘탈 모델 충돌 발견 (2026-05-20 진단), 패치 보류 | 시연 후 sprint |
| T2 (역할 분리) / T4 D5 (정적 cover AlarmRecord 영속화) / T5 / T7 | 시연 일정 제약 | 시연 후 sprint |

---

## 6. 트러블슈팅 사례 (10장 직접 인용)

### 6.1 ★ 알람 3대 증상 진단 (2026-05-20)

| 자료 | 핵심 |
|---|---|
| [docs/codereviews/2026_05_20/alarm-symptom-bottleneck-diagnosis.md](../../../docs/archive/codereviews/2026_05_20/alarm-symptom-bottleneck-diagnosis.md) | 진단 보고서 |
| [memory: alarm-symptom-diagnosis-2026-05-20](../../../../../.claude/projects/-home-cjy-diconai/memory/alarm_symptom_diagnosis_2026_05_20.md) | 1순위 `_AckStore` 24h 영구 차단 가설 + ack/RESOLVED 멘탈 모델 충돌 |

**문제**: 운영자가 ack 한 알람이 24h 동안 재발화 안 됨 (의도 vs 실제 충돌).
**원인**: localStorage `_AckStore` TTL 24h 가 RESOLVED 신호와 분리 안 됨 — 운영자 멘탈 모델 ("ack 했다고 영구 차단 아님") 과 코드 동작 충돌.
**해결**: 진단만 수행, 수정은 시연 후 sprint (멘탈 모델 명시 → 패치).

### 6.2 ★ T3 dedup 트러블슈팅 (2026-05-19~20)

| 자료 | 핵심 |
|---|---|
| [drf-server/docs/refactoring/2026_05_20_alarm_t3_troubleshooting.md](../../../drf-server/docs/refactoring/2026_05_20_alarm_t3_troubleshooting.md) | T3 적용 후 트러블슈팅 |
| [skill/plan/alarm-t3-dedup-unification.md](../../plan/alarm-t3-dedup-unification.md) | T3 plan |

**문제**: Celery `_push_to_ws` retry (max 3) 가 같은 payload 를 최대 3번 push → Redis 큐 중복 적재.
**원인**: choke point 부재.
**해결**: push_alarm 진입부 SET NX EX 30s fingerprint dedup. 룰 (event_id) / AI (anomaly_meta) / clear / cover 4 분기.
**효과**: 운영 중복 push 0% (`push_alarm_dedup_hits` Prometheus 카운터로 추적).

### 6.3 ★ AI vs rule 중복 알람 (2026-05-15)

| 자료 | 핵심 |
|---|---|
| [docs/changelog/alarm_reliability/alarm_ai_mute_and_cooldown_2026_05_15.md](../../../docs/archive/changelog/alarm_reliability/alarm_ai_mute_and_cooldown_2026_05_15.md) | AI mute 도입 |
| [memory: alarm-popup-policy-followups-2026-05-15](../../../../../.claude/projects/-home-cjy-diconai/memory/alarm_popup_policy_followups_2026_05_15.md) | Phase 1 후속 |

**문제**: 같은 채널의 AI 알람 + rule 기반 알람 동시 발화 → 운영자에게 같은 신호 2개 표시.
**원인**: fastapi (AI) 와 DRF Celery (rule) 가 같은 신호에 각자 발화.
**해결**: fastapi 가 AI 발화 시 `ai_fired:{device_id}:{channel}` Redis 키 60s TTL 마킹 → DRF rule task 가 `is_ai_mute_active` 가드로 mute.
**효과**: AI 발화 중인 채널은 rule 알람 무발화 — 운영자 알람 중복 0%.

### 6.4 알람 흐름도 stale (2026-05-15)

| 자료 | 핵심 |
|---|---|
| [memory: alarm-flow-doc-stale-2026-05-15](../../../../../.claude/projects/-home-cjy-diconai/memory/alarm_flow_doc_stale_2026_05_15.md) | skill/알람*.md 의 WS broadcast 섹션은 옛 5초 폴링 — 현재는 Redis BRPOP 즉시 |

**교훈**: 문서 stale 발견. **코드를 truth source 로**. 메모리에 포인터만 — 본인이 작업 시 코드 우선 확인.

### 6.5 알람 토스트 격상 타이머 race (2026-05-19)

| 자료 | 핵심 |
|---|---|
| [skill/troubleshooting/0519_alarm-toast-escalate-timer-race.md](../../troubleshooting/0519_alarm-toast-escalate-timer-race.md) | 토스트 격상 타이머 race |

### 6.6 alarm-popup Docker 트러블슈팅

| 자료 | 핵심 |
|---|---|
| [docs/infra/troubleshooting_alarm_popup_docker.md](../../../docs/infra/troubleshooting_alarm_popup_docker.md) | Docker 환경 알람 팝업 이슈 |

### 6.7 외부 리뷰 a/c path 충돌 (2026-05-20)

| 자료 | 핵심 |
|---|---|
| [memory: alarm-dataflow-review-2026-05-20](../../../../../.claude/projects/-home-cjy-diconai/memory/alarm_dataflow_review_2026_05_20.md) | 외부 리뷰어 4가지 지적. #1 (a/c path 충돌) — AI 알람 시 시그널 누락 위험. 조치 보류 → 시연 후. |

---

## 7. 11장 매핑

### 7.1 4장 요구사항-구현 매핑

| 요구사항 | 본 인덱스 | 자료 |
|---|---|---|
| CM-07 알람 팝업 개선 | §2.8 | [docs/features/cjy_CM-07_알람팝업개선_기능정의서.md](../../../docs/features/cjy_CM-07_알람팝업개선_기능정의서.md) |
| MN-04 geofence 알람 | §2.7 | [docs/features/cjy_MN-04_geofence_alarm.md](../../../docs/features/cjy_MN-04_geofence_alarm.md) |
| 알람 시스템 재설계 | §1, §5.1 | [skill/plan/alarm-system-redesign.md](../../plan/alarm-system-redesign.md) |
| T1+T6 정보 통일 | §2.6 | [skill/plan/alarm-t1-t6-info-unification.md](../../plan/alarm-t1-t6-info-unification.md) |
| T3 dedup 통일 | §2.2, §6.2 | [skill/plan/alarm-t3-dedup-unification.md](../../plan/alarm-t3-dedup-unification.md) |
| T4 AI vs 정적 계층화 | §2.1, §5.2 #7 | [skill/plan/alarm-t4-ai-static-hierarchy.md](../../plan/alarm-t4-ai-static-hierarchy.md) |
| AI mute (Phase 1) | §2.3 | [docs/changelog/alarm_reliability/alarm_ai_mute_and_cooldown_2026_05_15.md](../../../docs/archive/changelog/alarm_reliability/alarm_ai_mute_and_cooldown_2026_05_15.md) |

### 7.2 6장 DB 설계

§4 의 7개 모델 + 연관 3개 (MLAnomalyResult / SystemLog / Notification). ERD 작성 시 본 section 그대로 인용.

### 7.3 ★ 7장 실시간 대시보드·위험판단·알람 (본인 핵심 영역)

**7장의 뼈대 = 본 인덱스 전체**. 가이드 4단 패턴 (무엇/왜/어떻게/증빙) 적용:

| 단 | 7장 채움 |
|---|---|
| 무엇 | 다채널 알람 시스템 — fastapi 단일 결정자 (T4) + AI source 분리 + Redis BRPOP 실시간 broadcast + AI vs rule 중복 방지 |
| 왜 | 운영자 관점에서 "한 사건당 한 알람" + "AI 가 잡았는지 추적 가능" + "AI 침묵 시에도 정적이 cover" 3대 요구 |
| 어떻게 | decide_alarm 6 매트릭스 + push_alarm fingerprint dedup + AI mute (ai_fired:* TTL 60s) + algorithm_source 6 종 priority + EventAcknowledgement 분리 |
| 증빙 | 대시보드 캡처 (모달 + 토스트 + 회색) + Grafana 패널 (POWER_AI_ALARM_FIRED_TOTAL by algorithm_source) + 알람 발화 시나리오 영상 |

**7장 권장 분량 배분 (2 페이지)**:
- 1p: 알람 흐름 (§3 + §2.1 decide_alarm 매트릭스)
- 1p: AI vs rule 중복 방지 (§2.3 + §6.3) + algorithm_source (§2.6)

### 7.4 ★ 10장 트러블슈팅 (본인 핵심 영역)

§6 의 3 사례 (T3 dedup / AI vs rule 중복 / 알람 3대 증상 진단) 가 직접 인용 가능. Before/After 표 패턴:

| 사례 | Before | After |
|---|---|---|
| **T3 dedup** | Celery retry → 같은 push 최대 3회 중복 | NX EX 30s fingerprint dedup → 중복 push 0% |
| **AI vs rule 중복** | 같은 채널 AI + rule 동시 발화 → 운영자 알람 2개 | AI mute (`ai_fired:*` TTL 60s) → 중복 0% |
| **알람 3대 증상 진단** | ack 한 알람 24h 영구 차단 (운영자 멘탈 모델 충돌) | 진단 완료, 시연 후 sprint 에서 _AckStore TTL 분리 패치 |

### 7.5 11장 결론

§1 진화 타임라인 → 본인 회고:
- 2주 sprint (2026-05-15 ~ 2026-05-21) 안에 재설계 + T1+T6 + T3 + T4 모두 완료
- 시연 후 sprint: T2/T4 D5/T5/T7 + _AckStore 멘탈 모델 패치

---

## 8. 자료 인덱스 전체 (분류별)

### 8.1 Plan 문서 (skill/plan/) — 9개

| 자료 | 핵심 |
|---|---|
| [alarm-system-redesign.md](../../plan/alarm-system-redesign.md) | 2026-05-15 전체 재설계 plan (3대 요구 + 회색지대 5건) |
| [alarm-reliability-phase1.md](../../plan/alarm-reliability-phase1.md) | Phase 1 신뢰성 plan (AI mute + cooldown) |
| [alarm-popup-policy-followups.md](../../plan/alarm-popup-policy-followups.md) | 팝업 정책 follow-up |
| [alarm-t1-t6-info-unification.md](../../plan/alarm-t1-t6-info-unification.md) | T1+T6 정보 통일 |
| [alarm-t3-dedup-unification.md](../../plan/alarm-t3-dedup-unification.md) | T3 dedup 통일 |
| [alarm-t4-ai-static-hierarchy.md](../../plan/alarm-t4-ai-static-hierarchy.md) | T4 AI vs 정적 계층화 |
| [alarm-record-integration.md](../../plan/alarm-record-integration.md) | AlarmRecord ↔ Event 통합 |
| [alarm-post-ai-redesign.md](../../plan/alarm-post-ai-redesign.md) | AI 도입 후 알람 재설계 |
| [if-data-prep-and-alarm-binding.md](../../plan/if-data-prep-and-alarm-binding.md) | IF 학습 데이터 + 알람 binding |

### 8.2 T4 작업 changelogs (skill/alarm/) — 7개

| 자료 | 핵심 |
|---|---|
| [t4-source-message-spec.md](../../alarm/t4-source-message-spec.md) | source 별 메시지 패턴 spec |
| [t4-d1a-changelog.md](../../alarm/t4-d1a-changelog.md) | D1a 적용 |
| [t4-d1b-changelog.md](../../alarm/t4-d1b-changelog.md) | D1b 적용 |
| [t4-d2-implementation-spec.md](../../alarm/t4-d2-implementation-spec.md) | D2 구현 spec |
| [t4-d2-changelog.md](../../alarm/t4-d2-changelog.md) | D2 적용 |
| [t4-d3-changelog.md](../../alarm/t4-d3-changelog.md) | D3 적용 |
| [t4-d4-changelog.md](../../alarm/t4-d4-changelog.md) | D4 적용 |

### 8.3 코드리뷰 (docs/codereviews/) — 8개

| 자료 | 핵심 |
|---|---|
| [2026_05_09/04_alerts_events.md](../../../docs/archive/codereviews/2026_05_09/04_alerts_events.md) | 알람 시스템 초기 리뷰 |
| [2026_05_15/alarm-system-redesign-flow.md](../../../docs/archive/codereviews/2026_05_15/alarm-system-redesign-flow.md) | 재설계 flow |
| [2026_05_17/alarm-d-option-flow.md](../../../docs/archive/codereviews/2026_05_17/alarm-d-option-flow.md) | D 옵션 (도메인별) |
| [2026_05_17/alarm-phase2-flow.md](../../../docs/archive/codereviews/2026_05_17/alarm-phase2-flow.md) | Phase 2 UI flow |
| [2026_05_19/alarm-business-logic-as-is.md](../../../docs/archive/codereviews/2026_05_19/alarm-business-logic-as-is.md) | as-is 전체 |
| [2026_05_19/integrated-issues-triage.md](../../../docs/archive/codereviews/2026_05_19/integrated-issues-triage.md) | 통합 이슈 triage |
| [2026_05_19/power-5axis-policy-flow.md](../../../docs/archive/codereviews/2026_05_19/power-5axis-policy-flow.md) | 5축 → algorithm_source 흐름 |
| [2026_05_20/alarm-symptom-bottleneck-diagnosis.md](../../../docs/archive/codereviews/2026_05_20/alarm-symptom-bottleneck-diagnosis.md) | 3대 증상 진단 |

### 8.4 Refactoring 보고서 (drf-server/docs/refactoring/) — 5개

| 자료 | 핵심 |
|---|---|
| [alarm-system-redesign-2026-05-15.md](../../../drf-server/docs/refactoring/alarm-system-redesign-2026-05-15.md) | 재설계 적용 보고 |
| [alarm-d-option-2026-05-17.md](../../../drf-server/docs/refactoring/alarm-d-option-2026-05-17.md) | D 옵션 적용 |
| [alarm-phase2-completion-2026-05-17.md](../../../drf-server/docs/refactoring/alarm-phase2-completion-2026-05-17.md) | UI Phase 2 완료 |
| [2026_05_19_alarm_t1_t6.md](../../../drf-server/docs/refactoring/2026_05_19_alarm_t1_t6.md) | T1+T6 적용 |
| [2026_05_20_alarm_t3_troubleshooting.md](../../../drf-server/docs/refactoring/2026_05_20_alarm_t3_troubleshooting.md) | T3 트러블슈팅 |

### 8.5 Changelog (docs/changelog/alarm_reliability/) — 3개

| 자료 | 핵심 |
|---|---|
| [alarm_ai_mute_and_cooldown_2026_05_15.md](../../../docs/archive/changelog/alarm_reliability/alarm_ai_mute_and_cooldown_2026_05_15.md) | AI mute + cooldown 도입 |
| [alarm_reliability_phase1.md](../../../docs/archive/changelog/alarm_reliability/alarm_reliability_phase1.md) | Phase 1 신뢰성 |
| [ui_refactor_phase2.md](../../../docs/archive/changelog/alarm_reliability/ui_refactor_phase2.md) | UI refactor Phase 2 |

### 8.6 Memory (.claude/projects/-home-cjy-diconai/memory/) — 7개

| 자료 | 핵심 |
|---|---|
| [alarm-system-redesign-2026-05-15](../../../../../.claude/projects/-home-cjy-diconai/memory/alarm_system_redesign_2026_05_15.md) | 재설계 진입 + 3대 요구 결정 |
| [alarm-popup-policy-followups-2026-05-15](../../../../../.claude/projects/-home-cjy-diconai/memory/alarm_popup_policy_followups_2026_05_15.md) | Phase 1 후속 |
| [alarm-flow-doc-stale-2026-05-15](../../../../../.claude/projects/-home-cjy-diconai/memory/alarm_flow_doc_stale_2026_05_15.md) | 흐름도 stale 인지 |
| [alarm-t1-t3-pause-2026-05-20](../../../../../.claude/projects/-home-cjy-diconai/memory/alarm_t1_t3_pause_2026_05_20.md) | T1+T3 완료 + 시연 후 sprint 계획 |
| [alarm-t4-pre-entry-verified-2026-05-20](../../../../../.claude/projects/-home-cjy-diconai/memory/alarm_t4_pre_entry_verified_2026_05_20.md) | T4 진입 전 검증 |
| [alarm-symptom-diagnosis-2026-05-20](../../../../../.claude/projects/-home-cjy-diconai/memory/alarm_symptom_diagnosis_2026_05_20.md) | 3대 증상 진단 + 시연 후 sprint |
| [alarm-dataflow-review-2026-05-20](../../../../../.claude/projects/-home-cjy-diconai/memory/alarm_dataflow_review_2026_05_20.md) | 외부 리뷰 4지적 |

### 8.7 트러블슈팅 (skill/troubleshooting/ + docs/infra/) — 2개

| 자료 | 핵심 |
|---|---|
| [skill/troubleshooting/0519_alarm-toast-escalate-timer-race.md](../../troubleshooting/0519_alarm-toast-escalate-timer-race.md) | 토스트 격상 타이머 race |
| [docs/infra/troubleshooting_alarm_popup_docker.md](../../../docs/infra/troubleshooting_alarm_popup_docker.md) | Docker 환경 팝업 이슈 |

### 8.8 기능정의서 (docs/features/) — 5개

| 자료 | 핵심 | 본인? |
|---|---|---|
| [cjy_CM-07_알람팝업개선_기능정의서.md](../../../docs/features/cjy_CM-07_알람팝업개선_기능정의서.md) | 알람 팝업 개선 | ★ 본인 |
| [cjy_MN-04_geofence_alarm.md](../../../docs/features/cjy_MN-04_geofence_alarm.md) | geofence 알람 | ★ 본인 |
| [hjh_alarm-core-service_기능정의서.md](../../../docs/features/hjh_alarm-core-service_기능정의서.md) | 알람 core 서비스 | 참조 |
| [cm07_mn03_가스알람_이벤트.md](../../../docs/features/cm07_mn03_가스알람_이벤트.md) | 가스 알람 이벤트 | 참조 |
| [hjh_CM-07_MN-03_이벤트현황_유해가스현황_기능정의서.md](../../../docs/features/hjh_CM-07_MN-03_이벤트현황_유해가스현황_기능정의서.md) | 이벤트현황 + 유해가스현황 | 참조 |

### 8.9 skill 일반 자료 + skill/CJY/

| 자료 | 핵심 |
|---|---|
| [skill/알람 시나리오 관련 파일과 흐름도.md](../../알람%20시나리오%20관련%20파일과%20흐름도.md) | 알람 시나리오 파일 + 흐름도 (본인 정리) |
| [skill/지오펜스 알람 경로에 대해서.md](../../지오펜스%20알람%20경로에%20대해서.md) | geofence 경로 (본인 정리) |
| [skill/CJY/초안_알람_이벤트_관리.md](../../CJY/초안_알람_이벤트_관리.md) | 알람·이벤트 관리 초안 (본인) |
| [skill/CJY/02.알림 이벤트 관리 분석에 대해서.md](../../CJY/02.알림%20이벤트%20관리%20분석에%20대해서.md) | 알림 이벤트 관리 분석 (본인) |
| [skill/CJY/03.2 알림 발송 이력 관리 기준에 대해서.md](../../CJY/03.2%20알림%20발송%20이력%20관리%20기준에%20대해서.md) | 알림 발송 이력 |

### 8.10 .claude/skills/diconai/

| 자료 | 핵심 |
|---|---|
| [.claude/skills/diconai/alarm-flow.md](../../../.claude/skills/diconai/alarm-flow.md) | 알람 생성·전파 흐름 전체 가이드 (5 단계 architecture) |

---

## 부록 A. 코드 위치 인덱스

### A.1 fastapi-server

| 영역 | 파일 |
|---|---|
| decide_alarm 매트릭스 | [power/services/decide_alarm.py](../../../fastapi-server/power/services/decide_alarm.py) |
| push_alarm + fingerprint dedup | [websocket/services/alarm_queue.py](../../../fastapi-server/websocket/services/alarm_queue.py) |
| AI state + mark_ai_recent | [services/ai_mute.py](../../../fastapi-server/services/ai_mute.py) |
| WS broadcast | [websocket/services/broadcast.py](../../../fastapi-server/websocket/services/broadcast.py) |
| 전력 알람 결정 호출 | [power/services/anomaly_inference.py](../../../fastapi-server/power/services/anomaly_inference.py) |
| 가스 알람 결정 호출 | [gas/services/gas_service.py](../../../fastapi-server/gas/services/gas_service.py) |
| Celery → fastapi 알람 push 수신 | [internal/routers/alarm_router.py](../../../fastapi-server/internal/routers/alarm_router.py) `/internal/alarms/push/` |
| DRF forward | [services/anomaly_alarm.py](../../../fastapi-server/services/anomaly_alarm.py) |

### A.2 drf-server

| 영역 | 파일 |
|---|---|
| Celery 알람 태스크 | [apps/alerts/tasks.py](../../../drf-server/apps/alerts/tasks.py) (`fire_danger_alarm_task` / `fire_warning_alarm_task` / `fire_geofence_alarm_task` / `fire_clear_notification_task`) |
| Event 생성·병합 | [apps/alerts/services/event_service.py](../../../drf-server/apps/alerts/services/event_service.py) `create_alarm_and_event` |
| 동일 이벤트 병합 정책 | [apps/alerts/services/merge_policy.py](../../../drf-server/apps/alerts/services/merge_policy.py) |
| AI mute 가드 | [apps/alerts/services/alarm_dedupe.py](../../../drf-server/apps/alerts/services/alarm_dedupe.py) `is_ai_mute_active` |
| ALGORITHM_SOURCE_PHRASE | [apps/core/constants.py](../../../drf-server/apps/core/constants.py) |
| WS push 수신 view | [apps/alerts/views/anomaly_alarm_record.py](../../../drf-server/apps/alerts/views/anomaly_alarm_record.py) |
| AlarmRecord model | [apps/alerts/models/alarm_record.py](../../../drf-server/apps/alerts/models/alarm_record.py) |
| Event model | [apps/alerts/models/event.py](../../../drf-server/apps/alerts/models/event.py) |

### A.3 frontend (drf-server/static/js/)

| 영역 | 파일 |
|---|---|
| 알람 팝업 컨트롤러 | [shared/alarm-popup.js](../../../drf-server/static/js/shared/alarm-popup.js) |
| 알람 팝업 스타일 | [shared/alarm-popup.css](../../../drf-server/static/js/shared/alarm-popup.css) |
| WS 수신 라우터 | [dashboard/websocket.js](../../../drf-server/static/js/dashboard/websocket.js) |
| AlarmMapper (정규화) | [shared/alarm-mapper.js](../../../drf-server/static/js/shared/alarm-mapper.js) |
| 알람 WS handler | [shared/alarm-ws.js](../../../drf-server/static/js/shared/alarm-ws.js) (있다면) |

---

## 부록 B. 시연 후 sprint 계획 (11장 향후 인용)

| 우선 | 작업 | 자료 |
|---|---|---|
| 1 | `_AckStore` 멘탈 모델 패치 — 24h 영구 차단 분리 | [memory: alarm-symptom-diagnosis-2026-05-20](../../../../../.claude/projects/-home-cjy-diconai/memory/alarm_symptom_diagnosis_2026_05_20.md) |
| 2 | T2 (역할 분리) | [memory: alarm-t1-t3-pause-2026-05-20](../../../../../.claude/projects/-home-cjy-diconai/memory/alarm_t1_t3_pause_2026_05_20.md) |
| 3 | T4 D5 (정적 cover AlarmRecord 영속화) | 동일 |
| 4 | T5 / T7 | 동일 |
| 5 | a/c path 충돌 — AI 알람 시그널 누락 위험 패치 | [memory: alarm-dataflow-review-2026-05-20](../../../../../.claude/projects/-home-cjy-diconai/memory/alarm_dataflow_review_2026_05_20.md) |
| 6 | 정상화 → 회색 처리 디자인 결정 | [memory: alarm-popup-policy-followups-2026-05-15](../../../../../.claude/projects/-home-cjy-diconai/memory/alarm_popup_policy_followups_2026_05_15.md) |
| 7 | 작업자 디바이스 UX (Phase 3) | [memory: worker-device-undecided-2026-05-15](../../../../../.claude/projects/-home-cjy-diconai/memory/worker_device_undecided_2026_05_15.md) |

---

## 부록 C. 증빙 자료 체크리스트 (시연 전 수집)

| # | 자료 종류 | 7장 / 10장 |
|---|---|---|
| 1 | 알람 모달 캡처 (danger, AI source 라벨 표시) | 7장 |
| 2 | 알람 토스트 캡처 (warning, source_label "압연기A 이상 수치·패턴 동시 탐지") | 7장 |
| 3 | 회색 처리 토스트 캡처 (resolved) | 7장 (있다면) |
| 4 | EventAcknowledgement "(N 확인 중)" 시그널 캡처 | 7장 |
| 5 | algorithm_source 6 종 분포 Grafana 패널 | 7장 / 9장 |
| 6 | `push_alarm_dedup_hits_total` Grafana 카운터 (T3 효과) | 10장 |
| 7 | `is_ai_mute_active` 차단 카운터 (AI vs rule 효과) | 10장 |
| 8 | 알람 흐름 시퀀스 다이어그램 (router → service → Celery → push → WS → 브라우저) | 5장·7장 |
| 9 | decide_alarm 6 매트릭스 표 시각화 | 7장 |
| 10 | Before/After 표 3개 (T3 dedup / AI vs rule / 3대 증상) | 10장 |
| 11 | 운영 시나리오 1~2개 영상 (정상 → 가스 누출 → 모달 + 토스트 → ack → resolved) | 7장 |
| 12 | dummy 가동 1주 후 알람 발화 통계 (algorithm_source 별 비율) | 7장·10장 |

---

## 부록 D. 한눈 요약 (7장 본인 깊이 영역)

```
[알람 시스템 = 4 핵심 컴포넌트 직교]

  ┌─ decide_alarm 6 매트릭스 ──── AI state × static_risk → source 결정 (단일 결정자)
  ├─ push_alarm fingerprint dedup ─ event_id / ai_meta / clear / cover 4 분기 NX EX 30s
  ├─ AI mute (ai_fired:* TTL 60s) ─ rule task 의 is_ai_mute_active 가드
  └─ rate limit (sensor_identifier 60s) ─ 같은 센서 폭주 회피

[운영자 톤 (T1+T6)]
  ALGORITHM_SOURCE_PHRASE 6 종 한글 ("이상 수치 탐지" 등) — DRF + fastapi 단일 동기

[Event lifecycle]
  CREATED → ACK (EventAcknowledgement) → RESOLVED (자동 또는 수동)
  같은 facility + 같은 alarm_type 활성 Event 에 AlarmRecord 만 추가 (merge_policy)

[흐름]
  센서 → Celery (DRF) 또는 fastapi (전력) → push_alarm
  → Redis BRPOP → broadcast_loop → sensor_clients / worker_clients
  → AlarmPopup.show (모달/토스트)

[시연 후 sprint] _AckStore TTL 분리 + T2/T4 D5/T5/T7 + a/c path 충돌 패치
```

작성 시 본 요약을 7장 도입부 또는 부록에 그대로 인용 가능.
