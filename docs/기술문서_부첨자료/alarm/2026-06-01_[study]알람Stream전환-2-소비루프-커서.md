# 알람 스트림 전환 학습 — Step 2: 소비 루프 (BRPOP 단건 → XREAD 배치·커서·lag)

> **대상 파일:** `fastapi-server/websocket/routers/ws_router.py` (`alarm_flush_loop`)
> **곁들임:** `fastapi-server/core/metrics.py` (`ALARM_STREAM_LAG` 신규)
> **SoT:** [skill/plan/alarm-stream-migration.md](../plan/alarm-stream-migration.md)
> **선행:** [Step 1 — 큐 계층](alarm-stream-step1-queue-xadd-xread-2026-06-01.md)
> **작성일:** 2026-06-01

Step 1이 "스트림에 어떻게 쌓고 어떻게 읽는 함수를 만드나"였다면, Step 2는 "그 함수를
**소비 루프가 어떻게 굴리나**"다. 커서를 들고 있는 주체가 바로 이 루프다.

---

## A. 개념 학습

### A-1. 커서는 "누가" 들고 있나 (설계결정 D3·D4)

Step 1의 `read_alarms_blocking(last_id, ...)`는 커서를 **인자로 받기만** 한다. 실제로
커서 값을 **기억하고 다음 호출에 넘기는 주체**가 `alarm_flush_loop`이다.

```python
last_id = "$"                 # 루프 시작 시 1회 — "부팅 이후 신규만"
while True:
    new_last_id, payloads = await read_alarms_blocking(last_id, timeout=1)
    ...
    last_id = new_last_id     # 다음 iteration에 넘길 커서 갱신 (메모리에 보관)
```

- **커서 위치 = 메모리 (D4):** Redis나 DB에 저장하지 않는다. 재시작하면 다시 `"$"`부터 =
  실시간 알람만. **과거 알람을 무한 replay할 이유가 없으니** 메모리로 충분하다.
- **시작점 = `"$"` (D3):** 부팅 직후 쌓여 있던 과거 알람을 쏟아내지 않고, **부팅 이후
  새로 들어온 것만** 받는다.
- **replica별 독립:** 각 replica의 루프가 자기 메모리에 자기 커서를 들고 있다 →
  Step 1에서 말한 fan-out이 여기서 실제로 성립.

### A-2. [M-1] "클라이언트 없으면 보존" — 커서 동결로 재현

전환 전 BRPOP 시절의 함정: **브라우저가 0명일 때 BRPOP으로 pop하면 알람이 영구 소실**된다
(pop = 제거인데 받을 사람이 없음). 그래서 옛 코드는 "pop 전에 클라이언트 수를 먼저 확인"
했다(이게 [M-1] 수정).

Stream에서는 이 보존이 **훨씬 자연스럽게** 된다. 스트림은 읽어도 안 지워지므로:

```python
if not sensor_clients:
    await asyncio.sleep(1)
    continue                  # ⚠ XREAD 자체를 호출 안 함 → 커서 동결
```

클라이언트가 없으면 **읽지 않고 커서를 그 자리에 멈춰둔다.** 그동안 알람은 스트림에
계속 쌓이고, 브라우저가 재접속하면 **커서 이후 누적분이 다음 XREAD에서 배치로 한 번에**
전달된다. "pop하면 소실" 문제가 구조적으로 사라진다.

### A-3. 왜 stream lag 메트릭을 지금 넣나 (설계결정 D6)

fan-out 멀티레플리카가 되면 새 질문이 생긴다: **"어느 replica가 뒤처지나?"** 어떤 replica의
소비 루프가 느리면 그 replica에 붙은 브라우저만 알람이 늦는다 — 눈에 안 보이는 장애.

이를 위해 **스트림 말단 ID와 내 커서의 시간차(초)** 를 메트릭으로 노출한다. Step 1에서
본 entry ID의 ms 부분 차이로 계산하니 **XINFO 같은 추가 호출이 필요 없다.**

```
lag = (말단 entry의 ms − 내 커서의 ms) / 1000
```

- 평상시 내가 다 따라잡았으면 말단 ≈ 커서 → **lag ≈ 0.**
- 내 루프가 소화를 못 하면 말단이 앞서가 → **lag 증가.**
- Prometheus가 **pod별로 스크랩**하므로 멀티레플리카 시 replica별 lag이 자동 분리되어
  "뒤처지는 replica"가 그래프에서 바로 보인다.

> **지금 넣는 이유(D6):** 멀티레플리카를 켜는 시점에 부랴부랴 추가하지 않도록 골격에
> 선반영(<0.5d). 메트릭 *정의*(`ALARM_STREAM_LAG`)는 metrics.py에 미리 넣었다.

---

## B. 구현 변경 (Before / After)

### B-1. `alarm_flush_loop` — 단건 루프 → 배치·커서 루프

```python
# ── Before (BRPOP 단건) ──
while True:
    if not sensor_clients:
        await asyncio.sleep(1); continue
    payload = await pop_alarm_blocking(timeout=1)   # 1건 또는 None
    if payload is None: continue
    ingress_ts = payload.pop("ingress_ts", None)
    if ingress_ts is not None: E2E_ALARM_LATENCY.labels(...).observe(...)
    base = build_broadcast_payload(include_alarms=False)
    base["alarms"] = [payload]
    await _send_to_all(base)

# ── After (XREAD 배치 + 커서 + lag) ──
last_id = "$"                                       # 부팅 커서
while True:
    if not sensor_clients:
        await asyncio.sleep(1); continue            # 커서 동결 = [M-1] 보존
    new_last_id, payloads = await read_alarms_blocking(last_id, timeout=1)
    for payload in payloads:                         # ⚠ 배치 전부 순회
        ingress_ts = payload.pop("ingress_ts", None)
        if ingress_ts is not None: E2E_ALARM_LATENCY.labels(...).observe(...)
        base = build_broadcast_payload(include_alarms=False)
        base["alarms"] = [payload]
        await _send_to_all(base)
    last_id = new_last_id                            # 커서 전진(빈 결과면 그대로)
    tail = await stream_tail_id()                    # lag 계산
    if tail is not None and last_id != "$":
        ALARM_STREAM_LAG.set((_id_ms(tail) - _id_ms(last_id)) / 1000)
    else:
        ALARM_STREAM_LAG.set(0)
```

**불변(중요):** E2E latency observe, FIFO 순서, `_send_to_all`, payload shape
(`{"alarms":[payload], ...}`)는 그대로 → **프론트 무수정, 시연 영향 0.**

### B-2. 무엇이 바뀌었나 — 한눈에

| 항목 | Before | After |
|---|---|---|
| 소비 명령 | `pop_alarm_blocking` (BRPOP 1건) | `read_alarms_blocking` (XREAD 배치) |
| 커서 | 없음 (pop=제거) | `last_id` 메모리 보유, `"$"` 시작 |
| 반환 처리 | 단건 if/continue | **배치 for 순회** |
| [M-1] 보존 | "pop 전 클라 확인" | "클라 없으면 안 읽음 = 커서 동결" |
| 신규 | — | iteration 말미 **stream lag set** |
| import | `pop_alarm_blocking` | `read_alarms_blocking, stream_tail_id, _id_ms`, `ALARM_STREAM_LAG` |

### B-3. lag 계산의 0 처리 (엣지케이스)

`ALARM_STREAM_LAG.set(0)`이 되는 두 경우:
- **`tail is None`** — 스트림이 아직 비었다 (말단 없음).
- **`last_id == "$"`** — 아직 한 건도 처리 안 함 → `_id_ms("$")`는 파싱 불가.

둘 다 "지연이라 부를 게 없는 상태"라 0으로 둔다.

### B-4. `metrics.py` — `ALARM_STREAM_LAG` 신규 (선반영)

```python
ALARM_STREAM_LAG = Gauge(
    "fastapi_alarm_stream_lag_seconds",
    "Time gap (s) between stream tail and this process cursor in the WS alarm stream",
    multiprocess_mode="liveall",
)
```

`ALARM_QUEUE_LENGTH`와 같은 패턴(Gauge + liveall). `alarm_flush_loop`이 set하는 대상이라
Step 2에 함께 넣었다(라벨 rename·docstring parity 등 나머지 metrics 정비는 Step 3).

### B-5. 테스트 매핑

**신규** [tests/test_alarm_flush_loop.py](../../fastapi-server/tests/test_alarm_flush_loop.py) 3종.
무한 `while True`라 mock의 side effect로 sentinel 예외를 던져 원하는 iteration 직후 탈출.

| 테스트 | 검증 |
|---|---|
| `..._broadcasts_batch_and_advances_cursor` | 배치 2건 각각 broadcast(엣지①) + 커서 전진 + lag set |
| `..._freezes_cursor_when_no_clients` | [M-1] 클라 없으면 **XREAD 미호출** + sleep, 커서 동결 |
| `..._pops_ingress_ts_and_observes_latency` | ingress_ts를 broadcast 전 pop + risk_level 라벨로 latency observe |

**검증:** Step 2 테스트 3 passed / 전체 스위트 227 passed (컨테이너).

---

## 한 줄 요약

> 소비 루프를 "BRPOP 단건 + pop=소실 방어"에서 "메모리 커서 + XREAD 배치 + 클라 없으면
> 커서 동결(보존)"으로 바꾸고, 뒤처지는 replica를 잡을 stream lag 메트릭을 골격에 선반영했다.
> 프론트·시연 영향 0.
