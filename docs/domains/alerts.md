# 알람(alerts) 도메인

> 코드리뷰용 흐름 이해 문서. 관련 커밋: `a9d72a6`(tasks/event/dedupe), `9f5c64a`(모델·뷰·셀렉터)
> **가스·전력·지오펜스가 공유하는 알람 수렴점.** 각 센서 도메인이 위험 감지 후 여기로 모인다.
> 이 문서 하나로 "알람이 어떻게 생기고, 왜 안 중복되고, 어떻게 화면까지 가는가"를 코드 없이 따라갈 수 있게 하는 것이 목표.

---

## 1. 파일 맵

| 레이어 | 파일 | 핵심 심볼 |
|---|---|---|
| 진입(Celery) | `tasks.py` | `fire_danger_alarm_task` / `fire_warning_alarm_task` / `fire_clear_notification_task` / `fire_power_*` / `fire_geofence_alarm_task` / `_push_to_ws` / `_get_event_ack_names` |
| 서비스 | `services/event_service.py` | `create_alarm_and_event` ★, `acknowledge_event`, `auto_resolve_active_events`, `_notify_safe` |
| 서비스 | `services/alarm_dedupe.py` | `try_transition` ★, `get_state`, `clear_state`, `is_ai_mute_active`, `is_gas_ai_mute_active` |
| 서비스 | `services/policy_matcher.py` | `match_policy`, `invalidate_policy_cache` |
| 모델 | `models/alarm_record.py` | `AlarmRecord` (불변 판정) + `get_short_message()` |
| 모델 | `models/event.py` | `Event` (업무 워크플로우) + `is_mergeable_time_window`, `MERGE_WINDOW_HOURS=12` |
| 모델 | `models/event_log.py` | `EventLog` (감사 추적, append-only) |
| 모델 | `models/event_acknowledgement.py` | `EventAcknowledgement` (user-scoped ack) |
| 모델 | `models/alert_policy.py` | `AlertPolicy` (운영자 편집 정책) |
| 셀렉터 | `selectors/event_ack_selector.py` | `get_acked_user_ids`, `get_user_unread_event_count` |
| 셀렉터 | `selectors/event_history.py` | 이벤트 이력 필터 조회 |
| 뷰 | `views/event.py` | `EventViewSet` (`update_status`, `ack`) |
| 뷰 | `views/alarm_record.py` | `AlarmRecordViewSet` (`summary`, `catch_up`), `MyStatusView`, `WorkerSummaryView` |
| 시그널 | `signals.py` | AlertPolicy save/delete → `invalidate_policy_cache` |

## 2. 전체 시퀀스 (가스 DANGER 예시)

```
센서값 danger
  │
gas_alarm.trigger_gas_alarms(gas_data)
  │   ├─ try_transition("alarm:state:{sid}:{gas}", "danger", 60)  ── Redis Lua, True 면 1회만
  │   └─ fire_danger_alarm_task.delay(sensor_id, gas, value, facility_id, label)
  ▼
[Celery worker — alarm 큐]
tasks.fire_danger_alarm_task
  │   ① try: create_alarm_and_event(...)        ◀── DB 트랜잭션 (event_service)
  │   │       └─ 실패 시 self.retry (DB 재시도)
  │   ② if event and alarm:                       ◀── alarm=None 이면 쿨다운 이내 → push 안 함
  │   │     try: _push_to_ws({event_id, ...})     ◀── 별도 try (DB 와 분리)
  │   │       └─ POST http://fastapi:8001/internal/alarms/push/
  │   │       └─ 실패 시 retry 안 함 + WARN 로그 (DB 는 이미 커밋됨)
  ▼
[fastapi] internal/routers/alarm_router.py
  │   push_alarm(payload)  ── fingerprint dedup → Redis LPUSH(diconai:ws:alarms)
  ▼
[fastapi] alarm_flush_loop  ── BRPOP 즉시 소비 → _send_to_all(sensor_clients)
  ▼
브라우저
```

**왜 DB try 와 WS try 가 분리됐나** (tasks.py:159~214):
```python
try:
    event, alarm = create_alarm_and_event(...)   # ① DB
except Exception as exc:
    raise self.retry(exc=exc)                    # DB 실패만 retry

if event is not None and alarm is not None:      # alarm=None → 쿨다운 이내, push 스킵
    try:
        _push_to_ws({...})                       # ② WS
    except Exception as exc:
        logger.warning("WS 푸시 실패 (DB 저장은 완료): %s", exc)
        return                                   # ★ WS 실패는 retry 안 함
```
→ 합쳐 두면 WS 실패 시 retry 가 `create_alarm_and_event` 를 재실행해 **AlarmRecord 중복 생성**. 분리로 "DB 는 진실의 원천, WS 는 best-effort" 보장. 재발화 필요 시 다음 Celery tick 이 처리 (fingerprint dedup 이 30s 중복 차단하므로 안전).

## 3. create_alarm_and_event — 생성/병합 핵심

`event_service.py:40` · `@transaction.atomic`

```python
def create_alarm_and_event(
    facility_id, alarm_type,
    sensor_id=None, power_device_id=None, geofence_id=None, worker_id=None,
    gas_type="", measured_value=None, threshold_value=None,
    risk_level=RiskLevel.WARNING, source_label="", summary="",
    detected_at=None, channel=None, algorithm_source="", source="",
) -> tuple[Event | None, AlarmRecord | None]:
```

### 분기 결정표

| 상황 | 동작 | 반환 |
|---|---|---|
| 활성 Event 없음 | Event + AlarmRecord + EventLog(CREATED) 생성, `match_policy` 로 policy 채움, Notification on_commit | `(event, alarm)` |
| 활성 Event + 윈도우 내 + 쿨다운 초과/격상 | AlarmRecord 추가, last_notified_at 갱신, Notification 재발송 | `(event, alarm)` |
| 활성 Event + 윈도우 내 + 쿨다운 이내 | AlarmRecord 추가, Event 갱신만 | **`(event, None)`** ← push 스킵 신호 |
| 활성 Event + **윈도우 초과(12h)** | 기존 Event 강제 RESOLVED 분리 → 새 Event 경로 | `(event, alarm)` |

### 핵심 코드 — 병합/쿨다운/격상 (event_service.py:104~160)

```python
else:  # 윈도우 내 — 정상 병합
    alarm = AlarmRecord.objects.create(event=active_event, ...)
    active_event.last_detected_at = detected_at

    # 위험도 상승(WARNING→DANGER) → Event risk_level 갱신 + EventLog
    risk_escalated = RISK_LEVELS.index(risk_level) > RISK_LEVELS.index(active_event.risk_level)
    if risk_escalated:
        active_event.risk_level = risk_level
        EventLog.objects.create(action=STATUS_CHANGED, note=f"위험도 상승: {prev} → {risk_level}")

    # 쿨다운: 격상은 무시(즉시 알림), 그 외엔 60초 경과해야 재알림
    cooldown = timedelta(seconds=settings.ALARM_REPOPUP_COOLDOWN_SEC)
    needs_renotify = (
        risk_escalated
        or active_event.last_notified_at is None
        or (timezone.now() - active_event.last_notified_at) >= cooldown
    )
    if needs_renotify:
        active_event.last_notified_at = timezone.now()
        transaction.on_commit(lambda: _notify_safe(active_event))  # 커밋 후 알림
        return active_event, alarm    # 푸시함
    return active_event, None         # 쿨다운 이내 — 푸시 안 함
```

세 가지 리뷰 포인트:
- **`select_for_update`** (event_service.py:66): 동일 facility 동시 알람 생성 race 차단. 트랜잭션 안에서 활성 Event 락.
- **`transaction.on_commit`**: Notification 생성을 커밋 후로 미룸 — 롤백될 수 있는 Event 를 Notification 이 참조하는 상황 방지.
- **격상 cooldown 우회**: 위험이 올라가는 중(WARNING→DANGER)인데 쿨다운으로 막으면 위험. `risk_escalated` 가 cooldown 조건을 OR 로 우회.

## 4. 데이터 모델 — 판정과 업무의 분리

| 모델 | 역할 | 가변성 |
|---|---|---|
| **AlarmRecord** | 자동 판정의 **순간적 사실** (이 시각 이 센서 danger) | 불변 (기록) |
| **Event** | 업무 워크플로우 (N개 AlarmRecord 묶음) | 상태 전이 |
| **EventLog** | Event 상태 변화 이력 | append-only |
| **EventAcknowledgement** | (event, user) 쌍별 확인 | get_or_create |
| **AlertPolicy** | 운영자 편집 알람 정책 | CRUD |

**왜 나눴나**: AlarmRecord 는 "센서가 뭘 감지했나"(불변 사실), Event 는 "운영자가 어떻게 처리 중인가"(가변 워크플로우). v4 재설계에서 AlarmRecord 의 `is_active`/`status`/`resolved_*` 를 전부 제거하고 Event 로 이관 — 판정은 안 변하고 업무 상태만 변하므로.

### Event 상태 전이 (views/event.py:95 `update_status`)

```python
allowed = {
    ACTIVE:       [ACKNOWLEDGED, IN_PROGRESS, RESOLVED],
    ACKNOWLEDGED: [IN_PROGRESS, RESOLVED],
    IN_PROGRESS:  [RESOLVED],
}
```
```
ACTIVE ──┬─→ ACKNOWLEDGED ──┬─→ IN_PROGRESS ──→ RESOLVED
         ├──────────────────┴──────────────────→ ┘
         └─────────────────────────────────────→ ┘
```
- 허용 안 된 전환 → 400. 전환마다 EventLog 기록 + acknowledged_by/resolved_by 자동 세팅.
- **RESOLVED 전이 시** `_push_to_ws({event_resolved_at: ...})` broadcast (views/event.py:140) → 브라우저가 같은 event_id 팝업 close + "위험 해소" 토스트. WS 실패해도 트랜잭션은 성공(`raise_on_failure=False`).

## 5. user-scoped ack (다중 관리자 핵심)

**문제 (Before)**: `Event.status = ACKNOWLEDGED` 는 글로벌 단일 상태 → 운영자 A 가 확인하면 B 화면에서도 알람이 사라짐.

**해결 (After)**: `(event, user)` 쌍별 ack 행을 별도 저장. broadcast 시 user 단위 분기.

```python
# selectors/event_ack_selector.py
def get_acked_user_ids(event_id) -> set[int]:        # broadcast 분기: 이 user 가 ack 했나
def get_user_unread_event_count(user_id) -> int:     # 헤더 "🔔 N" 배지 (본인 미확인 활성 이벤트)

# views/event.py — ack 엔드포인트 (idempotent)
ack_obj, created = EventAcknowledgement.objects.get_or_create(event=event, user=request.user)
```
- `UniqueConstraint(event, user)` + `get_or_create` 이중 보호 → race 시에도 중복 행 없음.
- `event_ack_users` 페이로드로 토스트에 "(N 확인 중)" 시그널 — **ack 와 dedup 은 분리** (ack 는 표시용 시그널, 실제 재팝업 차단은 별도). 안전망.
- Event.status 와 **공존** — 글로벌 워크플로우 의미는 유지하면서 화면 표시만 user별.

## 6. dedup 3계층 (폭주·중복 방지)

| 계층 | 위치 | 메커니즘 | 막는 것 |
|---|---|---|---|
| ① 상태 천이 | `alarm_dedupe.try_transition` | Redis **Lua** GET+CMP+SET 원자 | 동시 다중 호출 중 1개만 fire |
| ② Event 쿨다운 | `event_service` `ALARM_REPOPUP_COOLDOWN_SEC`=60s | last_notified_at 비교 | 60초 내 재알림 (격상은 우회) |
| ③ push fingerprint | fastapi `alarm_queue` (30s TTL) | Redis SET NX EX | Celery retry 중복 push |

### ① Lua 원자 천이 (alarm_dedupe.py:25)
```lua
local cur = redis.call('GET', KEYS[1])
if cur == ARGV[1] then return 0 end          -- 같은 상태면 천이 안 함 (skip)
redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
return 1                                       -- 천이 성공 → 이 호출자만 fire
```
```python
def try_transition(state_key, new_state, ttl=3600) -> bool:
    # GET→CMP→SET 을 한 Lua 명령으로 — "조회 후 set" 사이 race 원천 제거.
    # 동시 N개 호출 중 정확히 1개만 True, 나머지 False.
```
→ 이게 없으면 `cache.get` → `cache.set` 사이에 다른 워커가 끼어들어 **같은 알람 N번 fire**. Lua 로 단일 원자 연산화.

### AI mute 가드 (dedup 의 변종)
```python
is_ai_mute_active(device_id, channel, rule_level)   # 전력: AI 발화 후 룰 60s 억제
is_gas_ai_mute_active(sensor_id, gas_type, level)   # 가스: co/h2s/co2 한정
```
AI 가 잡은 걸 룰이 중복으로 또 울리지 않게. AI 우선. 상세는 [power.md](power.md) §4 / [gas.md](gas.md) §3.

## 7. AlertPolicy 즉시 반영 (signals.py)

```python
# AlertPolicy save/delete → policy_matcher 캐시 invalidate
@receiver([post_save, post_delete], sender=AlertPolicy)
def _invalidate(...): invalidate_policy_cache(instance.event_type)
```
- 캐시 TTL 만료를 기다리지 않고 signals 로 즉시 무효화 → 어드민에서 정책 바꾸면 곧바로 적용 (시연 시나리오 C).
- `match_policy` 는 (facility, alarm_type, 발생원) 으로 우선순위 매칭 (facility specific > 전역).

## 8. 리뷰 시 주의 (안티패턴·함정)

1. **`(event, None)` 미체크**: `create_alarm_and_event` 가 None 반환(쿨다운 이내)인데 호출자가 push 하면 빈 알람. tasks 는 `if event and alarm:` 으로 가드 — 새 호출자 추가 시 필수.
2. **source vs algorithm_source 혼동**: `source`(검출주체 ai/static_*)와 `algorithm_source`(IF/ARIMA/combined)는 **직교 차원**, 같은 AlarmRecord 행에 공존. [power.md](power.md) §4.
3. **try_transition ttl 기본값 함정**: 시그니처 기본 `ttl=3600` 이지만 gas/power_alarm 은 `_CACHE_TTL=60` 으로 호출 — 쿨다운(60s)과 정렬. 기본값으로 호출하면 1시간 dedup → "한 번 뜨고 안 뜸" 버그.
4. **정상화 9종 폭주**: 가스 정상화는 9가스가 각각 task 발화 → fastapi 가 source_label 단위 dedup 으로 패널 1줄만 노출. drf 단에서 막는 게 아님.
5. **on_commit 누락 주의**: Notification 을 트랜잭션 안에서 바로 생성하면 롤백 시 유령 참조. 반드시 `transaction.on_commit`.

## 9. 알람 룰·문구 인벤토리 (운영자 화면 문구 SoT)

"어떤 룰로 발화하고, 화면에 어떤 글자가 박히는가"의 단일 진실 공급원.
모든 문구는 코드 verbatim (placeholder `{…}` 는 런타임 치환값).

> ⚠️ **모달 본문은 `message` 우선** — `_process()` 의 `const msg = data.message || data.summary`.
> 백엔드의 긴 `summary`("…즉시 대피하고 관리자에게 보고하세요")는 **Discord·알림·DB 용**이지
> **모달 본문이 아니다.** 모달엔 짧은 `message`(get_short_message) + `action`(행동 안내)이 뜬다.

### 9.1 팝업 anatomy — 어느 문구가 어디에

```
┌──────────────────────────────────────────────────────────┐
│ 발생 시간 2026-06-02 11:12:28 KST                    [ ✕ ] │①②
│                          ⚠                                 │
│                      긴급 알림                              │③ typeLabel
│   ┌────┐                                                   │
│   │위험│   메인 전력반                                      │④ badge | ⑤ sensor_name
│   └────┘                                                   │
│   메인 전력반 이상 수치·패턴 동시 탐지 (14,187.2 W)         │⑥ message
│   위험 기준 3700 초과 (측정 3860)            ← 룰 알람만    │⑦ threshold 줄
│   설비 정지 후 정밀 점검 (AI 이상 패턴)                     │⑧ action (굵게)
│   [ AI 미탐 의심 ]                           ← 전력 cover만 │⑨ cover 배지+사유
│   (홍길동 외 2명 확인 중)                    ← 다중 관리자  │⑩ ack 시그널
│   ┌───────────┐   ┌───────────┐                            │
│   │  상세 보기  │   │  확인 완료  │                          │⑪ 버튼
│   └───────────┘   └───────────┘                            │
└──────────────────────────────────────────────────────────┘
  테두리·펄스·비프음:  danger=빨강 880Hz×3 / warning=노랑 660Hz×2
  자동닫힘:           danger 15s / warning 30s   (normal 은 모달 아님 → 우하단 토스트 5s)
```

| # | 화면 칸 | 데이터 필드 | 코드 출처 |
|---|---|---|---|
| ① | 발생 시간(KST) | `timestamp` | `TimeFormat.abs()` |
| ③ | 헤더 라벨 | (레벨 고정) | `_POPUP_CFG[level].typeLabel` |
| ④ | 위험도 배지 | (레벨 고정) | `_POPUP_CFG[level].badgeText` |
| ⑤ | 센서·설비명 | `sensor_name`/`source_label` | `Event.source_label` |
| ⑥ | **본문** | `message` (>`summary`) | `AlarmRecord.get_short_message()` / fastapi push |
| ⑦ | 임계 줄 | `threshold_value`+`measured_value` | 룰 알람 push payload (둘 다 있을 때만) |
| ⑧ | **행동 안내** | (`alarm_type`×`level`) | `_ACTION_TEXT[type][level]` → 없으면 `_POPUP_CFG` |
| ⑨ | cover 배지·사유 | `alarm_source` | `ALARM_SOURCE_BADGE`/`REASON` |
| ⑩ | 확인 시그널 | `event_ack_users` | `_formatAckSignal` |

### 9.2 무엇이 팝업을 띄우나 (레벨별)

| 레벨 | 표시 | 헤더 | 배지 | 자동닫힘 | 비프 |
|---|---|---|---|---|---|
| **danger** | 중앙 모달(빨강) | `긴급 알림` | `위험` | 15s | 880Hz×3 |
| **warning** | 중앙 모달(노랑) | `주의 알림` | `주의` | 30s | 660Hz×2 |
| **normal** | ❌모달 X → 우하단 토스트 | — | — | 5s | 없음 |

---

### 9.3 LIVE 알람별 — 발화 룰 + 문구 (verbatim)

#### ① gas_threshold (가스 경보) — 룰
**룰:** 가스 농도 임계 초과 → `danger` 즉시 / `warning` 3초 지속 후. (60s dedup, AI mute co/h2s/co2)

| 칸 | danger | warning |
|---|---|---|
| 본문(message) | `{GAS} 임계치 초과 ({value} ppm)` | `{GAS} 임계치 초과 ({value} ppm)` |
| 임계 줄 | `위험 기준 {임계} 초과 (측정 {value})` | `주의 기준 {임계} 초과 (측정 {value})` |
| 행동(action) | `작업자 즉시 대피 / 외부 환기 가동 · 책임자 통보` | `작업 중단 + 환기 / 농도 추이 확인` |
| summary(알림용) | `[긴급] {가스명} 위험 수준 초과 ({value} {unit}) — 즉시 대피하고 관리자에게 보고하세요.` | `[주의] {가스명} 주의 수준 3초 지속 ({value} {unit}) — 작업을 중단하고 환기 후 관리자에게 보고하세요.` |

#### ② gas_anomaly_ai (가스 AI 이상) — AI(IF)
**룰:** CO·H2S·CO2 30틱 change-point 게이트 + IF `pred==-1` + 60s rate limit → `danger`.

| 칸 | danger |
|---|---|
| 본문·summary | `가스 이상 감지 (AI) \| CO:{co} H2S:{h2s} CO2:{co2}` ← fastapi 직접 push |
| 행동(action) | `해당 구역 작업자 대피 / AI 누출 의심 — 센서 위치 확인` |

> ⚠️ 본문 톤이 거침(디버그성). DRF `get_short_message` 엔 `{GAS} {IF|ARIMA} 이상 감지 ({value} ppm)` 깔끔본이 있으나 실제 팝업은 fastapi push 문구가 노출됨. → 다듬을 거리.

#### ③ power_overload (전력 이상) — 룰
**룰:** 채널 3축 max. **W·A: 정격 ≥80% warning / ≥100% danger. V: ±5% warning / ±10% danger.** danger 즉시 / warning 3초 후.

| 칸 | danger | warning |
|---|---|---|
| 본문(message) | `{채널라벨} 임계치 초과 ({value:,.1f} W)` | `{채널라벨} 임계치 초과 ({value:,.1f} W)` |
| 행동(action) | `해당 설비 즉시 정지 / 부하·발열 점검` | `설비 부하·온도 확인` |
| summary(알림용) | `[긴급] {라벨} 전력 과부하 ({value}W) — 즉시 확인하고 관리자에게 보고하세요.` | `[주의] {라벨} 전력 경고 수준 3초 지속 ({value}W) — 설비 상태를 확인하세요.` |

#### ④ power_anomaly_ai (전력 AI 이상) — AI(5축)
**룰:** combined_risk `caution/predict_warn/warning`→**warning**, `danger`→**danger**. 60s rate limit. 채널 (1,9,14,15).

| 칸 | danger | warning |
|---|---|---|
| 본문·summary | `{채널라벨} {phrase} ({value:,.1f} W)` | `{채널라벨} {phrase} ({value:,.1f} W)` |
| 행동(action) | `설비 정지 후 정밀 점검 (AI 이상 패턴)` | `부하·발열 추이 확인 / 이상 지속 시 정지` |

`{phrase}` = 알고리즘별 → **9.5 표** 참조 (예: combined = `이상 수치·패턴 동시 탐지`).

#### ⑤ 정상화 (gas_clear / power_clear) — normal (모달 아님, 우하단 토스트)

| | 본문(message) | summary(알림용) |
|---|---|---|
| gas_clear | `{GAS} 정상 복귀` / `정상 복귀` | `[안전] {source_label} — {가스들} 농도가 정상 범위로 복귀했습니다. 관리자 확인 후 작업을 재개하세요.` |
| power_clear | `{채널라벨} 정상 복귀` | `[안전] {source_label} — 전력이 정상 범위로 복귀했습니다. 관리자 확인 후 작업을 재개하세요.` |

---

### 9.4 전력 정적 cover (AI 공백을 룰이 보완) — source별 문구·배지·톤

AI가 못 잡을 때 룰이 대신 발화. 모달 톤이 노랑으로 진정되고 배지가 붙는다.

| source | 언제 (decide_alarm) | summary 꼬리말 | 배지(⑨) | 톤 |
|---|---|---|---|---|
| `ai` | AI FIRED | — | (없음) | **risk** (빨강/노랑) |
| `static_cover_miss` | AI=정상인데 룰 발화 | `… — AI 미탐 의심 — 정적 임계치 초과` | `AI 미탐 의심` | **cover** (노랑) |
| `static_cover_inference_fail` | AI 추론 실패 | `… — AI 추론 실패 보완` | `AI 추론 실패 보완` | **cover** |
| `static_cover_warmup` | AI 워밍업 중 | `… (AI 윈도우 빌드 중 — 정적룰 보완)` | `AI 준비 중 보완` | **cover** |
| `static_no_ai_available` | AI 비활성 채널 | — | (없음) | **risk** |
| `static_legacy` | T4 이전 데이터 | — | (없음) | **risk** (신규 미발화) |

### 9.5 AI 알고리즘 → 본문 phrase (`ALGORITHM_SOURCE_PHRASE`)

| algorithm_source | 본문 phrase | 배지 라벨(`_LABEL`) |
|---|---|---|
| `isolation_forest` | `이상 수치 탐지` | IF |
| `arima` | `이상 패턴 탐지` | ARIMA |
| `combined` | `이상 수치·패턴 동시 탐지` | IF+ARIMA |
| `zscore` | `통계 이상 수치` | Z-score |
| `change_point` | `패턴 변화 탐지` | 급변 |
| `night_abnormal` | `야간 이상 가동` | 야간 가동 |

### 9.6 임계치 표 (현재값)

**가스** (출처: `monitoring/utils/gas_thresholds.py`) — `danger` 발화 기준 / `warning` 구간:

| 가스 | warning 구간 | **danger** |
|---|---|---|
| CO | 25 ~ 200 ppm | ≥ 200 ppm |
| H2S | 10 ~ 15 ppm | ≥ 15 ppm |
| CO2 | 1000 ~ 5000 ppm | ≥ 5000 ppm |
| O2 | 16.0 ~ 18.0 % | **< 16.0 %** (저산소) |
| NO2 | 3 ~ 5 ppm | ≥ 5 ppm |
| SO2 | 2 ~ 5 ppm | ≥ 5 ppm |
| O3 | 0.06 ~ 0.12 ppm | ≥ 0.12 ppm |
| NH3 | 25 ~ 35 ppm | ≥ 35 ppm |
| VOC | 0.5 ~ 1.0 ppm | ≥ 1.0 ppm |

**전력** (출처: `power/services/threshold_eval.py`) — 채널 정격(`channel_meta`) 대비 %:

| 축 | warning | danger |
|---|---|---|
| W (전력) | ≥ 80 % | ≥ 100 % |
| A (전류) | ≥ 80 % | ≥ 100 % |
| V (전압, 양방향) | ±5% 이탈 (95~105%) | ±10% 이탈 (90~110%) |

→ 채널 종합 위험도 = `max(W, A, V)`.

### 9.7 action 미정의 fallback + 미발화(dormant) 타입

- `_ACTION_TEXT` 에 없는 type → `_POPUP_CFG` 기본값: danger `즉시 대피하세요!` / warning `주의하세요!`
- **정의돼 있으나 현재 발화 경로 없음(팝업 안 뜸):** `geofence_intrusion`(task만 있고 호출부 없음), `sensor_fault`, `ppe_violation`, `vr_training_not_done`, `safety_check_pending`, `inspection_scheduled`, `batch_failed`, `storage_overdue`.
  - 이 중 일부는 `_ACTION_TEXT` 에 행동 안내가 미리 등록돼 있으나(향후 확장용 자리), 백엔드 push 가 없어 실제로는 미노출.

---

## 10. 관련 문서
- 센서 진입: [gas.md](gas.md) / [power.md](power.md) / [positioning.md](positioning.md)
- WS 전달: [websocket.md](websocket.md)
- AI mute 상세: [ai-ml.md](ai-ml.md)
