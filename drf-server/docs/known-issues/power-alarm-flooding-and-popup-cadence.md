# 전력 알람 폭주 + "버튼 누르면 다음 알람 바로 울림"

**발견일**: 2026-06-02 (팀원 피드백 — 전력 DANGER/WARNING 폭주 + 팝업 연쇄)
**상태**: 진단 완료 — fix 는 [skill/plan/power-alarm-flood-fix.md](../../../skill/plan/power-alarm-flood-fix.md) 로 분리
**시연 영향**: 시연 시나리오 B(전력)에서 체감 큼. 현재 구성(`STATIC_THRESHOLD_AT_FASTAPI=False`, 기본 모드 `mixed`)에서 실재.
**검증 방식**: 코드 직접 확인 + 독립 에이전트 6건 adversarial verify (전부 confirm / 2건 뉘앙스 정정)

---

## 증상

팀원 피드백 두 가지:

1. **전력 DANGER/WARNING 알람이 비정상적으로 폭주** — 가스에선 안 보이는 현상.
2. **팝업 "확인 완료" 버튼을 누르면 다음 알람이 바로(0초) 울림** — 비프음과 함께 연쇄.

두 증상은 **한 뿌리의 앞/뒤 구간**이다 (아래 결론).

---

## 데이터 흐름 (현재 상태)

```
더미(1초 주기, 16채널 W·A·V) → fastapi 수신
  → drf 임계 평가 trigger_power_alarms (채널별 max-of-3축)
  → Celery fire_power_{danger,warning,clear}_task
  → create_alarm_and_event (Event 병합/생성)
  → Redis Stream(diconai:ws:alarms) → flush_loop broadcast
  → 프론트 AlarmPopup 큐 → 모달
```

**dedupe 경계 핵심:** 전력은 `(device, channel)` 단위로 발화하지만, **Event 병합은 `(facility, event_type, device)` — 채널 무시**. 즉 16채널이 디바이스당 Event **하나**를 공유한다.

---

## 구간 A — 백엔드: "폭주"의 진짜 원인

### A-1. 정정된 메커니즘 — clear 가 Event 를 디바이스 전체로 RESOLVE → event_id churn

초기 가설("채널×16 = 팝업×16")은 **틀렸다.** 룰 Event 는 디바이스 단위로 병합되고([event_service.py:67-83](../../apps/alerts/services/event_service.py#L67-L83)) 60초 cooldown 재알림([event_service.py:139-158](../../apps/alerts/services/event_service.py#L139-L158))이라, 같은 event_id 는 프론트가 dedup 한다. 진짜 원인은 **정상화(clear) 처리의 비대칭**이다:

| | clear 호출 | 결과 |
|---|---|---|
| **가스** | `auto_resolve_active_events(..., cleared_gases=gas_types)` ([tasks.py:425-429](../../apps/alerts/tasks.py#L425-L429)) | event 알람 gas 가 **전부 cleared 일 때만** RESOLVE ([event_service.py:299](../../apps/alerts/services/event_service.py#L299)) — 일부만 정상이면 Event 유지 |
| **전력** | `auto_resolve_active_events(event_type_prefix="power", power_device_id)` ([tasks.py:638-640](../../apps/alerts/tasks.py#L638-L640)) | **채널 무관, 디바이스 전체** RESOLVE (prefix `"power"` 라 `power_overload`·`power_anomaly_ai` 둘 다) |

**가스가 이미 `cleared_gases` 로 고친 race 를 전력은 그대로 안고 있다.** 흐름:

```
1. ch2 danger → Event E1(event_id=100) 생성 → 팝업. 프론트 _DedupStore[event:100] (60s)
2. ch2 잠깐 정상 복귀 → fire_power_clear_task → 디바이스 Event 전체 RESOLVED (ch3 위험해도)
3. 다음 위험(같은/다른 채널) → E1 닫혔으니 새 Event E2(event_id=101) 생성
4. 프론트 dedup·ack store 는 event_id 키 → 101 은 처음 보는 값 → dedup 통과 → 즉시 새 팝업
5. mixed 모드(기본)는 16채널이 비동기로 임계 부근을 들락날락 → 새 event_id 가 계속 찍혀
   60초 throttle 을 무력화 → 폭주
```

가스는 1센서·전이형(누출→해소)이라 churn 이 잘 안 나지만, 전력은 16채널이 비동기로 오르내려 churn 이 상시 발생 → **"전력만 폭주"의 정체.**

### A-2. 보조 — 60초 재발화 cadence

위험 지속 시 `_CACHE_TTL=60` ([power_alarm.py:59-63](../../apps/monitoring/services/power_alarm.py#L59-L63)) 만료로 매 분 재알림(의도된 escalation). **같은 event_id 면** 프론트가 dedup(분당 1회) → 정상. churn(A-1)으로 event_id 가 바뀌면 이 throttle 이 깨진다.

### A-3. clear 는 떠있는 팝업을 닫지 않는다 (UX 갭)

`fire_power_clear_task` push 는 `risk_level=normal`·`is_new_event=False`·**event_id/event_resolved_at 없음** ([tasks.py:623-634](../../apps/alerts/tasks.py#L623-L634)). 프론트 `_handleResolved` 는 `event_resolved_at` 로 트리거되므로([alarm-popup.js:459](../../static/js/shared/alarm-popup.js#L459)) **전력 clear 는 떠있는 DANGER 팝업을 닫지 않고** 정상 토스트만 띄운다. DB Event 는 백엔드에서 조용히 RESOLVE 되지만 운영자 화면의 팝업은 자동닫힘(15s)/수동 ack 까지 남는다 → 그 위로 새 event_id 팝업이 쌓임.

---

## 구간 B — 프론트: "버튼 누르면 다음 알람 바로 울림"

`확인 완료` → `close({acknowledged:true})` 마지막 줄에서 **동기로 `this._process()`** 호출([alarm-popup.js:700-718](../../static/js/shared/alarm-popup.js#L700-L718)) → `queue.shift()` 직후 렌더 + `_playAlarmSound` ([:578,:592](../../static/js/shared/alarm-popup.js#L575-L596))까지 **0ms·디바운스 없음**.

### 정정 (adversarial verify)
- **자동닫힘 경로엔 이미 간격이 있다** — `_AUTO_CLOSE_MS = {danger:15000, warning:30000}` ([:393](../../static/js/shared/alarm-popup.js#L393)). 팝업을 가만 두면 다음 게 15~30초 뒤 등장.
- **따라서 "바로 울림"은 수동 ack(버튼) 경로 한정** — 운영자가 폭주를 빨리 넘기려 버튼을 연타할 때만 0ms 연쇄 + 비프 폭격. 이게 정확히 팀원이 본 현상.

즉 구간 A 가 큐를 채우고 → 운영자가 버튼으로 빠르게 비우려 하면 구간 B 가 0ms 로 다음을 들이민다.

---

## 결론 — 한 뿌리

> 전력이 (A) **clear 의 device-wide resolve 로 event_id churn** 을 일으켜 60초 throttle 을 무력화 → 폭주.
> 운영자가 (B) **수동 ack 로 큐를 비우면 0ms·비프와 함께 다음이 즉시** 표출.
> 둘이 곱해져 "폭주 + 버튼 누르면 바로" 한 세트로 체감.

---

## 관련 파일·라인

| 파일 | 라인 | 역할 |
|---|---|---|
| `apps/alerts/tasks.py` | 638-640 | **fire_power_clear_task — device-wide resolve (A-1 핵심)** |
| `apps/alerts/tasks.py` | 425-429 | 가스 clear — `cleared_gases` 전달 (비대칭 비교) |
| `apps/alerts/services/event_service.py` | 67-83 | Event 병합 키 (channel 미포함) |
| `apps/alerts/services/event_service.py` | 241-328 | `auto_resolve_active_events` (287-310 = 가스 subset 게이팅) |
| `apps/monitoring/services/power_alarm.py` | 266-274 | normal 분기 — clear 발화 + `clear_state` |
| `apps/monitoring/services/power_alarm.py` | 59-63 | `_CACHE_TTL=60` 재발화 cadence (A-2) |
| `apps/monitoring/services/power_alarm.py` | 188, 195, 234-236 | value=현재 축 / aggregate=max-of-3 (부가 발견) |
| `static/js/shared/alarm-popup.js` | 700-718 | `close()` → 동기 `_process()` (B 핵심) |
| `static/js/shared/alarm-popup.js` | 575-596 | `_process()` shift + 비프 0ms |
| `static/js/shared/alarm-popup.js` | 393 | `_AUTO_CLOSE_MS` (자동닫힘 간격 — 수동만 0ms) |
| `static/js/shared/alarm-popup.js` | 489-498, 544 | 격상 unshift+close / show 의 `!isOpen` 가드 |

---

## 영향 범위

- **전력 DANGER/WARNING 알람 운영자 UX** (모니터링 페이지 모달). admin-panel 토스트 경로는 자체 stack 이라 영향 작음.
- 가스는 `cleared_gases` 로 이미 보호됨 — 본 이슈 무관.
- 데이터/DB 무결성 문제 아님 (Event 가 일찍 RESOLVE 될 뿐, AlarmRecord 이력은 보존).
- 안전 부작용 1건: A-1 step 2 에서 ch2 clear 가 ch3(아직 위험) Event 를 RESOLVE → ch3 위험이 일시적으로 "활성 Event 없음" 상태가 됨 (다음 60s state 만료 시 재발화). 시연 영향은 폭주 체감 쪽이 큼.

---

## 검증 방법 (재현·관찰)

1. **재현:** 더미 `mixed` 모드(기본) 또는 다채널 시나리오(`voltage_drop`)로 5분 가동 → 모니터링 페이지에서 전력 팝업이 새 event_id 로 반복 등장하는지 확인.
2. **백엔드 churn 관찰:** `drf-server/logs/app.log` 에서 `전력 정상화 알림 | ... resolved=N` 과 `전력 DANGER/WARNING ... new_event=True` 의 교대 패턴. resolved 직후 새 발화가 짧은 간격으로 반복되면 churn.
   - 참고 로그 근거: [app.log:1090-1118](../../logs/app.log#L1090-L1118)(ch2 60초 재발화), [app.log:1240-1256](../../logs/app.log#L1240-L1256)(20:46 16채널 동시 정상화).
3. **프론트 0ms 연쇄:** 큐에 2건 이상 쌓인 상태에서 `확인 완료` 연타 → 다음 팝업이 즉시 + 비프음과 함께 뜨는지.

---

## 부가 발견 (본 이슈와 별개 — 보고만)

1. **DANGER 표시값 혼란 (confirmed):** 위험 판정은 `aggregate=max(W,A,V)` ([power_alarm.py:195](../../apps/monitoring/services/power_alarm.py#L195))인데 팝업 `measured_value` 는 **현재 처리 축의 값**([:188](../../apps/monitoring/services/power_alarm.py#L188))뿐. 저전압 축이 DANGER 를 끌어올린 순간 watt 페이로드가 처리되면 정격 3700W 채널에 `15.71W` 가 위험으로 표시 → "왜 이게 위험?" 혼란. 폭주 원인 아님. → 별도 sprint.
2. **AI rate-limit 이 프로세스 메모리·축별 키** — multi-replica 시 새는 부분. 알람 스트림 이니셔티브에서 다룸.
3. **더미 single 모드 매 틱 `enter_scenario` 재진입** — 테스트 하네스 한정, 운영 무관.

---

## Fix 방향

→ [skill/plan/power-alarm-flood-fix.md](../../../skill/plan/power-alarm-flood-fix.md) (A: 전력 clear 채널-aware / B: 수동 ack 간격 + 비프 throttle)
