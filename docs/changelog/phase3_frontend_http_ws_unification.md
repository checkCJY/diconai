# 변경 기록서 — Phase3 프론트 HTTP·WebSocket 통일

> 작성일: 2026-05-04
> 브랜치: feature/project_4_refactoring
> 작업 종류: refactor + cleanup
> 하위 호환성: **non-breaking** — 동일 엔드포인트/응답 그대로. 내부 호출 경로만 통일. 단 리팩토링 범위가 넓어 회귀 검증 필수.

---

## 1. 변경 개요

- **목적(Why):** 코드 분석에서 식별된 3가지 HTTP 호출 패턴(`Auth.apiFetch` / 직접 `fetch+Authorization` / `localStorage.getItem('access_token')` 직접 접근)이 14+ 곳에 흩어져 있어 한쪽 수정이 다른 쪽에 적용되지 않는 문제 + WS URL 7곳 하드코딩으로 운영 환경 전환 불가 + 동일 `/ws/sensors/` 엔드포인트에 alarm-ws / dashboard / detail JS가 별개 연결을 만들어 중복 트래픽 발생.
- **결과(What):** 모든 인증 HTTP 호출을 `Auth.apiFetch` 단일 진입점으로 통일(401→자동 refresh→재시도 일원화). WebSocket 호출을 신규 `shared/ws-client.js`로 통일하여 동일 path 캐시 + 자동 재연결 + 라이프사이클 콜백 다중 구독 제공. WS·API URL은 모두 Phase 1의 `window.AppConfig`를 경유 → `.env` 변경만으로 운영 호스트 전환 가능. localStorage 직접 접근(`access_token`/`role`) 5곳을 `Auth` 모듈 헬퍼로 일원화.
- **영향 범위(Where):** drf-server 프론트엔드 정적 자산만(`static/js/`, `templates/`). 백엔드·fastapi 영향 없음. 응답·요청 스키마 변경 없음.

## 2. Before / After 비교

| 구분 | Before | After |
|---|---|---|
| HTTP 호출 패턴 | `Auth.apiFetch` / 수동 `fetch+Authorization` / `localStorage.getItem('access_token')` 직접 — 3가지 혼재 | **모두 `Auth.apiFetch` 단일 진입점** |
| WS URL | `ws://127.0.0.1:8001/...` 7곳 하드코딩 | **`WSClient.connect('/ws/...')` → `AppConfig.WS_BASE` 자동 prefix** |
| WS 동일 엔드포인트 | alarm-ws + dashboard/websocket + detail/* 가 각자 새 `WebSocket()` 생성 → 다중 연결 | **WSClient 인스턴스 캐시로 같은 path는 1개만** |
| 401 토큰 만료 처리 | `Auth.apiFetch` 호출처만 자동 refresh, 나머지는 수동 | **모든 인증 호출이 자동 refresh + 재시도 + 실패 시 로그인 리다이렉트** |
| 토큰 헤더 부착 | `_authHeaders()` 헬퍼(3곳) / `'Authorization': \`Bearer ${token}\`` 인라인(7곳) / `localStorage.getItem('access_token')` 직접(2곳) | **`Auth.apiFetch` 내부에서 자동 부착** |
| localStorage 직접 접근 | 5개 파일 | **`Auth.setRole/getRole/setTokens/clear` 경유** |
| WS 재연결 | 각 파일이 `setTimeout(connect, 3000)` 자체 구현 | **WSClient가 내부 자동(3초)** |

### 코드 차이 예시

```js
// Before (admin/facility/facility.js)
function _authHeaders() {
  const token = Auth.getAccessToken();
  return { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` };
}
const res = await fetch(`/api/equipments/?${qs}`, { headers: _authHeaders() });
const res = await fetch(url, { method, headers: _authHeaders(), body: JSON.stringify(payload) });

// After
const res = await Auth.apiFetch(`/api/equipments/?${qs}`);
const res = await Auth.apiFetch(url, { method, body: JSON.stringify(payload) });
```

```js
// Before (dashboard/websocket.js)
ws = new WebSocket('ws://127.0.0.1:8001/ws/sensors/');
ws.onopen   = () => setWsStatus('● 실시간 연결', 'connected');
ws.onmessage = (e) => { const data = JSON.parse(e.data); ... };
ws.onclose = () => setTimeout(connect, 3000);

// After
const ws = WSClient.connect('/ws/sensors/');
ws.onOpen(() => setWsStatus('● 실시간 연결', 'connected'));
ws.onMessage((data) => { ... });
ws.onClose(() => setWsStatus('● 연결 끊김', 'error'));
// 재연결은 WSClient가 자동
```

## 3. 변경 파일 목록

### 신규
| 파일 | 역할 |
|---|---|
| `drf-server/static/js/shared/ws-client.js` | WebSocket 단일 래퍼. `AppConfig.WS_BASE` 자동 prefix + URL 단위 인스턴스 캐시 + 자동 재연결 + onMessage/onOpen/onClose/onError 다중 구독 |

### 수정 (총 18개 파일)

#### shared 인프라 (3개)
| 파일 | 변경 요약 |
|---|---|
| `static/js/shared/auth.js` | `setTokens`/`setRole` 헬퍼 추가, `_resolveUrl`로 `AppConfig.apiUrl` 자동 통합, refresh 엔드포인트도 `AppConfig` 경유 |
| `static/js/shared/alarm-ws.js` | `WebSocket()` 직접 호출 → `WSClient.connect('/ws/sensors/')` |
| `static/js/shared/worker-ws.js` | 동상. `/ws/worker/{userId}/` 사용 |

#### Dashboard / Detail (5개)
| 파일 | 변경 요약 |
|---|---|
| `static/js/dashboard/websocket.js` | `ws://127.0.0.1:8001` 2곳 하드코딩 → `WSClient.connect('/ws/sensors/')`, `WSClient.connect('/ws/positions/')`. status UI 갱신 로직은 `onOpen/onError/onClose`로 분리 |
| `static/js/dashboard/panels/map-panel.js` | 3곳의 수동 `fetch+Authorization` → `Auth.apiFetch` |
| `static/js/dashboard/panels/worker-panel.js` | `localStorage.getItem('role')` → `Auth.getRole()` |
| `static/js/detail/websocket_gas.js` | `WebSocket(GAS_WS_URL)` → `WSClient.connect('/ws/sensors/')`. `_startCountdown` 로직 제거(WSClient 자동 재연결로 대체), `_handleError`는 UI 갱신만 |
| `static/js/detail/websocket_power.js` | 동상. `WebSocket(WS_URL)` → `WSClient.connect('/ws/sensors/')` |
| `static/js/detail/monitoring_workers.js` | `WebSocket(WS_SENSORS)` + 자체 setTimeout 재연결 → `WSClient.connect('/ws/sensors/')` |
| `static/js/detail/safety_vr.js` | 3곳 수동 `fetch+Authorization` → `Auth.apiFetch` (keepalive 옵션 그대로 통과) |

#### Admin 패널 (8개)
| 파일 | 변경 요약 |
|---|---|
| `static/js/admin/main.js` | `localStorage.setItem('role', ...)` 2곳 → `Auth.setRole(...)` |
| `static/js/admin/accounts/accounts.js` | `localStorage.getItem('access_token')` + 수동 `Bearer` 7곳 → `Auth.apiFetch`. 토큰 임시변수(`const token = Auth.getAccessToken()`) 4곳 제거 |
| `static/js/admin/facility/facility.js` | `_authHeaders()` 헬퍼 제거. `fetch`+`_authHeaders` 7곳 → `Auth.apiFetch` |
| `static/js/admin/gas_sensor/gas_sensor.js` | 동상 — `_authHeaders()` 제거 + 7곳 마이그레이션 |
| `static/js/admin/power_system/power_system.js` | 동상 — `_authHeaders()` 제거 + 6곳 마이그레이션 |
| `static/js/admin/geofence/geofence.js` | 수동 `Bearer` 5곳 → `Auth.apiFetch` |
| `static/js/admin/map_editor/map_editor.js` | 수동 `Bearer` 2곳 → `Auth.apiFetch` |
| `static/js/admin/organizations/organizations.js` | `_api()` 헬퍼 내부 `localStorage.getItem('access_token')` + `Bearer` → `Auth.apiFetch` |

#### Auth 페이지 (1개)
| 파일 | 변경 요약 |
|---|---|
| `static/js/auth/login.js` | 페이지 로드 시 토큰 존재 검증을 `Auth.apiFetch('/api/auth/me/')` 사용. 로그인 성공 시 `localStorage.setItem` 4번 → `Auth.setTokens(...)`. 로그인 API URL은 `AppConfig.apiUrl` 경유 |

#### Layout / Templates (12개)
| 파일 | 변경 요약 |
|---|---|
| `static/js/shared/layout.js` | `localStorage.setItem('role', user.role)` → `Auth.setRole(user.role)` |
| `templates/admin_panel/base.html`, `dashboard/main.html`, `auth/login.html`, `snb_details/*.html` (10개) | `auth.js` 직후 `<script src="ws-client.js">` 추가 (auth/login.html은 별도로 `auth.js`도 추가됨 — 기존엔 누락되어 있어 `Auth` 사용 불가능했음) |

### 삭제
해당 없음.

## 4. API / 응답 / 인터페이스 변경
**런타임 API 변경 없음.** 백엔드 호출하는 URL/메서드/페이로드/응답 모두 그대로. 프론트 내부 호출 경로만 통일.

## 5. 환경변수·설정 변경
해당 없음 (Phase 1에서 이미 정의된 `FRONTEND_API_BASE_URL`, `FRONTEND_WS_BASE_URL`을 본 Phase에서 *실제로 사용*하기 시작).

## 6. 마이그레이션 가이드

```bash
# 1. 풀 받기
git pull

# 2. 정적 파일은 자동 반영 (collectstatic 불필요, 개발 환경)
#    운영: python manage.py collectstatic --noinput

# 3. DB·의존성 변경 없음

# 4. 서버 재시작
cd drf-server && python manage.py runserver
cd ../fastapi-server && uvicorn app:app --reload --port 8001

# 5. 브라우저 강제 새로고침 (Ctrl+Shift+R) — JS 캐시 무효화 권장
```

## 7. 결정 근거 (ADR)

| 결정 | 채택안 | 검토했던 대안 | 근거 |
|---|---|---|---|
| 단일 HTTP 진입점 | **`Auth.apiFetch` 강화** | 별도 `api_client.js` 신설 | Plan agent 권장: 새 모듈 추가 X, 기존 잘 동작하는 `Auth.apiFetch`(401 refresh 보유)를 정식 진입점으로 정착. 모듈 수 최소화. |
| WS 통일 방식 | **`WSClient` 신규 모듈** | dashboard/websocket.js에 직접 통합 | dashboard 외에도 alarm-ws/worker-ws/detail의 3개 WS가 같은 엔드포인트를 별개로 연결하던 문제. 인스턴스 캐시(URL 단위)로 자연스럽게 중복 제거. |
| WSClient 라이프사이클 콜백 | **onMessage/onOpen/onClose/onError 다중 구독** | onMessage만 노출, status UI는 호출자가 직접 polling | dashboard/websocket.js가 status 배지를 ws lifecycle에 강하게 결합 → onOpen/onClose 노출 필수. Set 기반 다중 구독은 alarm-ws + dashboard 두 모듈이 같은 ws에 핸들러 붙일 때 필요. |
| 자체 재연결 로직 | **WSClient가 내부 자동(3초)** | 호출자가 setTimeout(connect, 3000) | 모든 호출자가 동일 패턴 반복 → DRY. websocket_gas의 `_startCountdown` UX(3,2,1 카운트다운)는 손해지만 "재연결 시도 중..." 텍스트로 충분. |
| keepalive 옵션 처리 | **그대로 통과** | keepalive=true면 Auth.apiFetch 우회 | `Auth.apiFetch` 내부 `{ ...opts, headers }` 스프레드로 keepalive 옵션 자동 통과. unload 시점 401 refresh는 의미 없지만 무해 — 코드 단순성 우선. |
| dashboard/websocket.js의 onmessage 본문 150줄 | **그대로 유지** | 별도 함수로 추출 | Phase 3 범위는 호출 경로 통일. 로직 분해는 별도 작업이 더 안전. Surgical Changes. |
| JS 모듈 패턴 통일(IIFE↔Object) | **본 Phase 범위 제외** | 함께 진행 | 회귀 위험 큰 별개 작업. 마스터 플랜에서도 "단계적: 한 PR당 2-3개 파일"로 권장. 추후 별도 Phase 또는 작은 PR로 분리 추천. |
| CSS 중복 정리 | **본 Phase 범위 제외** | dashboard.css ↔ dashboard_CJY.css 통합 | 시각적 회귀 위험 큼. 별도 작업으로 분리. |

## 8. 검증 방법 / 결과

### 자동 검증 (실행 완료)

```bash
cd drf-server && source .venv/bin/activate

# (1) Django check
python manage.py check
# 결과: ✅ System check identified no issues (0 silenced).

# (2) 하드코딩된 WS URL 잔존
grep -rn "ws://127.0.0.1\|http://localhost:8001\|http://127.0.0.1:8001" static/js/ --include="*.js"
# 결과: ✅ shared/config.js의 WS_BASE fallback 1건만 (의도)

# (3) 수동 Authorization 헤더
grep -rn "Authorization.*Bearer" static/js/ --include="*.js" | grep -v shared/auth.js
# 결과: ✅ 0건

# (4) localStorage 직접 접근
grep -rn "localStorage\.\(getItem\|setItem\|removeItem\)" static/js/ --include="*.js" \
  | grep -v shared/auth.js
# 결과: ✅ 0건

# (5) _authHeaders 잔존
grep -rn "_authHeaders" static/js/ --include="*.js"
# 결과: ✅ 0건

# (6) Auth.getAccessToken 직접 사용
grep -rn "Auth\.getAccessToken" static/js/ --include="*.js" \
  | grep -v shared/auth.js | grep -v shared/ws-client.js
# 결과: ✅ 2건 (layout.js, login.js — 모두 토큰 *존재 여부* 확인용으로 정당)
```

### 검증 미완 (브라우저 실측 필요)

- [ ] **JWT 만료 시 자동 refresh** — 짧은 lifetime(예: 1분) JWT 발급 후 admin CRUD 진행 → 만료 시점에 `Auth.apiFetch`가 자동 refresh로 작업 연속성 유지하는지 확인
- [ ] **WS 중복 연결 제거** — DevTools Network → WS 탭에서 `/ws/sensors/` 연결이 1개만 있는지 (이전: 2-3개)
- [ ] **WS_BASE 환경변수 갱신** — `.env` `FRONTEND_WS_BASE_URL`을 다른 호스트로 변경 → 재시작 후 새 호스트로 WS 연결되는지
- [ ] **모든 admin 페이지 회귀** — 8개 admin 화면(accounts, facility, gas_sensor, power_system, geofence, map_editor, organizations, gas/power data) CRUD 정상 동작
- [ ] **dashboard 회귀** — 메인 대시보드 가스/전력/위치 실시간 갱신, 알람 팝업, 지도 패널 정상
- [ ] **detail 페이지 회귀** — `/dashboard/monitoring/{realtime,gas,power,workers,events}/` 5개 페이지 정상
- [ ] **safety VR** — `/dashboard/safety/vr/` 진행률 저장/복원 정상
- [ ] **로그인 → 토큰 만료 → 자동 로그인 페이지 리다이렉트** 시나리오

## 9. 하위 호환성 / 롤백

### 하위 호환
- **non-breaking.** 백엔드 API 호출(URL/메서드/페이로드/응답)은 그대로 유지.
- 프론트 내부 호출 경로만 통일된 것이라 사용자가 체감하는 동작은 동일 (기능 회귀가 없는 한).

### 위험 요소
- **회귀 가능성 큼** — 18개 파일 수정. 모든 admin·dashboard·detail 화면을 한 번씩 클릭해 봐야 안전.
- WSClient의 자동 재연결과 호출자의 reconnect 로직이 충돌하면 한 번에 2번 재연결 시도할 수 있음 — 본 PR에서 모든 호출자의 자체 setTimeout 재연결을 제거했지만 누락 가능성 검증 필요.

### 롤백
- `git revert <SHA>`로 충분.
- 의존성·DB 변경 없음.
- 단, Phase 1의 `AppConfig` 메커니즘은 그대로 유지 (Phase 1 PR과 분리 가능).

## 10. 후속 작업 / 참고

### 본 Phase에서 의도적으로 미룬 것
- **JS 모듈 패턴 통일** — accounts/geofence/organizations는 Object 패턴, gas_sensor/facility/monitoring_workers는 함수형+전역변수 — 별개 작업으로 분리.
- **CSS 중복 정리** — `dashboard.css` ↔ `dashboard_CJY.css` 통합, 모달/폼/버튼 컴포넌트화 — 시각적 회귀 위험으로 분리.
- **dashboard/websocket.js의 onmessage 핸들러 분해** — 150줄 단일 함수의 책임 분리는 별개 Phase에서.
- **WSClient에 하트비트(ping/pong) 추가** — 현재는 `WebSocket.onclose`만으로 재연결 트리거. 네트워크 단절 즉시 감지가 필요하면 별도 추가.

### 관련 문서
- 응답 봉투 표준: `docs/api_response_convention.md`
- Phase 1 변경 기록: `docs/changelog/phase1_config_centralization.md`
- Phase 2 변경 기록: `docs/changelog/phase2_admin_security_pagination.md`
- 마스터 검증 체크리스트: `docs/changelog/00_pr_verification_checklist.md`
- 변경기록 프롬프트: `skill/system_instruction_changelog.md`
