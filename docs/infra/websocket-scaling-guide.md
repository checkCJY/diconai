# 실시간 알람·broadcast 확장성 가이드 (팀 공유용)

> **이 문서를 읽어야 하는 사람**: 알람/WebSocket 코드를 만지거나, "사용자 늘면 어떻게 되냐"
> "worker 올려도 되냐"를 판단해야 하는 모든 팀원.
> **전제**: 사전 지식 없이 읽을 수 있게 썼습니다. 모르는 단어는 맨 아래 [용어집](#용어집) 참고.
>
> 작성 배경: 2026-06-01 "Redis LIST가 사용자 1000명일 때 터지지 않나" 논의에서 정리.
> 결론부터 — **지금 구조는 맞습니다. 단, `workers`를 올리는 순간 깨집니다.** 이유를 아래에 설명합니다.

---

## 0. 30초 요약 (바쁘면 이것만)

1. 더미/IoT 장비가 **FastAPI 1곳**에 HTTP로 데이터를 보낸다. (엣지 게이트웨이 없음)
2. 알람은 **Redis LIST 큐**에 쌓였다가, `alarm_flush_loop`이 하나씩 꺼내 브라우저에 뿌린다.
3. **사용자가 1000명이 돼도 LIST는 안 터진다.** 알람 개수는 *센서 이벤트 수*로 정해지지 *사용자 수*로 정해지지 않기 때문.
4. 1000명에서 실제로 느려지는 건 LIST가 아니라 **broadcast fan-out**(연결된 브라우저에 순서대로 보내는 `for`문). 이건 몇 줄로 병렬화 가능.
5. **진짜 경계선**: FastAPI를 `--workers 2` 이상으로 올리면(= 프로세스 여러 개), 지금의 메모리 공유 상태 + 단일 LIST 구조가 **조용히 깨진다.** 그때는 **Redis pub/sub 전환 + 상태 외부화**가 세트로 필요하다.
6. **지금 당장 할 일은 없다.** workers는 1로 두고, "올려야 할 신호(CPU 포화)"가 `/metrics`에 보일 때 착수한다. 미리 만들지 않는다.

---

## 1. 현재 데이터 흐름 (그림 한 장)

```
[ IoT 가스/전력/위치 장비 ]   ← 지금은 dummies/*.py 가 장비 역할 대행
        │  HTTP POST  /api/sensors/gas 등 (1초 주기)
        ▼
┌─────────────────────────────────────────────┐
│  FastAPI 서버 (:8001)  — 프로세스 딱 1개      │
│                                               │
│  ① 수신: gas_router / power_router            │
│        → 검증 → 메모리(state.py)에 최신값 저장 │
│                                               │
│  ② broadcast_loop (5초마다)                    │
│        → 연결된 모든 브라우저에 센서 데이터 전송│
│                                               │
│  ③ alarm_flush_loop (즉시)                     │
│        → Redis LIST에서 알람 꺼내 브라우저 전송 │
└─────────────────────────────────────────────┘
        │ 저장 요청                    ▲ 알람 push
        ▼                              │
   [ DRF :8000 (DB) ]  ──Celery──▶ [ Redis LIST 큐 ]
```

핵심: **수신·저장·broadcast가 전부 한 프로세스 안**에서 일어나고, 서로 **프로세스 메모리**
([`fastapi-server/websocket/state.py`](../../fastapi-server/websocket/state.py))로 데이터를 주고받는다.
이게 "지금 잘 도는 이유"이자 "나중에 깨지는 이유"의 핵심이다. (5절에서 다시 설명)

---

## 2. 알람은 어떻게 흐르는가 (Redis LIST 큐)

관련 코드: [`fastapi-server/websocket/services/alarm_queue.py`](../../fastapi-server/websocket/services/alarm_queue.py)

```
위험 감지 (Celery)  ──LPUSH──▶  [ Redis LIST: diconai:ws:alarms ]  ──BRPOP──▶  alarm_flush_loop
   알람을 큐 왼쪽에 넣음              알람이 줄 서서 대기                  큐 오른쪽에서 하나씩 꺼냄
                                                                          → 모든 브라우저에 전송
```

- **LPUSH / BRPOP**: Redis 명령어. "왼쪽으로 넣고(L-push) 오른쪽에서 꺼낸다(BR-pop)" = 먼저 들어온
  알람이 먼저 나가는 **줄서기(FIFO)**.
- **왜 메모리 list가 아니라 Redis LIST인가?** (2026-05-12, 커밋 `57e8391`에서 전환)
  - 메모리 list는 서버 재시작 시 **휘발**(쌓인 알람 증발)
  - 동시에 넣고 빼면 **race**(경합)로 알람 손실
  - 옛 구현은 **5개 cap**(5개 넘으면 잘림) 제한이 있었음
  - → Redis LIST는 디스크 보존 + 원자적 명령(race 없음) + `LTRIM`으로 10,000개까지 안전하게 해결.
- **dedup**: Celery가 같은 알람을 재시도(retry)로 여러 번 보내도, fingerprint로 **첫 1건만** 통과시키고
  나머지는 버린다. (`_payload_fingerprint`)

> 이 LIST 전환은 **올바른 결정이었다.** 실제로 있던 문제 3개를 정확히 해결했고, 지금도 잘 돈다.

---

## 3. 가장 중요한 개념 — "연결 수"와 "프로세스 수"는 다르다

팀 전체가 헷갈린 핵심. **이 둘을 구분 못 하면 모든 판단이 틀어진다.**

### 축 A — 연결 수 (클라이언트 측)

```
브라우저/디바이스 1000대 ──┐
브라우저/디바이스 ...      ├──▶ [ FastAPI 프로세스 "1개" ]
브라우저/디바이스 1000대 ──┘        sensor_clients = [ws1, ws2, ... ws1000]
```

- 사용자 1000명이 1000대 디바이스로 **한 FastAPI에 접속** = 이 그림.
- 프로세스는 **여전히 1개**. 단지 `sensor_clients` 리스트가 1000칸으로 길어질 뿐.
- **이 상황에서 Redis LIST는 멀쩡하다.** (4절 참고)

### 축 B — 프로세스 수 (서버 측)

```
[ FastAPI 워커1 ]  sensor_clients = [...250]
[ FastAPI 워커2 ]  sensor_clients = [...250]   ← 이게 "다중 게이트웨이"
[ FastAPI 워커3 ]  sensor_clients = [...250]
[ FastAPI 워커4 ]  sensor_clients = [...250]
```

- FastAPI를 `--workers 4`로 띄우거나, FastAPI 컨테이너를 여러 대 두는 것 = **프로세스가 여러 개**.
- 이건 **연결이 많다고 자동으로 생기는 게 아니다.** "한 프로세스로 CPU가 안 버텨서" 사람이 결정해야 생긴다.
- **이 상황에서 비로소 Redis LIST가 깨진다.** (5절 참고)

> ⚠️ **흔한 착각**: "디바이스 1000대가 접속하니까 다중 게이트웨이 아닌가?"
> → **아니다.** 그건 축 A(연결 많음, 프로세스 1개)다. 다중 게이트웨이는 축 B(프로세스 여러 개)다.

---

## 4. "사용자 1000명이면 LIST 터지지 않나?" → 안 터진다

가장 많이 나온 걱정. 결론은 **No**. 이유:

**Redis LIST의 부하는 "사용자 수"가 아니라 "센서 이벤트 수"로 정해진다.**

- 알람을 **만드는 건 가스/전력 임계치 초과**(센서 이벤트)지, 브라우저가 아니다.
- 사용자가 10명이든 1000명이든 **큐에 들어오는 알람 개수는 똑같다.**
- 알람은 분당 몇 건 ~ 버스트 시 수십 건. Redis LPUSH/BRPOP은 **초당 수만 건**도 우습게 처리한다.
- `MAX_QUEUE_LEN = 10_000` + `LTRIM`으로 폭주 시 메모리도 보호된다.

→ **1000명이 LIST를 누르는 구조가 아니다.** LIST는 걱정 대상이 아니다.

### 그럼 1000명에서 진짜 느려지는 곳은?

[`ws_router.py`](../../fastapi-server/websocket/routers/ws_router.py)의 `_send_to_all`:

```python
for ws in list(sensor_clients):
    await ws.send_json(payload)   # ← 1000명이면 1000번을 "순서대로" 기다림
```

이건 **순차 O(N) 루프**(broadcast fan-out)다. 알람마다, 그리고 5초 broadcast마다 돈다.
1000명이면 한 번 뿌릴 때 send를 1000번 줄세워 기다린다.

**하지만 이것도 두 가지 짚어야 한다:**
1. 여기서 N = `sensor_clients` = **관제 대시보드 보는 운영자 수**다. 관제실에서 동시 1000명이
   같은 화면을 보지 않는다. 구조적으로 N은 작게 유지된다.
2. 정말 N이 크면, 해법은 **"LIST 버리기"가 아니라** fan-out 병렬화다:
   ```python
   await asyncio.gather(*[ws.send_json(payload) for ws in sensor_clients])
   ```
   몇 줄 수정. 이것도 구조 변경이 아니다.

---

## 5. 진짜 경계선 — `workers`를 올리면 LIST가 깨진다

여기가 이 문서에서 **제일 중요한 부분**이다.

현재 실행 설정: `uvicorn app:app --workers 1` (단일 프로세스).
([Dockerfile](../../fastapi-server/Dockerfile) · [docker-compose.yml](../../docker-compose.yml))

그런데 [compose 주석](../../docker-compose.yml)과 [entrypoint.sh](../../fastapi-server/entrypoint.sh)에는
*"운영 배포 시 workers=(2*CPU)+1 권장"*이라고 적혀 있다. **이 권장을 무심코 따르면 사고가 난다.**

### 왜 깨지나

uvicorn 워커는 각자 **독립된 파이썬 프로세스 = 독립된 메모리**다. workers를 늘리면:

1. `state.py`(가스 스냅샷·`sensor_clients` 등)가 **워커마다 따로** 생긴다. (메모리는 공유 안 됨)
2. 디바이스 1000대가 로드밸런서로 4워커에 분산 → 워커당 250대.
3. 알람 1건이 LIST에 들어오면, **`BRPOP`은 4워커 중 1명만** 집어간다.
   (LIST는 "한 원소 = 한 소비자". 이게 LIST의 본질)
4. 결과: 그 워커에 붙은 **250명만 알람 받고, 나머지 750명은 알람을 못 받는다.** ← 조용히 깨짐.

```
            알람 1건
              │
              ▼
        [ Redis LIST ]
              │ BRPOP — 단 1명만 가져감
              ▼
   ┌──── 워커1 (받음) ────┐    워커2 (못 받음)   워커3 (못 받음)   워커4 (못 받음)
   │ 내 250명에게만 전송  │     내 250명 → 누락    내 250명 → 누락    내 250명 → 누락
   └──────────────────────┘
```

### 해법 = Redis pub/sub (+ 상태 외부화)

- **pub/sub**: "한 메시지를 모든 구독자에게 복사 전달"하는 Redis 기능. (LIST의 1:1과 정반대인 1:N)
- 모든 워커가 알람 채널을 **구독** → 알람 1건이 4워커 **전부**에 도착 → 각 워커가 자기 250명에게 전송.
- 동시에 `state.py`의 공유 상태(가스/전력 스냅샷 등)도 메모리 → **Redis로 외부화**해야 워커 간 일관성 유지.

> 이게 예전에 논의된 **"B안 — 수신/게이트웨이 분리"**의 정당한 버전이다.
> **B안이 영원히 틀린 게 아니라, "지금" 틀린 것.** workers를 올려야 하는 실제 신호가 보이면 맞는 답이 된다.

---

## 6. 그래서 언제 무엇을 하나 (의사결정 표)

| 상황 | LIST 적절성 | 해야 할 일 |
|---|---|---|
| **지금** (workers=1, 운영자 소수, 시연·내부 관제) | ✅ 맞음 | **아무것도 안 함.** 유지 |
| 단일 프로세스인데 연결 N이 매우 큼 | ✅ 여전히 맞음 | fan-out을 `asyncio.gather`로 병렬화 (몇 줄) |
| **workers를 2 이상으로 올림** (다중 게이트웨이) | ❌ 깨짐 | **Redis pub/sub 전환 + state 외부화** (세트) |

### worker를 올려야 하는 유일한 신호

worker 1개 = **CPU 코어 1개**. WebSocket 연결은 대부분 **놀고 있는(idle)** I/O라, 단일 워커가
**수천 연결을 무리 없이** 들고 있다. **연결이 많다고 worker를 올리는 게 아니다.**

올려야 하는 유일한 트리거 = **한 코어 CPU가 포화**될 때. 후보는 둘:
- **(a) broadcast 쪽 포화** → 먼저 fan-out `gather` 병렬화로 해결 시도. 그래도 안 되면 pub/sub.
- **(b) 센서 수신 쪽 포화** → 수신 경로만 workers 늘리고 broadcast는 단일 유지 (= B안의 정당한 형태).

이건 **추측하지 말고 `/metrics`(Prometheus)로 확인**한다. CPU가 안 박히면 올릴 이유가 없다.

---

## 7. 지금 하지 말아야 할 것

- ❌ **선제적 pub/sub 전환 금지.** 안 올 부하 대비로 동작하는 구조를 갈아엎는 것.
- ❌ **무심코 `--workers` 올리기 금지.** 5절 사고가 난다. 올리려면 pub/sub 전환이 선행돼야 한다.
- ✅ 대신 **"경고 주석 + 트리거 기준"을 코드 옆에 남겨둔다.** 나중에 누가 와도 지뢰를 안 밟게.

---

## 용어집

| 용어 | 쉬운 설명 |
|---|---|
| **FastAPI** | 센서 수신·실시간 broadcast를 담당하는 파이썬 서버 (:8001). |
| **프로세스 / worker** | 서버 프로그램의 실행 단위. worker 1개 = CPU 1코어 = 메모리 1덩어리. 워커끼리 메모리 공유 안 됨. |
| **연결(connection)** | 브라우저/디바이스가 서버에 붙은 선 1개. `sensor_clients` 리스트가 이걸 들고 있음. |
| **WebSocket** | 서버↔브라우저가 실시간 양방향으로 데이터를 주고받는 연결. broadcast가 이걸로 나감. |
| **broadcast** | 연결된 모든 브라우저에 같은 데이터를 한 번에 뿌리는 것. |
| **fan-out** | 1개 데이터를 N개 대상에 퍼뜨리는 것. 지금은 `for`문으로 순서대로(O(N)) 보냄. |
| **Redis** | 메모리 기반 초고속 데이터 저장소. 큐·캐시·pub/sub에 씀. |
| **LIST (Redis)** | 줄서기 자료구조. **한 원소를 한 소비자만** 가져감 (1:1). 알람 큐가 이걸 씀. |
| **LPUSH / BRPOP** | LIST에 "왼쪽으로 넣기 / 오른쪽에서 (대기하며) 꺼내기" 명령. FIFO 줄서기. |
| **pub/sub (Redis)** | 발행/구독. **한 메시지를 모든 구독자에게 복사 전달** (1:N). 다중 워커 broadcast에 필요. |
| **race (경합)** | 동시에 같은 데이터를 건드려 결과가 깨지는 현상. |
| **dedup** | 중복 제거. 같은 알람이 여러 번 와도 1건만 통과시킴. |
| **O(N)** | 대상이 N개면 시간도 N배로 느는 처리. 여기선 broadcast가 연결 수에 비례해 느려짐. |
| **엣지 게이트웨이** | 여러 장비 데이터를 현장에서 모아 서버로 보내는 중간 노드. **현재 구조엔 없음** (장비가 FastAPI로 직송). |

---

## 관련 문서·코드

- 알람 큐 코드: [`fastapi-server/websocket/services/alarm_queue.py`](../../fastapi-server/websocket/services/alarm_queue.py)
- broadcast/연결 코드: [`fastapi-server/websocket/routers/ws_router.py`](../../fastapi-server/websocket/routers/ws_router.py)
- 공유 상태: [`fastapi-server/websocket/state.py`](../../fastapi-server/websocket/state.py)
- Redis/Celery 인프라: [redis-celery-guide.md](redis-celery-guide.md)
- 전체 아키텍처 1페이지: [docs/architecture.md](../architecture.md)
