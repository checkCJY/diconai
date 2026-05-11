# 08. 어드민 패널 공통 자산 (Shared JS · Templates · Layout)

## 1. 범위

이 도메인은 01~07에서 다루지 않은 **공통 자산**을 횡단으로 리뷰. 어드민 패널의 페이지 셸·헤더·SNB·공유 JS·CSS·아이콘·유틸이 대상.

### 1.1 페이지 셸 (TemplateView 기반)
어드민 패널 진입점 — 도메인별 페이지의 HTML 셸 + JS bootstrap.
- [drf-server/templates/admin_panel/base.html](../../../drf-server/templates/admin_panel/base.html) — 어드민 공통 베이스
- [drf-server/templates/components/header.html](../../../drf-server/templates/components/header.html)
- [drf-server/templates/components/admin_sidebar.html](../../../drf-server/templates/components/admin_sidebar.html)
- [drf-server/templates/components/app_config.html](../../../drf-server/templates/components/app_config.html) — `window.AppConfig` 주입

### 1.2 공유 JS (총 9개 파일, [drf-server/static/js/shared/](../../../drf-server/static/js/shared/))
| 파일 | 역할 | 줄 수 (대략) |
|---|---|---|
| `auth.js` | JWT 토큰 보관·apiFetch 래퍼·자동 refresh | ~110 (01에서 검토) |
| `ws-client.js` | WebSocket 연결 캐시·자동 재연결·다중 핸들러 | ~135 |
| `alarm-ws.js` | 비대시보드 페이지용 알람 수신 | ~35 (04에서 검토) |
| `worker-ws.js` | 작업자 개인 알림 채널 | (07에서 언급) |
| `alarm-popup.js` | 팝업 모달 렌더 | (별도) |
| `layout.js` | SNB·메뉴 렌더·헤더·시계·로그아웃 | ~250 |
| `util.js` | pad/nowLabel/nowDateLabel/pushData/MAX_POINTS/levelLabel | ~52 |
| `config.js` | AppConfig.apiUrl/wsUrl 등 환경 분기 | (별도) |
| `app-sub.js` | 서브 페이지 공통 진입(Auth.getMe → 메뉴 렌더) | (별도) |

### 1.3 어드민 패널 페이지 (도메인 02·05·07에서 다룬 페이지의 셸 부분)
- 사용자/조직 관리 (02 도메인 참고)
- 시설/설비/장치 관리 (05 도메인 참고)
- 지오펜스 관리 (07 도메인 참고)
- 데이터 조회 (06 도메인 참고)

## 2. 기능 흐름

### 2.1 어드민 페이지 진입 표준 흐름
```
1. /admin-panel/<X>/ 진입 (TemplateView가 HTML 셸 렌더)
2. base.html이 head에 config.js → auth.js → ws-client.js → util.js 로드
3. <body> 끝에서 layout.js → 페이지별 JS 로드
4. layout.js의 initHeaderAndSNB() async 호출:
   ├─ Auth.getAccessToken() 없으면 → /accounts/login/ 리다이렉트
   ├─ Auth.getMe() → /api/auth/me/ → menu_tree, role, admin_url
   ├─ Header.renderUser(username, role)
   ├─ Header.showAdminBtn(role) — 관리자만 어드민 버튼 노출
   ├─ Menu.render(menu_tree) — 권한별 메뉴 SVG 아이콘 + 아코디언
   └─ Header.init() — 시계·새로고침·홈·관리자·로그아웃 핸들러 바인딩
5. 페이지별 JS의 init() 호출 → fetchList/연결/렌더링
```

### 2.2 로그아웃 흐름
```
1. layout.js Header.initLogout() 모달 바인딩
2. 사용자 로그아웃 버튼 클릭 → 확인 모달
3. 확인 → POST /api/auth/logout/
4. 성공 모달 → "확인" 클릭 → Auth.redirectLogin() (= clear + /accounts/login/)
※ 서버 측에서 토큰을 폐기하지 않음 (01의 A1 블랙리스트 시급)
```

### 2.3 새로고침 흐름
```
1. 헤더 새로고침 버튼 클릭 → Header.handleRefresh()
2. GET /dashboard/api/refresh/ → admin_url 등 권한 의존 데이터 조회
3. 401 → Auth.redirectLogin()
4. EventPanel.loadEventList() (대시보드인 경우 글로벌)
5. updateLastUpdated() — 헤더의 갱신 시각 표시
```

## 3. 백엔드 소견 (페이지 뷰 부분만)

### 3.1 일반 코드 리뷰
- **[중] 페이지 뷰가 도메인 앱마다 산재**
  TemplateView가 dashboard, facilities, accounts, geofence 등 각 앱에. URL 라우팅이 도메인 앱에 종속 — `/admin-panel/<x>/` URL과 도메인 매핑이 명확. 다만 페이지 뷰만 모은 `apps/admin_panel/` 별도 앱 도입 검토 가능 (트레이드오프: 검색 편의 vs 도메인 응집).
- **[하] page TemplateView의 active_nav 패턴 일관**
  ([facility_admin.py:43-46](../../../drf-server/apps/facilities/views/facility_admin.py#L43-L46)) `ctx["active_nav"] = "facility"` — 사이드바 활성 탭. 일관 패턴이지만 string 매직. enum 또는 url name으로 단일화 가능.

## 4. 프론트엔드(JS/HTML) 소견 — **이 도메인의 핵심**

### 4.1 공유 JS 책임 분리
- **[참고] ws-client.js는 모범 사례**
  연결 캐시·자동 재연결·다중 핸들러·옵션 토큰. 큰 보일러플레이트 없이 깔끔. 다만 한 가지 주의:
  - **[중] WSClient.connect의 attachToken 옵션이 alarm-ws.js / worker-ws.js / dashboard/websocket.js 일관 적용 여부**
    [04의 D2, 07의 G1] /ws/worker/ JWT 인증 시 `attachToken: true` 옵션 명시 필수. 누락 시 서버는 인증 통과 못 하고 끊김 반복.
- **[중] auth.js의 동시성 미보호 (01의 A3 재확인)**
  여러 페이지에서 같은 이슈. `_refresh` 호출이 동시 다발 시 race. 01의 A3로 통합 처리.
- **[중] util.js의 `levelLabel` 매핑 오류**
  [util.js:51](../../../drf-server/static/js/shared/util.js#L51) `levelLabel = { danger:'위험', caution:'주의', safe:'정상' }`. 백엔드는 `RiskLevel.DANGER='danger'`, `WARNING='warning'`, `NORMAL='normal'` 사용. **`caution`·`safe`는 백엔드에 존재하지 않는 키**. 실제로 어디서 쓰이는지 확인 필요 — 사용 중이라면 항상 `levelLabel[level]` 미스 → undefined 반환 → silent UI 깨짐. 사용 안 한다면 dead code.
- **[하] util.js의 `pushData` 차트 헬퍼와 `MAX_POINTS=30`**
  `MAX_POINTS=30`은 30 데이터 포인트만 차트에 보유 → 1초 1포인트면 30초만 보임. 사용자 의도와 맞는지 확인.

### 4.2 layout.js
- **[중] SVG 아이콘이 JS에 인라인**
  [layout.js:33-37](../../../drf-server/static/js/shared/layout.js#L33-L37) `iconMap`에 SVG 마크업 string. 새 아이콘 추가 시 layout.js 수정 + 이스케이프 위험. **SVG sprite + `<svg><use href>`** 패턴 권장.
- **[중] iconMap 미정의 → '•' 폴백**
  [layout.js:54](../../../drf-server/static/js/shared/layout.js#L54) `const icon = this.iconMap[menu.icon] || '•';`. 메뉴 트리에서 새 아이콘 키 추가 시 silent 폴백 → 디자인 깨짐. 적어도 `console.warn` 또는 빌드 시 검증.
- **[중] `innerHTML`을 동적 데이터로 사용**
  [layout.js:60-63, 74](../../../drf-server/static/js/shared/layout.js#L60-L63) `btn.innerHTML = \`...${menu.label}...\``. menu.label이 백엔드에서 오는 데이터지만 향후 사용자 제공 데이터를 innerHTML에 넣으면 XSS 위험. 텍스트는 `textContent` 권장. 현재는 정의된 메뉴이므로 즉시 위험은 낮으나 패턴 정착 필요.
- **[중] async initHeaderAndSNB의 부분 실패 처리**
  [layout.js:235-245](../../../drf-server/static/js/shared/layout.js#L235-L245) `getMe()` 실패 시 `Menu.showError()` 호출. 그러나 SNB.init/Header.init은 그대로 호출 → 부분적으로 동작하는 헤더. 사용자 입장에선 "메뉴는 안 보이는데 헤더는 보임" 혼란. 명확한 에러 화면 또는 강제 로그아웃 권장.

### 4.3 페이지별 JS의 패턴 중복
- **[상] 5+ 페이지(facility/gas_sensor/power_system/accounts/organizations/geofence)가 동일 admin-list 패턴**
  - filters 객체 + sort + page + selected Set
  - fetchList → `Auth.apiFetch(url+queryString)` → render
  - 모달 (생성/수정) bindEvents
  - 일괄 삭제
  - badge 색상·라벨 매핑 dict
  → 동일 버그가 5곳에 복제. **`shared/admin-list-page.js`** 베이스 추출 시급 (05의 E9와 동일).
- **[중] `showAccessDenied` 모달이 페이지별로 인라인**
  [accounts.js:42-65](../../../drf-server/static/js/admin/accounts/accounts.js#L42-L65) 같은 패턴이 다른 admin 페이지에도 있을 가능성. shared로 추출.

### 4.4 base.html / 공통 템플릿
- **[하] `<script>` 태그 순서 의존성**
  config → auth → ws-client → util → layout 순서 강제. ES Modules 또는 빌드 도구 도입 시 자동화 가능. 현재 규모에선 OK이나 페이지 추가 시 누락 위험.
- **[하] CSP·Subresource Integrity 헤더 부재**
  CDN 사용 시 SRI hash 미설정 가능성. 현재는 모든 정적 자산이 self-hosted라 영향 적음.

### 4.5 CSS·디자인 일관성 (간접)
- **[하] inline style 사용 빈번 (사전 진단)**
  accounts.js의 `_showAccessDenied`에 `style="..."` 인라인. 디자인 시스템과 일관성 위해 CSS class로 분리 권장.

## 5. 개선 제안

### H1. `levelLabel` 매핑 정합 [상 · 소]
- **왜 필요?**: 백엔드와 키 불일치 → silent UI 깨짐 가능. 실제 사용 시 디버깅 어려움.
- **장점**: 정합 / 백엔드 변경 시 한 곳 수정.
- **단점**: 없음 (사용 중이면 즉시 수정, 미사용이면 제거).
- **변경 위치**: [util.js:51](../../../drf-server/static/js/shared/util.js#L51) `{ danger:'위험', warning:'주의', normal:'정상' }`로 수정 + grep으로 사용처 확인.

### H2. shared/admin-list-page.js 베이스 추출 [상 · 대]
- **왜 필요?**: 5+ 페이지가 90% 동일한 admin-list 패턴 — 같은 버그가 5곳에 복제.
- **장점**: 새 도메인 추가 시 100줄로 페이지 완성 / 버그 수정 1곳.
- **단점**: 학습 비용 / 일부 도메인 특수 케이스가 베이스에 안 맞을 수 있음 (escape hatch 필요).
- **변경 위치**: [shared/admin-list-page.js](../../../drf-server/static/js/shared/) 신규. 페이지별 JS는 컬럼·필터·모달만 정의.

### H3. innerHTML → textContent (XSS 패턴 정착) [중 · 소]
- **왜 필요?**: 향후 사용자 제공 데이터가 innerHTML에 들어가면 즉시 XSS. 패턴이 정착되어 있으면 새 코드도 자연스럽게 안전하게 작성.
- **장점**: 보안 / 기본 안전 패턴.
- **단점**: 마크업이 들어가는 정당한 케이스(아이콘 등)는 `<svg>` 요소 직접 생성으로 변경 — 약간의 코드 길이 증가.
- **변경 위치**: [layout.js Menu.render](../../../drf-server/static/js/shared/layout.js#L40-L100) 등 동적 데이터 처리 부분.

### H4. SVG sprite + `<use>` [중 · 중]
- **왜 필요?**: 아이콘 string이 JS에 인라인 — 디자이너 협업·재사용 어려움.
- **장점**: 한 곳 / 디자인 도구 export 직접.
- **단점**: 빌드 도구 또는 정적 sprite 파일 도입 필요.
- **변경 위치**: [static/img/icons.svg](../../../drf-server/static/img/) sprite + [layout.js iconMap](../../../drf-server/static/js/shared/layout.js#L33) 제거.

### H5. WSClient attachToken 일관 [중 · 소]
- **왜 필요?**: WS 인증 강화(04 D2 / 07 G1) 시 모든 WS 호출 지점에서 `attachToken:true` 누락 없어야 함.
- **장점**: 인증 일관성.
- **단점**: 없음 (옵션 추가).
- **변경 위치**: [alarm-ws.js, worker-ws.js, dashboard/websocket.js, detail/websocket_*.js](../../../drf-server/static/js/) WSClient.connect 호출 부분.

### H6. shared/access-denied 모달 [중 · 소]
- **왜 필요?**: 권한 없음 모달이 페이지별 인라인.
- **장점**: 일관 UX.
- **변경 위치**: [shared/access-denied.js](../../../drf-server/static/js/shared/) 신규.

### H7. iconMap 미정의 검증 [하 · 소]
- **왜 필요?**: 새 메뉴 아이콘 silent 폴백.
- **변경 위치**: [layout.js:54](../../../drf-server/static/js/shared/layout.js#L54) `console.warn` 또는 빌드 검증.

### H8. initHeaderAndSNB 부분 실패 화면 [하 · 소]
- **왜 필요?**: getMe 실패 시 헤더만 보이는 깨진 상태.
- **변경 위치**: [layout.js:235-245](../../../drf-server/static/js/shared/layout.js#L235-L245) — 명시적 에러 페이지로 분기 또는 강제 로그아웃.

### H9. 페이지뷰 별도 앱 검토 [하 · 중]
- **왜 필요?**: TemplateView가 도메인 앱에 산재 → 사이드바 구조 변경 시 수정 지점 다수.
- **단점**: 도메인 응집과 트레이드오프. 강한 의견 아님.
- **변경 위치**: `apps/admin_panel/` 신규 또는 현재 유지.

### H10. 페이지 inline style → CSS class [하 · 중]
- **왜 필요?**: 디자인 시스템 일관성.
- **변경 위치**: 페이지별 JS의 `style="..."` 모두 css class로 변환.

## 6. 구현 추천 순서

### 1단계 — 정합성 (즉시) ⚡
- **H1** levelLabel 매핑 정합 (또는 dead code 제거)
- **H5** WSClient attachToken 일관 (D2/G1과 함께)
- **이유**: 정합성 미스는 silent 버그로 사용자에게 노출됨. 변경 작은데 효과 큼.

### 2단계 — 보안 패턴 정착 (1주 내) 🔐
- **H3** innerHTML → textContent
- **이유**: 향후 사용자 데이터 추가 시 자동으로 안전. 변경 산발적이지만 일괄 grep으로 가능.

### 3단계 — 공유 베이스 추출 (다음 sprint) 🏗
- **H2** admin-list-page 베이스 (가장 큰 효과)
- **H6** access-denied 모달
- **H4** SVG sprite (디자이너 협업 시점)
- **이유**: 코드 중복 제거 + 새 페이지 추가 가속. H2는 큰 작업이지만 ROI 매우 높음.

### 4단계 — 클린업 (여유 시) 🧹
- **H7** iconMap 검증
- **H8** initHeaderAndSNB 부분 실패
- **H9** 페이지뷰 앱 분리 (강한 의견 아님)
- **H10** inline style 정리

### ⚠️ 주의사항 (초보자용)
- **H1 levelLabel 수정 전 grep 필수**: 다른 곳에서 `caution`/`safe` 키를 의도적으로 쓰고 있다면 단순 변경이 회귀. 먼저 `grep -r 'levelLabel\|caution\|safe' static/` 후 결정.
- **H2 admin-list-page 베이스는 "단순 케이스부터" 마이그레이션**: facility/equipment 같은 표준 CRUD부터 시작. 지오펜스(지도 기반) 같은 특수 케이스는 마지막에 검토 — 안 맞으면 베이스에 escape hatch 필요.
- **H4 SVG sprite 도입은 디자이너와 협업**: 색상·크기 토큰을 sprite로 인코딩하는 방식이 디자인 시스템과 맞는지 확인. 디자이너가 Figma export로 sprite 만들 수 있는지 사전 확인.
- **H3 innerHTML 일괄 변경 시 마크업 의도 보존**: `<a href="...">${label}</a>` 같은 정당한 마크업은 `createElement('a')` + `textContent`로. 한꺼번에 sed 변환은 위험.
