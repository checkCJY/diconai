# 06. 공통 유틸 (util.js · config.js)

## 1. 관련 파일 및 의존성

### 1.1 파일 목록
- [drf-server/static/js/shared/util.js](../../../drf-server/static/js/shared/util.js) — **52줄**, 4개 함수 + 2개 상수
- [drf-server/static/js/shared/config.js](../../../drf-server/static/js/shared/config.js) — **22줄**, AppConfig + 2개 헬퍼

### 1.2 호출자 인벤토리 (grep 결과)
- **`pad`** (가장 많이 사용 — 6+ 파일):
  - [shared/layout.js:119-120](../../../drf-server/static/js/shared/layout.js#L119-L120) (initClock)
  - [detail/gas_monitoring.js:355](../../../drf-server/static/js/detail/gas_monitoring.js#L355)
  - [detail/safety_checklist.js:4](../../../drf-server/static/js/detail/safety_checklist.js#L4)
  - [detail/safety_history.js:4](../../../drf-server/static/js/detail/safety_history.js#L4) — ❗ **로컬 재정의** (`function pad(n) { return String(n).padStart(2, '0'); }`)
  - [detail/safety_vr.js:6](../../../drf-server/static/js/detail/safety_vr.js#L6)
  - [detail/monitoring_workers.js:33-34](../../../drf-server/static/js/detail/monitoring_workers.js#L33-L34)
  - [detail/power_system.js:292](../../../drf-server/static/js/detail/power_system.js#L292)
- **`nowLabel`** (4 파일):
  - util.js:20 (자체 사용)
  - layout.js:119 (initClock 내부 인라인 — pad만 씀)
  - dashboard/websocket.js:317, 383 (차트 X축 라벨)
  - dashboard/charts.js (의존 주석)
- **`nowDateLabel`** (1 파일):
  - layout.js:129 (Header.updateLastUpdated)
- **`pushData`** (1 파일):
  - dashboard/charts.js (의존 주석) — **사용 위치 grep으로 더 확인 필요**
- **`MAX_POINTS`** (1 파일):
  - dashboard/charts.js (의존 주석)
- **`levelLabel`** ❗:
  - util.js:51 (정의)
  - **호출자 grep 결과 없음** — dead code 가능성 (검증 필요, 이전 리뷰 08 H1)
- **`AppConfig.apiUrl`**: auth.js, login.js, 모든 admin 페이지의 fetch URL
- **`AppConfig.wsUrl`**: ws-client.js만 (간접적으로 모든 WS 연결)

### 1.3 의존성 그래프
```
config.js (window.AppConfig 정의)
    │
    ▼ (window 글로벌)
auth.js, ws-client.js (apiUrl/wsUrl 사용)

util.js (pad, nowLabel, nowDateLabel, pushData, MAX_POINTS, levelLabel — 모두 글로벌 함수/상수)
    │
    ▼ (전역 식별자 직접 호출)
layout.js, dashboard/*, detail/*
```

> **주의**: util.js와 config.js는 **로드 순서 의존성**이 있음 — auth.js/ws-client.js/layout.js가 사용하므로 더 먼저 로드되어야 함. base.html에서 순서 보장 필수.

## 2. 기능 흐름

### 2.1 시각 라벨 생성 흐름
```
사용자 페이지 진입
    │
    ▼ Header.initClock() (layout.js)
    │   → 매 1초마다 tick():
    │       → pad(date.getMonth()+1), pad(...) 등 사용
    │       → "2026.05.09 14:30:00" 포맷 출력
    │
    ▼ dashboard/websocket.js의 차트 데이터 수신
    │   → ws.onMessage → nowLabel() 호출
    │   → "14:30:00" 라벨로 차트 X축에 push
    │   → pushData(chart, label, ...values) — 30개 포인트만 유지
```

### 2.2 API URL 해석
```
JS의 fetch('/api/...') 또는 Auth.apiFetch('/api/...')
    │
    ▼ AppConfig.apiUrl(path)
    ├─ 빈 path → API_BASE 반환
    ├─ 절대 URL (https://...) → path 그대로
    ├─ API_BASE 빈 문자열 → path 그대로 (same-origin)
    └─ API_BASE + path 조합 (trailing/leading slash 정규화)
```

### 2.3 WS URL 해석
```
WSClient.connect('/ws/sensors/')
    │
    ▼ AppConfig.wsUrl('/ws/sensors/')
    ├─ 빈 path → WS_BASE 반환
    ├─ 절대 URL (wss://) → path 그대로
    └─ WS_BASE + path 조합 → "ws://127.0.0.1:8001/ws/sensors/"
```

## 3. 함수 분석

### 3.1 [shared/util.js](../../../drf-server/static/js/shared/util.js) — 글로벌 함수/상수

#### `pad(n)` (util.js:15)
- **시그니처**: `(n: number) => string`
- **역할**: 숫자를 2자리 0-padded 문자열로 변환
- **단계별 동작**:
  1. `String(n).padStart(2, '0')` — 1줄짜리 화살표 함수
- **호출하는 함수**: `String#padStart`
- **호출자**: layout.js, detail/* 다수
- **올바름 검증**:
  - ✅ 매우 단순. `padStart`는 ES2017+ — 모든 모던 브라우저 지원.
  - ✅ `pad(9)` → `'09'`, `pad(10)` → `'10'`, `pad(100)` → `'100'` (3자리도 그대로 통과 — 자르지 않음).
  - ⚠️ **`pad(null)` → `'0null'`** — null/undefined 명시적 검증 없음. 호출자 책임. 정상 사용 케이스에선 영향 없음.
  - 💡 [detail/safety_history.js:4](../../../drf-server/static/js/detail/safety_history.js#L4)에서 **로컬 재정의** — util.js 로드 누락 또는 의존성 명확화 의도? **dead code 또는 중복** (R7).

#### `nowLabel()` (util.js:18-21)
- **시그니처**: `() => string`
- **역할**: 현재 시각을 `HH:MM:SS` 포맷으로 반환 (차트 X축용)
- **단계별 동작**:
  1. `const d = new Date();` (19)
  2. `return '${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}';` (20)
- **호출자**: dashboard/websocket.js (차트 데이터 push 시), dashboard/charts.js (의존 주석)
- **올바름 검증**:
  - ✅ 단순·정확.
  - 💡 매번 `new Date()` 호출 — 매우 빠른 작업, 영향 없음.
  - 💡 timezone은 브라우저 로컬 시각 — 의도 (차트 보는 사용자 시각).

#### `nowDateLabel()` (util.js:24-28)
- **시그니처**: `() => string`
- **역할**: 현재 날짜+시각을 `YYYY.MM.DD HH:MM:SS` 포맷으로 반환
- **단계별 동작**:
  1. `const d = new Date();`
  2. `return '${d.getFullYear()}.${pad(d.getMonth() + 1)}.${pad(d.getDate())} ${pad(...)}'`
- **호출자**: layout.js Header.updateLastUpdated (헤더 갱신 시각 라벨)
- **올바름 검증**:
  - ✅ 단순·정확.
  - ✅ `getMonth() + 1` — JS Date의 month는 0-based, 1을 더해야 정확.
  - 💡 두 함수(nowLabel, nowDateLabel)가 같은 패턴 반복 — `formatTime(date)`/`formatDateTime(date)`로 분리 + 인자 받기로 일반화 가능 (사소).

#### `pushData(chart, label, ...values)` (util.js:37-45)
- **시그니처**: `(chart: ChartJS, label: string, ...values: number[]) => void`
- **역할**: Chart.js 인스턴스에 데이터 포인트 추가, MAX_POINTS 초과 시 앞에서 제거 (rolling window)
- **단계별 동작**:
  1. `chart.data.labels.push(label);` (38)
  2. `values.forEach((v, i) => chart.data.datasets[i].data.push(v));` (39) — 각 dataset에 대응 값 push
  3. `if (chart.data.labels.length > MAX_POINTS)` (40):
     - `chart.data.labels.shift();` (41)
     - `chart.data.datasets.forEach(ds => ds.data.shift());` (42)
  4. `chart.update('none');` (44) — 애니메이션 없이 갱신
- **호출자**: dashboard/charts.js (또는 websocket.js), detail/websocket_*.js
- **올바름 검증**:
  - ✅ shift+push 패턴 — 시계열 차트에 일반적.
  - ✅ `chart.update('none')` — 애니메이션 비활성으로 1초 주기 부드러움.
  - ❌ **values.length가 datasets.length와 일치한다는 가정** — 안 맞으면 `chart.data.datasets[i]`가 undefined → `undefined.data` NPE. 호출자가 정확히 매칭해야 함 — 검증 부재.
  - ⚠️ **MAX_POINTS=30 매직넘버** — 30초 데이터만 표시. 사용자가 더 긴 트렌드를 보고 싶으면 모든 차트에 영향. 차트별로 별도 설정 어려움.
  - ⚠️ **Chart.js 의존성** — 라이브러리 변경 시 호출 인터페이스 깨짐. 추상화 부족.
  - 💡 `values.forEach((v, i) => ...)` 인덱스 매핑 — datasets 순서가 values 순서와 정확히 일치해야 함. 호출자가 잘못 전달하면 silent 데이터 swap.

#### `MAX_POINTS = 30` (util.js:48)
- **타입**: `const number`
- **역할**: 차트 보관 데이터 포인트 최대 수
- **올바름 검증**:
  - ✅ 모듈 상수 노출.
  - 💡 차트별 설정 부재 — 모든 차트가 같은 값 사용.

#### `levelLabel = { danger: '위험', caution: '주의', safe: '정상' }` (util.js:51)
- **타입**: `const object`
- **역할**: 위험도 한글 라벨 매핑
- **올바름 검증**:
  - ❌ **호출자 grep 결과 없음** — **dead code 가능성**. 검증: `grep -rn 'levelLabel' static/` → util.js 외 호출자 없음.
  - ❌ **백엔드 enum과 불일치**: 백엔드 `RiskLevel`은 `danger`/`warning`/`normal`인데 여기는 `caution`/`safe` 사용 (이전 리뷰 08 H1). **사용 중이라면 silent 깨짐**.
  - ⚠️ ui-exception.js의 `caution`/`safe` CSS 클래스명과는 일치 (05 R3 참조). CSS 디자인 토큰이 백엔드 enum과 다른 이름 사용 — 의도된 분리?
  - 💡 만약 사용 중이라면 `{danger:'위험', warning:'주의', normal:'정상'}`로 키 변경 필수.
  - 💡 만약 dead code면 제거.

### 3.2 [shared/config.js](../../../drf-server/static/js/shared/config.js) — `AppConfig` 헬퍼

#### `window.AppConfig = window.AppConfig || {...}` (config.js:6-9)
- **타입**: 객체 fallback
- **역할**: app_config.html에서 정의된 AppConfig가 있으면 사용, 없으면 기본값
- **단계별 동작**:
  1. `window.AppConfig` 존재? → 그대로
  2. 없으면 `{ API_BASE: "", WS_BASE: "ws://127.0.0.1:8001" }` 할당
- **호출자**: 자기 자신 즉시 (모듈 로드 시)
- **올바름 검증**:
  - ✅ **idempotent fallback** — 두 번 로드되어도 안전.
  - ✅ `API_BASE: ""` 빈 문자열 = same-origin 의도. apiUrl 헬퍼가 처리.
  - ⚠️ **WS_BASE 기본값 `ws://127.0.0.1:8001`** — 로컬 개발 가정. **운영 배포 시 app_config.html이 반드시 정의되어야 함**. 부재 시 운영에서도 localhost 시도 → 연결 실패. 명시적 가드 필요.
  - 💡 `let` 또는 `const`가 아닌 `window.` 직접 할당 — 글로벌 스코프 의도.

#### `window.AppConfig.apiUrl(path)` (config.js:11-16)
- **시그니처**: `(path: string) => string`
- **역할**: API URL 해석 — base + path 조합
- **단계별 동작**:
  1. `if (!path) return window.AppConfig.API_BASE;` (12) — 빈 path → base만 반환
  2. `if (/^https?:\/\//i.test(path)) return path;` (13) — 절대 URL은 그대로
  3. `if (!window.AppConfig.API_BASE) return path;` (14) — base 비었으면 path 그대로 (same-origin)
  4. `return window.AppConfig.API_BASE.replace(/\/$/, "") + (path.startsWith("/") ? path : "/" + path);` (15)
     - base의 trailing slash 제거
     - path가 / 시작이면 그대로, 아니면 / 추가
- **호출자**: Auth._resolveUrl, login.js fetch 호출
- **올바름 검증**:
  - ✅ 4가지 분기 명확.
  - ✅ trailing/leading slash 정규화 — `base="https://api"` + `path="/v1"` → `"https://api/v1"` 정확.
  - ✅ 정규식 `/^https?:\/\//i` — case-insensitive, http/https 모두.
  - ⚠️ **`path` 인자 검증 부재** — null/undefined 들어오면 `if (!path)` 분기로 base 반환 (의도 명확하지만 호출자가 인지해야).
  - ⚠️ **`wss://` 스킴은 인식 안 함** — wsUrl 책임. 의도된 분리.
  - 💡 `i.test(path)` — i는 case-insensitive flag. 정확.

#### `window.AppConfig.wsUrl(path)` (config.js:18-22)
- **시그니처**: `(path: string) => string`
- **역할**: WS URL 해석 — base + path 조합
- **단계별 동작**:
  1. `if (!path) return window.AppConfig.WS_BASE;` (19)
  2. `if (/^wss?:\/\//i.test(path)) return path;` (20) — ws://, wss:// 절대 URL
  3. `return window.AppConfig.WS_BASE.replace(/\/$/, "") + (path.startsWith("/") ? path : "/" + path);` (21)
- **호출자**: WSClient._resolveUrl
- **올바름 검증**:
  - ✅ apiUrl과 거의 동일 패턴 — 일관성.
  - ⚠️ **apiUrl의 step 3 (base 빈 문자열 → path 그대로)에 해당하는 분기 없음** — wsUrl은 base가 빈 문자열이면 마지막 step이 `"" + "/path"` = `"/path"` 반환. WS는 `"/path"`로 연결 시도 → 브라우저는 **현재 페이지 URL의 host를 사용해 ws://current.host/path** 시도. 즉 동작은 하지만 의도 불명확. apiUrl과 동일한 명시 분기 권장.
  - 💡 wsUrl의 fallback `ws://127.0.0.1:8001`이 운영에서 잘못 사용되면 모든 WS 연결 실패.

## 4. 종합 평가

### 강점
- ✅ **단순·명확한 헬퍼 함수** — pad, nowLabel, nowDateLabel.
- ✅ **AppConfig fallback 패턴** — app_config.html 부재 시도 일부 동작.
- ✅ **idempotent (window.AppConfig = window.AppConfig || ...)**.
- ✅ **apiUrl/wsUrl의 4가지 분기** — 다양한 입력 처리.
- ✅ **trailing/leading slash 정규화**.

### 약점
- ❌ **`levelLabel`이 dead code 또는 contract 깨짐** — 검증 + 결정 필요.
- ❌ **`pushData`의 dataset/values 길이 검증 부재** — silent NPE 위험.
- ❌ **safety_history.js의 pad 로컬 재정의** — util.js 로드 보장이 안 되거나, 의도적인 의존 격리.
- ⚠️ **MAX_POINTS 차트별 설정 부재**.
- ⚠️ **WS_BASE 운영 fallback 위험** — app_config.html 부재 시 localhost 시도.

### 중복 / 누락
- 📌 `nowLabel`/`nowDateLabel`이 layout.js의 initClock 내에서 직접 인라인 (pad만 사용). 두 함수의 활용도 낮음.
- 📌 safety_history.js가 pad 로컬 재정의 — util.js 의존성 누락 또는 모듈화 부재 영향.
- 📌 운영용 환경별 AppConfig 분기 부재 — dev/staging/prod에 따른 base URL이 app_config.html에서만 결정.

### contract 정합성
- ⚠️ `levelLabel` 백엔드 enum 불일치.
- ✅ apiUrl/wsUrl은 backend Django settings의 ALLOWED_HOSTS·CSRF_TRUSTED_ORIGINS과 호환.

## 5. 리팩토링 권고

### R1. `levelLabel` 정합성 결정 [상 · 소]
- **왜 필요?**: 현재 dead code 가능 + 사용 시 백엔드 enum과 불일치. 두 옵션 — 제거 or 정합.
- **장점**: 진실 원천 단일화 또는 dead code 제거.
- **단점**: 옵션 결정 필요.
- **변경 위치**: [util.js:51](../../../drf-server/static/js/shared/util.js#L51)
- **변경 예시**:
  ```js
  // 옵션 A: dead code 제거 (grep 결과 호출자 없음 확인 후)
  // const levelLabel = { ... }; ← 삭제

  // 옵션 B: 백엔드 정합 (사용 중이라면)
  const LEVEL_LABEL = Object.freeze({
    danger: '위험',
    warning: '주의',  // 'caution' → 'warning'
    normal: '정상',   // 'safe' → 'normal'
  });
  ```
- **사전 작업**: `grep -rn 'levelLabel' static/ templates/` 전체 검색. 호출자 발견 시 옵션 B + 호출자 패치. 미발견 시 옵션 A.

### R2. `pushData`의 dataset/values 길이 검증 [상 · 소]
- **왜 필요?**: values.length > datasets.length 시 silent NPE. Chart.js 라이브러리 변경 시 디버깅 어려움.
- **장점**: 명확한 에러 / 빠른 디버깅.
- **단점**: 정상 케이스에 검사 비용 (미미).
- **변경 위치**: [util.js:37-45](../../../drf-server/static/js/shared/util.js#L37-L45)
- **변경 예시**:
  ```js
  // before
  function pushData(chart, label, ...values) {
    chart.data.labels.push(label);
    values.forEach((v, i) => chart.data.datasets[i].data.push(v));
    ...
  }

  // after
  function pushData(chart, label, ...values) {
    if (!chart || !chart.data) return;
    if (values.length > chart.data.datasets.length) {
      console.warn('[pushData] values.length > datasets.length',
                   { values: values.length, datasets: chart.data.datasets.length });
    }
    chart.data.labels.push(label);
    values.forEach((v, i) => {
      const ds = chart.data.datasets[i];
      if (ds) ds.data.push(v);
    });
    if (chart.data.labels.length > MAX_POINTS) {
      chart.data.labels.shift();
      chart.data.datasets.forEach(ds => ds.data.shift());
    }
    chart.update('none');
  }
  ```

### R3. WS_BASE 운영 가드 [상 · 소]
- **왜 필요?**: app_config.html 미정의 시 localhost 시도 → 운영에서 모든 WS 연결 실패. 발견 늦음.
- **장점**: 운영 사고 즉시 감지.
- **단점**: 없음.
- **변경 위치**: [config.js:6-9](../../../drf-server/static/js/shared/config.js#L6-L9)
- **변경 예시**:
  ```js
  // before
  window.AppConfig = window.AppConfig || {
    API_BASE: "",
    WS_BASE:  "ws://127.0.0.1:8001"
  };

  // after
  if (!window.AppConfig) {
    console.warn('[AppConfig] not defined by template, using localhost fallback (dev only)');
    window.AppConfig = {
      API_BASE: "",
      WS_BASE:  "ws://127.0.0.1:8001",
    };
  }
  // 또는 운영 환경 가드:
  if (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1' &&
      window.AppConfig.WS_BASE.includes('127.0.0.1')) {
    console.error('[AppConfig] WS_BASE points to localhost in production!');
  }
  ```

### R4. wsUrl base 빈 문자열 분기 [중 · 소]
- **왜 필요?**: apiUrl과 동일한 fallback 분기 부재. base="" + path="/ws/.." 결과 의도 불명확.
- **장점**: apiUrl과 일관 / 의도 명시.
- **단점**: 없음.
- **변경 위치**: [config.js:18-22](../../../drf-server/static/js/shared/config.js#L18-L22)
- **변경 예시**:
  ```js
  // before
  window.AppConfig.wsUrl = function (path) {
    if (!path) return window.AppConfig.WS_BASE;
    if (/^wss?:\/\//i.test(path)) return path;
    return window.AppConfig.WS_BASE.replace(/\/$/, "") + (path.startsWith("/") ? path : "/" + path);
  };

  // after
  window.AppConfig.wsUrl = function (path) {
    if (!path) return window.AppConfig.WS_BASE;
    if (/^wss?:\/\//i.test(path)) return path;
    if (!window.AppConfig.WS_BASE) {
      // base 미정 — 현재 페이지 host 사용 (브라우저가 자동 처리)
      // ws/wss는 명시 필요 — 'ws://' + location.host + path
      const proto = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
      return proto + window.location.host + (path.startsWith("/") ? path : "/" + path);
    }
    return window.AppConfig.WS_BASE.replace(/\/$/, "") + (path.startsWith("/") ? path : "/" + path);
  };
  ```

### R5. safety_history.js의 pad 로컬 재정의 제거 [중 · 소]
- **왜 필요?**: util.js의 pad 글로벌이 있는데 로컬 재정의 → util.js 로드 보장이 의문. 또는 모듈화 의도 — 어느 쪽인지 명시 부족.
- **장점**: 단일 출처 / 코드 정리.
- **단점**: util.js 로드 보장 필수.
- **변경 위치**: [detail/safety_history.js:4](../../../drf-server/static/js/detail/safety_history.js#L4)
- **변경 예시**:
  ```js
  // before (safety_history.js)
  function pad(n) { return String(n).padStart(2, '0'); }

  // after — 제거. util.js의 pad 사용.
  // (단, base.html 또는 페이지 템플릿에서 util.js가 safety_history.js보다 먼저 로드되는지 확인)
  ```

### R6. MAX_POINTS 차트별 설정 [중 · 소]
- **왜 필요?**: 모든 차트가 30개 강제. 트렌드 길게 보고 싶은 차트는 어쩔 수 없이 직접 shift 구현.
- **장점**: 차트별 유연성.
- **단점**: pushData 시그니처 변경 (호출자 영향).
- **변경 위치**: [util.js:37-45](../../../drf-server/static/js/shared/util.js#L37-L45)
- **변경 예시**:
  ```js
  function pushData(chart, label, ...values) {
    const maxPoints = chart._maxPoints || MAX_POINTS;
    chart.data.labels.push(label);
    values.forEach((v, i) => {
      const ds = chart.data.datasets[i];
      if (ds) ds.data.push(v);
    });
    if (chart.data.labels.length > maxPoints) {
      chart.data.labels.shift();
      chart.data.datasets.forEach(ds => ds.data.shift());
    }
    chart.update('none');
  }

  // 호출자 (dashboard/charts.js 등):
  // chart._maxPoints = 60;  // 차트 객체에 attribute로 부착
  ```

### R7. nowLabel/nowDateLabel 일반화 [하 · 소]
- **왜 필요?**: 두 함수가 같은 패턴. 다른 포맷 필요 시 또 추가.
- **장점**: 재사용 / 일관성.
- **단점**: 호출자 변경 (단순).
- **변경 위치**: [util.js:18-28](../../../drf-server/static/js/shared/util.js#L18-L28)
- **변경 예시**:
  ```js
  // before
  function nowLabel() {
    const d = new Date();
    return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  }
  function nowDateLabel() {
    const d = new Date();
    return `${d.getFullYear()}.${pad(d.getMonth() + 1)}.${pad(d.getDate())} ` +
           `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  }

  // after
  function formatTime(d = new Date()) {
    return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  }
  function formatDate(d = new Date()) {
    return `${d.getFullYear()}.${pad(d.getMonth() + 1)}.${pad(d.getDate())}`;
  }
  function formatDateTime(d = new Date()) {
    return formatDate(d) + ' ' + formatTime(d);
  }
  // 기존 호출 호환을 위해 alias 유지:
  const nowLabel = () => formatTime();
  const nowDateLabel = () => formatDateTime();
  ```

### R8. AppConfig 환경별 분기 명시 [하 · 중]
- **왜 필요?**: 현재 app_config.html이 단일 진실 원천 — 빌드/배포에 따른 분기 부재.
- **장점**: 환경별 자동 분기 / 운영 사고 차단.
- **단점**: Django settings + template 변경. 큰 작업.
- **변경 위치**: app_config.html (Django template)
- **변경 예시**:
  ```html
  <!-- components/app_config.html -->
  <script>
    window.AppConfig = {
      API_BASE: "{{ APP_CONFIG.API_BASE|default:'' }}",
      WS_BASE: "{{ APP_CONFIG.WS_BASE|default:'ws://127.0.0.1:8001' }}",
      ENV: "{{ APP_CONFIG.ENV|default:'dev' }}",  // 환경 식별자
      passwordPolicy: {{ APP_CONFIG.PASSWORD_POLICY|safe|default:'{}' }},  // R4 in 01
    };
  </script>
  ```
  ```py
  # settings.py
  APP_CONFIG = {
      'API_BASE': env('APP_API_BASE', default=''),
      'WS_BASE': env('APP_WS_BASE', default='ws://127.0.0.1:8001'),
      'ENV': env('DJANGO_ENV', default='dev'),
      'PASSWORD_POLICY': json.dumps({...}),
  }
  ```

### R9. 모듈 패턴 (util.js / config.js를 객체화) [하 · 대]
- **왜 필요?**: 글로벌 함수 다수 — 네임스페이스 오염 + 충돌 위험.
- **장점**: 단일 진입 / 충돌 차단.
- **단점**: 호출자 모두 변경 (대규모 마이그레이션).
- **변경 위치**: 전 시스템.
- **변경 예시**:
  ```js
  // shared/util.js after
  const Util = {
    pad(n) { return String(n).padStart(2, '0'); },
    nowLabel() { ... },
    nowDateLabel() { ... },
    pushData(chart, label, ...values) { ... },
    MAX_POINTS: 30,
  };

  // 호출자: Util.pad(...), Util.nowLabel() 등
  ```
  ※ 현재 사용 빈도(50+)를 고려하면 마이그레이션 비용 큼. ES Modules 도입 시점에 함께.

### R10. AppConfig.apiUrl/wsUrl 단위 테스트 [하 · 소]
- **왜 필요?**: 4가지 분기를 가진 헬퍼 — 회귀 위험.
- **변경 위치**: 신규 [tests/js/config.test.js](../../../drf-server/static/js/tests/) (테스트 인프라 부재 시 jest 등 도입).
- **변경 예시**:
  ```js
  // 테스트 케이스
  test('apiUrl with empty base returns path as-is', () => {
    window.AppConfig.API_BASE = '';
    expect(window.AppConfig.apiUrl('/api/auth')).toBe('/api/auth');
  });
  test('apiUrl with absolute URL returns as-is', () => {
    expect(window.AppConfig.apiUrl('https://x.com/api')).toBe('https://x.com/api');
  });
  // ...
  ```

## 6. 단계별 적용 순서

### 1단계 — 즉시 (1일) ⚡
- **R1** levelLabel 결정 — grep 후 옵션 A(제거) 또는 B(정합).
- **R2** pushData 검증 — 1줄 추가.
- **R3** WS_BASE 운영 가드 — console.warn/error 추가.
- **R5** safety_history.js pad 재정의 제거.
- **이유**: 모두 작은 변경. 보안·정합성 즉시 향상.

### 2단계 — 1주 내 🔧
- **R4** wsUrl base 빈 문자열 분기 — apiUrl과 일관.
- **R6** MAX_POINTS 차트별 설정 — 트렌드 차트 유연성.
- **이유**: 코드 일관성 + 미래 확장 대비.

### 3단계 — 다음 sprint 🏗
- **R7** nowLabel/nowDateLabel 일반화 — 호출자 알리아스 호환.
- **R8** AppConfig 환경별 분기 — 백엔드 협업 (Django settings).
- **이유**: 운영 안정성.

### 4단계 — 여유 시
- **R9** 모듈 패턴 — 대규모 마이그레이션, ES Modules 도입과 함께.
- **R10** 단위 테스트 — JS 테스트 인프라 도입 시점.

### ⚠️ 주의사항 (초보자용)

- **R1 levelLabel 제거 전 grep 필수**: `grep -rn 'levelLabel' /home/cjy/diconai/drf-server/static/ /home/cjy/diconai/drf-server/templates/`. 호출자 발견 시 옵션 B (정합) 진행.
- **R3 WS_BASE 가드는 운영 모니터링과 연동**: console.error는 운영자에게 안 보임. Sentry 등 도입 시 의미 있음. 단기엔 배포 점검 자동화.
- **R5 safety_history.js pad 제거 전 로드 순서 확인**: 페이지 템플릿(snb_details/safety_history.html)에서 util.js가 safety_history.js보다 먼저 로드되는지 검증. 안 그러면 ReferenceError.
- **R7 nowLabel/nowDateLabel 일반화 시 alias 유지**: 호출자 50+ 곳 한꺼번에 변경 위험. 새 함수 추가 + 기존 함수를 alias로 유지 → 점진 마이그레이션.
- **R8 AppConfig 환경 분기는 백엔드 협업 필수**: Django settings.APP_CONFIG 변경 + template 수정 + JS 호환성. 한 PR에 묶어 처리.
- **모든 변경 후 페이지 진입 검증**: util.js 변경은 거의 모든 페이지에 영향. 대시보드·서브페이지·어드민 페이지 각각 진입해 콘솔 에러 확인.
