# 알람 스트림 전환 학습 — Step 1: 큐 계층 (LIST/BRPOP → Stream/XADD·XREAD)

> **대상 파일:** `fastapi-server/websocket/services/alarm_queue.py`
> **SoT:** [skill/plan/alarm-stream-migration.md](../plan/alarm-stream-migration.md)
> **커밋:** `feat(alarm): 알람 큐 LIST/BRPOP → Stream/XREAD 전환`
> **작성일:** 2026-06-01

이 문서는 두 부분이다. **A. 개념 학습** (왜 이렇게 했는가 — 시연/면접 설명용),
**B. 구현 변경** (무엇이 바뀌었는가 — 코드 안 보고도 이해되는 changelog).

---

## A. 개념 학습

### A-1. 문제: BRPOP은 "경쟁 소비자"다

전환 전 알람은 Redis **LIST + BRPOP**으로 흘렀다.

```
Celery 알람 태스크 → LPUSH(diconai:ws:alarms) → alarm_flush_loop이 BRPOP으로 pop → 브라우저
```

BRPOP의 핵심 성질: **알람 1건을 단 한 소비자만 꺼낸다(pop = 제거).** fastapi가 단일
프로세스(`replicas=1`)인 지금은 완벽하다. 그런데 수평 확장을 위해 **replica를 2개로
늘리는 순간 깨진다**:

```
        ┌─ replica A (BRPOP) ─ 알람을 꺼냄 → A에 붙은 브라우저만 받음
알람 1건 ┤
        └─ replica B (BRPOP) ─ 못 꺼냄 → B에 붙은 브라우저는 알람 누락
```

알람은 **모든 브라우저가 다 받아야 하는 방송(fan-out)** 인데, BRPOP은 한 명만 받는
**작업 분배(work queue)** 모델이라 구조가 안 맞는다.

### A-2. 해법: Redis Stream + replica별 독립 XREAD

Stream은 LIST와 달리 **읽어도 데이터가 지워지지 않는다.** 각 소비자는 "내가 어디까지
읽었나"를 가리키는 **커서(last_id)** 를 들고, 그 이후 데이터를 XREAD로 읽는다.

```
        ┌─ replica A (XREAD, 커서 A) ─ 전체를 읽음 → A의 브라우저 다 받음
알람 1건 ┤   (스트림에 그대로 남아 있음)
        └─ replica B (XREAD, 커서 B) ─ 전체를 읽음 → B의 브라우저 다 받음
```

커서가 소비자마다 독립이라 **모든 replica가 모든 알람을 받는 fan-out**이 된다.
`replicas=1`이면 그냥 단일 reader, `replicas≥2`가 되면 fan-out이 **자동으로** 켜진다.

### A-3. ⚠ 왜 Consumer Group이 아닌가 (설계결정 D1)

Redis에는 **Consumer Group**이라는 기능도 있다. "이름만 보면" 여러 소비자를 묶는
거라 fan-out에 맞을 것 같지만 **정반대다.** Consumer Group은 그룹 멤버끼리 **경쟁
분배**한다 — 한 알람을 그룹 안에서 **단 한 멤버만** 받는다. 즉 BRPOP과 똑같이 깨진다.

> **결론(D1):** 알람은 fan-out이 필요하므로 **그룹을 쓰지 않고**, 각 replica가
> 독립 `XREAD`로 자기 커서를 들고 스트림 전체를 읽는다.

| 방식 | 한 알람을 받는 소비자 | 알람에 적합? |
|---|---|---|
| LIST + BRPOP | 1명 (경쟁) | ❌ 멀티레플리카서 누락 |
| Stream + Consumer Group | 1명 (경쟁) | ❌ 그룹도 경쟁 분배 |
| **Stream + replica별 XREAD** | **전원 (fan-out)** | ✅ |

### A-4. 알아둘 Stream 기본기

- **entry ID 형식:** `"<밀리초timestamp>-<시퀀스>"` 예: `1718000000123-0`. 시간순 단조
  증가. → 두 ID의 ms 부분 차이로 **시간 지연(lag)** 을 XINFO 없이 직접 계산할 수 있다
  (Step 2에서 사용).
- **`XADD key MAXLEN ~ 10000 ...`:** 적재와 동시에 오래된 entry를 잘라낸다(트리밍 내장).
  `~`(approximate)는 "정확히 10000이 아니라 대략 그 근처에서 효율적으로 자른다"는 뜻 —
  성능을 위해 약간의 여유를 허용. → 전환 전 별도 `LTRIM` 호출이 **사라졌다.**
- **`XREAD BLOCK <ms> STREAMS key <last_id>`:** 커서 이후 새 entry가 생길 때까지
  최대 `<ms>` 대기. `last_id="$"`는 **"지금 이후 새 것만"** 이라는 특수 sentinel.
- **`decode_responses=True`** (이 프로젝트 redis 클라이언트 설정): entry의 field/value가
  bytes가 아니라 str로 온다 → `json.loads` 바로 가능.

---

## B. 구현 변경 (Before / After)

### B-1. `push_alarm` — LPUSH+LTRIM → XADD(MAXLEN ~)

dedup(SET NX EX)·fingerprint는 **한 줄도 안 바뀜**(load-bearing). 큐 적재 명령만 교체.

```python
# Before
await r.lpush(ALARM_QUEUE_KEY, json.dumps(payload, ensure_ascii=False))
REDIS_COMMAND_DURATION.labels("lpush").observe(...)
await r.ltrim(ALARM_QUEUE_KEY, 0, MAX_QUEUE_LEN - 1)   # 별도 트리밍 명령

# After
await r.xadd(
    ALARM_QUEUE_KEY,
    {"data": json.dumps(payload, ensure_ascii=False)},  # 단일 필드 "data"에 JSON
    maxlen=MAX_QUEUE_LEN,                                # 트리밍을 XADD에 포함
    approximate=True,                                   # MAXLEN ~ (효율적 근사 트림)
)
REDIS_COMMAND_DURATION.labels("xadd").observe(...)      # 라벨 lpush→xadd
```

- **payload 인코딩:** XADD는 field-value 쌍이 필요 → `{"data": <json 문자열>}` 단일
  필드로 저장. 읽을 때 `entry["data"]`를 `json.loads`로 복원.

### B-2. `pop_alarm_blocking`(BRPOP) → `read_alarms_blocking`(XREAD) — 시그니처 변경

가장 중요한 변경. **커서를 호출자가 보유**하도록 시그니처가 바뀌었다.

| | Before `pop_alarm_blocking` | After `read_alarms_blocking` |
|---|---|---|
| 인자 | `timeout` | **`last_id`**, `timeout` |
| 반환 | `dict \| None` (1건) | **`(new_last_id, [payload,...])`** (배치) |
| 명령 | BRPOP (pop=제거) | XREAD BLOCK (커서 이후 읽기, 제거 안 함) |

```python
async def read_alarms_blocking(last_id, timeout=0) -> tuple[str, list[dict]]:
    result = await r.xread({ALARM_QUEUE_KEY: last_id}, block=timeout * 1000)  # 초→ms
    if not result:                       # BLOCK timeout(빈 결과)
        return last_id, []               #   → 커서 유지(전진 금지)
    _, entries = result[0]               # 키 1개라 [0]
    new_last_id, payloads = last_id, []
    for entry_id, fields in entries:     # ⚠ 배치 전부 순회
        new_last_id = entry_id           #   커서는 배치 마지막 ID로
        payloads.append(json.loads(fields["data"]))
    return new_last_id, payloads
```

### B-3. 신규 헬퍼 3종

| 함수 | 역할 | 핵심 |
|---|---|---|
| `queue_len` (변경) | 적체량 메트릭 | `LLEN` → **`XLEN`** |
| `reset_stream_if_wrongtype` | 배포 시 잔존 LIST 정리 | `TYPE`이 **`list`일 때만 `DEL`**. `stream`/`none`은 보존(무조건 DEL 금지 — 매 재시작 wipe됨). lifespan 1회, 예외는 삼킴 |
| `stream_tail_id` | lag 계산용 말단 ID | `XREVRANGE key + - COUNT 1`. 비면 None |
| `_id_ms` | lag 계산용 ms 파싱 | `"<ms>-<seq>"` → int(ms) |

> `reset_stream_if_wrongtype`가 필요한 이유(D2): 키 `diconai:ws:alarms`를 그대로
> 재사용하는데 타입이 LIST→Stream으로 바뀐다. 배포 직후 옛 LIST가 남아 있으면 XADD가
> **WRONGTYPE 에러**. startup에서 옛 LIST만 1회 지워 충돌을 막는다. 알람은 휘발성이라
> 잔존분 폐기는 무해.

### B-4. 엣지케이스 (구현자가 틀리기 쉬운 곳)

1. **⚠ XREAD는 배치 반환** — BRPOP은 1건씩이지만 XREAD는 그동안 쌓인 N건을 리스트로
   준다. **전부 순회**하고 커서는 **마지막 entry ID**로. 단건 가정 시 알람 누락/순서 꼬임.
2. **`last_id="$"`** — XREAD에서만 쓰는 sentinel(XADD엔 못 씀). 첫 XREAD 후 실제 ID로 치환.
3. **BLOCK timeout(빈 결과)** — 커서 그대로 유지, 다음 iteration 계속 (전진 금지).
4. **dedup으로 skip 시** — 기존과 동일 early return (큐 적재 없음).

### B-5. 테스트 매핑

- **신규** [tests/test_alarm_stream.py](../../fastapi-server/tests/test_alarm_stream.py) 12종 —
  XADD MAXLEN 호출 shape / XREAD 배치 순서·커서 전진(엣지①) / 빈결과·예외 시 커서 동결 /
  깨진 entry skip 후 커서 전진 / XLEN / 타입가드 list-only DEL / tail·`_id_ms`.
- **정정** [tests/test_push_alarm_dedup.py](../../fastapi-server/tests/test_push_alarm_dedup.py) —
  기존 dedup 테스트가 `redis.lpush.await_count`로 **큐 명령**을 단언했어서 lpush→xadd 전환에
  10개가 깨졌다. dedup *동작*(첫 도착만 적재)은 그대로라, **명령 단언만** `lpush/ltrim`→`xadd`로
  따라가게 수정(`set.await_count`·counter·fingerprint 키 단언은 불변).
  → **교훈:** "동작 테스트"와 "구현 세부 단언"을 섞으면 내부 구현 교체 시 깨진다.

**검증:** Step 1 두 파일 31 passed / 전체 스위트 224 passed (컨테이너).

---

## 한 줄 요약

> BRPOP(경쟁 소비, 한 명만 받음)을 Stream+XREAD(커서별 독립 읽기, 전원 받음)로 바꿔
> 알람 계층을 fan-out 준비 완료 상태로 만들었다. 동작은 그대로(시연 영향 0), dedup·키 불변.
