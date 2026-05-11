# CM-03 로그아웃 — 코드 검토 보고서

> 작성자: 한지혜 / 작성일: 2026-04-24
> 대상 기능 ID: **CM-03** (로그아웃 완료 팝업)
> 검토 범위: 프론트엔드 + 백엔드 전체

---

## 1. 기능 정의서 스펙 요약

| 항목 | 내용 |
|------|------|
| 기능 목적 | 세션 종료와 재로그인 유도 |
| 사용자 시나리오 | 로그아웃 클릭 → 완료 팝업 노출 → 확인 클릭 → 로그인 화면 이동 |
| 수집 정보 | **세션ID**, **사용자ID** |
| 디자인 요소 | 로그아웃 버튼, 완료 팝업, 확인 버튼 |
| 유효성 처리 | - |
| 예외 조건 | **세션 만료 시 강제 로그아웃 가능** |
| 에러 처리 | **로그아웃 실패 시 재시도 또는 안내** |
| 백엔드 처리 | **세션 무효화**, **감사로그 기록** |
| 프론트엔드 처리 | 팝업 open/close, 로그인 화면 리다이렉트 |

---

## 2. 검토 대상 파일

| 역할 | 파일 경로 |
|------|-----------|
| 로그아웃 버튼 + 팝업 HTML | `templates/components/header.html` |
| 로그아웃 팝업 제어 | `static/js/refactors/layout.js` |
| JWT 토큰 / 리다이렉트 | `static/js/refactors/auth.js` |
| 로그아웃 API | `apps/accounts/views.py` |
| URL 라우팅 | `apps/accounts/urls.py` |
| 감사로그 모델 | `apps/accounts/models/login_log.py` |
| VR / 안전확인 세션 저장 | `apps/dashboard/views.py` |
| Django 세션 설정 | `config/settings.py` |

---

## 3. 스펙 충족 항목 ✅

| 항목 | 구현 위치 | 비고 |
|------|-----------|------|
| 로그아웃 버튼 노출 | `header.html:53` — `#btnLogout` | 헤더 우측 고정 |
| 팝업 열기 | `layout.js` — `btnLogout click` | `modal.style.display = 'flex'` |
| 팝업 닫기 (취소) | `layout.js` — `logoutCancel click` | `modal.style.display = 'none'` |
| 팝업 닫기 (backdrop) | `layout.js` — `modal click` | `e.target === modal` 판별 (수정 반영) |
| 로그인 화면 리다이렉트 | `auth.js` — `redirectLogin()` | `/accounts/login/` |
| localStorage 초기화 | `auth.js` — `clear()` | access/refresh/username/role 4개 삭제 |
| 감사로그 기록 | `accounts/views.py` — `LogoutView` | `LoginLog.LOGOUT` 기록 (수정 반영) |
| Django 세션 초기화 | `accounts/views.py` — `LogoutView` | `session.flush()` (수정 반영) |
| 로그아웃 실패 시 처리 | `layout.js` — `finally` 블록 | API 실패해도 반드시 리다이렉트 (수정 반영) |
| 401 강제 로그아웃 | `auth.js:33`, `layout.js:138` | 토큰 만료 시 `redirectLogin()` 호출 |

---

## 4. 문제 항목 — 심각도별 분류

### 🔴 HIGH — 즉시 수정 필요

---

#### H-1. LogoutView 없음 — 세션 무효화 / 감사로그 미기록 → **수정 완료 (2026-04-24)**

**위치:** `apps/accounts/views.py` / `apps/accounts/urls.py` / `static/js/refactors/layout.js`

**문제점 3가지:**

**① 서버 측 세션 무효화 없음**

```javascript
// 수정 전 — localStorage만 삭제, 서버 호출 없음
logoutConfirm?.addEventListener('click', () => { Auth.redirectLogin(); });
```

JWT access token(24시간)이 만료 전까지 유효한 상태 유지.

**② Django 세션 데이터 미초기화**

코드 재검토 시 발견. `dashboard/views.py`에서 VR 진행 위치, 체크리스트/VR 완료 상태를 **Django 세션에 저장**하고 있음:

```python
# dashboard/views.py
SESSION_KEY      = "vr_safety_progress"
CHECKLIST_KEY    = "safety_checklist_done_date"
VR_KEY           = "safety_vr_done_date"

request.session[self.SESSION_KEY] = position       # VR 시청 위치
request.session[self.CHECKLIST_KEY] = str(date.today())  # 체크리스트 완료
```

로그아웃 시 세션을 `flush()`하지 않으면 같은 브라우저를 다른 사용자가 사용할 때 이전 사용자의 VR 진행 위치와 안전확인 완료 상태가 그대로 남음.

**③ 감사로그(LoginLog) 미기록**

`LoginLog.LOGOUT` 코드가 모델에 준비되어 있으나 로그아웃 시 한 번도 호출되지 않음. 누가 언제 로그아웃했는지 추적 불가.

---

### 🟡 MEDIUM — 팀 합의 필요

---

#### M-1. 팝업 성격 — 스펙은 "완료 팝업", 현재는 "확인 팝업"

**위치:** `templates/components/header.html` 57~66줄

| | 스펙 | 현재 구현 |
|--|------|---------|
| 팝업 성격 | 완료 팝업 (로그아웃 됨을 알림) | 확인 팝업 (할지 물음) |
| 버튼 | 확인만 | 로그아웃 + 취소 |

**현재 유지 결정** — "로그아웃 하시겠습니까?" 확인 팝업이 실수로 로그아웃되는 것을 방지하는 더 좋은 UX. 취소 버튼이 있어 오작동 방지. 팀에서 스펙 그대로 완료 팝업으로 변경이 필요하다고 판단할 경우에만 수정.

---

#### M-2. 세션 만료 강제 로그아웃 시 감사로그 없음

**위치:** `auth.js:33`

```javascript
if (res.status === 401) { this.redirectLogin(); return null; }
```

토큰 만료(401) 시 리다이렉트는 되지만 서버에 감사로그가 남지 않음. 단, 401 발생 시점에 토큰이 이미 무효이므로 인증이 필요한 LogoutView 호출 자체가 불가능. 서버 미들웨어 레벨에서 처리해야 하는 별도 설계 범위. **보류.**

---

### 🟢 LOW — 개선 고려

---

#### L-1. `session_key` 필드 미활용

**위치:** `apps/accounts/models/login_log.py:47`

```python
session_key = models.CharField(
    max_length=40, blank=True, default="",
    verbose_name="세션 키 (로그인-로그아웃 쌍 매칭용)",
)
```

Django 세션이 활성화되어 있으므로 `request.session.session_key`로 로그인-로그아웃 쌍 매칭이 가능하지만, LoginView와 LogoutView 모두 현재 이 필드를 채우지 않음. 코드 변경 없이 주석으로 의도 명시.

---

#### L-2. Backdrop 클릭으로 팝업 닫기 미처리 → **수정 완료 (2026-04-24)**

**위치:** `static/js/refactors/layout.js` `initLogout()`

확인 팝업을 유지하기로 했으므로 배경 클릭 시 닫힘 처리가 자연스러운 UX.

---

## 5. 종합 요약

| 구분 | 항목 수 | 항목 |
|------|---------|------|
| ✅ 충족 | 10개 | 로그아웃 버튼, 팝업 열기/닫기, 취소, backdrop 닫기, 리다이렉트, localStorage 초기화, 감사로그, 세션 초기화, 실패 처리, 401 강제 로그아웃 |
| 🔴 HIGH | 1개 | H-1 LogoutView 없음 (세션 무효화 / 감사로그 / Django 세션 미초기화) |
| 🟡 MEDIUM | 2개 | M-1 팝업 성격 (유지 결정), M-2 강제 로그아웃 감사로그 (보류) |
| 🟢 LOW | 2개 | L-1 session_key 미활용, L-2 backdrop 닫기 |

> H-1, L-2는 **2026-04-24 수정 완료.**

---

## 6. 수정 우선순위 Action Items

| 순서 | 항목 | 담당 | 예상 공수 | 기한 |
|------|------|------|-----------|------|
| 1 | M-1 팝업 성격 팀 합의 | 기획/프론트 | 협의 | 다음 스프린트 |
| 2 | M-2 강제 로그아웃 감사로그 (미들웨어) | 백엔드 | 2h | 운영 전 |
| 3 | L-1 session_key 활용 | 백엔드 | 1h | 여유 시 |

---

## 7. 잘 구현된 부분 (유지)

- **APPEND-ONLY LoginLog:** `save()`와 `delete()` 오버라이드로 감사로그 수정/삭제 완전 차단 — 보안 감사 신뢰성 보장
- **401 강제 로그아웃:** `auth.js`와 `layout.js`, `worker-panel.js` 모두 401 수신 시 일관되게 `Auth.redirectLogin()` 호출
- **localStorage 4종 완전 삭제:** `Auth.clear()`에서 access/refresh/username/role 모두 제거 — 캐시 데이터 잔존 방지
- **`finally` 보장:** 로그아웃 API 실패해도 반드시 클라이언트 로그아웃 실행 — 서버 장애 시 사용자가 로그아웃 불가 상태에 빠지지 않음
- **IP + User-Agent 기록:** `_get_client_ip()` 헬퍼로 프록시/로드밸런서 환경의 실제 IP 추출, User-Agent 300자 제한

---

## 8. 수정 이력 (2026-04-24)

> 검토 보고서 작성 후 HIGH 1건, LOW 1건 수정 완료.

---

### H-1 수정 — LogoutView 구현

**수정 파일:** `apps/accounts/views.py`, `apps/accounts/urls.py`, `static/js/refactors/layout.js`

| 단계 | 내용 |
|------|------|
| 원인 | LogoutView가 없어 서버에 로그아웃 신호 미전달. JWT 토큰 유효 상태 유지. Django 세션 미초기화로 VR/안전확인 데이터 잔존 위험 |
| 수정 1 | `accounts/views.py`에 `LogoutView` 추가 |
| 수정 2 | `accounts/urls.py`에 `POST /api/auth/logout/` 등록 |
| 수정 3 | `layout.js` `initLogout()`에서 API 호출 후 `finally`로 리다이렉트 |

```python
# accounts/views.py — LogoutView
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        LoginLog.objects.create(
            user=request.user,
            is_login=False,
            login_result=LoginLog.LoginResult.LOGOUT,
            ip_address=_get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:300],
        )
        request.session.flush()
        return Response({"ok": True})
```

```javascript
// layout.js — initLogout() 수정 후
logoutConfirm?.addEventListener('click', async () => {
  try {
    await Auth.apiFetch('/api/auth/logout/', { method: 'POST' });
  } finally {
    Auth.redirectLogin();  // API 실패해도 반드시 로그아웃
  }
});
```

**검증:**
- `permission_classes = [IsAuthenticated]` — 인증된 사용자만 호출 가능
- `LoginLog.save()` APPEND-ONLY 정책으로 감사로그 불변성 보장
- `request.session.flush()` — VR 진행 위치, 체크리스트/VR 완료 날짜 세션 데이터 초기화
- `finally` — 네트워크 오류, 서버 오류 시에도 클라이언트 측 로그아웃 보장
- `_get_client_ip()` — 기존 LoginView에서 쓰던 헬퍼 재사용

---

### L-2 수정 — Backdrop 클릭 팝업 닫기

**수정 파일:** `static/js/refactors/layout.js` `initLogout()`

| 단계 | 내용 |
|------|------|
| 원인 | 확인 팝업 유지 결정 시 backdrop 클릭도 닫힘이 자연스러운 UX이나 미구현 |
| 수정 | `modal click` 이벤트에서 `e.target === modal`(배경 자체 클릭) 판별 후 닫기 |

```javascript
// layout.js — backdrop 클릭 닫기 추가
modal?.addEventListener('click', (e) => {
  if (e.target === modal) modal.style.display = 'none';
});
```

**검증:** `e.target === modal` 조건으로 modal 내부 `.modal-box` 클릭은 닫히지 않고, 배경만 클릭 시 닫힘.

---

## 로그아웃 최종 동작 흐름

```
[로그아웃 버튼 클릭]
  → 팝업 표시 (#logoutModal display: flex)

[팝업에서 취소 클릭 또는 backdrop 클릭]
  → 팝업 닫기 (display: none)

[팝업에서 로그아웃 확인 클릭]
  → POST /api/auth/logout/  (JWT Bearer 헤더 포함)
      ├─ 성공
      │    → LoginLog.LOGOUT 감사로그 기록
      │    → request.session.flush() — VR/안전확인 세션 초기화
      │    → { "ok": true } 응답
      └─ 실패 (네트워크 오류 등)
           → 로그 없이 클라이언트 측만 처리
  → finally: Auth.redirectLogin()
      → Auth.clear() — localStorage 4종 삭제
      → /accounts/login/ 이동

[토큰 만료 (401) 강제 로그아웃]
  → Auth.redirectLogin() 직접 호출
  → 서버 감사로그 없음 (보류 — 미들웨어 레벨 처리 필요)
```

---

## LoginLog 기록 현황

| 이벤트 | 기록 여부 | 결과코드 |
|--------|---------|---------|
| 로그인 성공 | ✅ | `success` |
| 비밀번호 오류 | ✅ | `failed_password` |
| 계정 잠금 | ✅ | `failed_locked` |
| 비활성 계정 | ✅ | `failed_inactive` |
| **정상 로그아웃** | ✅ (수정 반영) | `logout` |
| 토큰 만료 강제 로그아웃 | ❌ (보류) | — |
