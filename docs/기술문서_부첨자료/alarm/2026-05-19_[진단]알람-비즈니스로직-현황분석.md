# 알람 비즈니스 로직 현황 분석 (As-Is, 2026-05-19)

작성일: 2026-05-19
대상: AI 추론 → 5축 결합 → AlarmRecord → WebSocket push → 클라 dedup → 토스트·모달 격상 까지 전 경로
목적: 현재 비즈니스 로직의 **실제 동작** 을 한 장에 명시화하고, **의도 vs 실제 차이가 짚일 만한 후보 갭** 을 §5 에 정리. 사용자가 본 문서를 읽으며 "이 부분은 내 의도와 다르다" 짚기 위한 베이스라인.

선행 sprint: 5축 정책 엔진 도입 (D2/E1/F, 2026-05-19). 본 문서는 이 작업 직후 시점의 As-Is 스냅샷.

---

## §1. 분석 범위

| 영역 | 포함 | 제외 |
|---|---|---|
| AI 추론 (process_anomaly_inference) | ✅ | — |
| 5축 결합 + algorithm_source 결정 | ✅ | — |
| AlarmRecord 생성·DB 저장 | ✅ | — |
| Threshold 룰 발화 (POWER_OVERLOAD 등) | ✅ (AI 와 상호작용 범위까지) | 룰 자체 임계치 정의 |
| Event 병합·신규 생성·RESOLVED | ✅ | — |
| Celery push_alarm task | ✅ | — |
| FastAPI alarm_queue + WebSocket broadcast | ✅ | — |
| 클라 dedup (localStorage) | ✅ | — |
| 토스트·모달 격상·헤더 배지 | ✅ | — |
| EventAcknowledgement (user-scoped) | ✅ | — |
| 이벤트 패널 표시 | ✅ | 이력 페이지 별도 |
| AI mute 가드 + 격상 bypass | ✅ | — |
| 다중 탭 / 페이지 이탈 / catch-up | ✅ | — |

**범위 외**: 알람 정책 (AlertPolicy) 관리 UI, 관리자 화면 별도 알람 페이지, 작업자 디바이스 (geofence_intrusion 의 worker WS) 는 본 문서 제외.

---

## §2. 전체 흐름 — 10 단계 + 분기

### 종합 다이어그램

```
[엣지게이트웨이 → POST /api/power/watt]
       │
       ▼
[FastAPI] process_anomaly_inference (power_service.py:172-466)
       │
       ├─ (1) quality_guard 검사 (통신단절/오버플로우/센서고정 → skip)
       ├─ (2) IF 추론 (sliding window 30 + 4-피처)
       ├─ (3) Z-score (STEP D) → (bool, |z|)
       ├─ (4) Change Point (STEP E) → (bool, meta) — _cp_windows 60
       ├─ (5) ARIMA forecast → arima_violation
       ├─ (6) threshold_risk = calculate_power_risk(value, 정격)
       ├─ (7) combine_risk_5axis → (combined, escalation_source)
       ├─ (8) night_abnormal 시각 격상 (KST 22~05 + watt > 정격 30%)
       ├─ (9) algorithm_source 결정 (6단계 priority)
       │       night > combined > change_point* > arima > zscore* > IF
       │       (* escalation_source 매칭 시만)
       │
       └─ (10) should_fire = (combined ∈ _FIRE_LEVELS) AND (rate_limit 60s 통과)
                │
                ▼
       forward_inference_e2e (services/anomaly_alarm.py:70-146) — 비동기 분기
                │
                ├─ (10a) PUSH (독립 asyncio.create_task) — should_fire=True 시만
                │         │
                │         ▼
                │       POST /internal/alarms/push/  ← [FastAPI 내부 엔드포인트]
                │         │
                │         ▼
                │       Redis dedup fingerprint (30s TTL) + LPUSH alarm_queue
                │       fingerprint: `ai:power_anomaly_ai:{device}:{ch}:{level}`
                │         │
                │         ▼
                │       alarm_flush_loop (BRPOP 무한 대기) → _send_to_all
                │         │
                │         ▼
                │       WebSocket broadcast → /ws/sensors/ 클라 전체
                │
                ├─ (10b) AI mute 마킹 — Redis `ai_fired:{device}:{ch}:{level}` (60s TTL)
                │         (룰 측 trigger_power_alarms 가 이 키로 60s suppress)
                │
                ├─ (10c) ML forward (await) — POST /api/ml/anomaly-results/
                │         → MLAnomalyResult DB 저장 + ml_id 반환
                │
                └─ (10d) AlarmRecord forward (await, should_fire=True 시) ─────┐
                         POST /alerts/api/anomaly-alarm-records/                 │
                                                                                 ▼
[DRF] AnomalyAlarmRecordCreateView (views/anomaly_alarm_record.py:30-112)
       │
       ├─ Serializer 검증 (alarm_type, risk_level, algorithm_source, ...)
       ├─ source FK 조회 (PowerDevice / GasSensor 매칭)
       │
       ▼
event_service.create_alarm_and_event (services/event_service.py:20-150)
       │
       ├─ 활성 Event 조회 (select_for_update — facility+alarm_type+source)
       ├─ 기존 Event 있음: AlarmRecord 신규 생성 + Event 갱신 + 쿨다운 (60s) 체크
       ├─ 신규 Event: AlertPolicy 자동 매칭 → Event 생성 + AlarmRecord + EventLog(CREATED)
       └─ 타임 윈도우 초과: 기존 Event 강제 완료 + 신규 Event
                │
                ▼
       AlarmRecord DB 저장 (algorithm_source 포함, save() 불변성)
                │
                ▼
       Celery fire_*_task → 별도 push_alarm (위 10a 와 같은 경로, 중복은 dedup 으로 차단)
```

### 별개 흐름 — Threshold 룰 발화

```
[DRF] PowerData 저장 → trigger_power_alarms (monitoring/services/power_alarm.py)
       │
       ├─ 채널별 3축 (W/A/V) max 위험도 산출
       ├─ DANGER 즉발: AI mute 가드 확인 (Redis ai_fired:{device}:{ch}:danger)
       │   - 키 부재 → fire_power_danger_task.delay (Celery)
       │   - 키 존재 → suppress (AI 가 이미 발화)
       ├─ WARNING 3초 타이머: cache.add SETNX (3s 중복 방지) → fire_power_warning_task
       │
       └─ AI mute 격상 bypass: AI=warning 발화 후 룰=danger 산출 시
           (danger 키는 별도라 fire_power_danger_task 통과)
```

→ AI 알람 (POWER_ANOMALY_AI) 과 룰 알람 (POWER_OVERLOAD) 은 **별도 alarm_type** 으로 분리. 같은 channel·시각에 둘 다 발화 가능 (AI mute 60s 안에서만 룰 측이 suppress).

---

## §3. 핵심 컴포넌트 (코드 위치 + 책임)

| 컴포넌트 | 위치 | 책임 |
|---|---|---|
| `process_anomaly_inference` | `fastapi-server/power/services/power_service.py:172-466` | IF + Z-score + CP + ARIMA + 5축 + night + algorithm_source + push/forward 트리거 |
| `combine_risk_5axis` | `fastapi-server/ai/risk_combine.py:120-163` | 5축 우선순위 매핑 (base=3axis 위임) → (combined, escalation_source) |
| `forward_inference_e2e` | `fastapi-server/services/anomaly_alarm.py:70-146` | push (독립 task) + AI mute 마킹 + ML forward + AlarmRecord forward |
| `push_alarm` | `fastapi-server/websocket/services/alarm_queue.py:52-130` | Redis dedup fingerprint (30s) + LPUSH alarm_queue |
| `alarm_flush_loop` | `fastapi-server/websocket/routers/ws_router.py:48-71` | Redis BRPOP → broadcast → clients drop if 0 |
| `AnomalyAlarmRecordCreateView` | `drf-server/apps/alerts/views/anomaly_alarm_record.py:30-112` | Serializer 검증 + source FK + create_alarm_and_event 호출 |
| `create_alarm_and_event` | `drf-server/apps/alerts/services/event_service.py:20-150` | Event 병합/신규 + AlarmRecord + EventLog + 쿨다운 |
| `trigger_power_alarms` | `drf-server/apps/monitoring/services/power_alarm.py:119-207` | 룰 발화 + AI mute 가드 + 격상 bypass |
| `fire_power_danger_task` / `fire_power_warning_task` | `drf-server/apps/alerts/tasks.py:120-503` | Celery 측 AlarmRecord 재생성 + push |
| `WSClient` (클라 WS 수신) | `drf-server/static/js/shared/alarm-ws.js:8-29` | `/ws/sensors/` 수신 → AlarmMapper → AlarmPopup.show / AlarmToast.show |
| `_DedupStore` | `drf-server/static/js/shared/alarm-popup.js:54-114` | localStorage `diconai:alarm:popup:dedup` 60s TTL |
| `AlarmToastStack` / `AlarmPopup` | `drf-server/static/js/shared/alarm-popup.js:135-248` | /admin-panel/* 우상단 토스트 / 기타 중앙 모달 |
| `alarm-badge.js` | `drf-server/static/js/shared/alarm-badge.js:29-117` | 헤더 미확인 배지 (API + CustomEvent) |
| `EventAcknowledgement API` | `drf-server/apps/alerts/views/event.py:155-200` | POST /alerts/api/events/{id}/ack/ (user-scoped) |
| `event-panel.js` | `drf-server/static/js/dashboard/panels/event-panel.js:21-319` | 이벤트 패널 — source 그룹화 30분 윈도우 + AI 아이콘 |

---

## §4. 메시지 / Payload 구조

### WebSocket broadcast 메시지 (서버 → 클라)

```json
{
  "alarms": [
    {
      "alarm_type": "power_anomaly_ai" | "power_overload" | "gas_threshold" | "geofence_intrusion",
      "risk_level": "warning" | "danger",
      "source_label": "CH1",
      "summary": "[IF 이상 감지] CH1 watt=7925.8 (score 0.0292, combined=warning)",
      "message": "송풍기A AI 이상 패턴 감지",
      "is_new_event": true,
      "event_id": 123,
      "anomaly_meta": {
        "combined_risk": "predict_warn",
        "anomaly_score": -0.0292,
        "device_id": "63200c3afd12",
        "channel": 1,
        "data_type": "watt",
        "algorithm_source": "zscore",
        "arima_forecast": 1091.5,
        "arima_ci": [645, 1538],
        "z_score_anomaly": true,
        "change_point": false,
        "cp_mean_shift": null,
        "cp_std_ratio": null
      }
    }
  ],
  "timestamp": "2026-05-19T...",
  "device_id": "sensor-01"
}
```

### 클라 dedup key

| 우선순위 | key |
|---|---|
| 1 | `event:${event_id}` (룰 알람 — event 보유) |
| 2 (fallback) | `${alarm_type}:${sensor_name}:${level}` (AI 알람 / event_id 없는 케이스) |

→ localStorage `diconai:alarm:popup:dedup` map, TTL 60s (백엔드 cooldown 과 동기).

---

## §5. 의도 vs 실제 차이가 짚일 만한 잠재 갭 (사용자 확인 필요)

본 문서의 **핵심 영역** — 매핑하면서 발견한 잠재 의도 불일치 후보. 세 카테고리로 분리:

- **§5A 백엔드 동작·정책 갭** (10건) — 발화 조건·우선순위·중복 방지 정책 자체
- **§5B JS ↔ 백엔드 인터페이스 미스매치** (11건) — 백엔드가 보낸 것을 JS 가 다르게 해석·미사용
- **§5C 알람 팝업 텍스트 구성 문제** (8건) — 운영자가 보는 텍스트의 일관성·포맷·정보 노출

사용자가 짚는 항목에 따라 §6 plan 우선순위 결정.

### §5A 백엔드 동작·정책 갭 (10건)

### 5.1 algorithm_source / 5축 라벨이 UI 까지 전달되지 않음

**현재 동작**:
- fastapi 측이 summary 에 prefix 로 주입 (`[Z-score 이상 감지] CH1 watt=5341 ...`)
- 클라는 summary 를 그대로 표시 (별도 분리 안 함)
- 토스트/모달에 `algorithm_source` 별도 칩·배지 표시 **없음**
- 이벤트 패널은 AI 알람에 `brain-circuit` 아이콘만 통합 표시 (IF / Z-score / CP 구분 X)

**의도 추정 갭**:
- 본 sprint §F 의 의도 — 운영자가 어떤 축이 발화했는지 즉시 인지
- 실제 — summary 문자열 안에 prefix 만 들어가 있고 시각적 구분 약함

**짚을 만한 후보**:
- (a) 토스트/모달에 algorithm_source 별 색상·아이콘 차별화
- (b) 이벤트 패널에서 5축 (IF/Z/CP/ARIMA/Night) 칩 색상 구분
- (c) "Z-score 4.17σ" 같은 디테일 노출

### 5.2 anomaly_meta 4 필드 (z/cp/cp_mean_shift/cp_std_ratio) UI 활용 0

**현재 동작**:
- fastapi push_payload 에 4 필드 모두 들어감 (확인됨)
- 클라이언트가 받아서 **어디에도 사용 안 함** — alarm-popup.js / event-panel.js 모두 미사용

**의도 추정 갭**:
- 본 sprint §F 의 의도 — UI 가 "급변 mean_shift=4.2 std_ratio=1.1" 같은 디테일 표시
- 실제 — 코드 작성 안 됨

**짚을 만한 후보**:
- (a) 토스트 본문에 cp_mean_shift / cp_std_ratio 디테일 추가
- (b) 이벤트 상세 페이지에서 anomaly_meta 전체 노출
- (c) UI 작성 자체를 보류 (시연 후)

### 5.3 AI 알람 vs Threshold 룰 알람의 중복 가능성

**현재 동작**:
- **POWER_ANOMALY_AI** (AI 측) 와 **POWER_OVERLOAD** (룰 측) 은 별도 alarm_type
- 같은 channel·시점에 둘 다 발화 가능
- **AI mute 가드 (60s)**: AI 가 먼저 발화하면 룰 측 60s suppress (Redis ai_fired)
- **격상 bypass**: AI=warning 발화 + 룰=danger 산출 시 룰 통과 (별도 키)
- 사용자에게 토스트가 두 종류 (`[IF 이상 감지]` + `[전력 이상]`) 동시 표시 가능

**의도 추정 갭**:
- 운영자 관점 — 같은 채널 1건 이상 = 1번만 알람? 아니면 AI / 룰 분리 표시?
- 현재 — 두 알람 type 이 별개로 노출. 운영자가 같은 사건을 2번 보는 느낌

**짚을 만한 후보**:
- (a) AI 가 발화하면 룰 알람 완전 suppress (현재는 60s 만)
- (b) AI · 룰 알람을 같은 토스트로 묶어 표시
- (c) 현 상태 유지 (별도 트랙)

### 5.4 3중 중복 방지의 의도

**현재 동작**:
- **rate_limit** (60s) — fastapi 측 같은 sensor_identifier push 1회/분
- **dedup fingerprint** (30s) — Redis SET NX, Celery retry 폭주 차단
- **cooldown** (60s) — DRF Event.last_notified_at, 재알림 skip
- **클라 dedup** (60s localStorage) — 다중 탭 중복 표시 방지

**의도 추정 갭**:
- 4 단계 중복 방지 — 의도된 다층 방어? 또는 과도?
- 시연 시 운영자가 "알람 자주 안 옴" 인지할 가능성 — 도메인별 cooldown 조정 필요?

**짚을 만한 후보**:
- (a) cooldown 60s → 30s 단축 (시연 가시성)
- (b) AI 알람만 cooldown 별도 (룰과 다른 TTL)
- (c) 현 상태 유지

### 5.5 EventAcknowledgement (user-scoped) vs 클라 dedup (localStorage)

**현재 동작**:
- **EventAcknowledgement**: 사용자가 "확인" 버튼 누름 → DB 저장 → 그 사용자만 재팝업 skip
- **localStorage dedup**: 60s 안에 같은 event_id 도착하면 클라가 자동 skip (사용자 액션 무관)

**의도 추정 갭**:
- 의도 추정 — 사용자 액션 (ack) + 자동 (dedup) 둘 다 작동
- 실제 — 둘 다 작동하지만 의미 다름. 사용자가 헷갈릴 수 있음 ("내가 확인 안 했는데도 알람이 사라졌어요?")

**짚을 만한 후보**:
- (a) dedup 시 시각적 표시 (예: 헤더 배지에 "60s 안 발생 알람 자동 묶음")
- (b) EventAcknowledgement 와 dedup 통합 UX
- (c) 현 상태 유지

### 5.6 모달 격상 정책 (60s 무응답 → 차단형)

**현재 동작**:
- `/admin-panel/*` 경로 → 우상단 토스트 스택
- 그 외 경로 → 중앙 차단형 모달
- DANGER 토스트 + 60s 무응답 → 모달 격상 (강제)
- WARNING → 10s 자동 닫힘

**의도 추정 갭**:
- 시연 시 운영자가 차단형 모달 닫지 않으면 작업 불능
- WARNING 10s 자동닫힘 — 운영자가 못 본 사이 알람 사라짐

**짚을 만한 후보**:
- (a) 모달 격상 disable / 토스트만 유지
- (b) WARNING 도 60s 자동 닫힘 (현재 10s 너무 짧음)
- (c) 시연 모드 / 운영 모드 분리

### 5.7 발화 등급별 표시 차이 (caution / predict_warn / warning / danger)

**현재 동작**:
- `_COMBINED_TO_RISK_LEVEL = {"caution": "warning", "predict_warn": "warning", "warning": "warning", "danger": "danger"}`
- AlarmRecord.risk_level 은 3단계 (normal/warning/danger) 로 압축
- combined_risk 4단계가 anomaly_meta 안에만 보존
- 토스트는 risk_level 만 보고 색상 결정 — caution / predict_warn 차이 X

**의도 추정 갭**:
- 본 sprint §F 5축 엔진의 의도 — 5단계 우선순위 (CRITICAL > ML_ANOMALY > ANOMALY_WARNING > TREND_SHIFT > PREDICTIVE_ALERT)
- 실제 UI — 2 색상 (warning/danger) 만

**짚을 만한 후보**:
- (a) UI 에 4단계 색상 (caution/predict_warn/warning/danger) 도입
- (b) RiskLevel enum 자체를 4단계로 확장 (현재 3단계 — TODO 주석에 "4차 추가 예정: CRITICAL")
- (c) 현 상태 유지 + combined_risk 칩 별도 표시

### 5.8 Event RESOLVED 자동 close 정책

**현재 동작**:
- Event.update_status(RESOLVED) → broadcast `event_resolved_at` 신호
- 클라가 같은 event_id 의 팝업 자동 close
- 정상화 토스트는 별도 (alarm_type 끝에 `_clear`)

**의도 추정 갭**:
- 위험 해소 시 자동 close — 운영자 관점에서 자연스러움
- 하지만 "내가 확인하기도 전에 사라짐" 불편 가능

**짚을 만한 후보**:
- (a) RESOLVED 시 alert close 대신 "위험 해소" 상태 표시 후 사용자가 닫기
- (b) 현 상태 유지
- (c) RESOLVED 알림 자체 비활성화

### 5.9 페이지 이탈 / 다중 탭 동작

**현재 동작**:
- WS 끊김 60s 지속 → fallback 폴링 (30s 주기, /alerts/api/alarms/catch-up/?since=)
- 재연결 시 catch-up API 호출 — 놓친 알람 일괄 수신
- 다중 탭 — localStorage 공유로 dedup / ack 동기 (헤더 배지는 탭별 독립)

**의도 추정 갭**:
- 페이지 이탈 후 돌아오면 모든 미확인 알람이 한꺼번에 표시될 수 있음 (catch-up 폭주)
- 다중 탭 — 한 탭에서 ack 했어도 다른 탭의 헤더 배지는 페이지 새로고침 전까지 안 줄어듬

**짚을 만한 후보**:
- (a) catch-up 시 토스트 폭주 방지 (최근 N건만)
- (b) 다중 탭 헤더 배지 실시간 동기
- (c) 현 상태 유지

### 5.10 algorithm_source="" (빈 값) 케이스

**현재 동작**:
- threshold 단독 발화 (예: 정격 100% 초과인데 IF 정상, ARIMA 정상, Z 정상, CP 정상)
- algorithm_source = `""` → UI fallback "AI" (또는 빈 칩)

**의도 추정 갭**:
- AlarmRecord 가 `algorithm_source=""` 인 케이스 = 사실상 "AI 가 발화한 게 아님"
- 그런데 alarm_type = POWER_ANOMALY_AI (AI 트랙) 로 저장됨
- 운영자가 "AI 가 잡았어?" 인지 모순

**짚을 만한 후보**:
- (a) algorithm_source="" 케이스에 POWER_OVERLOAD 로 분류 (룰 측에서 발화하도록)
- (b) 빈 라벨 → 별도 라벨 ("threshold_only" 같은)
- (c) 현 상태 유지 + UI fallback "AI" 명확화

---

### §5B JS ↔ 백엔드 인터페이스 미스매치 (11건)

**§5A 가 정책 수준 의문** 이라면, **§5B 는 코드 수준 인터페이스 어긋남**. 백엔드가 만들어 보낸 데이터가 JS 에 도달했을 때 다르게 해석되거나 사용 안 되는 영역.

#### 5B.1 anomaly_meta 4 필드를 JS 가 미수신·미처리

**현재 동작**:
- 백엔드 (`fastapi-server/power/services/power_service.py:432-449`) — `push_payload.anomaly_meta` 에 `z_score_anomaly`, `change_point`, `cp_mean_shift`, `cp_std_ratio` 4 필드 탑재
- JS (`drf-server/static/js/shared/alarm-mapper.js:39-42`) — `fromSensorsAlarm()` 이 `anomaly_meta` 자체를 읽지 않음. nested dict 미처리

**증상**: AI 토스트/이벤트 패널이 Z-score 발화 강도·CP 변화 메타 미표시. 운영자가 "왜 predict_warn?" 근거 불명확.

**짚을 만한 후보**:
- (a) AlarmMapper 가 `anomaly_meta` 객체째로 보존 + UI 컴포넌트가 활용
- (b) anomaly_meta 의 일부 핵심 필드 (algorithm_source, z_score_anomaly, change_point) 만 매핑
- (c) 미사용 그대로 유지 (UI 변경 비용 회피)

#### 5B.2 algorithm_source 가 토스트 prefix 칩으로 변환 안 됨

**현재 동작**:
- 백엔드 — `push_payload.anomaly_meta.algorithm_source` 에 신규값 (`zscore` / `change_point` 등) 탑재
- JS — `AlarmMapper` 가 이 필드 미처리. 토스트/모달이 별도 칩으로 렌더링 X

**증상**: 토스트가 단순 summary 문자열만 표시. `[Z-score 이상 감지]` 같은 prefix 는 summary 안에만 있고 시각적 강조 X.

**짚을 만한 후보**:
- (a) UI 칩 컴포넌트 신설 — algorithm_source 별 색상·아이콘
- (b) 토스트 헤더에 라벨 텍스트 추가
- (c) 미적용 유지

#### 5B.3 summary prefix vs 토스트 분기 (warning/danger 가 토스트 안 거치는 경우)

**현재 동작**:
- 백엔드 — `summary = f"[{algo_label} 이상 감지] CH1 watt=..."` 형태로 payload 에 prefix 포함
- JS (`alarm-ws.js:23-24`) — `risk_level === 'normal'` 만 `AlarmToast.show()`. warning/danger 는 `AlarmPopup.show()` (모달 직접) 로 분기 → summary 의 prefix 가 토스트 경로에서는 활용 안 됨

**증상**: 정상화 (`risk_level=normal`) 토스트는 prefix 안 보임 (해당 없음). warning/danger 모달은 prefix 가 본문 텍스트로 묻혀 시각적 강조 X.

**짚을 만한 후보**:
- (a) warning/danger 도 토스트 → 모달 격상 경로로 통합
- (b) 모달에 algorithm_source 칩 별도 표시 (5B.2 와 결합)
- (c) 현 상태 유지

#### 5B.4 algorithm_source 가 DB 에 저장은 되나 이벤트 패널 미표시

**현재 동작**:
- 백엔드 — `AlarmRecord.algorithm_source` 필드 저장 + `get_short_message()` 가 라벨 prefix 생성
- JS (`event-panel.js:268`) — `data.message || data.alarm_type` 만 표시. `data.algorithm_source` 미사용

**증상**: 이벤트 패널이 AI 알람에 "전력 AI 이상 감지" 통합 text 만 노출. IF / Z-score / 급변 출처 칩 표시 X.

**짚을 만한 후보**:
- (a) 이벤트 패널 row 에 algorithm_source 칩 추가
- (b) 이벤트 상세 페이지에서만 노출
- (c) 미적용

#### 5B.5 dedup TTL 차이 — 백엔드 30s vs 클라 60s

**현재 동작**:
- 백엔드 `PUSH_DEDUP_TTL_SEC = 30` (`alarm_queue.py:40`) — Redis fingerprint
- 클라 `_DEDUP_TTL_MS = 60_000` (`alarm-popup.js:60`) — localStorage

**증상**: 30~60s 사이에 백엔드가 같은 알람 재push 하면 클라가 차단 (운영자가 두번째 발화 인지 못 함). 역으로 클라 만료 후 (60s+) 백엔드 dedup 통과 시 중복 팝업 가능 영역 있음.

**짚을 만한 후보**:
- (a) 두 TTL 통일 (60s) — 의도 일치
- (b) 30s 로 통일 — 시연 가시성
- (c) 의도된 차이라면 docstring 명시

#### 5B.6 EventAck (user-scoped) vs 클라 dedup (사용자 무관)

**현재 동작**:
- `_AckStore` (localStorage, event_id 키, 24h TTL) — **사용자별** ack 기록
- `_DedupStore` (alarm_type:source:level 키, 60s TTL) — **전체 사용자 무관**

**증상**: 다중 사용자 환경 — 사용자 A 가 ack 해도 사용자 B 의 dedup 은 별개로 동작. ack 의미 ("나만 봤음") 와 dedup 의미 ("최근 도착") 가 운영자에게 헷갈릴 수 있음.

**짚을 만한 후보**:
- (a) ack 시점에 dedup 도 강제 설정 (재팝업 X)
- (b) dedup 을 사용자별 (localStorage 키에 user_id 포함)
- (c) 현 상태 유지 + UI 에서 의도 설명

#### 5B.7 4단계 combined_risk vs 3단계 risk_level — UI 색상 collapse

**현재 동작**:
- 백엔드 — `combined_risk` 4단계 (normal/caution/predict_warn/warning/danger 사실상 5 — caution + predict_warn 별도) 산출
- 변환 — `_COMBINED_TO_RISK_LEVEL` 가 caution/predict_warn 둘 다 `warning` 으로 압축
- JS (`level-mapper.js:18-22`) — `TO_CSS = {danger, warning: caution, normal: safe}`. caution / predict_warn 시각적 동일

**증상**: STEP 5 권고의 5단계 우선순위 (CRITICAL > ML_ANOMALY > ANOMALY_WARNING > TREND_SHIFT > PREDICTIVE_ALERT) 가 UI 에서 2 색상 (warning/danger) 로 압축 — 운영자가 단계 구분 못 함.

**짚을 만한 후보**:
- (a) RiskLevel enum 자체를 4단계로 확장 (constants.py 의 TODO 주석 — "4차 추가 예정: CRITICAL")
- (b) anomaly_meta.combined_risk 를 JS 가 별도 읽어 색상 분기
- (c) 현 상태 유지 (시연 후 결정)

#### 5B.8 신규 algorithm_source 값 (zscore / change_point) JS 라벨 정의 없음

**현재 동작**:
- 백엔드 — `_ALGORITHM_SOURCE_LABEL` (fastapi) ↔ `ALGORITHM_SOURCE_LABEL` (drf) 양쪽에 한국어 라벨 보유
- JS — 동일 dict 가 `drf-server/static/js/` 에 **정의 안 됨**

**증상**: 만약 5B.2 / 5B.4 가 적용되어도 JS 가 `zscore` / `change_point` 문자열을 한국어 라벨 ("Z-score" / "급변") 로 변환 못 함. 원시값 그대로 표시 또는 무시.

**짚을 만한 후보**:
- (a) JS 측 `algorithmSourceLabel.js` 모듈 신설 — 백엔드 dict 와 동기
- (b) 백엔드가 `algorithm_source` 와 함께 `algorithm_source_label` (한국어) 도 push_payload 에 동봉
- (c) UI 미적용 결정 시 불필요

#### 5B.9 gas_anomaly_ai 아이콘 미정의 (불균형)

**현재 동작**:
- 백엔드 — `gas_anomaly_ai` 가 `POWER_ANOMALY_AI` 와 동일 구조
- JS (`event-panel.js:31`) — `ICON_BY_TYPE = {power_anomaly_ai: 'brain-circuit'}` 만 정의. `gas_anomaly_ai` 누락

**증상**: 가스 AI 알람이 이벤트 패널에 떴을 때 기본 'bell' 아이콘 사용 — 운영자가 AI 알람인지 인지 약함.

**짚을 만한 후보**:
- (a) `gas_anomaly_ai: 'brain-circuit'` 추가 — 즉시 통일
- (b) 가스 별도 아이콘 (다른 시각 구분)

#### 5B.10 event_resolved_at dedup 미고려 — RESOLVED 토스트 차단 가능

**현재 동작**:
- 백엔드 `alarm_queue.py:72-73` — `event_resolved_at` 박혀 있으면 dedup key `event:{id}:resolved` (별도)
- 클라 `alarm-popup.js:353` `_popupDedupKey()` — `event_resolved_at` 필드 무시. 원래 알람과 같은 `event:{id}` 키 사용

**증상**: 같은 event 의 원래 발화 후 RESOLVED 신호가 클라에 도달했을 때 **localStorage dedup 이 차단** → "위험 해소" 알림 미표시 가능.

**짚을 만한 후보**:
- (a) 클라가 `event_resolved_at` 필드 확인 후 별도 dedup key 생성
- (b) RESOLVED 신호 자체를 dedup 면제

#### 5B.11 CustomEvent newAlarmEvent payload 필드 불일치 (fallback 회피 중)

**현재 동작**:
- 백엔드 → AlarmMapper.fromSensorsAlarm() 변환 → `CustomEvent('newAlarmEvent', { detail: alarmData })` dispatch
- listener (`event-panel.js`, `alarm-badge.js`) — 기대 필드명 vs 실제 dispatch 필드명 일부 불일치 (예: `source_label` vs `sensor_name`) → fallback chain 으로 회피 중

**증상**: 치명적 오류 X. 다만 listener 코드의 fallback 체인이 길어지고 의도 흐려짐. 새 필드 추가 시 listener 마다 일일이 매핑 추가 부담.

**짚을 만한 후보**:
- (a) AlarmMapper 결과 스키마 명시화 + listener 가 단일 객체 형식 의존
- (b) Type/Interface 정의 (TS 도입 또는 JSDoc)
- (c) 현 상태 유지 (fallback 으로 충분)

---

### §5C 알람 팝업 텍스트 구성 문제 (8건)

**§5A 가 정책, §5B 가 코드 인터페이스** 라면, **§5C 는 운영자가 실제로 보는 텍스트 자체의 일관성·포맷·정보 노출 문제**. 5B 와 일부 영역이 겹치지만 관점이 다름 — 5B 는 "어느 필드를 어떻게 매핑하는가", 5C 는 "결과 텍스트가 운영자에게 어떻게 보이는가".

#### 5C.1 ML 기술용어가 운영자 팝업에 그대로 노출

**현재 동작**:
- 백엔드 (`power_service.py:393-396`):
  ```python
  summary = (
      f"[{algo_label} 이상 감지] {label} {data_type}={value} "
      f"(score {score:.4f}, combined={combined})"
  )
  ```
- 결과 예: **`[IF 이상 감지] 송풍기A watt=7925.8 (score 0.0292, combined=warning)`**
- JS (`alarm-popup.js:465`, `event-panel.js:268`) — `data.message || data.summary` 그대로 표시

**증상**: `score 0.0292` (IF decision_function 값) 와 `combined=warning` (내부 enum) 같은 ML 내부 상태가 팝업·이벤트 패널에 노출. 운영자가 의미 모름.

**짚을 만한 후보**:
- (a) summary 에서 `(score ..., combined=...)` 제거 — 단순화
- (b) ML 메타는 `anomaly_meta` 에만 보존, summary 는 운영자 문장만
- (c) 현 상태 유지 (운영자가 ML 학습 기회)

#### 5C.2 message vs summary 필드 이원화 — 같은 알람의 두 가지 텍스트

**현재 동작**:
- **WS push summary**: `[IF 이상 감지] 송풍기A watt=7925.8 (score 0.0292, combined=warning)` (기술적)
- **DB short_message** (`alarm_record.py:148-189` `get_short_message()`): `송풍기A AI 이상 감지 (7925.8 W)` (운영자 친화)
- JS 매핑 (`alarm-mapper.js:22`): `message: src.message || src.summary` — message 가 채워졌으면 message, 아니면 summary fallback

**증상**: WS 토스트 = summary (기술적) vs 알람 이력 페이지 (API 호출) = short_message (친화적). **같은 알람이 위치에 따라 다른 텍스트**.

**짚을 만한 후보**:
- (a) push_payload 의 summary 도 short_message 와 동일 포맷으로 통일
- (b) 둘 다 push 에 동봉 — 토스트는 short_message, ML 모달은 summary
- (c) DB 와 push 의 명확한 분리 (각자 의도 다름) + JS 매핑 명시화

#### 5C.3 토스트 / 모달 / 이벤트 패널 표시 텍스트 불일치

**현재 동작**:
- 토스트 (`alarm-popup.js:198`): `data.message || data.summary`
- 모달 (`alarm-popup.js:465`): `data.message || data.summary`
- 이벤트 패널 (`event-panel.js:268`): `data.message || data.alarm_type` ← `alarm_type` fallback ("power_anomaly_ai" 영문 코드)

**증상**: message 가 없는 알람이 이벤트 패널에 떴을 때 **`power_anomaly_ai` 같은 영문 코드가 노출**. 운영자에게 의미 없음.

**짚을 만한 후보**:
- (a) 이벤트 패널 fallback 을 `alarm_type` 대신 사람 친화 라벨 (`AlarmType` choices label) 로 변경
- (b) 모든 위치 fallback 통일 (`message || short_message || summary || "AI 이상 감지"`)
- (c) 현 상태 유지

#### 5C.4 도메인별 메시지 형식 불일치 (전력 vs 가스)

**현재 동작**:
- 전력 summary (`power_service.py:393`): `[IF 이상 감지] 송풍기A watt=7925.8 (...)` (영문 prefix + 영문 단위)
- 가스 summary (`tasks.py:140`): `[긴급] CO 위험 수준 초과` (한국어 prefix + 한국어 자연어)
- AlarmRecord.get_short_message: `송풍기A AI 이상 감지 (7925.8 W)` (한국어 + W)

**증상**: 운영자가 알람을 받았을 때 도메인별로 메시지 패턴이 다름. **`[IF 이상 감지]` vs `[긴급]` vs `[주의]`** — 같은 시스템 알람인데 prefix 양식 다름.

**짚을 만한 후보**:
- (a) 통일 포맷 — `[위험도/출처] 발생원 현상 (측정값 단위)` 예: `[위험·IF] 송풍기A 이상 (7,925 W)` / `[위험·임계] CO 누출 (52 ppm)`
- (b) 도메인별 자유 형식 (현 상태) + 컨벤션 가이드만
- (c) 단순화 — prefix 제거하고 `algorithm_source` 칩으로 시각 분리

#### 5C.5 정상화 메시지 (위험 해소) 형식 불통일

**현재 동작**:
- 백엔드 — 가스/전력 fire_clear_*_task 측 형식 불일치
- AlarmRecord.get_short_message — `"정상 복귀"`
- JS (`alarm-popup.js:533`) — `message: '위험 해소'` (하드코딩)

**증상**: 동일 사건의 정상화가 어디서는 "정상 복귀", 어디서는 "위험 해소". 운영자가 혼동 가능.

**짚을 만한 후보**:
- (a) 백엔드가 정상화 메시지 단일 source 로 push — JS 하드코딩 제거
- (b) 운영자 친화 통일 — "위험 해소 — {발생원} {현상} 정상 복귀"
- (c) 현 상태 유지

#### 5C.6 숫자·단위 포맷 — 천단위 구분·단위 접미사 통일성

**현재 동작**:
- 전력 (`power_service.py:394`): `watt=7925.8` (단위 없음, 천단위 구분 없음)
- 가스 (`tasks.py:163`): `(2.5 ppm)` (단위 있음, 천단위 무관)
- short_message (`alarm_record.py:180`): `(7925.8 W)` (단위 있음, 천단위 구분 없음)

**증상**: 큰 숫자 (예: `12345.67 W`) 가 한 줄로 노출되면 가독성 ↓. `12,345 W` 형식이 운영자 친화.

**짚을 만한 후보**:
- (a) 통일 포맷터 신설 (백엔드 또는 JS 측) — `format_value(value, unit, decimals=1)` 으로 모든 메시지 통과
- (b) JS 만 포맷팅 (현재 raw 값 push)
- (c) 현 상태 유지

#### 5C.7 시간 표시 — TimeFormat 의존성·시간대 명시

**현재 동작**:
- 백엔드 — `created_at` UTC ISO-8601 (`tasks.py:71`)
- JS — `TimeFormat.abs(ts)` (있으면) / `toLocaleTimeString()` (fallback)
- TimeFormat 모듈 로드 실패 시 raw ISO 또는 부분 시간만

**증상**:
- TimeFormat 미로드 환경에서 절대시각·"방금 전" 같은 친화 표시 안 됨
- KST / UTC 시간대 명시 부재 — 운영자가 헷갈릴 수 있음

**짚을 만한 후보**:
- (a) TimeFormat 을 코어 의존성으로 명시·로드 보장
- (b) 백엔드가 KST 변환된 사람 친화 시각도 같이 push (`"display_time": "2026-05-19 15:34 KST"`)
- (c) 현 상태 유지

#### 5C.8 algorithm_source 라벨이 텍스트의 어디에도 별도 칩으로 안 보임

**현재 동작**:
- summary 안에 `[IF 이상 감지]` prefix 로만 들어가 있음 — text 안에 묻힘
- `anomaly_meta.algorithm_source` 는 push 되지만 JS 가 미사용 (5B.2 참조)
- 토스트·모달·이벤트 패널 어디에도 IF / Z-score / 급변 / ARIMA / 야간 가동 **시각적 배지 없음**

**증상**: 본 sprint §F 의 의도 — "운영자가 어떤 축이 발화했는지 즉시 인지" — 가 텍스트 묻힘으로 약화. summary 끝까지 안 읽으면 출처 모름.

**짚을 만한 후보**:
- (a) 토스트·이벤트 패널에 `algorithm_source` 별 색상·아이콘 칩 추가 (5B.2·5B.4 와 결합)
- (b) summary 의 prefix 제거 → 칩으로 대체
- (c) 현 상태 유지 (prefix 텍스트로 충분)

### 좋은 점 (현 시스템의 강점)

| # | 강점 | 의의 |
|---|---|---|
| 1 | `algorithm_source` 를 `anomaly_meta` 별도 구조로 보존 (`power_service.py:446`) | UI 통합 시 칩 표시 위한 기반 마련됨 |
| 2 | dedup 컨벤션 토스트·이벤트 패널 일관 (`alarm-popup.js:54-106` + `event-panel.js:82-92`) | 한 알람이 두 곳에 중복 표시 방지 일관성 |

---

## §6. 다음 단계 — 사용자 인터뷰 → plan

본 문서를 읽고 §5A 10건 + §5B 11건 + §5C 8건 (총 29개 후보) 중 **의도와 다른 것 / 재수정 필요한 것** 을 짚어주시면:

1. **Step 2 — 의도 차이 정리**: 짚인 항목별로 (a)/(b)/(c) 중 어느 방향 + 구체적 의도 인터뷰
2. **Step 3 — 재설계 plan**: 시연 리허설 (D-7, 2026-06-07) 전까지 Phase 분리. 우선순위 매트릭스 ↔ 일정.
3. **Step 4 — 적용 + 검증**: 단위·모듈·e2e + 라이브 시나리오

§5A·§5B·§5C 외에도 본 문서를 보면서 새로 인지된 갭이 있으면 그것도 짚기.

---

## §7. 부록 — 코드 위치 빠른 인덱스

| 영역 | 진입점 | 핵심 함수 |
|---|---|---|
| AI 추론 | `fastapi-server/power/services/power_service.py` | `process_anomaly_inference` |
| 5축 결합 | `fastapi-server/ai/risk_combine.py` | `combine_risk_5axis` |
| AI mute | `fastapi-server/services/ai_mute.py` | `mark_ai_recent`, `is_recently_fired` |
| forward 통합 | `fastapi-server/services/anomaly_alarm.py` | `forward_inference_e2e` |
| Redis dedup | `fastapi-server/websocket/services/alarm_queue.py` | `push_alarm` |
| WS broadcast | `fastapi-server/websocket/routers/ws_router.py` | `alarm_flush_loop`, `_send_to_all` |
| 룰 발화 | `drf-server/apps/monitoring/services/power_alarm.py` | `trigger_power_alarms` |
| Event 병합 | `drf-server/apps/alerts/services/event_service.py` | `create_alarm_and_event` |
| AlarmRecord 모델 | `drf-server/apps/alerts/models/alarm_record.py` | `AlarmRecord` |
| Celery task | `drf-server/apps/alerts/tasks.py` | `fire_*_task` (gas/power/geofence) |
| WS 클라 수신 | `drf-server/static/js/shared/alarm-ws.js` | `WSClient.connect('/ws/sensors/')` |
| 클라 dedup | `drf-server/static/js/shared/alarm-popup.js` | `_DedupStore` |
| 토스트/모달 | `drf-server/static/js/shared/alarm-popup.js` | `AlarmToastStack`, `AlarmPopup` |
| 헤더 배지 | `drf-server/static/js/shared/alarm-badge.js` | `AlarmBadge` |
| EventAck API | `drf-server/apps/alerts/views/event.py` | `EventAckView.post` |
| 이벤트 패널 | `drf-server/static/js/dashboard/panels/event-panel.js` | `EventPanel` |

---

> **이 문서의 핵심 메시지**:
> 알람 비즈니스 로직은 (1) AI 추론 → 5축 결합 → AlarmRecord 생성, (2) Redis dedup + WebSocket broadcast, (3) 클라 dedup + 토스트/모달 + 배지 + EventAck 세 레이어로 구성. 본 문서 §2 가 전 흐름 다이어그램, §3 가 컴포넌트별 책임, §4 가 페이로드 구조. **§5A 백엔드 동작·정책 갭 10건 + §5B JS-백엔드 인터페이스 미스매치 11건 + §5C 알람 팝업 텍스트 구성 문제 8건 = 총 29개 후보** 중 사용자가 짚는 항목에 따라 다음 단계 (재설계 plan) 우선순위 결정.
