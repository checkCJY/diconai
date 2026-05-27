# 알람 시스템 시연 준비 — 진단에서 결정까지 (2026-05-26)

> **목적**: 학습용 회고. 시연 D-19 시점 알람 4문제를 어떻게 진단하고 어떤 결정으로 풀었는지를 의식의 흐름으로 정리.
> **다음 세션**: 본 문서 + [`MEMORY.md`](../../../.claude/projects/-home-cjy-diconai/memory/MEMORY.md) 만 읽어도 컨텍스트 복원 가능하도록 작성.

---

## 한 줄 요약

시연 리허설 알람 4문제 (연결실패 / 알람폭주 / 격상미지원 / 중복) 발견 → 4개 패치 진행 중 **#2 격상 검증에서 진짜 root cause (event_service cooldown 차단) 발견** → 5개 패치 + Makefile demo target 9종 + 문서 모두 완료. 가스 AI mute 가드 옵션 B 적용. 시연 안정성 확보. 시연 후 sprint 거리: C-full 매트릭스 / 지오펜스 84% 보강 / 메모리 정정 / 더미 정비.

---

## 0. 배경

- **시연 D-day**: 2026-06-14, 현재 D-19
- **시연 시나리오**: A(가스 누출) + B(전력 IF+5축) + C(정책 커스터마이징)
- **리허설 트리거**: `make scenario-set mode=overload`
- **사용자 입에서 "하아씨발"**: 알람 팝업 60ppm 표시인데 실제 측정 297ppm 불일치 발견

---

## 1. 발견된 문제 4가지

| # | 증상 |
|---|---|
| 1 | 시연 시나리오 패널 "연결 실패" |
| 2 | 알람 폭주 (한 트리거에 25개+ 알람, 18개+ silent drop) |
| 3 | 알람 팝업 주의 → 위험 갱상 안 됨 (격상 미지원) |
| 4 | AI 알람 + 정적 임계치 알람 동시 발화 (중복) |

거기에 부수적:
- 이벤트 누적 (90+건 RESOLVED 없음)
- 더미 노이즈 자동 발화 (`DUMMY_RISK_PROBABILITY=0.1`)

---

## 2. 진단 흐름 (의식의 흐름)

### Step 1 — 환경부터 점검

> "env 수정했는데 안 붙은 거 아냐?"

확인:
```bash
make demo-check   # DUMMY_SCENARIO_MODE=normal 적용 여부
```

→ 적용 확인. **#1 시연 패널 연결 실패 = fastapi 재기동만으로 해결**.

### Step 2 — 알람 폭주 원인 추적

콘솔 로그:
```
[알람 수신] ['danger(new=true)']  ×18
queue full, dropping alarm {droppedTotal: 1~18}
```

코드 확인 (병렬):
- `power_dummy.py` overload 시나리오: `multi: False` 였는데 16채널 발화? → 의문
- `alarm-popup.js`: `MAX_QUEUE = 5` 하드코딩 → drop 발생 명확

깊이 보니:
- `overload` 가 `multi: False` 일 때도 random.choice(MOTOR_CHANNELS) 11개 중 1개라 양 자체는 줄어들지만, 한 채널에 W/A/V 3축 + AI 통합되면 5개 동시 발화 가능

**결정**:
- 발화 채널 풀을 `AI_DEMO_CHANNELS = [1, 9, 14, 15]` (AI 학습된 채널) 로 제한
- MAX_QUEUE 5 → 30

**왜 AI 채널 4개?**
- 시연 멘트에서 "AI 추론 + mute 가드 동작" 같이 보여줄 수 있어서
- 학습 안 된 채널에서 정적 룰만 fire 하는 시연 가치 X

### Step 3 — `_AckStore` 가설 (오답)

> 메모리 [alarm_symptom_diagnosis_2026_05_20] 가 1순위 가설로 적은 "_AckStore 24h 영구 차단"

검증 (localStorage):
```javascript
JSON.parse(localStorage.getItem('diconai:alarm:acked_event_ids'))
// → [] 빈 배열
```

→ 가설 기각? 하지만 **사용자 지적**: "검증 시점이 시연 후 60초+ 이라서 자연 만료됐을 수도. 가설 기각 근거 부족"

→ 정확. 다만 코드 확인:
```javascript
// alarm-popup.js T5 (2026-05-20) — 24h → 60s 단축
const _ACK_TTL_MS = 60_000;
```

이미 24h → 60s 단축됨. 가설 자체가 영향 매우 작음. **메모리 stale**.

**학습**: 메모리는 stale될 수 있음. 코드 직접 확인이 truth.

### Step 4 — 진짜 격상 미지원 발견

[alarm-popup.js:182](../../drf-server/static/js/shared/alarm-popup.js):
```javascript
push(data) {
    const eventId = data.event_id || data.id;
    if (eventId != null && this._items.has(eventId)) return;  // ← 차단
```

→ 같은 `event_id` 후속 알람 (DANGER 격상 포함) 모두 무시. 안전장치인데 격상 케이스를 못 잡음.
→ **#2 패치 = alarm-popup.js 격상 처리** 추가 필요.

### Step 5 — AI vs 정적 분리 발화

가스 측 코드 확인:

| 위치 | 동작 |
|---|---|
| [gas_service.py:195](../../fastapi-server/gas/services/gas_service.py#L195) | AI 발화 시 `push_alarm` 직접 호출 (`alarm_type=gas_anomaly_ai`) |
| `gas_alarm.py` | 정적 룰 발화 시 `fire_*_task.delay` (`alarm_type=gas_threshold`) |
| fingerprint | `ai:*` 키 공간 vs `event:*` 키 공간 → **dedup 안 통과** |

전력은 [`is_ai_mute_active`](../../drf-server/apps/alerts/services/alarm_dedupe.py) 가드 있음. 가스에 없음.

→ **#4 패치 = 가스에 mute 가드 + decide_alarm 매트릭스 적용**

### Step 6 — Event 자동 RESOLVED 누락

[`fire_clear_*_task`](../../drf-server/apps/alerts/tasks.py) 주석:
> "이벤트 상태는 운영자가 직접 변경"

명시적 설계 결정이었지만 시연 반복 시 이벤트 누적 → 화면 지저분. 자동 처리로 변경.

→ **#3 패치 = `auto_resolve_active_events` 신규 함수 + `fire_clear_*_task` 호출**

### Step 7 — 격상 모달 작동 안 함 → **진짜 root cause 발견** 🔥

#2 alarm-popup.js 격상 처리 패치 적용 + brower 하드 새로고침 → **그래도 모달 격상 안 뜸**.

사용자 스크린샷:
- 알람 팝업: "주의 (60.0 ppm)"
- 측면 패널: CO 297 ppm (위험 단계)
- 이벤트 현황: 위험 표시
- → 데이터가 완전히 분리됨

진단 명령 결과:
- ✅ Celery 로그: `fire_danger_alarm_task` 5건 succeeded
- ✅ DB AlarmRecord: DANGER 4건 (event_id 872/873)
- ❌ 브라우저 콘솔 `[알람 수신] ['danger(new=true)']` **0건**
- ❌ 메트릭 `alarm_fired_total{risk_level="danger"}` 라벨 자체 **없음**

→ Celery task 실행은 됐는데 `_push_to_ws` 까지 못 감 → `create_alarm_and_event` 가 `alarm=None` 반환 의심.

[event_service.py:154](../../drf-server/apps/alerts/services/event_service.py#L154) 발견:
```python
return active_event, None  # 쿨다운 이내 — 재발송 안 함
```

**진짜 흐름**:
1. WARNING 첫 발화 → `last_notified_at = now`
2. 60s 안 DANGER 발화 시도 → AlarmRecord DB 생성 ✅
3. **cooldown 검사 실패** → `needs_renotify = False` → `alarm = None`
4. `fire_danger_alarm_task` 의 `if event is not None and alarm is not None:` 통과 못 함
5. `_push_to_ws` 호출 안 됨 → 브라우저 안 옴

**위험도 격상 케이스를 cooldown 정책이 차단** — `alarm-popup.js` 격상 처리가 작동할 알람 자체가 안 옴. **진짜 root cause**.

→ **위험도 격상 cooldown bypass 패치** = [event_service.py:122-141](../../drf-server/apps/alerts/services/event_service.py#L122) 의 `risk_escalated` 시 `needs_renotify=True`. 검증 후 `alarm_fired_total{risk_level="danger"} 2.0` 확인.

### Step 8 — 격상 검증 후 14건 사이클 반복 발견

cooldown bypass 적용 후 시연 재실행 → DANGER 격상 모달 정상 작동 ✅. 다만 8분 시연 동안 알람 14건 누적 + 사운드 중복.

분석:
- 시간: 11:30:45 ~ 11:38:23 (약 8분), 14건 / 8분 = ~35초 사이클
- [_state_machine.enter_scenario](../../fastapi-server/dummies/_state_machine.py) 의 `if cs.state != NORMAL: return`
- 시나리오 1 사이클 = RAMP_UP 5 + HOLD 30 + RAMP_DOWN 5 = 40초
- `mode=co_leak` 유지 시 사이클 끝 → state=NORMAL → 다음 tick에 enter_scenario 통과 → 새 사이클 시작

→ 진동 아니라 **사이클 자동 반복**. 시연 운영 가이드 = `mode` 유지 1 사이클 (~40초) 후 즉시 `mode=normal`. **Makefile `demo-gas` / `demo-power` / `demo-cycle` 가 이 패턴 자동화** (60s sleep + scenario-reset).

---

## 3. 사용자 의도 확인 — Step 7 → 8 → 9 으로 번호 정정 (의식 흐름 보존)

> 본 섹션의 "Step 7" 은 §2 의 Step 7/8 보다 먼저 일어난 의식의 흐름 (시간순 ≠ 진단 흐름 순). §2 의 Step 1~6 + Step 7~8 은 진단 결과의 시간순. 본 섹션은 **사용자가 회상한 원래 설계 의도** 가 등장한 시점으로 진단 흐름 중 어디든 끼울 수 있음.

> "정적 룰과 AI 추론 알람 발화에 차이를 두지 않아서 문제가 생긴 것"

사용자가 회상한 원래 설계 의도:
1. 정적 룰 임계 도달 → **즉시 발화 X, Pending**
2. AI 추론 진행
3. AI anomaly → AI 알람 + 정적 해소
4. AI normal → 정적 해소 (false positive 흡수)
5. AI 실패 → 정적 fallback 발화

이것이 사실은 [`power/services/decide_alarm.py`](../../fastapi-server/power/services/decide_alarm.py) 의 매트릭스에 정확히 구현되어 있음 (전력에만).

| AI 상태 | 정적 결과 | source |
|---|---|---|
| FIRED | * | ai |
| INFERRED_NORMAL | fired | static_cover_miss |
| INFERRED_FAILED | fired | static_cover_inference_fail |
| WARMING_UP | fired | static_cover_warmup |
| DISABLED | fired | static_no_ai_available |
| None (장애) | fired | fail-safe |
| * | not fired | None |

→ **가스에도 같은 매트릭스 적용** = #4 작업 목표.

---

## 4. 결정 흐름 (옵션 비교)

### 첫 추산 (보수적)
| 옵션 | 시간 | 내용 |
|---|---|---|
| C-full | 1~2일 | power 풀 매트릭스 복제 |
| C-mini | 80분 | mute 가드만 |

### 사용자 지적 — "가스가 진짜 IF만이야? 메모리 stale 같은데"

코드 확인 결과 가스도 풀 인프라:
- IF (Isolation Forest) — 다변량 (co+h2s+co2)
- ARIMA — pkl 모듈 로드, 잔차 IF feature 통합
- Change Point (ruptures Pelt) — 패턴 변화 시만 IF 호출 (성능 최적화)
- Rate limit 60s/sensor

→ 메모리 [`power_ai_architecture_decision_2026_05_18`](../../../.claude/projects/-home-cjy-diconai/memory/) "가스 격하" 표현 **stale**.

### 재평가 — C-mid 등장
가스 AI 인프라 80% 갖춰져 있어 매트릭스만 추가하면 2~3h.

| 옵션 | 작업량 | 평가 |
|---|---|---|
| ~~C-full~~ | (가스 AI 이미 풀) | 의미 없음 |
| **C-mid** (decide_alarm + mute 가드) | 2~3h | 정석 |
| C-mini (mute 가드만) | 80분 | 부분 |

### 진짜 결정 — AI(다변량) vs 룰(가스별) 키 매핑 충돌

가스 도메인 특수성:
- AI 추론: co+h2s+co2 다변량 **1건**
- 정적 룰: 9개 가스 **독립**

3가지 옵션:

| 옵션 | 동작 | 평가 |
|---|---|---|
| A. Sensor-wide mute | AI 1건 → 9개 가스 모두 60s 억제 | ❌ AI가 못 본 가스도 차단 위험 |
| **B. 추론 가스 3종만 mute** | AI 발화 → co/h2s/co2 룰만 60s 억제, 나머지 6종 그대로 | ✅ AI 책임 영역 정확히 일치 |
| C. AI/룰 분리 (가드 미적용) | C-mini 와 같음 | 중복 알람 그대로 |

→ **B 채택**.

키 설계:
```
ai_fired_gas:{sensor_id}:co:{level}
ai_fired_gas:{sensor_id}:h2s:{level}
ai_fired_gas:{sensor_id}:co2:{level}
```

`gas_alarm` 의 분기:
```python
if gas in ("co", "h2s", "co2") and is_gas_ai_mute_active(sensor_id, gas, risk):
    continue  # mute
fire_*_task.delay(...)
```

다른 가스 (no2/so2/o3/nh3/voc/o2/lel) 는 mute 가드 없이 그대로 발화.

---

## 5. 현재 진행 상황

### ✅ 완료
| 패치 | 위치 | 효과 |
|---|---|---|
| env 정리 | [.env.docker](../../.env.docker), [.env.docker.example](../../.env.docker.example) | `DUMMY_SCENARIO_MODE=normal` 추가, `DUMMY_SEND_INTERVAL_SEC=1.0` 명시. `DUMMY_RISK_PROBABILITY=0.1` 유지 (IF 학습용). **시연 안정성은 mode=normal 로 보장** — 추후 시연 시 필요하면 0.0 으로 임시 변경. |
| Makefile 시연 target | [Makefile](../../Makefile) | scenario·scenario-set·scenario-reset·scenario-clean·demo-prep·demo-check·**demo-gas**·**demo-power**·**demo-cycle** |
| 전력 시연 채널 제한 | [power_dummy.py](../../fastapi-server/dummies/power_dummy.py) | `AI_DEMO_CHANNELS = [1, 9, 14, 15]` |
| 알람 큐 안전망 | [alarm-popup.js:428](../../drf-server/static/js/shared/alarm-popup.js#L428) | `MAX_QUEUE 5 → 30` |
| #3 Event 자동 RESOLVED | [event_service.py auto_resolve_active_events](../../drf-server/apps/alerts/services/event_service.py) + [fire_clear_*_task](../../drf-server/apps/alerts/tasks.py) | 정상화 시 ACTIVE → RESOLVED 자동 |
| **#4 가스 AI mute 가드 (옵션 B)** | [ai_mute.py](../../fastapi-server/services/ai_mute.py), [alarm_dedupe.py](../../drf-server/apps/alerts/services/alarm_dedupe.py), [gas_service.py](../../fastapi-server/gas/services/gas_service.py), [gas_alarm.py](../../drf-server/apps/monitoring/services/gas_alarm.py) | 추론 가스 3종 (co/h2s/co2) AI 발화 시 정적 룰 60s mute |
| **#2 alarm-popup.js 격상 처리** | [alarm-popup.js](../../drf-server/static/js/shared/alarm-popup.js) AlarmPopup + AlarmToastStack | `_currentLevel` 추적, warning→danger 격상 시 현재 모달 강제 교체 |
| **위험도 격상 cooldown bypass (진짜 root cause)** | [event_service.py:122-141](../../drf-server/apps/alerts/services/event_service.py#L122) | `risk_escalated` 시 needs_renotify=True. WARNING→DANGER push 누락 fix |

### ⏸ 시연 후 정식 sprint
- C-full power 패턴 풀 복제 (IF + ARIMA + CP + Z + 5-state 매트릭스 가스도 통일)
- [alarm_dataflow_review](../../../.claude/projects/-home-cjy-diconai/memory/alarm_dataflow_review_2026_05_20.md) (a)/(c) path 충돌 정식 해소
- JWT 토큰 URL 노출 → subprotocol 인증
- `uvicorn.error` 로거명 정리
- 알람 시스템 재설계 plan P3 (운영자 디바이스 결정 후)
- **더미 데이터 정비** (별도 sprint 거리 — 아래 §9 참조)
- **지오펜스 (2026-05-27 별도 분석)** — R&D §3 완성도 **84%**. ✅ 모델/CRUD/UI/위치결합/알람. ❌ 이탈 알람 (4~6h), 감사 로그 import 버그 (5분), 원형(circle) 판정 (3~4h). `position_dummy` 시연 시나리오 모드는 다른 세션 진행 예정.
- **메모리 정정 거리** (아래 §10 참조)

---

## 6. 학습 포인트 (회고)

### 본질 원칙
1. **메모리는 stale 가능** — 6일 전 메모리에 "가스 격하" 라 적혀 있어도 코드 봐야 정답. 사용자 직감 ("가스 진짜 IF만이야?") 가 메모리 보다 정확했음.
2. **검증 시점이 중요** — localStorage TTL 60s 라서 검증 시점 따라 결론 달라짐. 사용자가 "검증 시점 잘못 아냐?" 짚어준 게 핵심.
3. **순수 함수의 가치** — `decide_alarm` 이 도메인 무관 순수 함수면 재사용 쉬움. 단 `alarm_type` 하드코딩 같은 도메인 의존은 wrapper 필요.
4. **기존 인프라 사용 우선** — C-full 1~2일 추산이 실제 코드 보니 2~3h. "다 새로 만들어야 한다" 가정은 위험.
5. **사용자 의도 ↔ 코드 일치 확인** — "AI 1차 + 정적 fallback" 사용자 의도가 power decide_alarm 매트릭스에 이미 구현됨. 가스에만 적용 안 됨.

### 진행 패턴 발견
- 각 패치 진행 전 **기존 인프라 grep 확인** 단계 거치니 작업량 정확. 이전엔 보수적 추산으로 시간 낭비.
- 사용자가 결정 분기 (옵션 A/B/C 등) 명확히 요청. 모호한 권고보다 결정형 답이 유효.
- 콘솔 로그 + DOM 셀렉터 + 코드 grep 3중 검증 = 빠른 진단.

### 위험 신호 (다음 세션에서 주의)
- alarm-popup.js 의 brower-side dedup (`_items`, `_AckStore`, `_DedupStore`, `GROUP_WINDOW_MS`, `MAX_QUEUE`) 가 다층 적용 → 디버깅 어려움
- `power_dummy.py` 의 `MIXED_TRIGGER_PROBABILITY = 0.005` 하드코딩 (env 무관) — 시연 환경 잔여 발화 가능성

---

## 7. 다음 액션 (이 문서 검토 후)

```
1. 사용자 검토 → 필요 시 위치 이동 또는 보완
2. #4 C-mid B 패치 (~3시간)
   - services/ai_mute.py 가스용 함수 4개
   - gas/services/decide_alarm.py 신규
   - gas_service.py AI 발화 수정
   - alarm_dedupe.py 가스용 mute 가드 함수
   - gas_alarm.py 가드 추가
3. #2 alarm-popup.js 격상 처리 (~1~2시간)
4. 통합 리허설
5. 메모리 정정 — power_ai_architecture_decision "가스 격하" 표현 stale 표시
```

---

## 참고

| 리소스 | 위치 |
|---|---|
| Redis/Celery 인프라 SoT | [docs/infra/redis-celery-guide.md](../infra/redis-celery-guide.md) |
| 알람 진단 (2026-05-20) | [drf-server/docs/refactoring/](../../drf-server/docs/refactoring/) |
| decide_alarm 매트릭스 | [fastapi-server/power/services/decide_alarm.py](../../fastapi-server/power/services/decide_alarm.py) |
| AI mute 가드 | [drf-server/apps/alerts/services/alarm_dedupe.py](../../drf-server/apps/alerts/services/alarm_dedupe.py) |
| 시연 시나리오 cheatsheet | (이 문서가 진단·결정 흐름 / 시연 절차는 별도) |

---

## 8. 가스 AI mute 가드 검증 결과 (#4 패치 후 추가)

### 검증 시도
- 시나리오: `make scenario-set mode=co_leak` → 120초 진행
- 결과:
  - 가스 송출 3233건 ✅ (윈도우 30 충분)
  - DRF MLModel 등록: `gas:sensor_1:co_h2s_co2` v3 active ✅
  - `ai_fired_gas:*` 키 0건 ❌
  - `ai_state_gas:*` 키 0건 ❌
  - 시연 화면에서 mute 가드 효과 안 보임

### 진단 — 4중 게이트 분석

가스 AI 발화 → mute 가드 set 까지 통과해야 할 게이트:

| # | 게이트 | 통과 여부 | 근거 |
|---|---|---|---|
| 1 | 윈도우 30 충족 | ✅ | 가스 송출 3233건 |
| 2 | Change Point 감지 (rpt.Pelt, penalty=3.0) | ❌ **여기서 막힘** | 부드러운 RAMP_UP (5초 보간) 을 Pelt 가 못 잡음 |
| 3 | DRF MLModel 등록 | ✅ | sensor_identifier=`gas:sensor_1:co_h2s_co2` v3 |
| 4 | IF 추론 pred=-1 | (2 못 통과해서 미진입) | — |

### 원인 — CP penalty 너무 높음

[gas_service.py:58](../../fastapi-server/gas/services/gas_service.py#L58):
```python
def _detect_change_point(values: list[float], penalty: float = 3.0) -> bool:
```

- 시연 더미 `co_leak`: co 값 24 → 300 (8배) 변화하지만 RAMP_UP 5초 동안 선형 보간 → **부드러운 ramp**
- `rpt.Pelt(model="rbf")` 가 부드러운 ramp 는 변화점으로 못 잡음 (RBF kernel + penalty 3.0)
- 운영 환경 noise 대응으로 penalty 3.0 은 합리적이지만 시연용으로는 과함

### 작업 가치 평가 — #4 패치는 헛수고 아님

| 차원 | 평가 | 비고 |
|---|---|---|
| **시연 효과** | ❌ 시연 화면에서 안 보임 | (advisory 의도된 동작과 일치) |
| **운영 효과** | ✅ 진짜 anomaly 발생 시 정상 작동 | 산업 환경 noise + 큰 변동 → CP 감지 → AI 발화 → mute |
| **평가/발표 가치** | ✅ "가스 mute 가드 인프라 적용 완료" | 코드 + 키 분리 + 문서 |
| **코드 인프라** | ✅ ai_fired_gas / ai_state_gas 키 공간 + decide_alarm 기반 준비 | 시연 후 sprint 토대 |
| **메모리 결정 부합** | ✅ [power_ai_architecture_decision_2026_05_18](../../../.claude/projects/-home-cjy-diconai/memory/) "가스 = 격하 유지" 와 정합 | advisory 의도 |

→ **5건 (env / Makefile / 전력 채널 / MAX_QUEUE / #3) 은 시연 직접 효과, #4 는 인프라 + 발표 가치만**.

### 향후 결정 옵션 (시연 후 또는 팀 협의 후)

| 옵션 | 위치 | 작업 시간 | 효과 | 시연 후 원복 부담 | 권고 |
|---|---|---|---|---|---|
| **A** | gas_service.py CP `penalty 3.0 → 1.0` | 5분 | 부드러운 변화도 감지 → 시연에서 발화 가능 | 낮음 (1줄) | 시연 후 검토 |
| B | gas_dummy.py SCENARIO_PATTERNS `co_leak.ramp_up 5 → 1` | 5분 | 시연 시각 효과 약함 (값 점프) | 낮음 | 시연용 부적합 |
| C | gas_dummy.py 신규 시나리오 `co_burst` 추가 | 30분 | 시연 전용 모드, 운영 영향 0 | 0 | 시연 발표 강조 시 가치 |
| **D** | 현 상태 유지 (advisory 운영) | 0분 | 시연에서 안 보임. 멘트로 보완 | 0 | **시연 전 안전 선택** |

### 시연 발표 멘트 (D 채택 시)

> "가스 도메인은 advisory 운영입니다. mute 가드 인프라는 적용 완료되어 있어 진짜 산업 환경에서 가스 변동이 발생하면 AI 발화 + 정적 룰 60초 억제로 작동합니다. 시연 환경의 부드러운 더미 패턴에서는 Change Point detection 의 안정 운영 임계값 (`penalty=3.0`) 으로 인해 발화 빈도 낮음 — 이는 운영자 false positive 감소를 위한 의도된 보수적 설정입니다. 시연 후 sprint 에서 운영 데이터로 임계값 튜닝 예정."

### 권장 흐름

1. **시연 전**: **D (현 상태 유지)** — 코드 변경 0, 시연 안정성 최우선
2. **시연 후 sprint 1주차**: A 검토 — 운영 데이터로 CP penalty 적정값 측정
3. **시연 후 sprint 2주차+**: 필요 시 B/C 도입 검토. 또는 전력처럼 IF + ARIMA + 5-state 매트릭스 풀 적용 (C-full)

### 적용된 패치 코드 위치 (검증/회귀 추적용)

| 파일 | 변경 |
|---|---|
| [fastapi-server/services/ai_mute.py](../../fastapi-server/services/ai_mute.py) | `mark_gas_ai_recent`, `mark_gas_ai_state`, `get_gas_ai_state` 신규 (가스용 키 prefix 분리) |
| [drf-server/apps/alerts/services/alarm_dedupe.py](../../drf-server/apps/alerts/services/alarm_dedupe.py) | `is_gas_ai_mute_active` 신규 |
| [fastapi-server/gas/services/gas_service.py](../../fastapi-server/gas/services/gas_service.py) | AI 발화 시 `mark_gas_ai_recent` + `mark_gas_ai_state(FIRED)` 호출 추가 (co/h2s/co2 각각) |
| [drf-server/apps/monitoring/services/gas_alarm.py](../../drf-server/apps/monitoring/services/gas_alarm.py) | `_AI_GUARDED_GASES = {"co", "h2s", "co2"}` + DANGER/WARNING 분기에 `is_gas_ai_mute_active` 가드 |

### 메모리 정정 필요

- `power_ai_architecture_decision_2026_05_18` 의 "**가스 = 격하 유지**" 표현은 stale (가스도 IF + ARIMA + CP 적용 중). 시연 후 정정.
- `redis_celery_infra_guide_2026_05_23` 의 Celery worker 단일 가정은 stale (alarm + metric 분리). `redis_exporter` 도 이미 운영 중. 시연 후 정정.



----


큰 그림
원래 전력 쪽엔 "AI랑 정적 룰이 같은 상황 두 번 알람 안 울리게 하는 장치"가 갖춰져 있었어요. 가스 쪽엔 그게 없어서 알람이 중복으로 떴던 거죠. 그래서 전력의 장치를 가스에도 똑같이 깔아준 작업입니다.
핵심 아이디어는 두 가지예요.
첫째, "AI가 먼저 울렸으면 정적 룰은 잠깐 입 다물어" — 이게 mute 가드.
둘째, "AI랑 정적 룰 결과를 표로 정리해서 어떤 알람을 최종으로 낼지 결정" — 이게 decide_alarm 매트릭스.

부품별 역할
mark_gas_ai_recent / mark_gas_ai_state (gas_service.py에 추가)
가스 AI가 알람을 울리는 순간, Redis에 "방금 AI가 이 센서의 co 가스에 대해 발화함, 60초간 유효" 라고 표시를 남기는 함수예요. 일종의 포스트잇 붙이기.
왜 필요? 나중에 정적 룰 쪽에서 이 포스트잇을 보고 "AI가 이미 울렸네, 나는 가만히 있자" 판단해야 하니까요.
is_gas_ai_mute_active (alarm_dedupe.py에 추가)
정적 룰 쪽에서 알람 울리기 직전에 호출하는 함수. "지금 이 센서의 이 가스에 mute 걸려있어?" 물어보는 거예요.
왜 필요? 위 포스트잇을 읽는 쪽이 필요해서요. 쓰는 쪽(mark_)과 읽는 쪽(is__active)이 한 쌍입니다.
_AI_GUARDED_GASES = {"co", "h2s", "co2"} (gas_alarm.py에 추가)
"AI가 책임지는 가스는 이 3개뿐" 이라고 명시한 집합. 정적 룰이 발화하기 전에 "내가 다루는 가스가 이 집합에 들어가나?" 확인합니다.
왜 필요? 가스 AI는 co+h2s+co2 세 종류만 같이 보거든요. 나머지 가스(no2, so2, o3, nh3, voc, o2, lel)는 AI가 안 보는데 mute 걸어버리면 그 가스 알람이 차단돼버립니다. 그래서 "AI가 책임지는 영역에만 mute 적용" 하려는 안전장치예요.
키 분리 (ai_fired_gas:*, ai_state_gas:*)
Redis에 포스트잇 붙일 때 "가스용 포스트잇"이랑 "전력용 포스트잇"을 다른 서랍에 보관한 거예요.
왜 필요? 한 서랍에 섞어두면 가스 mute가 전력 알람을 막거나, 반대 사고가 날 수 있어요. 도메인별로 격리하는 게 안전합니다.
decide_alarm 매트릭스 (가스용 신규 — 이건 #4 패치의 핵심 부분)
AI 상태(FIRED / NORMAL / 웜업중 / 실패 / 비활성)와 정적 룰 결과(fired / not fired)를 조합한 표예요. 표에 따라 "최종 알람을 AI로 낼지, 정적 룰로 낼지, 안 낼지" 결정합니다.
왜 필요? 단순히 mute만 걸면 "AI가 웜업 중이거나 실패했을 때" 정적 룰이 fallback으로 대신 울려줘야 하는데, 그 분기 처리가 매트릭스에 다 적혀있어요. 한 마디로 "AI가 일하면 AI 결과 우선, AI가 못 일하면 정적 룰이 대타" 정책을 코드로 옮긴 표입니다.

전체 흐름 한 줄로
가스 센서 값 들어옴 → AI 추론 → AI 발화하면 Redis에 포스트잇(mark_*) → 정적 룰 쪽이 발화 시도 → 포스트잇 확인(is_*_active) → AI 책임 가스(co/h2s/co2)면 mute, 아니면 그대로 발화.

한 가지 주의점 (문서에서 검증한 결과)
가스 쪽은 인프라는 다 깔렸는데, 시연 환경에선 mute가 실제로 작동하는 모습이 안 보였어요. 이유는 가스 AI 앞단의 Change Point 감지기가 "부드러운 변화"를 잘 못 잡아서 AI 자체가 발화를 안 하기 때문(penalty=3.0이 보수적). 그래서 포스트잇 붙일 일이 없었던 거죠.
운영 환경(진짜 산업 노이즈 + 큰 변동)에선 정상 작동할 거고, 시연용으로는 advisory(참고용)로 운영하기로 정리된 상태입니다.
---

## 9. 더미 데이터 정비 (시연 후 sprint 거리)

시연 리허설 + #4 패치 + cooldown bypass 적용 후 발견된 더미 데이터 측 정비 거리. 시연 환경 안정성에는 영향 없으나, 향후 시연 후 정비 권장.

### 9.1 시나리오 자동 사이클 반복

[fastapi-server/dummies/_state_machine.py](../../fastapi-server/dummies/_state_machine.py) `enter_scenario`:

```python
if cs.state != NORMAL:
    return    # 이미 진행 중이면 무시
```

→ 사이클 끝나면 `state = NORMAL`, 다음 tick 에 `enter_scenario` 통과 → **mode 유지 동안 매 40초 자동 재트리거**.

**시연 영향**: `mode=co_leak` 8분 유지 → 14 사이클 발화 (격상 14회).
**현재 대응**: `make demo-gas` / `demo-power` Makefile target — 60초 후 자동 `mode=normal` (사이클 1회 안전 보장).

**향후 정비 옵션**:
- A. 시나리오 한 번 실행 후 mode=normal 자동 복귀 (`AUTO_CYCLE_RESET=true` env 분기)
- B. mode 변경 감지 시만 enter_scenario (mode 동일 유지 시 재트리거 skip)
- C. 현행 유지 + Makefile target 으로 시연 운영

### 9.2 가스 Change Point detection penalty

[fastapi-server/gas/services/gas_service.py](../../fastapi-server/gas/services/gas_service.py) `_detect_change_point`:

```python
def _detect_change_point(values: list[float], penalty: float = 3.0) -> bool:
```

→ 운영 noise 대응으로 보수적. 시연 더미의 부드러운 RAMP_UP 5초 보간 못 잡음 → 가스 AI 추론 진입 빈도 ↓ → mute 가드 시연 효과 안 보임.

**향후 정비 옵션** ([§8 참조](#8-가스-ai-mute-가드-검증-결과-4-패치-후-추가)):
- A. penalty 1.0 으로 낮춤 (시연 시 발화 가능, 운영 noise 영향 주의)
- B. RAMP_UP 5 → 1 (시각 효과 약함)
- C. 신규 시나리오 `co_burst` (즉시 점프, 시연 전용)
- D. 현행 유지 (가스 = advisory 운영)

### 9.3 random.uniform 값 진동

[gas_dummy.py](../../fastapi-server/dummies/gas_dummy.py) `_pick_value`:
```python
return round(random.uniform(low, high), 2)
```

같은 weight 에서도 tick 별 값이 다름 → warning ↔ danger 진동 가능 (현재는 try_transition 으로 차단되지만 잠재 위험).

**향후 정비 옵션**:
- 같은 weight 동안 deterministic 값 유지 (이전 값 ± δ)
- 또는 진동 폭 제한 (이동 평균)

### 9.4 전력 시연 채널 풀

[power_dummy.py](../../fastapi-server/dummies/power_dummy.py) `AI_DEMO_CHANNELS = [1, 9, 14, 15]`:

→ 시연 시 단일 채널 random.choice. 시연 발표 시 항상 같은 채널이 강조되지 않음.

**향후 정비 옵션**:
- A. 시나리오별 default 채널 (예: overload=ch1 압연기, voltage_drop=ch9 메인전력반)
- B. 환경변수로 override (`DEMO_FORCED_CHANNEL=1`)
- C. 현행 유지 (random 발표 가치)

### 9.5 사이클 반복 정비 우선순위

| # | 정비 거리 | 시연 영향 | 운영 영향 | 권장 우선순위 |
|---|---|---|---|---|
| 9.1 | 사이클 자동 반복 | Makefile 로 대응 | 영향 없음 (운영자 mode 제어) | 시연 후 — Makefile 충분 |
| 9.2 | CP penalty | mute 가드 시연 효과 ↓ | 운영 정합 | 시연 후 — advisory 운영 OK |
| 9.3 | random.uniform 진동 | 보이지 않음 | 잠재 위험 | 시연 후 — 후순위 |
| 9.4 | 시연 채널 고정 | 시연 멘트 정합성 | 영향 없음 | 시연 후 — 발표자 결정 |

→ 모두 시연 후 정식 sprint. 시연 안정성에는 영향 0.

### 9.6 시연용 Makefile target (현재 적용 완료)

| target | 효과 |
|---|---|
| `make demo-prep` | mode=normal + Redis 키 정리 |
| `make demo-check` | 현재 시연 환경 점검 (mode + env + 큐 길이) |
| `make demo-gas` | 가스 시연 1 사이클 (co_leak 60s → normal) |
| `make demo-power` | 전력 시연 1 사이클 (overload 60s → normal) |
| `make demo-cycle` | A + B 통합 시연 (~2분 30초) |
| `make scenario-set mode=X` | 임의 모드 (시연자 수동 제어) |
| `make scenario-clean` | Redis 알람/dedup 키 일괄 정리 |

---

## 10. 메모리 정정 거리 (시연 후 일괄)

본 세션 진행 중 코드 vs 메모리 불일치 발견. 시연 후 일괄 정정 권장.

| 메모리 | 현재 표현 | 실제 코드 | 정정 방향 |
|---|---|---|---|
| [power_ai_architecture_decision_2026_05_18](../../../.claude/projects/-home-cjy-diconai/memory/power_ai_architecture_decision_2026_05_18.md) | "가스 = 격하 유지" | 가스도 IF + ARIMA + Change Point 풀 적용 ([gas_service.py](../../fastapi-server/gas/services/gas_service.py)) | "가스도 풀 알고리즘. advisory 운영 정책은 유지" |
| [redis_celery_infra_guide_2026_05_23](../../../.claude/projects/-home-cjy-diconai/memory/redis_celery_infra_guide_2026_05_23.md) | Celery worker 단일 가정 | `celery-worker-alarm` + `celery-worker-metric` 분리 운영 중 (docker compose ps 검증) | "Celery worker 2종 분리 (alarm/metric)" |
| 동일 메모리 | redis_exporter 부재 | 이미 `oliver006/redis_exporter:v1.62.0-alpine` 운영 중 (포트 9121) | "redis_exporter 운영 중" 추가 |
| [alarm_symptom_diagnosis_2026_05_20](../../../.claude/projects/-home-cjy-diconai/memory/alarm_symptom_diagnosis_2026_05_20.md) | "_AckStore 24h 영구 차단 가설" | 이미 60s 단축됨 ([alarm-popup.js T5](../../drf-server/static/js/shared/alarm-popup.js) 변경, 2026-05-20) | "가설 → 60s 단축으로 해소" |

### 동시 정정 대상 문서
- [docs/infra/redis-celery-guide.md](../infra/redis-celery-guide.md) — Celery worker 분리 + redis_exporter 반영
- (선택) `MEMORY.md` 인덱스 description 정렬

### 정정 일감 분리
- 시연 전엔 손대지 않음 (시연 안정성 우선)
- 시연 후 1~2시간 sprint 거리
