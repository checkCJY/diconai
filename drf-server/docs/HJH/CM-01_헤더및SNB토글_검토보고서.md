# CM-01 헤더 및 SNB 토글 — 코드 검토 보고서

> 작성자: 한지혜 / 작성일: 2026-04-24
> 대상 기능 ID: **CM-01** (헤더 및 SNB 토글)
> 검토 범위: 프론트엔드 + 백엔드 전체

---

## 1. 기능 정의서 스펙 요약

| 항목 | 내용 |
|------|------|
| 기능 목적 | 전역 이동과 현재 사용자 인지 제공 |
| 사용자 시나리오 | 로그인 후 모든 화면 상단 헤더 노출, 햄버거 클릭 시 SNB 열림/닫힘 |
| 수집 정보 | 사용자명, **권한 기본정보** |
| 디자인 요소 | 로고, 시스템명, 사용자 영역, 햄버거, 홈, 로그아웃 |
| 유효성 처리 | 권한별 메뉴 표시 |
| 예외 조건 | 햄버거 재클릭 시 접힘 |
| 에러 처리 | - (별도 명시 없음) |
| 백엔드 처리 | 사용자/권한 기반 메뉴 트리 조회 |
| 프론트엔드 처리 | 전역 헤더 렌더링, SNB open 상태관리 |
| 참고사항 | **Depth1 메뉴 아이콘 포함** |

---

## 2. 검토 대상 파일

| 역할 | 파일 경로 |
|------|-----------|
| 헤더 + SNB 컴포넌트 | `templates/components/header.html` |
| 메인 대시보드 | `templates/main_dashboard.html` |
| 서브 페이지 | `templates/snb_details/*.html` |
| SNB 토글 / 메뉴 / 헤더 제어 | `static/js/refactors/layout.js` |
| JWT 토큰 관리 | `static/js/refactors/auth.js` |
| 메인 앱 초기화 | `static/js/refactors/app.js` |
| 서브 페이지 초기화 | `static/js/refactors/app-sub.js` |
| 공통 유틸 | `static/js/refactors/util.js` |
| 헤더 / SNB 스타일 | `static/css/components/header.css` |
| 권한별 메뉴 트리 | `apps/dashboard/menu.py` |
| 메뉴 API / 대시보드 뷰 | `apps/dashboard/views.py` |
| URL 라우팅 | `apps/dashboard/urls.py` |
| 사용자 정보 + 메뉴 API | `apps/accounts/views.py` |
| UserType 정의 | `apps/core/constants.py` |

---

## 3. 스펙 충족 항목 ✅

| 항목 | 구현 위치 | 비고 |
|------|-----------|------|
| 로그인 후 모든 화면 헤더 노출 | `{% include 'components/header.html' %}` | 메인 + 모든 서브 페이지 적용 |
| 햄버거 클릭 시 SNB 열림 | `layout.js` — `SNB.toggle()` | |
| 햄버거 재클릭 시 SNB 닫힘 | `layout.js` — `SNB.toggle()` | z-index 버그 수정 완료 |
| 오버레이 클릭 시 SNB 닫힘 | `layout.js` — `SNB.init()` overlay 이벤트 | |
| 사용자명 표시 | `header.html` — `#headerUsername` | `/api/auth/me/` 연동 |
| 권한 표시 | `header.html` — `#headerRole` | 한글 변환 표시 (수정 반영) |
| 권한별 메뉴 분기 | `menu.py` — `get_menu_tree(role)` | facility_admin / super_admin 분기 (수정 반영) |
| 관리자 버튼 조건부 노출 | `layout.js` — `Header.showAdminBtn()` | facility_admin / super_admin만 표시 |
| Depth1 메뉴 아이콘 | `layout.js` — `iconMap` | SVG 아이콘 (shield / monitor / settings) |
| 아이콘 미정의 fallback | `layout.js` — `iconMap[icon] \|\| '•'` | |
| 현재 경로 active 하이라이트 | `layout.js` — `Menu.currentPath` | 해당 Depth1 자동 펼침 |
| Me API 실패 시 graceful 처리 | `layout.js` — `initHeaderAndSNB()` | localStorage 캐시값으로 표시, SNB 오류 안내 |
| 인증 없이 접근 시 리다이렉트 | `layout.js` — `initHeaderAndSNB()` | `/accounts/login/` 이동 |
| 새로고침 중복 요청 방지 | `layout.js` — `Header.isRefreshing` | 플래그로 중복 클릭 차단 |
| 로그아웃 확인 모달 | `header.html` — `#logoutModal` | 확인 클릭 시 localStorage 초기화 + 리다이렉트 |

---

## 4. 문제 항목 — 심각도별 분류

### 🔴 HIGH — 즉시 수정 필요

---

#### H-1. `menu.py` 권한 체크 값 불일치 → **수정 완료 (2026-04-24)**

**위치:** `apps/dashboard/menu.py` 70줄

```python
# 수정 전 — DB에 존재하지 않는 값으로 체크
if role in ("admin", "superadmin"):

# 수정 후
if role in ("facility_admin", "super_admin"):
```

**문제점:**
- `constants.py`에 정의된 실제 DB 값은 `"facility_admin"`, `"super_admin"`
- `"admin"`, `"superadmin"` 이라는 값은 시스템 어디에도 존재하지 않음
- 어떤 관리자 계정으로 로그인해도 "관리자 전용" 메뉴가 절대 표시되지 않음

**다른 파일과의 비교:**

| 파일 | 관리자 권한 체크 값 | 정확 여부 |
|------|-------------------|----------|
| `menu.py` (수정 전) | `"admin"`, `"superadmin"` | ❌ |
| `layout.js` — `Header.showAdminBtn()` | `"facility_admin"`, `"super_admin"` | ✅ |
| `dashboard/views.py` — `DashboardRefreshView` | `"facility_admin"`, `"super_admin"` | ✅ |

---

#### H-2. SNB-05 관리자 메뉴 path 404 → **수정 완료 (2026-04-24)**

**위치:** `apps/dashboard/menu.py` 63줄

```python
# 수정 전 — 등록되지 않은 URL
{"id": "SNB-05", "label": "전체 이력 현황", "path": "/admin-panel/history"}

# 수정 후 — 기존 관리자 페이지로 임시 연결 (SNB-05 구현 시 교체 필요)
{"id": "SNB-05", "label": "전체 이력 현황", "path": "/dashboard/admin/"}
```

**문제점:**
- H-1을 수정해 관리자 메뉴가 노출되더라도 클릭 시 404 반환
- `config/urls.py`, `dashboard/urls.py` 어디에도 `/admin-panel/history` 등록 없음

---

### 🟡 MEDIUM — 운영 전 수정 권장

---

#### M-1. 헤더 권한 표시 누락 → **수정 완료 (2026-04-24)**

**위치:** `templates/components/header.html` 33~36줄 / `static/js/refactors/layout.js` 171줄

**스펙 요구사항:** 수집 정보 — "사용자명, **권한 기본정보**"

```html
<!-- 수정 전 — 사용자명만 표시 -->
<div class="user-info">
  <div class="user-name" id="headerUsername">-</div>
</div>

<!-- 수정 후 — 권한 추가 -->
<div class="user-info">
  <div class="user-name" id="headerUsername">-</div>
  <div class="user-role" id="headerRole">-</div>
</div>
```

```javascript
// 수정 전
renderUser(username) { ... }

// 수정 후
renderUser(username, role) {
  const roleLabel = {
    worker: '작업자', facility_admin: '공장관리자',
    super_admin: '슈퍼관리자', viewer: '열람자',
  };
  ...
}
```

**비고:** CSS `.user-role` 클래스는 `header.css:22`에 이미 정의되어 있었으나 HTML 요소가 없어 미적용 상태였음.

---

#### M-2. JWT 토큰 자동 갱신 미구현

**위치:** `static/js/refactors/auth.js` 30~38줄

```javascript
// 현재 — 401 수신 즉시 로그인 리다이렉트
async getMe() {
  const res = await this.apiFetch('/api/auth/me/');
  if (res.status === 401) { this.redirectLogin(); return null; }
  ...
}
```

**문제점:**
- `TokenRefreshView` URL이 `accounts/urls.py`에 등록되어 있으나 실제로 호출하는 코드가 없음
- 액세스 토큰 만료 시 refresh 시도 없이 바로 로그아웃 처리됨

**현재 설정값 (`config/settings.py` 140줄):**
```python
"ACCESS_TOKEN_LIFETIME":  timedelta(hours=24),  # 24시간
"REFRESH_TOKEN_LIFETIME": timedelta(days=30),    # 30일
```

**24시간 토큰이라 개발 중 영향은 낮으나 운영 배포 전 필수 구현.**

**권장 수정 방향:**
```javascript
// auth.js — apiFetch에 refresh 로직 추가
async apiFetch(url, opts = {}) {
  let res = await fetch(url, { ...headers });
  if (res.status !== 401) return res;

  // refresh 시도
  const refreshed = await this.tryRefresh();
  if (!refreshed) { this.redirectLogin(); return res; }

  // 새 토큰으로 재시도
  return fetch(url, { ...headersWithNewToken });
},
```

---

#### M-3. 로그아웃 서버 측 처리 없음

**위치:** `static/js/refactors/layout.js` 168줄

```javascript
// 현재 — localStorage 삭제 + 리다이렉트만 수행
logoutConfirm?.addEventListener('click', () => { Auth.redirectLogin(); });
```

**문제점:**
- 서버에 로그아웃 신호를 보내지 않아 JWT 만료 전까지 토큰이 유효한 상태로 남음
- 기능 정의서 CM-03: "세션 무효화" 요구사항 미이행

**현재 상태:**
- `LoginLog` 모델에 `LOGOUT` 결과코드와 `session_key` 필드가 이미 준비됨
- `LogoutView`만 추가하면 연동 가능한 구조

**→ CM-03 구현 시 함께 처리 권장.**

---

### 🟢 LOW — 장기 개선 고려

---

#### L-1. 햄버거 버튼 이모지 유지

**위치:** `templates/components/header.html` 16줄

```html
<!-- 현재 — 이모지 -->
<button id="hamburger">☰</button>
```

홈 버튼, Depth1 메뉴 아이콘은 SVG로 통일됐으나 햄버거만 `☰` 이모지 유지.
OS / 브라우저마다 렌더링 모양이 다를 수 있음.

**권장 수정:**
```html
<button id="hamburger">
  <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
    <path d="M3 18h18v-2H3v2zm0-5h18v-2H3v2zm0-7v2h18V6H3z"/>
  </svg>
</button>
```

---

#### L-2. `aria-expanded` 접근성 미적용

**위치:** `static/js/refactors/layout.js` 16~23줄

```javascript
// 현재 — CSS 클래스만 토글, aria 속성 미변경
open()  { this.drawer.classList.add('open');    this.overlay.classList.add('open'); },
close() { this.drawer.classList.remove('open'); this.overlay.classList.remove('open'); },
```

스크린리더 등 보조 기기에서 SNB 열림/닫힘 상태를 인식할 수 없음.

**권장 수정:**
```html
<!-- header.html — 초기값 추가 -->
<button id="hamburger" aria-expanded="false" aria-controls="snbDrawer">
```
```javascript
// layout.js — open/close에 속성 변경 추가
open()  { ...; document.getElementById('hamburger')?.setAttribute('aria-expanded', 'true'); },
close() { ...; document.getElementById('hamburger')?.setAttribute('aria-expanded', 'false'); },
```

---

#### L-3. `MenuView` 미사용 엔드포인트

**위치:** `apps/dashboard/views.py` 54~65줄 / `apps/dashboard/urls.py` 26줄

`GET /dashboard/api/menu/`는 메뉴 트리만 반환하는 별도 API이나, 프론트엔드에서 실제로 호출하는 코드가 없음. `MeView`(`/api/auth/me/`)가 `menu_tree`를 이미 포함해 반환하므로 중복 구조.

향후 메뉴만 단독으로 갱신하는 기능에 활용 가능성이 있어 삭제하지 않으나, 사용 의도를 주석으로 명시 권장.

---

## 5. 종합 요약

| 구분 | 항목 수 | 항목 |
|------|---------|------|
| ✅ 충족 | 15개 | 헤더 노출, SNB 토글, 오버레이 닫힘, 사용자명, 권한 표시, 권한별 메뉴, 관리자 버튼, Depth1 아이콘, active 하이라이트, fallback, graceful 실패 처리, 인증 리다이렉트, 새로고침 중복 방지, 로그아웃 모달 |
| 🔴 HIGH | 2개 | H-1 권한 체크 불일치, H-2 SNB-05 path 404 |
| 🟡 MEDIUM | 3개 | M-1 권한 표시 누락, M-2 JWT refresh 미구현, M-3 로그아웃 서버 처리 없음 |
| 🟢 LOW | 3개 | L-1 햄버거 이모지, L-2 aria-expanded, L-3 MenuView 중복 |

> H-1, H-2, M-1은 **2026-04-24 수정 완료.**

---

## 6. 수정 우선순위 Action Items

| 순서 | 항목 | 담당 | 예상 공수 | 기한 |
|------|------|------|-----------|------|
| 1 | M-2 JWT 토큰 자동 갱신 (`auth.js`) | 프론트 | 2h | 운영 배포 전 |
| 2 | M-3 로그아웃 서버 측 처리 (`LogoutView`) | 백엔드+프론트 | 2h | CM-03 구현 시 |
| 3 | L-1 햄버거 이모지 → SVG | 프론트 | 15min | 여유 있을 때 |
| 4 | L-2 `aria-expanded` 접근성 추가 | 프론트 | 30min | 여유 있을 때 |
| 5 | L-3 `MenuView` 주석 명시 | 백엔드 | 5min | 여유 있을 때 |

---

## 7. 잘 구현된 부분 (유지)

- **헤더 컴포넌트 분리:** `header.html`을 독립 파일로 분리하고 `{% include %}`로 전체 페이지에 일관 적용 — 향후 헤더 수정 시 파일 하나만 변경하면 됨
- **CSS 폴더 구조:** `auth/`, `components/`, `snb_details/`로 템플릿 구조와 동일하게 정렬 — 파일 추적 용이
- **z-index 계층 설계:** `modal(1000) > header(900) > snb(801) > overlay(800)` 명확히 정의, 오버레이가 햄버거를 가리던 버그 방지
- **SNB 상태 복원:** 페이지 진입 시 현재 경로(`window.location.pathname`)와 일치하는 Depth1 메뉴 자동 펼침 + active 클래스 적용
- **아이콘 일관성:** OS/브라우저 무관하게 동일하게 렌더링되는 Material Design SVG 아이콘 사용 (홈, 메뉴 아이콘)
- **새로고침 중복 방지:** `Header.isRefreshing` 플래그로 연속 클릭 시 중복 API 호출 차단
- **Soft Delete 정책:** `CustomUser.delete()` 오버라이드로 계정 실수 삭제 원천 차단 — `LoginLog`, `EventLog` 등 전체 FK 연결 보존
- **정규식 최적화:** `_PWD_PATTERNS`를 모듈 상수로 분리해 `validate_password()` 호출마다 재컴파일 방지
- **공통 초기화 함수:** `initHeaderAndSNB()`로 메인/서브 페이지 헤더+SNB 초기화 로직 단일화 — 수정 시 한 곳만 변경

---

## 8. 수정 이력 (2026-04-24)

> 검토 보고서 작성 후 HIGH 2건, MEDIUM 1건, 관련 리팩토링 2건 수정 완료.

---

### H-1 수정 — `menu.py` 권한 체크 값 불일치

**수정 파일:** `apps/dashboard/menu.py` 70줄

| 단계 | 내용 |
|------|------|
| 원인 | `"admin"`, `"superadmin"`으로 체크했으나 DB 실제 값은 `"facility_admin"`, `"super_admin"` |
| 영향 | `facility_admin`, `super_admin` 계정으로 로그인해도 "관리자 전용" 메뉴 미노출 |
| 수정 | `("admin", "superadmin")` → `("facility_admin", "super_admin")` |

**검증:**
- `Header.showAdminBtn()`과 `DashboardRefreshView` 모두 `"facility_admin"`, `"super_admin"`으로 올바르게 체크 중 → `menu.py`만 불일치 상태였음 확인 후 수정

---

### H-2 수정 — SNB-05 관리자 메뉴 path 404

**수정 파일:** `apps/dashboard/menu.py` 63줄

| 단계 | 내용 |
|------|------|
| 원인 | `/admin-panel/history` path가 `config/urls.py`, `dashboard/urls.py` 어디에도 등록 없음 |
| 영향 | H-1 수정 후 관리자 메뉴가 표시되더라도 클릭 시 404 반환 |
| 수정 | `/dashboard/admin/` (기존 관리자 페이지)로 임시 연결 + 주석 명시 |

> **SNB-05 구현 시 전용 URL 등록 후 이 path를 교체해야 합니다.**

---

### M-1 수정 — 헤더 권한 표시 추가

**수정 파일:** `templates/components/header.html`, `static/js/refactors/layout.js`

| 단계 | 내용 |
|------|------|
| 원인 | 기능 정의서 수집 정보 "권한 기본정보" 미충족. CSS `.user-role` 클래스는 정의되어 있었으나 HTML 요소 누락 |
| 수정 | `#headerRole` div 추가, `renderUser(username, role)` 파라미터 추가 및 한글 변환 매핑 |

**권한 한글 표시:**

| DB 값 | 표시 |
|-------|------|
| `worker` | 작업자 |
| `facility_admin` | 공장관리자 |
| `super_admin` | 슈퍼관리자 |
| `viewer` | 열람자 |

---

### 리팩토링 1 — `initHeaderAndSNB()` 공통 함수 추출

**수정 파일:** `static/js/refactors/layout.js` (추가), `app.js`, `app-sub.js`

| 단계 | 내용 |
|------|------|
| 원인 | `app.js`와 `app-sub.js`의 토큰 확인 → Me API → 헤더/메뉴 렌더링 → SNB/Header init 블록이 완전히 중복. M-1(role 전달) 수정 시 두 파일 모두 변경해야 하는 구조 |
| 수정 | 공통 블록을 `layout.js`의 `initHeaderAndSNB()`로 추출, 두 파일에서 호출 |
| 효과 | 향후 헤더/SNB 초기화 로직 수정 시 `layout.js` 한 곳만 변경하면 됨 |

---

### 리팩토링 2 — `viewer` 권한 처리 명시

**수정 파일:** `apps/dashboard/menu.py` 73줄

```python
# viewer는 worker와 동일 메뉴 (읽기 전용 권한은 API 레벨에서 제어)
return menus
```

`constants.py`에 `VIEWER` role이 정의되어 있으나 `menu.py`에 분기가 없어 묵시적으로 worker와 동일 메뉴가 적용되던 구조를 주석으로 명시해 의도를 명확화.
