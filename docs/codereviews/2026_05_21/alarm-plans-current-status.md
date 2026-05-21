# 알람 plan 진행 현황 점검 (2026-05-21)

> **작업일**: 2026-05-21
> **트리거**: 사용자 질문 — "현재 알람쪽 플랜들 중에서 진행이 안된 내용들이 있는걸로 아는데 파악해주세요"
> **결론**: 알람 관련 9개 plan 중 시연 전 작업은 **사실상 모두 완료**. 미완으로 보이던 항목 6건은 다른 PR 에서 처리됨이 확인됨. T4 마저 코드 구현이 끝나있고 flag 토글 + 브랜치 머지만 남은 상태. 다만 **DRF 가 알람 정적 평가를 하는 아키텍처 위반 잔재**가 가스/전력/지오펜스 3 도메인에 5+개 surface 로 남아있음.

---

## 1. 점검 범위

알람 관련 plan 9개 ([skill/plan/](../../../skill/plan/) 디렉토리):

| Plan | 한 줄 목적 |
|---|---|
| [alarm-popup-policy-followups.md](../../../skill/plan/alarm-popup-policy-followups.md) | 이벤트 패널 원안 디자인 + 정상화 dedup + message 일관화 |
| [alarm-post-ai-redesign.md](../../../skill/plan/alarm-post-ai-redesign.md) | AI 5축 완성 후 T1~T7 작업 묶음 정렬 |
| [alarm-record-integration.md](../../../skill/plan/alarm-record-integration.md) | AlarmRecord 저장 통합 (양측 공용 인프라) |
| [alarm-reliability-phase1.md](../../../skill/plan/alarm-reliability-phase1.md) | 알람 신뢰성 개선 (SQLite WAL + Redis 큐 + push 신뢰성) |
| [alarm-system-redesign.md](../../../skill/plan/alarm-system-redesign.md) | 파이프라인 픽스 + user-scoped ACK + 작업자 라우팅 (Phase 1/2/3) |
| [alarm-t1-t6-info-unification.md](../../../skill/plan/alarm-t1-t6-info-unification.md) | T1+T6 sub-plan (운영자 정보 통일 + 메시지 표준화) |
| [alarm-t3-dedup-unification.md](../../../skill/plan/alarm-t3-dedup-unification.md) | T3 sub-plan (중복 방지·dedup 의미 통일) |
| [alarm-t4-ai-static-hierarchy.md](../../../skill/plan/alarm-t4-ai-static-hierarchy.md) | T4 sub-plan (AI vs 정적룰 위계 명시) |
| [if-data-prep-and-alarm-binding.md](../../../skill/plan/if-data-prep-and-alarm-binding.md) | IF 학습 데이터 준비 + 알람 결합 |

---

## 2. 조사 과정 (3 라운드)

### 라운드 1 — plan 본문 status 만 보고 정리

plan 의 status 표·체크리스트만 읽고 "완료/부분/미진행" 판정.

| Plan | 본문 status |
|---|---|
| alarm-popup-policy-followups | "P0/P1 working tree 미커밋 + D 옵션 보류" |
| alarm-system-redesign | "Phase 1 진행 중 (D-7까지)" |
| alarm-record-integration | "C1~C3 작업 분할 후 진입 안됨" |
| alarm-reliability-phase1 | "C1~C5 미진행" |
| alarm-t4-ai-static-hierarchy | "D1a~D4 4일 보수적, 미진행" |
| if-data-prep-and-alarm-binding | "트랙 0/1/2 모두 미진행" |

→ **결론**: 총 6+개 항목이 미완으로 보임. 사용자에게 보고.

### 라운드 2 — commit 범위 확장 (PR #45~#71)

사용자 피드백: "최근 커밋 범위 수 넓혀서 확인해줘, 몇 개는 한 것 같은데"

`git log` 50개 확장 결과:

| Plan | 본문 status | 실제 처리 PR |
|---|---|---|
| alarm-record-integration | "C1~C3 미진행" | ✅ #52 — 양측 공용 인프라 완료 |
| alarm-reliability-phase1 | "C1~C5 미진행" | ✅ #45, #55 — WAL + 락 폭주 해소 + Redis 큐 |
| alarm-system-redesign Phase 1 | "Phase 1 진행 중" | ✅ #60 — user-scoped ack + RESOLVED + catch-up |
| alarm-system-redesign Phase 2 | (계획됨) | ✅ #61, #64 — WS 안정성 + UX |
| alarm-popup-policy-followups P0+P1 | "미커밋" | ✅ #57 — 정상화 dedup + message 일관화 |
| alarm-popup-policy-followups D 옵션 | "보류" | ✅ #61, #64 — "D 옵션 본격" |
| alarm-t1-t6-info-unification | "준비완료" | ✅ #70 — T1+T6+T3 통합 머지 |
| alarm-t3-dedup-unification | "준비완료" | ✅ #70 |

→ **결론**: plan 본문 상태가 **stale**. 6개 중 5개가 이미 머지됨. 미완 남은 것: T4, T2/T5/T7 (시연 후), Phase 3 (디바이스 미정), IF 트랙 1·2.

### 라운드 3 — 연관 작업 교차 검증

사용자 피드백: "내가 보기엔 일부분 작업들이 서로 연관되어 있어서 어느 정도 끝난 것 같은데"

4 가설 검증:

| 미완으로 보였던 항목 | 실제 처리 PR | 처리 방식 |
|---|---|---|
| 정상화 9건 도배 (popup 문제 A) | #57 | gas_clear/power_clear fingerprint dedup + 패널 dedup 키 일반화 (30s TTL) |
| message 길이/일관화 (popup 문제 B) | #57 | `AlarmRecord.get_short_message()` + WS payload `message` 필드 7곳 동봉 |
| 팝업 D 옵션 | #61, #64 | "D 옵션 본격" 별도 PR (계획대로 분리) |
| fastapi `AlarmPayload` 스키마 fix | #60, #70 | `event_ack_users` / `event_resolved_at` 필드 추가 |
| `_AckStore` 24h 영구 차단 (3대 증상) | #70 (T5) | `_ACK_TTL_MS` 24h → 60s + RESOLVED 시 `_AckStore.remove()` 동기 호출 |
| a/c path 충돌 (데이터흐름 리뷰 #1) | #56 | `_CACHE_TTL` 3600→300 + 백엔드 fingerprint dedup + AI mute 가드 |

→ **결론**: 미완으로 보였던 6 건 모두 다른 PR 에서 처리됨. 시연 전 알람 신규 작업 잔여는 사실상 없음.

---

## 3. 시연 후 sprint 로 남은 진짜 미완 항목

| # | 항목 | 출처 plan | 작업량 | 진입 조건 |
|---|---|---|---|---|
| 1 | **T4** AI vs 정적룰 위계 명시 | alarm-t4-ai-static-hierarchy | 4일 (D1a~D4) | T1+T6+T3 완료 ✅ · 5-state 매트릭스 리뷰 인계 보류 |
| 2 | **T2** 위험도 4단계 시각화 | alarm-post-ai-redesign | 중 | RiskLevel enum 결정 필요 |
| 3 | **T5** 모달·자동닫힘·이탈 정책 | alarm-post-ai-redesign | 중 | ack vs RESOLVED 멘탈모델 결정 필요 |
| 4 | **T7** JS 인프라 정리 | alarm-post-ai-redesign | 낮음 | T2/T5 후 |
| 5 | **Phase 3** 작업자 권한별 라우팅 | alarm-system-redesign | 별도 PR | **작업자 디바이스 결정 대기** |
| 6 | **IF 트랙 1 v2** C5~C10 | if-data-prep-and-alarm-binding | ~5일 | 트랙 2 smoke 검증 후 |
| 7 | **IF 트랙 2** smoke 3모델 비교 | if-data-prep-and-alarm-binding | 중 | `--since-days` 인자 추가 후 |
| 8 | **데이터흐름 리뷰 #2/#3/#4** | 진단 문서 | 진단만 완료 | 조치 방향 결정 필요 |

---

## 4. T4 코드베이스 검증 — 사실상 끝나있음

사용자 피드백: "진입하기 전에 현재 코드베이스가 많이 바뀐 상태인데 확인해줘"

현재 브랜치 `feature/0521_power_refactory` 기준:
- main 대비 **621 files, +68,359 lines** 변경
- T4 plan 의 D1a~D4 sub-step 이 이 브랜치에 거의 다 구현됨

### T4 plan vs 실제 구현 매핑

| Plan sub-step | 실제 구현 위치 | 상태 |
|---|---|---|
| **D1a** AI 5-state state machine | [fastapi-server/services/ai_mute.py](../../../fastapi-server/services/ai_mute.py) — `AIInferenceState` enum (FIRED/INFERRED_NORMAL/INFERRED_FAILED/WARMING_UP/DISABLED) + Redis 키 scoping | ✅ |
| **D1b** DRF threshold 5분 sync | [fastapi-server/power/services/threshold_sync.py](../../../fastapi-server/power/services/threshold_sync.py) + lifespan 등록 | ✅ |
| **D2** fastapi 단일 정책 결정 (6분기 매트릭스) | [fastapi-server/power/services/decide_alarm.py](../../../fastapi-server/power/services/decide_alarm.py) + [anomaly_inference.py](../../../fastapi-server/power/services/anomaly_inference.py) `process_anomaly_inference()` | ✅ |
| **D3a** DRF neutralize + source 필드 | [drf-server/apps/alerts/migrations/0019_alarmrecord_source.py](../../../drf-server/apps/alerts/migrations/0019_alarmrecord_source.py) + [AlarmSource enum](../../../drf-server/apps/core/constants.py#L111) + [power_alarm.py](../../../drf-server/apps/monitoring/services/power_alarm.py) | ✅ |
| **D3b** AlarmPayload source/reason 필드 | [fastapi-server/core/constants.py:27-28](../../../fastapi-server/core/constants.py#L27) `static_cover_miss` / `static_cover_inference_fail` | ✅ |
| **D4** 프론트 시각 분기 | `alarm-popup.js` source 별 분기 + `.alarm-popup-static-cover` / `.cover-badge` CSS | ✅ |
| **검증** | `test_decide_alarm.py` (236L) · `test_ai_mute_marking.py` · `test_threshold_sync.py` · `test_push_alarm_dedup.py` (407L) · `test_power_alarm_neutralize.py` | ✅ |

### T4 실제 남은 작업 (코드 작성 외)

| # | 항목 | 위치 |
|---|---|---|
| 1 | **`STATIC_THRESHOLD_AT_FASTAPI` flag 활성화** | [drf-server/config/settings.py:223](../../../drf-server/config/settings.py#L223) — 현재 `default=False` |
| 2 | **현재 working tree 미커밋 잔존** | `power_service.py` modified + `anomaly_inference.py / equipment_builder.py / night_escalation.py / zscore_anomaly.py` untracked |
| 3 | **브랜치 main 머지** | `feature/0521_power_refactory` 621 files 통째 PR 정리 |
| 4 | **5-state 매트릭스 외부 리뷰어 인계** | 시연 후 |

---

## 5. STATIC_THRESHOLD_AT_FASTAPI flag 의 의미

사용자 질문: "1번 항목은 대체 뭔 소리지, 이거 하면 뭐가 크게 달라져?"

### flag=False (현재 기본값)

```
[센서 raw] ──┬─→ fastapi  : AI + 정적 평가 → decide_alarm() → push
             └─→ DRF      : 정적 평가 → trigger_power_alarms() → fire
                            (단, AI mute 60s 가드로 일부 suppress)
```

- 두 서버가 같은 데이터를 각자 평가해서 알람 후보를 만듦
- 충돌 방지는 [power_alarm.py:203](../../../drf-server/apps/monitoring/services/power_alarm.py#L203) 부근의 AI mute 가드 (60s suppress)·_revoke (WARNING 타이머 취소)·is_ai_mute_active 체크 같은 **여러 조정 로직** 으로 처리
- 엣지케이스에서 중복/누락 발생 위험 (`alarm_dataflow_review_2026_05_20` 의 a/c path 충돌이 이 구조의 후유증)

### flag=True (T4 D3 의 핵심)

```
[센서 raw] ──→ fastapi : AI + 정적 평가 → decide_alarm() → push (단일 결정자)
                ↑
              DRF: 정적 평가는 하되 fire 안 함. shadow_audit 만 기록
```

- DRF 의 정적 fire 경로가 **통째로 skip** ([power_alarm.py:204](../../../drf-server/apps/monitoring/services/power_alarm.py#L204) — `continue`)
- DRF 는 "내가 만약 발화했다면 fastapi 가 같은 채널에서 알람을 만들었을까?" 만 검증 (shadow_audit) — mismatch counter Prometheus 로 노출
- AI mute 가드·WARNING 타이머 취소·revoke 같은 **조정 로직이 전부 dead code** 가 됨 (1~2주 후 mismatch=0 확인되면 정식 삭제 가능 — plan §6.1)

### 운영자 화면 관점

| | False (현재) | True (T4 활성화) |
|---|---|---|
| 정상 케이스 알람 | 똑같이 나옴 | 똑같이 나옴 |
| AI 발화 + 정적 같이 발화 | AI mute 가 정적 60s suppress (간접) | fastapi 가 처음부터 정적 silent (직접) |
| AI 미탐 → 정적만 fire | DRF 가 fire | fastapi 가 `source=static_cover_miss` 로 fire |
| 같은 사건 중복 알람 위험 | 두 결정점 race | 없음 |
| 코드 복잡도 | AI mute 가드 등 4~5개 조정 로직 잔존 | 단일 결정점, 추후 dead code 정리 가능 |

---

## 6. 아키텍처 위반 — DRF 의 정적 평가 surface 전수목록

사용자 통찰: "우리 아키텍처 흐름만 보면 필요 없는 내용 같은데"

### 6.1 아키텍처가 말하는 것

[CLAUDE.md](../../../.claude/CLAUDE.md) 의 데이터 흐름:
```
IoT → fastapi (수신·검증) → drf-server (저장) / WebSocket (브라우저)
```

→ DRF 의 역할은 **"저장"**. 알람 판정은 들어있을 이유가 없음.

### 6.2 그런데 DRF 가 알람 판정하는 곳들

**① 가스** — [drf-server/apps/monitoring/services/gas_alarm.py](../../../drf-server/apps/monitoring/services/gas_alarm.py)
- `trigger_gas_alarms(gas_data)` — [gas_data.py:100-102](../../../drf-server/apps/monitoring/serializers/gas_data.py#L100) **serializer.create() 안에서 호출**
- 내부에서 `try_transition()` → DANGER/WARNING 판정 → Celery fire_*_task 호출

**② 전력** — [drf-server/apps/monitoring/services/power_alarm.py](../../../drf-server/apps/monitoring/services/power_alarm.py)
- `trigger_power_alarms(objs, device)` — [power_data.py:162](../../../drf-server/apps/monitoring/serializers/power_data.py#L162) serializer.create() 호출
- 채널별 W/A/V 축 max 집계 → `try_transition` → fire_power_danger_task / fire_power_warning_task
- **T4 D3 flag 가 무력화하는 게 바로 이 함수의 fire 분기**

**③ Threshold → RiskLevel 매핑 (양 도메인 공용)** — [drf-server/apps/facilities/services/threshold_service.py](../../../drf-server/apps/facilities/services/threshold_service.py)
- `evaluate_gas_risk()` ([:91](../../../drf-server/apps/facilities/services/threshold_service.py#L91))
- `evaluate_power_risk()` ([:212](../../../drf-server/apps/facilities/services/threshold_service.py#L212))
- `evaluate_current_risk()` ([:245](../../../drf-server/apps/facilities/services/threshold_service.py#L245))
- `evaluate_voltage_risk()` ([:260](../../../drf-server/apps/facilities/services/threshold_service.py#L260))
- `_evaluate_with_rated()` ([:163](../../../drf-server/apps/facilities/services/threshold_service.py#L163))
- DB Threshold 조회 → "이 값이 DANGER/WARNING/NORMAL 인지" 판정

**④ 지오펜스** — [drf-server/apps/positioning/services/position_service.py:15](../../../drf-server/apps/positioning/services/position_service.py#L15)
- `evaluate_worker_risk_level(geofence)` — 작업자 위치 위험도 판정

**⑤ 알람 fire Celery 태스크 — 부분 적합** — [drf-server/apps/alerts/tasks.py](../../../drf-server/apps/alerts/tasks.py)
- `fire_danger_alarm_task` / `fire_warning_alarm_task` (가스)
- `fire_power_danger_task` / `fire_power_warning_task` (전력)
- `fire_geofence_alarm_task`
- **저장 + 알람 전파 (WS push) 책임이라 일부는 남아야 함** — 단, "판정" 책임을 빼면 OK

### 6.3 아키텍처 위반 여부 매핑

| Surface | 현재 역할 | 아키텍처 위반? | 비고 |
|---|---|---|---|
| gas_data serializer.create() → `trigger_gas_alarms` | 저장 + 판정 | **위반** | 저장만 해야 함 |
| power_data serializer.create() → `trigger_power_alarms` | 저장 + 판정 | **위반** (T4 flag 로 무력화 대상) | 저장만 해야 함 |
| `threshold_service.evaluate_*` | 임계치 판정 함수 | **위반** | fastapi 로 이동해야 함 — 일부는 이미 [threshold_sync.py](../../../fastapi-server/power/services/threshold_sync.py) + [threshold_eval.py](../../../fastapi-server/power/services/threshold_eval.py) 로 복제 완료 |
| geofence `evaluate_worker_risk_level` | 위치 위험 판정 | **위반** | 별도 도메인 — T4 범위 밖 |
| `fire_*_task` Celery | 판정결과 → AlarmRecord 저장 + WS push | 부분 적합 | "판정" 책임을 빼면 OK |

### 6.4 T4 가 다루는 범위

| 도메인 | 판정 위치 | flag=True 후 |
|---|---|---|
| 가스 | DRF (위반) | 그대로 (가스는 T4 범위 X — 메모리 [[power_ai_architecture_decision_2026_05_18]] "가스 = 격하 유지") |
| 전력 | DRF + fastapi (중복) | fastapi only ← **flag 의 역할** |
| 지오펜스 | DRF (위반) | 그대로 (T4 범위 X) |

→ **T4 는 5개 surface 중 "전력 정적 평가" 1개만 다룸.** 가스·지오펜스 정리는 별도 sprint 필요.

---

## 7. flag 의 정체 — 레거시 정리 전환 도구

원래 fastapi 도입 전 **DRF 가 모든 걸 하던 시절** 의 코드가 남아있는 것. fastapi 가 나중에 추가되면서 알람 판정 책임이 이관됐지만, 옛 경로는 안 지우고 두 곳에서 동시에 실행되는 상태가 됨.

```
flag=False (현재) — 레거시 그대로 (DRF 도 알람 판단)
flag=True         — DRF 평가 skip (아키텍처 원칙대로 동작) + shadow audit 검증
완전 정리         — flag·shadow audit·DRF 정적 eval 코드 삭제
```

**즉 flag 는 "레거시 코드를 한 번에 지우기 무서워서 만든 안전장치".** plan §6.1 도 "1~2주 mismatch=0 확인 후 환경변수·shadow_audit·DRF eval 정식 제거" 라고 명시.

---

## 8. 결론 및 의사결정 옵션

### 8.1 시연 전 (D-day 2026-06-14)

- **신규 알람 작업 잔여는 없음**. 9개 plan 중 시연 전 범위는 사실상 마감
- `feature/0521_power_refactory` 브랜치 정리 (working tree 4 파일 커밋 + main 머지) 가 가장 큰 잔여 작업
- stale 한 plan 본문 status 정비 (`alarm-system-redesign`, `alarm-popup-policy-followups`, `alarm-post-ai-redesign`) 는 시연 후 정리 가능

### 8.2 T4 flag 활성화 옵션

| 옵션 | 의미 | 리스크 |
|---|---|---|
| **A. flag=True 토글만** | DRF eval 은 코드상 남지만 작동 안 함. shadow audit 으로 fastapi 누락 감시 | 낮음 — 안전장치 동작 |
| **B. flag+레거시 코드 통째 삭제** | 아키텍처 원칙 그대로. flag·shadow_audit·trigger_power_alarms 정적 분기 모두 삭제 | fastapi 미탐 시 대안 없음 (이미 fastapi 가 동작 검증된 상태라 실질 리스크 낮음) |
| **C. 시연 후 결정** | flag·DRF eval 둘 다 그대로 두고 시연만 통과 | 시연 시 race 잠재 위험 (현재 AI mute 가드로 막혀있음) |

### 8.3 시연 후 sprint 우선순위 (참고)

1. T4 flag 활성화 + shadow audit 1~2주 관찰 → DRF 전력 정적 eval 정식 제거
2. T2 / T5 / T7 진행
3. Phase 3 작업자 라우팅 (디바이스 결정 후)
4. IF 트랙 2 → 트랙 1 v2
5. 가스·지오펜스의 DRF 정적 평가 정리 (별도 plan 필요)
6. 데이터흐름 리뷰 #2/#3/#4 조치 방향 결정

---

## 9. 관련 메모리

- [[alarm_t1_t3_pause_2026_05_20]] — T1/T3 완료 + T2/T4/T5/T7 시연 후 sprint
- [[alarm_t4_pre_entry_verified_2026_05_20]] — T4 진입 전 검증 완료, 5-state 매트릭스 인계 보류
- [[alarm_dataflow_review_2026_05_20]] — 외부 리뷰어 4가지 지적 (#1 은 #56 처리)
- [[alarm_symptom_diagnosis_2026_05_20]] — _AckStore 24h + ack/RESOLVED 멘탈모델 진단
- [[alarm_popup_policy_followups_2026_05_15]] — popup 후속 + D 옵션
- [[alarm_system_redesign_2026_05_15]] — Phase 1/2/3 설계
- [[worker_device_undecided_2026_05_15]] — 작업자 디바이스 미정 → Phase 3 보류
- [[power_ai_architecture_decision_2026_05_18]] — 가스 격하 유지 / 전력 un-downgrade
- [[demo_2026_06_14_arima_roadmap]] — 시연 일정 + D+30 un-downgrade

---

## 10. 변경 이력

- 2026-05-21 작성 — 알람 plan 진행 현황 점검 결과 (트리거 → 라운드 1~3 → T4 검증 → flag 의미 → 아키텍처 위반 surface)
