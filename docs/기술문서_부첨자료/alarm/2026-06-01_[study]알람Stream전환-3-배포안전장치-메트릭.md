# 알람 스트림 전환 학습 — Step 3: 배포 안전장치 (lifespan 타입가드 + 메트릭/문서 정합)

> **대상 파일:** `fastapi-server/app.py` (lifespan), `core/metrics.py`,
> `internal/routers/alarm_router.py` (docstring)
> **SoT:** [skill/plan/alarm-stream-migration.md](../plan/alarm-stream-migration.md)
> **선행:** [Step 1 — 큐 계층](alarm-stream-step1-queue-xadd-xread-2026-06-01.md) ·
> [Step 2 — 소비 루프](alarm-stream-step2-flush-loop-cursor-2026-06-01.md)
> **작성일:** 2026-06-01

Step 1·2가 "코드 동작"이었다면 Step 3은 **"배포가 안전하게 굴러가게 하는 마감"** 이다.
한 줄 핵심: **기존 LIST 키를 Stream으로 재사용하기 때문에 배포 순간 타입 충돌이 날 수
있고, 그걸 startup에서 막는다.**

---

## A. 개념 학습

### A-1. WRONGTYPE — 같은 키, 다른 타입

Redis의 키는 **타입**을 가진다 (string / list / stream / ...). 어떤 명령을 그 타입에
안 맞는 키에 쓰면 `WRONGTYPE` 에러가 난다.

우리는 키 이름 `diconai:ws:alarms`를 **그대로 유지**한다(D2 — 네임스페이스 일관성).
그런데 타입이 **LIST → Stream**으로 바뀐다. 그래서 배포 직후 위험 구간이 생긴다:

```
[배포 전] diconai:ws:alarms = LIST (옛 알람 몇 건 남아 있을 수 있음)
[배포 후] 새 코드가 XADD 시도 → 키가 아직 LIST → ❌ WRONGTYPE 에러
```

### A-2. 해법: startup에서 잔존 LIST만 1회 정리 (멱등 정리 패턴)

`reset_stream_if_wrongtype()`(Step 1에서 만든 함수)를 lifespan startup에서 1회 호출한다.

```python
async def reset_stream_if_wrongtype():
    key_type = await r.type(KEY)
    if key_type == "list":      # 옛 LIST 일 때만
        await r.delete(KEY)     #   지운다 (다음 XADD 가 새 Stream 생성)
    # "stream"/"none" 이면 그대로 둔다
```

**왜 `list`일 때만 지우나? — 무조건 DEL 하면 안 되는 이유:**

```
무조건 DEL 했다면:
  재시작 → DEL → 그동안 쌓인 알람 전부 wipe → 재시작할 때마다 스트림이 날아감 ❌
```

- `list` → 옛 LIST. 알람은 휘발성이라 폐기 무해 → DEL.
- `stream` → 정상 운영 중인 우리 스트림 → **건드리면 안 됨** (재시작 시 알람 보존).
- `none` → 키 없음 → 할 일 없음.

→ **멱등(idempotent):** 몇 번을 호출해도 "옛 LIST가 있으면 한 번 치우고, 없으면 아무것도
안 한다." 그래서 재시작/배포를 반복해도 안전하다. (Step 3 실 redis 스모크에서 직접 검증)

### A-3. 메트릭 라벨은 왜 "free-form"인가

Prometheus 메트릭의 라벨 값은 **코드에서 `.labels("xadd")` 처럼 호출 시점에 정해진다.**
메트릭 *정의* 쪽 주석의 `"lpush" | "brpop"`은 "이런 값이 들어온다"는 **문서일 뿐**, 강제가
아니다. 그래서 큐 명령이 바뀌면 **정의 객체는 그대로 두고 주석/설명만** 실제 값과 맞춰주면
된다 (Gauge/Histogram 재생성 불필요).

### A-4. ⚠ xadd는 측정, xread는 일부러 안 함 (parity)

`REDIS_COMMAND_DURATION`은 `xadd`만 `.observe()`한다. `xread`는 **측정하지 않는다.**

이유: XREAD는 `BLOCK <ms>`로 **대기**한다. 측정하면 "Redis가 느린 시간"이 아니라 "알람이
안 와서 기다린 시간"이 섞여 의미가 없어진다 (옛 BRPOP을 측정 안 했던 것과 **완전히 동일한
이유**). 그래서 docstring의 라벨 정의에는 `xread`를 남겨두되 **observe 코드는 추가하지
않는다**(plan 지시). Redis 병목 진단은 `xadd` 측정값으로 충분하다.

---

## B. 구현 변경 (Before / After)

### B-1. `app.py` — lifespan에 타입가드 1회 호출

```python
# import 추가
from websocket.services.alarm_queue import reset_stream_if_wrongtype

# lifespan startup, alarm_flush_loop task 생성 직전
task1 = asyncio.create_task(broadcast_loop())
+ # LIST→Stream 전환: 잔존 LIST 키가 있으면 1회 정리 (WRONGTYPE 방지).
+ await reset_stream_if_wrongtype()
task2 = asyncio.create_task(alarm_flush_loop())   # XREAD 시작
```

순서가 중요하다: `alarm_flush_loop`(XREAD)·`push_alarm`(XADD)이 키를 건드리기 **전에**
정리되어야 한다.

### B-2. `core/metrics.py` — 라벨/설명 정합 (구조 변경 없음)

| 메트릭 | 변경 |
|---|---|
| `ALARM_QUEUE_LENGTH` | 주석 "Redis LIST … push/pop" → **"Redis Stream … 적체 길이(XLEN) … push/read"** (Gauge 그대로) |
| `REDIS_COMMAND_DURATION` | 설명 `(lpush/brpop …)` → `(xadd/xread …)`, 라벨 주석에 **"xadd 측정 / xread 미측정(parity)"** 명시. observe 코드 불변 |
| `ALARM_STREAM_LAG` | (Step 2에서 이미 추가됨) |

### B-3. `internal/routers/alarm_router.py` — docstring만 (코드 0 변경)

```diff
- # Redis 알람 큐(`diconai:ws:alarms`)에 LPUSH한다 (Phase 1 C4).
- # alarm_flush_loop이 BRPOP으로 즉시 소비해 브라우저로 전달.
+ # Redis 알람 스트림(`diconai:ws:alarms`)에 XADD한다 (Phase 1 C4 → Stream 전환).
+ # alarm_flush_loop이 XREAD로 즉시 소비해 브라우저로 전달.
```

엔드포인트는 여전히 `push_alarm`만 호출 — **로직은 그대로**, 표현만 정정.

---

## C. 검증 (이번 단계의 하이라이트)

mock이 아니라 **실제 redis 컨테이너**로 Step 1~3 함수를 통합 검증했다 (redis-py 5.2.1 API
시그니처를 실물로 확인 — mock으로는 못 잡는 부분).

| 검증 | 결과 |
|---|---|
| 잔존 LIST seed → `reset_stream_if_wrongtype` | LIST 삭제됨, 이후 XADD WRONGTYPE 없음 ✅ |
| `push_alarm` ×3 (1건 중복) | XLEN=2 (dedup이 중복 1건 차단) ✅ |
| `read_alarms_blocking("0")` | FIFO 순서 `[1, 2]`, 커서 = 마지막 ID ✅ |
| `stream_tail_id` / `_id_ms` / lag | 따라잡음 → lag 0.0 ✅ |
| `"$"` 커서 | 과거 entry 미수신 (신규만) ✅ |
| stream 상태에서 reset 재호출 | 스트림 보존 (wipe 안 함) ✅ |
| `import app` + `/metrics` | app 로드 OK, `fastapi_alarm_stream_lag_seconds` 등록 ✅ |
| 전체 단위 스위트 | 227 passed ✅ |

> **남은 검증(Step 4):** 실제 부팅 + 시연 시나리오 A/B/C 회귀, 브라우저 도달, RESOLVED,
> 가스 9-clear, [M-1] 보존, E2E latency·stream lag 메트릭 — compose/cluster E2E에서.

---

## D. Rollout / Rollback (plan)

- **Rollout:** fastapi 이미지 재빌드 + 재시작. **신규 인프라/compose/k8s/configmap 변경 0.**
  startup 타입가드가 잔존 LIST를 1회 정리.
- **Rollback:** 코드 revert 후 키 타입이 Stream으로 바뀌어 있으므로 `redis-cli DEL
  diconai:ws:alarms` 1회 (또는 revert 측에도 동일 타입가드). 알람 휘발성이라 데이터 손실 무의미.

---

## 한 줄 요약

> 같은 키를 LIST→Stream으로 재사용하는 데서 오는 WRONGTYPE 위험을 startup 멱등 타입가드로
> 막고, 메트릭·docstring을 실제 명령(XADD/XREAD)과 정합시켰다. 실 redis 통합 스모크로
> redis-py API까지 실물 검증 완료.
