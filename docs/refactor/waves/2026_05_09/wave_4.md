# Wave 4 — JS [상] 권고 후속 적용 실행 보고서

> **브랜치**: `feature/0508_refactory_code`
> **작업일**: 2026-05-11
> **분석 베이스**: [docs/refactor/js/2026_05_09/](../../js/2026_05_09/) (00_overview.md Top 10 + 02·03·04·05 [상] 권고)
> **상태**: ✅ 완료
> **검증**: pytest 84/84 통과 (drf 62 + fastapi 22), Node 문법 검사 모든 신규/수정 JS OK

## 1. 작업 개요

### 1.1 목표

Wave 1~3 의 J 트랙 17건 적용 후 남아 있던 **[상] 우선순위 7건**을 추가 적용. 모두 분석 문서(`docs/refactor/js/2026_05_09/`)에 명시된 권고 옵션 중 **회귀 위험이 적고 팀 내부 결정만으로 진행 가능한 것** 위주로 선별.

도메인 횡단 Top 10 기준으로는 이번 작업으로 **9/10 적용** (이전 4건 + 이번 5건). 미적용 1건(02 R3 WS catch-up)은 서버 ring buffer 설계가 필요해 별도 PR로 분리.

### 1.2 범위

- WS 인프라 1건 (02 R1)
- 알람 파이프라인 4건 (03 R1, 03 R2, 03 R3, 05 R3 알람 시각·매퍼·큐 정책)
- 레이아웃 보안 1건 (04 R1)
- 페이지 인증 정합 1건 (05 R2)
- 신규 파일 2개 (`shared/alarm-mapper.js`, `shared/level-mapper.js`)

### 1.3 영향 파일 (15개)

| 분류 | 파일 |
|---|---|
| **JS 신규** | `drf-server/static/js/shared/alarm-mapper.js`, `drf-server/static/js/shared/level-mapper.js` |
| **JS 수정 (shared)** | `drf-server/static/js/shared/{ws-client,alarm-ws,worker-ws,alarm-popup,layout}.js` |
| **JS 수정 (dashboard)** | `drf-server/static/js/dashboard/{websocket,app}.js` |
| **백엔드 수정** | `drf-server/apps/alerts/tasks.py`, `fastapi-server/internal/routers/alarm_router.py` |
| **템플릿 수정** | `drf-server/templates/dashboard/main.html`, `drf-server/templates/snb_details/{event_detail,monitoring_events,monitoring_realtime}.html` |

### 1.4 미적용 — 별도 PR 보류 사유

| 권고 | 보류 사유 |
|---|---|
| **02 R3** WS 메시지 catch-up | 서버 측 ring buffer 설계 필요 (메모리 상한, 재시작 시 buffer 손실 정책, `last_event_id` 위변조 방지, 다중 fastapi 인스턴스 운영 시 sync 등). 운영 진입 후 disconnect 빈도/duration 데이터 보고 결정 권장. |
| **05 R3 (옵션 A)** CSS 클래스 리네임 | 옵션 B(매퍼)로 변환층 단일화 완료. CSS 리네임은 10+ 파일 영향이라 별도 sprint. |
| **04 R2** initHeaderAndSNB getMe 실패 처리 | "인증 만료 vs 네트워크 실패" UX 정책 결정 필요. |

## 2. 변경 항목 상세

각 항목은 다음 5섹션으로 정리:
**(A) 무엇이 바뀌었나** · **(B) 왜 바뀌었나 (분석 근거)** · **(C) 적용된 기능** · **(D) Before / After** · **(E) 다른 방법 trade-off**

---

### 02 R1. WS 지수 백오프 + 최대 시도 ([ws-client.js](../../../../drf-server/static/js/shared/ws-client.js))

**(A) 변경 내용**
- 상수 `RECONNECT_DELAY = 3000` (고정 3초) 제거
- `INITIAL_DELAY=1000` / `MAX_DELAY=30000` / `MAX_ATTEMPTS=20` / `JITTER=0.3` 모듈 상수 추가
- `_open()` 내 재연결 로직을 `_scheduleReconnect()` 함수로 분리. `attempts` 카운터로 지수 백오프 (1s → 2s → 4s → ... → 30s 상한, ±30% 지터)
- `MAX_ATTEMPTS` 도달 시 `errorHandlers` 에 `Error('max_reconnect_attempts')` 디스패치 후 재시도 중단
- `ws.onopen` 시점에 `attempts = 0` 리셋
- 사용 안 하던 `opts.reconnectDelay` 옵션 제거 (호출자 0건)

**(B) 왜 바뀌었나**
- 분석 근거: [02_ws_infrastructure.md R1](../../js/2026_05_09/02_ws_infrastructure.md) [상 · 소]
- 서버 영구 다운 시 3초마다 영구 재시도 → 콘솔 경고 폭주 + 클라이언트 자원 낭비
- 다수 클라이언트가 같은 시점 재시도하면 서버 복구 시 동시 부하 (thundering herd)

**(C) 적용된 기능**
- 서버 다운 시 점진적 백오프 — 첫 시도는 1s, 이후 2배씩 증가하다 30s 상한
- ±30% 지터로 다수 클라이언트 동시 재시도 분산
- 20회(누적 약 5~10분) 후 포기 → onError 핸들러로 사용자에게 알릴 수 있음
- 정상 연결 회복 시 `attempts` 자동 리셋

**(D) Before / After**
```js
// Before
const RECONNECT_DELAY = 3000;
ws.onclose = function (e) {
  _dispatch(closeHandlers, e);
  if (closed) return;
  reconnectTimer = setTimeout(_open, opts.reconnectDelay || RECONNECT_DELAY);
};

// After
const INITIAL_DELAY = 1000;
const MAX_DELAY     = 30000;
const MAX_ATTEMPTS  = 20;
const JITTER        = 0.3;
let attempts = 0;

function _scheduleReconnect() {
  if (closed) return;
  attempts += 1;
  if (attempts > MAX_ATTEMPTS) {
    console.warn('[WSClient] max reconnect attempts reached for', path);
    _dispatch(errorHandlers, new Error('max_reconnect_attempts'));
    return;
  }
  const base = Math.min(INITIAL_DELAY * Math.pow(2, attempts - 1), MAX_DELAY);
  const delay = base * (1 + (Math.random() - 0.5) * JITTER);
  reconnectTimer = setTimeout(_open, delay);
}

ws.onopen = function () {
  attempts = 0;
  _dispatch(openHandlers);
};
ws.onclose = function (e) {
  _dispatch(closeHandlers, e);
  _scheduleReconnect();
};
```

**(E) 다른 방법 trade-off**

| 옵션 | 장점 | 단점 | 채택 여부 |
|---|---|---|---|
| ✅ 지수 백오프 + 지터 + 최대 시도 | 자원 절감 / 부하 분산 / 복구 보장 | 사용자 경험 — 오래 끊긴 후 수동 새로고침 필요 (UI 보강 가능) | **채택** |
| 고정 간격 (현행 3s) | 단순 | 자원 폭주 | 변경 전 |
| 고정 간격 + 최대 시도만 | 단순 + 종료 보장 | 부하 분산 안 됨 | 미채택 |
| Long-polling fallback | WS 영구 실패 시도 회복 | 구현 복잡 / 서버 변경 필요 | 미채택 (sprint) |

---

### 03 R1. `shared/alarm-mapper.js` 추출 — 키 변환 단일화 ([alarm-mapper.js](../../../../drf-server/static/js/shared/alarm-mapper.js))

**(A) 변경 내용**
- 신규 `shared/alarm-mapper.js` (43줄) — `AlarmMapper.fromSensorsAlarm(serverAlarm)` / `AlarmMapper.fromWorkerAlert(serverData)` 두 함수
- 3 callers 의 동일 매핑 코드 제거:
  - `shared/alarm-ws.js` — 9줄 → 1줄
  - `shared/worker-ws.js` — 8줄 → 1줄
  - `dashboard/websocket.js` — 9줄 → 1줄
- 4 템플릿(`dashboard/main.html`, `snb_details/{event_detail,monitoring_events,monitoring_realtime}.html`) 에 `<script src="alarm-mapper.js">` 추가 — `alarm-popup.js` 와 `worker-ws.js` 사이에 일관 위치 삽입
- 매퍼는 03 R3 의 `created_at` 우선 사용 로직도 포함

**(B) 왜 바뀌었나**
- 분석 근거: [03_alarm_pipeline.md R1](../../js/2026_05_09/03_alarm_pipeline.md) [상 · 소]
- 백엔드 키(`risk_level`/`source_label`/`summary`)와 클라이언트 키(`alarm_level`/`sensor_name`/`message`)가 다른 도메인 — 변환층이 3곳에 분산되어 있어 백엔드 키 변경 시 한 곳 누락만으로도 silent break

**(C) 적용된 기능**
- 단일 진실 원천 — 백엔드 키 변경 시 1개 파일만 수정
- 단위 테스트 가능한 순수 함수
- `created_at` fallback 일관 처리 (03 R3 기능 동시 적용)

**(D) Before / After**
```js
// Before — alarm-ws.js (worker-ws / dashboard/websocket.js 도 거의 동일)
data.alarms.forEach(function (alarm) {
  const alarmData = {
    alarm_level:  alarm.risk_level,
    is_new_event: alarm.is_new_event,
    message:      alarm.summary,
    sensor_name:  alarm.source_label,
    timestamp:    new Date().toISOString(),
    gas_type:     alarm.gas_type,
    event_id:     alarm.event_id,
  };
  ...
});

// After
data.alarms.forEach(function (alarm) {
  const alarmData = AlarmMapper.fromSensorsAlarm(alarm);
  ...
});
```

```js
// shared/alarm-mapper.js (신규)
const AlarmMapper = (function () {
  function _common(src) {
    return {
      alarm_level:  src.risk_level,
      is_new_event: src.is_new_event,
      message:      src.summary,
      sensor_name:  src.source_label,
      timestamp:    src.created_at || new Date().toISOString(),
      event_id:     src.event_id,
    };
  }
  return {
    fromSensorsAlarm(s) { return Object.assign(_common(s), { gas_type: s.gas_type }); },
    fromWorkerAlert(s)  { return _common(s); },
  };
})();
```

**(E) 다른 방법 trade-off**

| 옵션 | 장점 | 단점 | 채택 여부 |
|---|---|---|---|
| ✅ 매퍼 모듈 분리 (옵션 B) | 단일 진실 원천 / 1줄 변경 | 신규 파일 1개 / 스크립트 로드 순서 관리 | **채택** |
| 백엔드 키를 클라이언트 키와 통일 | 매퍼 자체 제거 | 백엔드 호환성 영향 큼 / 외부 시스템 영향 | 미채택 |
| 인라인 함수 (각 파일에) | 의존 없음 | 분산 유지 → 권고 미해결 | 변경 전 |

---

### 03 R2. AlarmPopup 큐 정책 ([alarm-popup.js](../../../../drf-server/static/js/shared/alarm-popup.js))

**(A) 변경 내용**
- `droppedCount` 인스턴스 카운터 추가
- `GROUP_WINDOW_MS = 5000` 상수 추가
- `show(data)` 에 두 단계 로직 추가:
  1. **그룹핑(옵션 B)**: 마지막 큐 항목과 `sensor_name` + `alarm_level` 일치하고 `timestamp` 가 5초 이내면 `groupCount` 만 누적, 큐에 추가하지 않음
  2. **드롭 카운트(옵션 A)**: 큐가 `MAX_QUEUE` 도달 시 silent return 대신 `droppedCount` 증가 + `console.warn` 으로 누적·센서·레벨 노출
- `_process()` 의 메시지 렌더에 `groupCount > 1` 이면 `(×N)` suffix 추가

**(B) 왜 바뀌었나**
- 분석 근거: [03_alarm_pipeline.md R2](../../js/2026_05_09/03_alarm_pipeline.md) [상 · 중]
- 산재 예방 시스템에서 silent drop 은 사고 가능성 — 운영팀에 누락 통계 노출 부재
- 같은 센서 연속 알람이 빈발하면 큐가 동일 알람으로 차서 다른 센서 알람을 못 보여주는 문제

**(C) 적용된 기능**
- 같은 센서·동일 레벨 5초 내 연속 알람 그룹핑 → 큐 슬롯 절약 + UI 에 `(×N)` 표시로 빈도 가시화
- 큐 풀 시 `droppedCount` 운영 가시성 — 콘솔에 누적 카운트·센서·레벨 노출, 향후 운영 도구 전송 가능

**(D) Before / After**
```js
// Before
show(data) {
  const level = data.alarm_level;
  if (level !== 'danger' && level !== 'warning') return;
  if (this.queue.length >= this.MAX_QUEUE) return;   // silent drop
  this.queue.push(data);
  if (!this.isOpen) this._process();
},

// After
show(data) {
  const level = data.alarm_level;
  if (level !== 'danger' && level !== 'warning') return;

  // 옵션 B: 같은 센서·동일 레벨 5초 내 연속 알람은 마지막 큐 항목에 카운트만 누적
  const last = this.queue[this.queue.length - 1];
  if (last && last.sensor_name === data.sensor_name && last.alarm_level === data.alarm_level) {
    const lastTs = new Date(last.timestamp).getTime();
    if (Number.isFinite(lastTs) && (Date.now() - lastTs) < this.GROUP_WINDOW_MS) {
      last.groupCount = (last.groupCount || 1) + 1;
      return;
    }
  }

  // 옵션 A: 큐 풀 — silent drop 대신 카운트 노출
  if (this.queue.length >= this.MAX_QUEUE) {
    this.droppedCount += 1;
    console.warn('[AlarmPopup] queue full, dropping alarm', {
      droppedTotal: this.droppedCount,
      sensor: data.sensor_name,
      level: data.alarm_level,
    });
    return;
  }
  this.queue.push(data);
  if (!this.isOpen) this._process();
},
```

```js
// _process() 메시지 렌더 변경
const suffix = data.groupCount > 1 ? ` (×${data.groupCount})` : '';
msgEl.textContent = (sensor ? `${sensor} — ${msg}` : msg) + suffix;
```

**(E) 다른 방법 trade-off**

| 옵션 | 장점 | 단점 | 채택 여부 |
|---|---|---|---|
| ✅ B + A 결합 (그룹핑 + drop count) | 빈발 알람 큐 절약 + 누락 가시성 | 동일 센서 연속 알람만 그룹핑 (다른 센서는 silent drop 발생 가능) | **채택** |
| A 단독 (drop count) | 단순 | 동일 센서 알람도 큐 차지 → 빨리 풀 | 미채택 |
| C (위험도 우선순위 큐) | danger 우선 | 큐 재정렬 비용 / UX 일관성 깨짐 (시간 순서 X) | 미채택 |
| 운영 도구 전송 | 외부 분석 | 별도 인프라 필요 | sprint (옵션 A 의 console.warn 을 후속에 fetch 로 전송 가능) |

---

### 03 R3. 서버 timestamp 사용 (`created_at`)

**(A) 변경 내용**
- DRF [`apps/alerts/tasks.py::_push_to_ws()`](../../../../drf-server/apps/alerts/tasks.py) — fastapi 호출 직전에 `alarm_data.setdefault("created_at", datetime.now(timezone.utc).isoformat())` 자동 주입. 7개 callsite 일괄 적용 (각 callsite 수정 불필요)
- fastapi [`AlarmPayload`](../../../../fastapi-server/internal/routers/alarm_router.py) 에 `created_at: str | None = None` 필드 추가
- [`alarm-mapper.js`](../../../../drf-server/static/js/shared/alarm-mapper.js) 의 `_common()` 이 `src.created_at || new Date().toISOString()` — 서버 발신 시각 우선, 누락 시 도착 시각 fallback

**(B) 왜 바뀌었나**
- 분석 근거: [03_alarm_pipeline.md R3](../../js/2026_05_09/03_alarm_pipeline.md) [중 · 소]
- 기존 `new Date().toISOString()` (브라우저 도착 시각) 은 WS broadcast tick (1s 주기) + 큐 대기로 발신 시각과 차이 발생 가능
- 알람 시각이 부정확하면 사후 분석(언제 발생했는지)에 오차

**(C) 적용된 기능**
- 알람 발신(Celery task 실행) 시각 정확도 — UTC ISO-8601
- 호환성 — 옵트인이 아니라 항상 켜지지만 클라이언트가 모르는 키여도 매퍼가 fallback 함

**(D) Before / After**
```python
# Before — drf-server/apps/alerts/tasks.py
def _push_to_ws(alarm_data: dict) -> None:
    headers = {}
    token = getattr(settings, "INTERNAL_SERVICE_TOKEN", "") or ""
    if token: headers["Authorization"] = f"Bearer {token}"
    httpx.post(FASTAPI_INTERNAL_URL, json=alarm_data, headers=headers, timeout=3.0)

# After
def _push_to_ws(alarm_data: dict) -> None:
    from datetime import datetime, timezone
    alarm_data.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    headers = {}
    ...
```

```python
# fastapi-server/internal/routers/alarm_router.py
class AlarmPayload(BaseModel):
    ...
    # 서버(DRF Celery) 발신 시각 — 클라이언트가 우선 사용 (JS 03 R3).
    created_at: str | None = None
```

```js
// shared/alarm-mapper.js
function _common(src) {
  return {
    ...
    timestamp: src.created_at || new Date().toISOString(),
    ...
  };
}
```

**(E) 다른 방법 trade-off**

| 옵션 | 장점 | 단점 | 채택 여부 |
|---|---|---|---|
| ✅ 헬퍼 `_push_to_ws` 에 setdefault | 7 callsite 일괄 적용 / 호출자 수정 0 | 기존 호출자가 명시한 값은 보존 (의도된 동작) | **채택** |
| 각 task 에서 명시 추가 | 호출 시점 명확 | 7곳 수정 / 누락 위험 | 미채택 |
| Celery task 시작 시각 | 가장 이른 시점 | 큐 대기 시간 포함 → "발생 시각" 의미 흐려짐 | 미채택 |
| Event.created_at (DB 컬럼) | 영속 시각 | DB 조회 추가 / 일부 task 는 Event 미생성 | 미채택 |

---

### 04 R1. `Menu.render` innerHTML → createElement (XSS 패턴) ([layout.js](../../../../drf-server/static/js/shared/layout.js))

**(A) 변경 내용**
- `Menu.render()` 의 두 `innerHTML` 템플릿 리터럴(루트 버튼 + 자식 `<a>`) 을 `createElement` + `textContent` 패턴으로 교체
- `menu.label`, `child.label`, `child.path` 모두 `textContent` / `dataset` 으로 안전 처리
- icon 만 `innerHTML` 유지 — `iconMap` 의 인하우스 SVG 마크업으로 의도된 동작
- 코드 길이 ~30% 증가, 가독성은 빌더 패턴으로 보강

**(B) 왜 바뀌었나**
- 분석 근거: [04_layout_menu_header.md R1](../../js/2026_05_09/04_layout_menu_header.md) [상 · 중]
- 현재 `menu.label` 은 백엔드 데이터(안전)지만 향후 사용자 입력·테넌트 레이블·다국어 등 추가 시 즉시 XSS 위험
- 패턴 정착 — Menu 가 본보기가 되어 향후 동적 DOM 생성 코드의 표준 제공

**(C) 적용된 기능**
- XSS 자동 방지 — 사용자 데이터가 마크업으로 해석되지 않음
- 향후 `child.path` 에 사용자 입력 들어가도 `dataset.path` 는 attribute escape 자동

**(D) Before / After**
```js
// Before
btn.innerHTML = `
  <span class="menu-icon">${icon}</span>
  <span class="menu-label">${menu.label}</span>
  ${hasChildren ? '<span class="menu-arrow">▶</span>' : ''}
`;
...
subLi.innerHTML = `<a href="${child.path}" class="${isActive ? 'active' : ''}" data-path="${child.path}">${child.label}</a>`;

// After
const iconSpan = document.createElement('span');
iconSpan.className = 'menu-icon';
iconSpan.innerHTML = icon;          // 인하우스 SVG (의도)
btn.appendChild(iconSpan);

const labelSpan = document.createElement('span');
labelSpan.className = 'menu-label';
labelSpan.textContent = menu.label; // ← 안전 처리
btn.appendChild(labelSpan);

if (hasChildren) {
  const arrowSpan = document.createElement('span');
  arrowSpan.className = 'menu-arrow';
  arrowSpan.textContent = '▶';
  btn.appendChild(arrowSpan);
}

// child <a>
const a = document.createElement('a');
a.href = child.path;
if (isActive) a.classList.add('active');
a.dataset.path = child.path;
a.textContent = child.label;
subLi.appendChild(a);
```

**(E) 다른 방법 trade-off**

| 옵션 | 장점 | 단점 | 채택 여부 |
|---|---|---|---|
| ✅ createElement + textContent | XSS 자동 방지 / 패턴 정착 | 코드 길이 +30% | **채택** |
| innerHTML + escapeHtml() 헬퍼 | 코드 길이 유지 | 매번 escape 호출 누락 위험 / 부분 신뢰 데이터 식별 어려움 | 미채택 |
| 템플릿 엔진 (lit-html / Vue) | 선언적 | 런타임 의존성 추가 | 미채택 (현 stack 외) |

---

### 05 R2. `loadMySafetyStatus` → `Auth.apiFetch` ([dashboard/app.js](../../../../drf-server/static/js/dashboard/app.js))

**(A) 변경 내용**
- 직접 `fetch('/dashboard/api/safety-status/')` 를 `Auth.apiFetch('/dashboard/api/safety-status/')` 로 교체
- HTTP 에러 시 (`!res.ok`) `console.warn` 으로 status 기록 (J10 이 추가했던 catch 만의 console.warn 을 정상 응답 경로까지 확장)

**(B) 왜 바뀌었나**
- 분석 근거: [05_page_init.md R2](../../js/2026_05_09/05_page_init.md) [상 · 소]
- 직접 fetch 는 인증 헤더 미부착 + 401 자동 refresh 부재 + 토큰 만료 시 silently 실패
- 다른 페이지(`Auth.apiFetch` 사용) 와 일관성 결여
- 향후 백엔드 권한이 `AllowAny` → `IsAuthenticated` 로 강화될 때 즉시 깨짐 (대비)
- J10 (Wave 1) 은 catch 에 console.warn 만 추가 — 인증 일관성은 미해결 상태였음

**(C) 적용된 기능**
- 인증 헤더 자동 부착
- 401 시 `Auth._refresh` 싱글톤 (J12) → 토큰 갱신 후 자동 재시도
- 만료 시 `Auth.redirectLogin()` 자동 호출

**(D) Before / After**
```js
// Before — Wave 1 (J10) 적용 후 상태
async function loadMySafetyStatus() {
  try {
    const res = await fetch('/dashboard/api/safety-status/');
    if (!res.ok) return;
    const data = await res.json();
    ...
  } catch (e) {
    console.warn('[loadMySafetyStatus] fetch failed:', e);
  }
}

// After — Wave 4 적용 후
async function loadMySafetyStatus() {
  try {
    const res = await Auth.apiFetch('/dashboard/api/safety-status/');
    if (!res.ok) {
      console.warn('[loadMySafetyStatus] http error:', res.status);
      return;
    }
    const data = await res.json();
    ...
  } catch (e) {
    console.warn('[loadMySafetyStatus] fetch failed:', e);
  }
}
```

**(E) 다른 방법 trade-off**

| 옵션 | 장점 | 단점 | 채택 여부 |
|---|---|---|---|
| ✅ `Auth.apiFetch` 사용 | 인증·refresh·redirect 일관 / 백엔드 강화 시 자동 호환 | 변경 전과 응답 형식 동일 (회귀 위험 0) | **채택** |
| 직접 fetch 유지 | 변경 0 | 권고 미해결 / 백엔드 강화 시 깨짐 | 변경 전 |
| `Auth.apiFetch` + Sentry breadcrumb | 운영 가시성 | 인프라 추가 필요 | sprint |

---

### 05 R3. `caution/safe` ↔ `warning/normal` 변환층 단일화 ([level-mapper.js](../../../../drf-server/static/js/shared/level-mapper.js))

**(A) 변경 내용**
- 신규 `shared/level-mapper.js` (37줄) — `LevelMapper.toCssClass(level)` / `toLabel(level)` / `normalize(level)`
- `dashboard/websocket.js` 의 로컬 매핑 3개 제거: `_riskLabel`, `_riskClass`, `_RISK_LABEL`
- 호출처 4곳을 `LevelMapper.toCssClass()` / `LevelMapper.toLabel()` 로 교체 (전력 테이블 위험도 배지·row class·가스 KPI·가스 리스트 테이블)
- 2 템플릿(`dashboard/main.html`, `monitoring_realtime.html`) 에 `<script src="level-mapper.js">` 추가
- `LevelMapper.normalize()` 가 일부 경로에서 서버가 보내는 'safe' 표기를 'normal' 도메인 enum 으로 정규화 — 기존 `gas_monitoring.js::_normalizeRisk` 와 같은 보정 로직을 공통화

**(B) 왜 바뀌었나**
- 분석 근거: [05_page_init.md R3](../../js/2026_05_09/05_page_init.md) [상 · 중]
- 백엔드 enum 은 `danger`/`warning`/`normal` (RiskLevel), CSS 클래스는 `danger`/`caution`/`safe` — 두 표기 충돌
- 변환 로직이 `dashboard/websocket.js`, `monitoring_workers.js`, `gas_monitoring.js` 등에 분산
- 옵션 A (CSS 리네임)는 10+ CSS 파일 영향 → 옵션 B (매퍼 모듈) 채택

**(C) 적용된 기능**
- 도메인 enum 과 CSS 표기 사이 변환층 단일 진실 원천
- 서버가 일부 경로에서 CSS 표기 ('safe') 를 보내는 경우 정규화 — `LevelMapper.normalize('safe')` → `'normal'`
- 향후 새 호출자는 `LevelMapper` 만 사용 — 분산 매핑 추가 차단

**(D) Before / After**
```js
// Before — dashboard/websocket.js (로컬 매핑 3개)
const _riskLabel  = { normal: '정상', warning: '주의', danger: '위험' };
const _riskClass  = { normal: 'safe', warning: 'caution', danger: 'danger' };
const _RISK_LABEL = { danger: '위험', warning: '주의', normal: '정상', safe: '정상' };
...
`<span class="brisk ${_riskClass[eq.risk_level] || 'safe'}">${_riskLabel[eq.risk_level] || '-'}</span>`
` class="risk-row risk-${_riskClass[eq.risk_level] || 'safe'}"`
const riskCls = _riskClass[risk] || 'safe';
gasWorstRisk.textContent = _RISK_LABEL[worstRisk];
gasWorstRisk.className = worstRisk === 'normal' ? 'safe-text' : `${worstRisk}-text`;

// After — dashboard/websocket.js (모듈 위임)
// (로컬 매핑 3개 모두 삭제)
`<span class="brisk ${LevelMapper.toCssClass(eq.risk_level)}">${LevelMapper.toLabel(eq.risk_level)}</span>`
` class="risk-row risk-${LevelMapper.toCssClass(eq.risk_level)}"`
const riskCls = LevelMapper.toCssClass(risk);
gasWorstRisk.textContent = LevelMapper.toLabel(worstRisk);
gasWorstRisk.className = `${LevelMapper.toCssClass(worstRisk)}-text`;
```

```js
// shared/level-mapper.js (신규)
const LevelMapper = (function () {
  const TO_CSS   = { danger: 'danger', warning: 'caution', normal: 'safe' };
  const TO_LABEL = { danger: '위험',   warning: '주의',    normal: '정상' };
  const NORMALIZE = { safe: 'normal', caution: 'warning' };
  function _normalize(level) { if (!level) return 'normal'; return NORMALIZE[level] || level; }
  return {
    toCssClass(level) { return TO_CSS[_normalize(level)] || 'safe'; },
    toLabel(level)    { return TO_LABEL[_normalize(level)] || '-'; },
    normalize: _normalize,
  };
})();
```

**(E) 다른 방법 trade-off**

| 옵션 | 장점 | 단점 | 채택 여부 |
|---|---|---|---|
| ✅ B 매퍼 모듈 | cross-stack 변경 0 / 즉시 적용 | CSS 표기 잔존 → 매번 변환 비용 (미미) | **채택 (이번 작업)** |
| A CSS 클래스 리네임 (`caution`→`warning`) | 진실 원천 단일화 — 매퍼 불필요 | 10+ CSS 파일 + 마크업 + 다른 JS 동시 변경 | 미채택 (후속 sprint) |
| 백엔드 enum 을 `caution/safe` 로 변경 | 기존 CSS 그대로 | 백엔드 RiskLevel 의미 흐려짐 / DB 마이그·외부 영향 | 미채택 |

> **후속 sprint 계획**: 이번 매퍼는 변환층만 단일화. 옵션 A (CSS 일괄 리네임) 는 누락 없이 일괄 적용 가능한 시점에 별도 PR 로 진행. 진행 시 `monitoring_workers.js::_riskToCss` 등 다른 도메인의 분산 매핑도 `LevelMapper` 로 통합 가능.

---

## 3. 적용된 신규 기능 (요약)

### 3.1 `WSClient` 지수 백오프 (02 R1)

- 모듈 상수 `INITIAL_DELAY=1000` / `MAX_DELAY=30000` / `MAX_ATTEMPTS=20` / `JITTER=0.3`
- `_scheduleReconnect()` 내부 함수 — onclose / 생성 실패 시 호출
- 호출자 영향 0 (`opts.reconnectDelay` 사용 0건 — 안전 제거)

### 3.2 `AlarmMapper` 모듈 (03 R1·R3)

- 백엔드 `risk_level/source_label/summary` ↔ 클라이언트 `alarm_level/sensor_name/message` 변환
- `created_at` fallback 통합 — 서버 발신 시각 우선 (03 R3)
- 단위 테스트 가능한 순수 함수
- 노출: `window.AlarmMapper`

### 3.3 `LevelMapper` 모듈 (05 R3)

- `toCssClass`: 도메인 enum (`danger/warning/normal`) → CSS 클래스 (`danger/caution/safe`)
- `toLabel`: 도메인 enum → 한글 라벨 (`위험/주의/정상`)
- `normalize`: 서버가 보낸 CSS 표기('safe', 'caution') 를 도메인 enum 으로 정규화

### 3.4 `AlarmPopup` 큐 그룹핑 + drop count (03 R2)

- 같은 센서·동일 레벨 5초 내 연속 알람 → `groupCount` 누적, UI 에 `(×N)` 표시
- 큐 풀 시 `droppedCount` 콘솔 노출 — 운영 가시성

### 3.5 알람 페이로드 `created_at` (03 R3)

- DRF `_push_to_ws()` 가 자동 주입 (UTC ISO-8601)
- fastapi `AlarmPayload.created_at: str | None = None`
- 클라이언트 매퍼가 우선 사용, 누락 시 도착 시각 fallback

## 4. 검증

### 4.1 자동 테스트

| 대상 | 결과 | 비고 |
|---|---|---|
| drf-server pytest | **62/62 passed** | 회귀 0 |
| fastapi-server pytest | **22/22 passed** | 회귀 0 |
| Node 문법 검사 | **모든 신규/수정 JS OK** | ws-client / alarm-mapper / level-mapper / alarm-popup / alarm-ws / worker-ws / dashboard/websocket / dashboard/app / layout |

### 4.2 수동 검증 권고

브라우저에서:
1. 로그인 → 대시보드 진입 → WS 연결 정상 확인
2. 알람 강제 발생 (가스/전력 임계 초과) → 팝업 표시 + 메시지에 `(×N)` 그룹핑 확인 (같은 센서 5초 내 연속 발생 시)
3. WS 강제 종료 (서버 재시작) → 콘솔에서 백오프 간격이 1s → 2s → 4s → ... 증가하는지 확인
4. SNB 메뉴 렌더 정상 (DOM 검사로 `menu-label` 등이 텍스트로 들어갔는지 확인)
5. 콘솔에서 `loadMySafetyStatus` 가 `Authorization: Bearer ...` 헤더로 호출되는지 Network 탭 확인

## 5. 다음 단계

### 5.1 즉시 후속 (별도 PR)

- **02 R3 WS catch-up** — 서버 ring buffer 설계 (메모리 상한, 재시작 정책, last_event_id 위변조 방지, 다중 fastapi 인스턴스 sync). 운영 진입 후 disconnect 빈도/duration 데이터 보고 결정.

### 5.2 별도 sprint

- **05 R3 옵션 A** CSS 클래스 일괄 리네임 (`caution`→`warning`, `safe`→`normal`) — 10+ CSS 파일 + 마크업 + 다른 JS 분산 매핑(`monitoring_workers.js::_riskToCss` 등) 동시 정리
- **04 R2** `initHeaderAndSNB` getMe 실패 처리 — UX 정책 결정 후 적용
- **[중]/[하] 우선순위 ~33건** — 다음 sprint 정리 시 일괄 검토

### 5.3 운영 도구 연결 후보

- `AlarmPopup.droppedCount` 운영 도구 전송 (현재 console.warn 만)
- WS `max_reconnect_attempts` errorHandler 에 사용자 토스트 표시 ("연결 끊김 — 새로고침해 주세요")

## 6. 참고

- **TEAM_BRIEF**: 이번 작업의 팀 공유용 진입 문서 [TEAM_BRIEF.md](TEAM_BRIEF.md) §7 에 적용 현황 매트릭스 갱신 (Top 10 9/10 적용)
- **분석 베이스**: [docs/refactor/js/2026_05_09/](../../js/2026_05_09/) — 60건 권고 중 24건 (J 트랙 17 + Wave 4 의 7) 적용
