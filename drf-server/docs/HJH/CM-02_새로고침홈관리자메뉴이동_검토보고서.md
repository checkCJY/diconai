# CM-02 새로고침/홈/관리자 메뉴 이동 — 코드 검토 보고서

> 작성자: 한지혜 / 작성일: 2026-04-24
> 대상 기능 ID: **CM-02** (새로고침/홈/관리자 메뉴 이동)
> 검토 범위: 프론트엔드 + 백엔드 전체

---

## 1. 기능 정의서 스펙 요약

| 항목 | 내용 |
|------|------|
| 기능 목적 | 공통 네비게이션 제공 |
| 사용자 시나리오 | 관리자 메뉴 클릭 시 백오피스 이동, 새로고침 시 데이터 재호출, 홈 클릭 시 메인 이동 |
| 수집 정보 | **현재 시스템 시간**, **마지막 갱신 시간** |
| 유효성 처리 | - |
| 예외 조건 | **메인에서 홈 클릭 시 새로고침으로 대체 가능** |
| 에러 처리 | **새로고침 실패 시 오류화면 또는 값 `-` 처리** |
| 백엔드 처리 | **대시보드 재조회**, 시간정보 갱신, 관리자 URL 반환 |
| 프론트엔드 처리 | 라우팅, 재조회 로딩, 타임스탬프 갱신 |
| 참고사항 | **백오피스 URL/권한 분기 필요** |

---

## 2. 검토 대상 파일

| 역할 | 파일 경로 |
|------|-----------|
| 헤더 버튼 HTML | `templates/components/header.html` |
| 새로고침/홈/관리자/시계 제어 | `static/js/refactors/layout.js` |
| 이벤트 패널 (재조회 대상) | `static/js/refactors/event-panel.js` |
| 작업자 패널 (자동 폴링) | `static/js/refactors/worker-panel.js` |
| WebSocket 실시간 패널 | `static/js/refactors/websocket.js` |
| 공통 유틸 | `static/js/refactors/util.js` |
| 헤더 스타일 | `static/css/components/header.css` |
| 대시보드 리프레시 API | `apps/dashboard/views.py` |
| 사용자 정보 API | `apps/accounts/views.py` |
| 백오피스 URL 설정 | `config/settings.py` |

---

## 3. 스펙 충족 항목 ✅

| 항목 | 구현 위치 | 비고 |
|------|-----------|------|
| 현재 시스템 시간 표시 | `layout.js` — `initClock()` | `setInterval(1000)` 1초마다 갱신 |
| 마지막 갱신 시간 표시 | `layout.js` — `updateLastUpdated()` | 새로고침 성공 시 클라이언트 시각 갱신 |
| 새로고침 버튼 로딩 스피너 | `layout.js` — `.spinning` 클래스 | `header.css` `@keyframes spin` |
| 새로고침 중복 클릭 방지 | `layout.js` — `isRefreshing` 플래그 | 진행 중 재클릭 무시 |
| 홈 클릭 시 메인 이동 | `layout.js` — `handleHome()` | `/dashboard/`로 이동 |
| 메인에서 홈 클릭 시 새로고침 대체 | `layout.js` — `handleHome()` | `pathname === '/dashboard/'` 분기 |
| 관리자 버튼 권한별 조건부 노출 | `layout.js` — `showAdminBtn(role)` | `facility_admin`, `super_admin`만 표시 |
| 관리자 URL 환경변수 관리 | `config/settings.py:147` | `ADMIN_BACKOFFICE_URL` env 설정 |
| 백오피스 URL 권한 분기 | `dashboard/views.py`, `accounts/views.py` | 관리자 role에만 `admin_url` 반환 |
| 401 시 로그인 리다이렉트 | `layout.js` — `handleRefresh()` | 토큰 만료 시 처리 |

---

## 4. 문제 항목 — 심각도별 분류

### 🔴 HIGH — 즉시 수정 필요

---

#### H-1. 관리자 버튼 클릭 시 항상 잘못된 페이지로 이동 → **수정 완료 (2026-04-24) → 재수정 완료 (2026-04-24)**

**위치:** `apps/accounts/views.py` MeView / `static/js/refactors/layout.js` 110줄

**문제 흐름:**
```
페이지 로드
  → initHeaderAndSNB() → Auth.getMe() → MeView 응답
     { username, role, menu_tree }   ← admin_url 없음
  → Header.adminUrl = null            ← 초기값 그대로 유지
  → showAdminBtn(role) → 버튼 표시

관리자 버튼 클릭
  → handleAdmin()
  → this.adminUrl || '/dashboard/admin/'
  → adminUrl = null 이므로 /dashboard/admin/ 이동
     ← 내부 사용자 관리 페이지 (백오피스 아님)
```

`adminUrl`은 `handleRefresh()` 성공 시에만 설정됨. 새로고침 버튼을 한 번도 안 누른 상태에서는 관리자 버튼이 항상 틀린 페이지로 이동.

**다른 파일과의 비교:**

| 파일 | admin_url 처리 | 정확 여부 |
|------|---------------|----------|
| `accounts/views.py` MeView (수정 전) | 반환 없음 | ❌ |
| `dashboard/views.py` DashboardRefreshView | `admin_url` 반환 | ✅ |
| `layout.js` showAdminBtn() | 버튼 표시만 담당 | ✅ |

---

#### H-2. 새로고침 버튼이 이벤트 패널 데이터를 재조회하지 않음 → **수정 완료 (2026-04-24)**

**위치:** `static/js/refactors/layout.js` 131줄 `handleRefresh()`

**스펙 요구사항:** "새로고침 시 데이터 재호출", 백엔드: "대시보드 재조회"

**패널별 데이터 경로 분석:**

| 패널 | 데이터 방식 | 새로고침 트리거 필요? |
|------|-----------|-------------------|
| 가스/전력/차트/지도 | WebSocket 실시간 수신 | ❌ 이미 살아있음 |
| 작업자 현황 | `setInterval(30_000)` 자동 폴링 | ❌ 30초마다 자동 갱신 |
| **이벤트 현황** | `init()` 1회 REST 호출, 이후 WS 추가만 | ✅ 재조회 필요 |

새로고침 버튼을 눌러도 이벤트 목록이 갱신되지 않음. `EventPanel.loadEventList()`가 `init()` 이후 다시 호출되지 않음.

---

#### H-3. 서버 `last_updated` 반환값이 프론트에서 사용되지 않음 → **수정 완료 (2026-04-24)**

**위치:** `apps/dashboard/views.py` 130줄 / `static/js/refactors/layout.js` 139~145줄

```python
# 수정 전 — 서버에서 반환하지만
data = {"last_updated": datetime.now().isoformat()}
```

```javascript
// 수정 전 — 프론트에서 data.last_updated를 읽지 않고 무시
const data = await res.json();
if (data.admin_url) { ... }
this.updateLastUpdated();  // 클라이언트 시간으로 직접 생성
```

**결정 — B안 채택:**
- "마지막 갱신" = "사용자가 새로고침을 누른 시점" → 클라이언트 시간이 더 정확한 의미
- `last_updated` 서버 반환 코드와 `datetime` import 제거
- M-1(`datetime.now()` 타임존 문제)도 함께 해소

---

### 🟡 MEDIUM — 운영 전 수정 권장

---

#### M-1. `datetime.now()` 타임존 미고려 → **H-3 수정으로 자동 해소 (2026-04-24)**

`dashboard/views.py`에서 `last_updated` 필드와 함께 `datetime.now()` 코드 및 `datetime` import가 제거되어 별도 수정 없이 해소됨.

---

#### M-2. 새로고침 실패 시 사용자 피드백 없음 → **수정 완료 (2026-04-24)**

**위치:** `static/js/refactors/layout.js` 148줄 catch 블록

**스펙 요구사항:** "새로고침 실패 시 오류화면 또는 값 `-` 처리"

```javascript
// 수정 전 — 완전히 빈 catch
} catch { /* 실패 시 수치 '-' 처리는 각 패널 담당 */ }
```

실패해도 스피너만 멈추고 사용자는 성공/실패 여부를 알 수 없음. 주석이 언급한 "각 패널 담당" 처리 코드도 실제로 없음.

---

### 🟢 LOW — 장기 개선 고려

---

#### L-1. 새로고침 버튼 `⟳` 이모지 유지

**위치:** `templates/components/header.html` 46줄

홈 버튼, 메뉴 아이콘은 SVG인데 새로고침만 `⟳` 이모지 유지. OS/브라우저별 렌더링 차이 가능성. `.spinning` CSS 애니메이션은 SVG에도 그대로 동작하므로 추가 CSS 없이 교체 가능.

---

#### L-2. `handleAdmin()` fallback URL

**H-1 수정으로 자동 해소.** `MeView`에 `admin_url`이 추가되어 관리자 계정은 페이지 로드 시부터 `adminUrl`이 설정됨. fallback(`/dashboard/admin/`) 실행 경로가 사실상 없어짐.

---

## 5. 종합 요약

| 구분 | 항목 수 | 항목 |
|------|---------|------|
| ✅ 충족 | 10개 | 시계, 갱신시간, 스피너, 중복방지, 홈이동, 홈→새로고침대체, 관리자버튼 권한분기, URL 환경변수, 백오피스 권한분기, 401처리 |
| 🔴 HIGH | 3개 | H-1 adminUrl null, H-2 이벤트 패널 미재조회, H-3 last_updated 불일치 |
| 🟡 MEDIUM | 2개 | M-1 datetime.now (H-3 해소), M-2 실패 피드백 없음 |
| 🟢 LOW | 2개 | L-1 이모지, L-2 fallback (H-1 해소) |

> H-1, H-2, H-3, M-1, M-2는 **2026-04-24 수정 완료.**
> L-2는 H-1 수정으로 자동 해소.

---

## 6. 수정 우선순위 Action Items

| 순서 | 항목 | 담당 | 예상 공수 | 기한 |
|------|------|------|-----------|------|
| 1 | L-1 새로고침 버튼 이모지 → SVG | 프론트 | 10min | 여유 있을 때 |

---

## 7. 잘 구현된 부분 (유지)

- **중복 클릭 방지:** `isRefreshing` 플래그로 새로고침 진행 중 재클릭 완전 차단
- **스피너 구현:** `@keyframes spin` + `.spinning` 클래스 방식으로 CSS만으로 로딩 표현 — JS 부담 없음
- **홈 버튼 이중 동작:** 메인에서는 새로고침, 서브 페이지에서는 메인 이동으로 예외 조건 정확히 구현
- **백오피스 URL 환경변수:** `ADMIN_BACKOFFICE_URL`을 `settings.py`에서 관리하고 `.env`로 재정의 가능 — 배포 환경별 분리 가능
- **1초 시계:** `setInterval`을 `initClock()` 내부에 캡슐화해 전역 오염 없음
- **401 처리:** 새로고침 도중 토큰 만료 시 즉시 로그인 리다이렉트

---

## 8. 수정 이력 (2026-04-24)

> 검토 보고서 작성 후 HIGH 3건, MEDIUM 1건 수정 완료.

---

### H-1 수정 — 관리자 버튼 `adminUrl` 초기화

**수정 파일:** `apps/accounts/views.py`, `static/js/refactors/layout.js`

| 단계 | 내용 |
|------|------|
| 원인 | `MeView`가 `admin_url`을 반환하지 않아 페이지 로드 시 `Header.adminUrl = null` 유지 |
| 영향 | 새로고침 버튼을 한 번도 안 누른 상태에서 관리자 버튼 클릭 시 `/dashboard/admin/`(내부 페이지)로 이동 |
| 수정 | `MeView`에 `admin_url` 조건부 추가 + `initHeaderAndSNB()`에서 `Header.adminUrl` 설정 |

```python
# accounts/views.py — MeView 수정 후
data = {"username": user.username, "role": user.user_type, "menu_tree": menu_tree}
if user.user_type in ("facility_admin", "super_admin"):
    data["admin_url"] = getattr(settings, "ADMIN_BACKOFFICE_URL", "/admin/")
return Response(data)
```

```javascript
// layout.js — initHeaderAndSNB() 수정 후
if (user.admin_url) Header.adminUrl = user.admin_url;
```

**검증:**
- `DashboardRefreshView`에서도 `admin_url`을 계속 반환하므로 새로고침 시에도 URL 동기화됨
- 비관리자 계정은 `user.admin_url`이 `undefined`이므로 `if` 조건이 falsy → 버튼 표시 없음

---

### H-1 재수정 — `settings.py` 기본 URL 오류 (2026-04-24)

**수정 파일:** `config/settings.py`

| 단계 | 내용 |
|------|------|
| 원인 | H-1 수정으로 `MeView`가 `admin_url`을 반환하기 시작했으나, `settings.py`의 `ADMIN_BACKOFFICE_URL` 기본값이 `/admin/`(Django 어드민)으로 설정되어 있어 관리자 버튼이 Django 어드민 페이지로 이동함 |
| 영향 | H-1 수정 이전에는 `adminUrl = null` → fallback `/dashboard/admin/`으로 이동하여 우연히 정상 동작했으나, H-1 수정 후 `/admin/`(의도하지 않은 페이지)으로 이동하게 됨 |
| 수정 | `ADMIN_BACKOFFICE_URL` 기본값을 `/admin/` → `/dashboard/admin/`으로 변경 |

```python
# config/settings.py — 재수정 후
# 수정 전
ADMIN_BACKOFFICE_URL = env("ADMIN_BACKOFFICE_URL", default="/admin/")

# 수정 후
ADMIN_BACKOFFICE_URL = env("ADMIN_BACKOFFICE_URL", default="/dashboard/admin/")
```

**검증:**
- `MeView`, `DashboardRefreshView` 모두 `settings.ADMIN_BACKOFFICE_URL`을 참조하므로 이 한 곳의 수정으로 두 API 모두 올바른 URL 반환
- `.env`에 `ADMIN_BACKOFFICE_URL`을 별도로 지정한 경우 해당 값이 우선 적용됨 (환경변수 분리 유지)

---

### H-2 수정 — 새로고침 시 이벤트 패널 재조회

**수정 파일:** `static/js/refactors/layout.js` `handleRefresh()`

| 단계 | 내용 |
|------|------|
| 원인 | `EventPanel.loadEventList()`가 `init()` 1회만 호출됨. 이후 WebSocket은 신규 이벤트를 추가만 할 뿐 목록 전체를 갱신하지 않음 |
| 영향 | 새로고침 버튼 클릭 시 이벤트 목록이 갱신되지 않음 |
| 수정 | `handleRefresh()` 성공 시 `EventPanel.loadEventList()` 호출 추가 |

```javascript
// layout.js — handleRefresh() 수정 후
this.updateLastUpdated();
if (typeof EventPanel !== 'undefined') EventPanel.loadEventList();
```

**검증:**
- `typeof EventPanel !== 'undefined'` 가드로 서브 페이지(`app-sub.js`)에서 `EventPanel`이 없을 때 오류 없이 스킵
- 가스/전력/지도/차트 → WebSocket 실시간, 작업자 → 30초 폴링으로 이미 자동 갱신되므로 추가 트리거 불필요

---

### H-3 수정 — 서버 `last_updated` 불필요 필드 제거

**수정 파일:** `apps/dashboard/views.py`

| 단계 | 내용 |
|------|------|
| 원인 | `DashboardRefreshView`가 `last_updated`를 반환하지만 프론트에서 `data.last_updated`를 읽지 않고 `nowDateLabel()`(클라이언트 시간)을 직접 사용 |
| 결정 | B안 채택 — "마지막 갱신" = "새로고침 버튼 클릭 시점"으로 클라이언트 시간이 의미에 부합 |
| 수정 | `last_updated` 반환 코드 제거, 미사용 `datetime` import 정리 |

```python
# dashboard/views.py — 수정 전
from datetime import datetime, date
data = {"last_updated": datetime.now().isoformat()}

# 수정 후
from datetime import date   # datetime 제거
data = {}                   # last_updated 제거
```

**부수 효과:** `datetime.now()` 타임존 미고려 문제(M-1)도 함께 해소.

---

### M-2 수정 — 새로고침 실패 시 사용자 피드백 추가

**수정 파일:** `static/js/refactors/layout.js` `handleRefresh()` catch 블록

| 단계 | 내용 |
|------|------|
| 원인 | catch 블록이 완전히 비어 있어 실패 시 사용자에게 아무 피드백 없음 |
| 수정 | 버튼 색상 적색 전환 + tooltip 메시지 3초 표시 후 원복 |

```javascript
// layout.js — catch 수정 후
} catch {
  if (btn) {
    btn.style.color = 'var(--danger)';
    btn.title = '새로고침 실패 — 잠시 후 다시 시도하세요';
    setTimeout(() => { btn.style.color = ''; btn.title = '새로고침'; }, 3000);
  }
}
```

**검증:** `finally` 블록에서 `.spinning` 제거가 보장되므로 catch 후에도 스피너는 정상 종료됨.

---

## `handleRefresh()` 최종 동작 흐름

```
[새로고침 버튼 클릭]
  → isRefreshing 체크 → 진행 중이면 무시
  → isRefreshing = true, 스피너 시작
  → GET /dashboard/api/refresh/
      ├─ 401 → 로그인 리다이렉트
      ├─ 성공
      │    → data.admin_url 있으면 Header.adminUrl 갱신
      │    → updateLastUpdated() — 클라이언트 현재 시각 표시
      │    → EventPanel.loadEventList() — 이벤트 목록 재조회
      └─ 실패 (네트워크 오류 등)
           → 버튼 적색 + tooltip 3초 표시 후 원복
  → finally: isRefreshing = false, 스피너 종료
```

---

## 관리자 버튼 `adminUrl` 초기화 흐름 (수정 후)

```
페이지 로드
  → initHeaderAndSNB() → GET /api/auth/me/
     응답: { username, role, menu_tree, admin_url }  ← 관리자만
  → if (user.admin_url) Header.adminUrl = user.admin_url  ← 즉시 설정

새로고침 버튼 클릭
  → GET /dashboard/api/refresh/
     응답: { admin_url }  ← 관리자만 (URL 동기화)
  → Header.adminUrl 갱신 유지

관리자 버튼 클릭
  → handleAdmin()
  → this.adminUrl → 항상 올바른 백오피스 URL 이동 ✅
```
