# 02. WebSocket 인프라 (WSClient · 연결 캐시 · 자동 재연결)

## 1. 관련 파일 및 의존성

### 1.1 파일 목록
- [drf-server/static/js/shared/ws-client.js](../../../drf-server/static/js/shared/ws-client.js) — 135줄, **`WSClient` IIFE** (_resolveUrl, _create + instance 메서드)
- [drf-server/static/js/shared/config.js](../../../drf-server/static/js/shared/config.js) — 22줄, **`AppConfig.wsUrl` 헬퍼** (06에서 다룸 — 여기서는 wsUrl만 인용)

### 1.2 호출자 인벤토리 (grep 결과 8개 호출 지점)
- [shared/alarm-ws.js:10](../../../drf-server/static/js/shared/alarm-ws.js#L10) — `WSClient.connect('/ws/sensors/')` — 비대시보드 알람 수신
- [shared/worker-ws.js:11](../../../drf-server/static/js/shared/worker-ws.js#L11) — `WSClient.connect('/ws/worker/' + user.id + '/')` — 작업자 개인 알림
- [dashboard/websocket.js:270](../../../drf-server/static/js/dashboard/websocket.js#L270) — `WSClient.connect('/ws/sensors/')` — 대시보드 메인 스트림
- [dashboard/websocket.js:449](../../../drf-server/static/js/dashboard/websocket.js#L449) — `WSClient.connect('/ws/positions/')` — 대시보드 위치 스트림 (별도 채널)
- [detail/websocket_gas.js:43](../../../drf-server/static/js/detail/websocket_gas.js#L43) — `WSClient.connect('/ws/sensors/')` — 가스 디테일 페이지
- [detail/websocket_power.js:121](../../../drf-server/static/js/detail/websocket_power.js#L121) — `WSClient.connect('/ws/sensors/')` — 전력 디테일 페이지
- [detail/monitoring_workers.js:332](../../../drf-server/static/js/detail/monitoring_workers.js#L332) — `WSClient.connect('/ws/sensors/')` — 작업자 모니터링

> **중요한 정합성**: 같은 페이지에서 `/ws/sensors/`를 여러 모듈이 호출 — WSClient 캐시가 단일 연결로 통합 (성능·중복 메시지 방지). 단 **모든 호출자가 같은 onMessage 콜백을 받음** — 각자 자기 책임 영역만 처리하도록 책임 분리 필수.

### 1.3 의존성 그래프
```
WSClient.connect(path, opts)
    │
    ├─ _resolveUrl(path, opts)
    │   ├─ window.AppConfig.wsUrl(path) 사용 (config.js)
    │   └─ opts.attachToken 시 Auth.getAccessToken() (auth.js)
    │
    └─ _create(path, opts)
        ├─ _cache.get(url) — 캐시 hit 시 기존 instance 반환
        ├─ messageHandlers / openHandlers / closeHandlers / errorHandlers (Set)
        ├─ _open() — new WebSocket(url) + on{open,message,error,close} 핸들러
        └─ _addHandler(set, fn) — 핸들러 등록 + unsubscribe 함수 반환
```

## 2. 기능 흐름

### 2.1 페이지 진입 → WS 연결 → 메시지 수신
```
페이지 JS (예: dashboard/websocket.js)
    │
    ▼ WSClient.connect('/ws/sensors/')
_resolveUrl('/ws/sensors/', undefined)
    ├─ AppConfig.wsUrl('/ws/sensors/') → "ws://127.0.0.1:8001/ws/sensors/"
    └─ attachToken=undefined → 토큰 query 부착 안 함

_create(...) → _cache 확인
    ├─ cache hit → 기존 instance 반환 (다른 모듈이 이미 connect)
    └─ cache miss → 새 instance 생성
        ├─ _open() 즉시 호출
        │   ├─ ws = new WebSocket(url)
        │   ├─ ws.onopen → openHandlers 모두 dispatch
        │   ├─ ws.onmessage → JSON.parse → messageHandlers dispatch
        │   ├─ ws.onerror → console.warn + errorHandlers dispatch
        │   └─ ws.onclose → closeHandlers dispatch + 3초 후 _open 재시도
        ├─ _cache.set(url, instance)
        └─ instance 반환

페이지 JS:
    const off = ws.onMessage((data) => { ... })
    ws.onOpen(() => setStatus('connected'))
    ws.onClose(() => setStatus('disconnected'))
    ...
페이지 언마운트 시: off()
```

### 2.2 자동 재연결 시퀀스
```
WS 연결 끊김 → ws.onclose 트리거
    │
    ├─ closeHandlers dispatch (사용자 코드)
    ├─ closed === true? (수동 close)
    │   └─ Yes → 종료 (재시도 안 함)
    └─ No → setTimeout(_open, 3000ms)
        │
        ▼ 3초 후
        _open() 다시 호출
        └─ new WebSocket(url) → 같은 url로 재연결
            └─ 성공: openHandlers dispatch
            └─ 실패: 또 onclose → 무한 재시도 (closed===true 전까지)
```

## 3. 함수 분석

### 3.1 [shared/ws-client.js](../../../drf-server/static/js/shared/ws-client.js) — `WSClient` IIFE

이 파일 전체가 IIFE 패턴으로 `WSClient` 객체를 노출. 내부 함수와 외부 메서드를 분리해 분석.

#### 모듈 상수
- `RECONNECT_DELAY = 3000` (ws-client.js:25) — 자동 재연결 기본 지연 (ms)
- `_cache = new Map()` (ws-client.js:26) — `{[url]: instance}` 단일 연결 보장
- **올바름 검증**:
  - ✅ Map 사용 — string key 안전.
  - ⚠️ **모듈 글로벌 캐시** — 페이지 새로고침으로만 정리됨. 메모리 누수 가능성은 페이지 단위라 영향 미미.

#### `_resolveUrl(path, opts)` (ws-client.js:28-43)
- **시그니처**: `(path: string, opts?: {attachToken?: boolean}) => string`
- **역할**: WS 베이스 URL을 prefix하고 (옵션) JWT 토큰을 query string으로 부착
- **단계별 동작**:
  1. `if (window.AppConfig && typeof window.AppConfig.wsUrl === 'function')` — AppConfig 정상 로드 확인
  2. 정상 → `base = window.AppConfig.wsUrl(path)` — 예: `'/ws/sensors/'` → `'ws://127.0.0.1:8001/ws/sensors/'`
  3. 부재 → `base = path` (fallback, 상대 경로 — 정상 작동 어려움)
  4. `if (opts && opts.attachToken && typeof Auth !== 'undefined')` — Auth 모듈 로드 확인
  5. 토큰 존재 시 `?token=...` 또는 `&token=...` 추가 (sep는 `?` 포함 여부로 결정)
- **호출하는 함수**: `window.AppConfig.wsUrl`, `Auth.getAccessToken`, `encodeURIComponent`
- **호출자**: `_create` 내부에서 1회
- **올바름 검증**:
  - ✅ AppConfig·Auth 부재 fallback — 기본 동작.
  - ✅ `?` 포함 여부 분기 — query 문자열 안전 결합.
  - ⚠️ **AppConfig.wsUrl 부재 시 path 그대로 반환** — 브라우저는 same-origin ws:// 시도 → 8000 포트로 연결 실패. 디버깅 어려운 silent 실패. `console.warn` 권장.
  - ⚠️ **Auth 부재 + attachToken=true 시 silent skip** — 토큰 부착 실패가 사용자에게 안 보임. WS 인증 도입(이전 리뷰 04 D2) 후 모든 연결 실패로 이어짐.
  - 💡 token query 부착 — WebSocket 표준은 헤더 못 보냄 → query만 가능 (정상). 단, WS 서버 로그에 토큰이 노출됨 → access log filter 필요.
  - 💡 `encodeURIComponent` 사용 — JWT 토큰의 `.` `_` `-` 문자는 URL 안전. 그래도 방어적 인코딩 OK.

#### `_create(path, opts)` (ws-client.js:45-128)
- **시그니처**: `(path: string, opts?: object) => Instance`
- **역할**: WSClient 인스턴스 생성 (캐시 hit 시 재사용)
- **단계별 동작**:
  1. `opts = opts || {}` — 기본값 (ws-client.js:46)
  2. `const url = _resolveUrl(path, opts)` — 최종 URL 계산
  3. `const cached = _cache.get(url); if (cached) return cached;` — **캐시 hit 시 기존 인스턴스 반환** (ws-client.js:48-49)
  4. `messageHandlers/openHandlers/closeHandlers/errorHandlers = new Set()` — 핸들러 4종 (ws-client.js:51-54)
  5. `let ws = null; let closed = false; let reconnectTimer = null;` — WS 상태 변수 (ws-client.js:55-57)
  6. `_dispatch(set, ...args)` 내부 함수 정의 — Set 모든 fn 호출 + try-catch (ws-client.js:59-63)
  7. `_open()` 즉시 호출 — 첫 연결 시작
  8. `_addHandler(set, fn)` 정의 — Set add + unsubscribe 함수 반환
  9. `instance = {path, url, onMessage, onOpen, onClose, onError, send, close, get readyState}` (ws-client.js:99-124)
  10. `_cache.set(url, instance)` — 캐시 저장
  11. instance 반환
- **호출하는 함수**: `_resolveUrl`, `_open`(내부), `_addHandler`(내부), `_dispatch`(내부)
- **호출자**: 외부 노출된 `WSClient.connect`
- **올바름 검증**:
  - ✅ **단일 연결 보장 패턴** — 같은 url 호출 시 한 인스턴스. 8개 호출 지점이 같은 path면 1 연결로 통합. 모범.
  - ✅ `_dispatch`의 try-catch — 한 핸들러 에러가 다른 핸들러 전파 차단 (ws-client.js:60-62).
  - ⚠️ **closure로 ws/closed/reconnectTimer 캡처** — 인스턴스 내부 상태가 closure에 갇힘. 디버깅 시 외부 접근 불가 (의도된 캡슐화).
  - ⚠️ **opts가 첫 호출에만 적용** — 같은 url로 두 번째 호출 시 cache hit이라 새 opts 무시. 호출자가 다른 attachToken 옵션을 줘도 첫 호출의 url(query token 포함/미포함)이 사용됨. 매우 헷갈리는 동작.
  - 💡 `instance.path`/`instance.url` — 디버깅용 노출. OK.

#### `_open()` (ws-client.js:65-90, 내부 함수)
- **시그니처**: `() => void`
- **역할**: 새 WebSocket 생성 + 4개 라이프사이클 핸들러 바인딩 + 실패 시 재시도 등록
- **단계별 동작**:
  1. `try { ws = new WebSocket(url); } catch (e) { ... }` — WebSocket 생성자 자체 에러(잘못된 URL 등) 처리 (ws-client.js:66-74)
  2. catch: `_dispatch(errorHandlers, e)` + `if (!closed) reconnectTimer = setTimeout(_open, ...)` — 재시도
  3. `ws.onopen = () => _dispatch(openHandlers)` — 연결 성공
  4. `ws.onmessage = (event) => { JSON.parse 시도 → 실패 시 return; 성공 시 _dispatch(messageHandlers, data, event) }` (ws-client.js:76-80)
  5. `ws.onerror = (e) => { console.warn(...) + _dispatch(errorHandlers, e) }` (ws-client.js:81-84)
  6. `ws.onclose = (e) => { _dispatch(closeHandlers, e); if (closed) return; reconnectTimer = setTimeout(_open, RECONNECT_DELAY) }` (ws-client.js:85-89)
- **호출하는 함수**: `_dispatch`, `JSON.parse`, `setTimeout`, `WebSocket` 생성자
- **호출자**: `_create` 진입 시 1회 + 자기 자신 (재시도 setTimeout)
- **올바름 검증**:
  - ✅ **WebSocket 생성자 에러까지 catch** — 잘못된 URL·CSP 차단 등 처리. 좋은 방어 코드.
  - ✅ `JSON.parse` try-catch + return — 잘못된 메시지 무시. 정상.
  - ⚠️ **reconnectTimer 재할당 시 이전 timer 남음** — onclose가 빠르게 두 번 호출되면 두 setTimeout이 동시 실행 가능. 실제로는 ws.onclose는 최대 1회만 호출되므로 안전. 하지만 가드 코드(`clearTimeout(reconnectTimer)` 먼저)가 있으면 더 안전.
  - ⚠️ **재연결 무제한 + 고정 3초** — 서버가 영구 다운된 경우 무한 재시도로 콘솔 경고 폭주. **지수 백오프 (exponential backoff) + 최대 시도 횟수** 권장.
  - ⚠️ **`ws.onerror`의 console.warn**은 개발 편의지만 운영 환경에선 콘솔 노이즈. 프로덕션 빌드에서 제거 또는 logger 추상화 권장.
  - ❌ **onclose 후 onopen 재실행 시 핸들러는 **유지**되지만 그동안 발생한 메시지는 누락**. 백엔드 last-event-id 등 catch-up 메커니즘 부재 (이전 리뷰 07 G8).
  - 💡 onmessage의 `JSON.parse` 실패 시 silent return — 비-JSON 메시지(예: heartbeat ping)에 대한 의도. 디버깅 시 어떤 메시지가 무시됐는지 모름. `console.debug` 권장.

#### `_addHandler(set, fn)` (ws-client.js:94-97, 내부 함수)
- **시그니처**: `(set: Set, fn: Function) => () => boolean`
- **역할**: Set에 fn 추가 + unsubscribe 함수 반환
- **단계별 동작**:
  1. `set.add(fn)`
  2. `return () => set.delete(fn)` — unsubscribe 클로저
- **호출하는 함수**: `Set.add`
- **호출자**: 인스턴스의 `onMessage`/`onOpen`/`onClose`/`onError` 메서드
- **올바름 검증**:
  - ✅ **unsubscribe 패턴** — `const off = ws.onMessage(fn); ... off();` 명확.
  - ✅ Set 사용 — 동일 fn 중복 등록 안 됨 (참조 비교).
  - 💡 `Set.delete` 반환값(boolean) 그대로 노출 — 호출자가 사용 안 해도 OK이지만 의미 모호 (제거 성공 여부). `void` 반환이 더 명확.

#### `instance.send(payload)` (ws-client.js:106-112)
- **시그니처**: `(payload: string | object) => boolean`
- **역할**: WebSocket이 OPEN 상태면 send, 아니면 false
- **단계별 동작**:
  1. `if (ws && ws.readyState === WebSocket.OPEN)` — 연결 상태 체크
  2. `ws.send(typeof payload === 'string' ? payload : JSON.stringify(payload))` — string은 그대로, 그 외는 JSON
  3. return true
  4. else return false
- **올바름 검증**:
  - ✅ readyState 체크 — OPEN이 아니면 throw 대신 false 반환. 좋은 방어 코드.
  - ⚠️ **재연결 중 send는 silent fail** — 사용자가 send 결과 false를 무시하면 메시지 손실. 큐잉 로직 부재. 현 사용 패턴은 server→client 단방향이라 영향 적음.
  - 💡 `JSON.stringify` 실패(circular reference) 시 throw — 호출자가 catch해야 함. 명시적 try 권장 (사소).

#### `instance.close()` (ws-client.js:113-122)
- **시그니처**: `() => void`
- **역할**: 수동 종료 — 재시도 중지 + 핸들러 정리 + ws 종료 + 캐시 제거
- **단계별 동작**:
  1. `closed = true` — _open의 onclose가 재시도 안 하도록 플래그
  2. `clearTimeout(reconnectTimer)` — 진행 중 재시도 취소
  3. 4개 핸들러 Set `.clear()` — 모든 핸들러 제거
  4. `try { ws && ws.close(); } catch {}` — WebSocket close (이미 종료된 경우 throw 가능)
  5. `_cache.delete(url)` — 캐시에서 제거
- **올바름 검증**:
  - ✅ 완전한 cleanup — closed 플래그 + timer + handlers + ws + cache 모두 정리. 모범.
  - ⚠️ **closed=true 설정 후 onclose 발생 시** — 자연스러운 종료 시점에 closeHandlers는 이미 clear되어 있어 dispatch 안 됨. 수동 close 후 close 알림 부재. 의도일 수 있으나 명시 필요.
  - 💡 close() 호출 후 같은 url로 connect 호출 시 → cache miss → 새 인스턴스 생성. 정상.

#### `instance.readyState` getter (ws-client.js:123)
- **시그니처**: `() => number`
- **역할**: 현재 WS 상태 (CONNECTING=0, OPEN=1, CLOSING=2, CLOSED=3) 또는 null이면 CLOSED
- **올바름 검증**: ✅ 정상.

#### `WSClient.connect(path, opts)` (외부 노출, ws-client.js:131)
- **시그니처**: `(path: string, opts?: object) => Instance`
- **역할**: `_create`의 외부 alias
- **호출자**: 8개 페이지 JS

#### `WSClient._cache` (외부 노출, ws-client.js:132)
- **역할**: 디버깅용 Map 노출
- **올바름 검증**:
  - 💡 디버깅 시 `WSClient._cache`로 캐시 내용 확인 가능. 의도 명확.

## 4. 종합 평가

### 강점
- ✅ **연결 캐시로 단일 연결 보장** — 8개 호출 지점 → 같은 path면 1 connection. 트래픽 절감 + 중복 메시지 방지.
- ✅ **다중 핸들러 dispatch** — 한 연결을 여러 모듈이 구독 가능. 책임 분리 자연.
- ✅ **자동 재연결** — onclose 시 3초 후 재시도. 네트워크 일시 끊김 자연 복구.
- ✅ **opts.attachToken** — JWT 인증 도입 시 한 줄로 적용 가능 (서버 측 지원 필요).
- ✅ **WebSocket 생성자 에러 catch** — CSP 등 차단 시 silent crash 방지.
- ✅ **`_dispatch`의 핸들러 격리** — 한 핸들러 에러가 다른 핸들러 전파 차단.

### 약점
- ❌ **재연결 후 메시지 catch-up 부재** — 끊긴 동안 발생한 메시지 누락. last-event-id/sequence number 부재.
- ⚠️ **재연결 무제한 + 고정 3초** — 서버 영구 다운 시 영구 재시도. 지수 백오프 + 최대 시도 횟수 부재.
- ⚠️ **opts가 첫 connect에만 적용 (캐시 동작)** — 두 번째 호출자가 다른 attachToken 줘도 무시. 직관 어긋남.
- ⚠️ **AppConfig 부재 시 silent fallback** — 디버깅 어려움.
- ⚠️ **JSON 파싱 실패 silent skip** — 비-JSON 메시지 무시.

### 중복 / 누락
- 📌 같은 path 동시 connect는 안전하지만, **다른 path의 동시 연결 수 제한 부재** — 페이지가 무분별하게 connect 호출 시 서버 부담. 현 코드는 안전.
- 📌 **heartbeat / ping 부재** — 연결 끊김인지 무데이터인지 구분 불가 (이전 리뷰 09 I7).

### contract 정합성
- ✅ 서버 (fastapi `/ws/sensors/`, `/ws/worker/{id}/`, `/ws/positions/`)와 path 일치.
- ⚠️ JWT 인증 도입 시 **모든 호출자가 attachToken: true 일관 적용 필요** (이전 리뷰 08 H5).

## 5. 리팩토링 권고

### R1. 지수 백오프 + 최대 시도 횟수 [상 · 소]
- **왜 필요?**: 서버 영구 다운 시 3초마다 영구 재시도 → 콘솔 경고 폭주 + 클라이언트 자원 낭비. 서버 복구 시점이 늦어질수록 비용 증가.
- **장점**: 자원 절감 / 서버 부하 분산 (동시 클라이언트 다수가 같은 시점 재시도 안 함).
- **단점**: 사용자가 오래 끊긴 후엔 수동 새로고침 필요. → "재연결 시도 중... [수동 재연결] 버튼" UI로 보강 가능.
- **변경 위치**: [ws-client.js:25 RECONNECT_DELAY 상수, :70-89 _open 내부](../../../drf-server/static/js/shared/ws-client.js#L65-L89)
- **변경 예시**:
  ```js
  // before
  const RECONNECT_DELAY = 3000;
  // _open 내부:
  reconnectTimer = setTimeout(_open, opts.reconnectDelay || RECONNECT_DELAY);

  // after
  const INITIAL_DELAY = 1000;     // 1초부터 시작
  const MAX_DELAY = 30000;        // 최대 30초
  const MAX_ATTEMPTS = 20;        // 20회 후 포기
  const JITTER = 0.3;             // ±30% 무작위 (다수 클라이언트 동시 재시도 분산)

  let attempts = 0;
  function _scheduleReconnect() {
    if (closed) return;
    attempts++;
    if (attempts > MAX_ATTEMPTS) {
      _dispatch(errorHandlers, new Error('max_reconnect_attempts'));
      return;
    }
    const base = Math.min(INITIAL_DELAY * Math.pow(2, attempts - 1), MAX_DELAY);
    const delay = base * (1 + (Math.random() - 0.5) * JITTER);
    reconnectTimer = setTimeout(_open, delay);
  }
  // ws.onopen 시 attempts = 0 리셋
  // ws.onclose 시 _scheduleReconnect() 호출
  ```

### R2. attachToken 옵션 캐시 키 분리 [상 · 소]
- **왜 필요?**: 같은 path를 다른 attachToken 옵션으로 호출 시 첫 호출의 토큰 부착 여부가 캐시되어 의도와 다름. WS 인증 도입 시 침묵하는 버그 가능.
- **장점**: 의도 명확.
- **단점**: 캐시 hit 비율 약간 감소 (실제로 같은 path를 attachToken=true와 false로 둘 다 호출하는 케이스는 거의 없음).
- **변경 위치**: [ws-client.js:48-49](../../../drf-server/static/js/shared/ws-client.js#L48-L49)
- **변경 예시**:
  ```js
  // before
  const url = _resolveUrl(path, opts);
  const cached = _cache.get(url);

  // after
  const url = _resolveUrl(path, opts);
  // url 자체에 ?token=... 가 포함되어 있으니 _cache.get(url)으로 자연스럽게 분리됨
  // 단, 토큰 변경(refresh) 시엔 url이 달라져 캐시 미스 → 새 연결 (의도된 동작인지 확인)
  // 추가 보강: 토큰 갱신 시 기존 connection close 신호
  ```
  ※ 사실 현 코드는 token이 url에 포함되니 자동 분리됨. 다만 **토큰 회전 시 기존 연결이 캐시에 남아 stale token 사용** — 이게 실제 버그. R1·R2 통합 PR 권장.

### R3. 메시지 catch-up 메커니즘 (last_event_id) [상 · 중]
- **왜 필요?**: 재연결 시 그동안 발생한 메시지 누락 → 알람 누락 위험 (산재 예방 시스템 핵심).
- **장점**: 끊김 복구 시 사용자 신뢰 확보.
- **단점**: 서버 측 last_event_id 지원 필요. fastapi의 broadcast 페이로드에 sequence 추가 + 클라이언트 측 캐시.
- **변경 위치**: [ws-client.js:67-89 _open](../../../drf-server/static/js/shared/ws-client.js#L65-L89), 서버 측 broadcast.py + ws_router.py.
- **변경 예시**:
  ```js
  // 클라이언트 측
  let lastEventId = null;
  function _open() {
    const finalUrl = lastEventId
      ? `${url}${url.includes('?') ? '&' : '?'}last_event_id=${lastEventId}`
      : url;
    ws = new WebSocket(finalUrl);
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.event_id) lastEventId = data.event_id;
      _dispatch(messageHandlers, data, event);
    };
    ...
  }
  ```
  ※ 서버 측은 06 백엔드 변경 의존 — 본 PR에서는 클라이언트 인프라만 준비, 서버는 별도 PR.

### R4. AppConfig·Auth 부재 시 console.warn [중 · 소]
- **왜 필요?**: silent fallback은 디버깅 어려움. 운영 시 의도치 않은 same-origin 연결 시도 → 발견 늦음.
- **장점**: 1초만에 원인 파악.
- **단점**: 정상 케이스에선 출력 없음 (조건부).
- **변경 위치**: [ws-client.js:28-43 _resolveUrl](../../../drf-server/static/js/shared/ws-client.js#L28-L43)
- **변경 예시**:
  ```js
  // before
  function _resolveUrl(path, opts) {
    let base;
    if (window.AppConfig && typeof window.AppConfig.wsUrl === 'function') {
      base = window.AppConfig.wsUrl(path);
    } else {
      base = path;
    }
    ...
  }

  // after
  function _resolveUrl(path, opts) {
    let base;
    if (window.AppConfig && typeof window.AppConfig.wsUrl === 'function') {
      base = window.AppConfig.wsUrl(path);
    } else {
      console.warn('[WSClient] AppConfig.wsUrl unavailable, using same-origin fallback for', path);
      base = path;
    }
    if (opts && opts.attachToken) {
      if (typeof Auth === 'undefined') {
        console.warn('[WSClient] attachToken requested but Auth module not loaded');
      } else {
        const token = Auth.getAccessToken();
        if (!token) console.warn('[WSClient] attachToken requested but no token in storage');
        else {
          const sep = base.includes('?') ? '&' : '?';
          base += `${sep}token=${encodeURIComponent(token)}`;
        }
      }
    }
    return base;
  }
  ```

### R5. heartbeat / ping [중 · 중]
- **왜 필요?**: 클라이언트가 끊김인지 무데이터인지 구분 못 함. UI 상태 표시 부정확.
- **장점**: 연결 상태 정확 / 좀비 연결(half-open) 빠른 감지.
- **단점**: 트래픽 약간 증가. 서버 broadcast_loop은 5초 주기라 실질 heartbeat 역할 — 이미 부분적으로 충족.
- **변경 위치**: [ws-client.js _open 내부](../../../drf-server/static/js/shared/ws-client.js#L65-L89)
- **변경 예시**:
  ```js
  let heartbeatTimer = null;
  let lastSeen = Date.now();
  const HEARTBEAT_MS = 30000;
  const TIMEOUT_MS = 60000;

  ws.onmessage = (event) => {
    lastSeen = Date.now();
    ...
  };
  function _checkHeartbeat() {
    if (Date.now() - lastSeen > TIMEOUT_MS) {
      console.warn('[WSClient] no message in', TIMEOUT_MS, 'ms — forcing reconnect');
      try { ws && ws.close(); } catch {}
    }
  }
  ws.onopen = () => {
    lastSeen = Date.now();
    heartbeatTimer = setInterval(_checkHeartbeat, HEARTBEAT_MS);
    _dispatch(openHandlers);
  };
  ws.onclose = () => {
    clearInterval(heartbeatTimer);
    ...
  };
  ```

### R6. instance.path 외부 노출 시 caller 감사 가능 [하 · 소]
- **왜 필요?**: 디버깅 시 instance가 어떤 path인지 노출되어 있음 — 이미 OK. 추가 개선 없음.

### R7. JSON 파싱 실패 디버그 로그 [하 · 소]
- **왜 필요?**: 비-JSON 메시지(미래의 binary, ping 등) 도입 시 무시되는 메시지 디버깅 어려움.
- **변경 위치**: [ws-client.js:77-78](../../../drf-server/static/js/shared/ws-client.js#L77-L78)
- **변경 예시**:
  ```js
  ws.onmessage = function (event) {
    let data;
    try { data = JSON.parse(event.data); }
    catch {
      console.debug('[WSClient] non-JSON message ignored', event.data?.slice?.(0, 100));
      return;
    }
    _dispatch(messageHandlers, data, event);
  };
  ```

### R8. 프로덕션 빌드에서 console.warn 제어 [하 · 중]
- **왜 필요?**: 운영 콘솔에 노이즈. CSP/CDN 환경에서 정상 동작인데 경고만 발생.
- **변경 위치**: 빌드 도구 도입 시 / 또는 logger 추상화.
- **변경 예시**:
  ```js
  const log = window.AppConfig?.debug
    ? { warn: console.warn.bind(console), debug: console.debug.bind(console) }
    : { warn: () => {}, debug: () => {} };
  log.warn('[WSClient] error', path);
  ```
  ※ 구현 비용 vs 가치 — 현재 규모에선 필수 아님.

### R9. close() 후 closeHandlers dispatch 옵션 [하 · 소]
- **왜 필요?**: 수동 close 시 closeHandlers가 이미 clear되어 호출 안 됨. 호출자가 "내가 close했으니 알람 끄기" 로직 못 실행.
- **변경 위치**: [ws-client.js:113-122 close](../../../drf-server/static/js/shared/ws-client.js#L113-L122)
- **변경 예시**:
  ```js
  close() {
    closed = true;
    clearTimeout(reconnectTimer);
    // dispatch before clear
    _dispatch(closeHandlers, { code: 1000, reason: 'manual' });
    messageHandlers.clear();
    openHandlers.clear();
    closeHandlers.clear();
    errorHandlers.clear();
    try { ws && ws.close(); } catch {}
    _cache.delete(url);
  },
  ```

### R10. 연결 상태를 외부에 더 명확히 노출 [하 · 소]
- **왜 필요?**: readyState getter는 WebSocket 상수(0~3) 반환 — UI에서 매번 분기해야 함.
- **변경 위치**: instance에 `status` getter 추가.
- **변경 예시**:
  ```js
  get status() {
    if (!ws) return 'closed';
    return ['connecting', 'open', 'closing', 'closed'][ws.readyState];
  },
  ```

## 6. 단계별 적용 순서

### 1단계 — 즉시 (1일) ⚡
- **R4** AppConfig·Auth 부재 console.warn — 디버깅 가시성 향상, 1줄.
- **R7** JSON 파싱 console.debug — 미래 확장 대비.
- **R9** close() dispatch — 호출자 cleanup 정확.
- **이유**: 모두 작은 변경, 회귀 위험 거의 없음. 운영 가시성 즉시 향상.

### 2단계 — 1주 내 🔧
- **R1** 지수 백오프 + 최대 시도 — 서버 영구 다운 대응.
- **R2** attachToken 캐시 정합 — WS 인증 도입(이전 리뷰 09 I4) 사전 작업.
- **이유**: 인프라 안정성 핵심. R1은 단독, R2는 인증 도입과 함께.

### 3단계 — 다음 sprint 🏗
- **R3** 메시지 catch-up (서버 협업)
- **R5** heartbeat 정책
- **R10** status getter
- **이유**: 서버 측 변경 동반 또는 큰 작업. 핵심 공유 계층 안정 후 진행.

### 4단계 — 여유 시
- **R6** path 외부 노출 (이미 OK)
- **R8** 프로덕션 logger (빌드 도구 도입 시)

### ⚠️ 주의사항 (초보자용)

- **R1 지수 백오프 적용 시 attempts 리셋 누락 주의**: ws.onopen 시 `attempts = 0` 필수. 안 그러면 한 번 끊긴 후엔 영원히 백오프 누적.
- **R3 last_event_id는 서버 측 구현 의존**: 클라이언트만 변경하면 서버가 무시 → 효과 없음. 서버 PR과 동기화 필요. 본 PR에서는 클라이언트 인프라만 준비하고 실제 활성화는 서버 도입 후.
- **R5 heartbeat 적용 시 timeout 값 신중**: 30초 너무 짧으면 모바일 약전계에서 잘못된 reconnect 빈발. 60초 권장 시작값.
- **R2 캐시 동작 변경 후 e2e 회귀 검증**: 같은 페이지 alarm-ws + dashboard/websocket 두 모듈이 같은 path 호출 시 단일 연결 유지 확인 (PR-H 또는 수동 테스트).
- **모든 변경 후 PR-H 4종 테스트 회귀 필수**: WS 인프라 변경은 알람 흐름 직접 영향. 변경 전 PR-H 통과 확인 → 변경 → 다시 통과 확인.
