# 트러블슈팅 — VR 교육 관리 + 안전 확인 이력 연동

> 작성일: 2026-05-12
> 작성자: CJY
> 브랜치: `feature/admin_safety_check`
> 관련 PR: 미생성 (로컬 브랜치)
> 관련 기능정의서: [cjy_VR교육관리_안전이력연동_기능정의서.md](cjy_VR교육관리_안전이력연동_기능정의서.md)

---

## 1. 개요

VR 교육 관리 어드민 페이지 + 안전 확인 이력 DB 연동 작업을 머지한 직후, 사용자(`admin`)가 다음 시나리오를 검증하던 중 **이력 캘린더에 VR 교육이 영구히 ✕(미완료)로 표시되는 현상**이 발생했다. 시나리오:

1. 메인 대시보드 진입 → 체크리스트 + VR 교육 모두 완료
2. 메인 대시보드 카드에는 "완료" 두 항목 표시
3. 이력 캘린더에서 오늘 날짜는 ✕ 안전 체크리스트 / ✕ VR 교육 / 다른 날은 "미출근"

원인은 **세 개의 독립적인 버그가 직렬로 겹쳐 있는 상태**였으며, 각각 해결하면서도 다음 단계 버그 때문에 증상이 계속 나타났다.

---

## 2. 영향 받은 화면 / 기능

| 화면 | 증상 |
|---|---|
| `/dashboard/` 메인 카드 "나의 안전 확인" | 정상 (완료 표시) — 세션 기반이라 영향 없음 |
| `/dashboard/safety/history/` 이력 캘린더 | 모든 날 "미출근" 또는 ✕ 표시 |
| `/dashboard/safety/vr/` 작업자 VR 페이지 | (별도 이슈) 영상이 안 보임 — 본 문서에서는 다루지 않고 별도 항목 |

---

## 3. 세 개의 직렬 버그

### 버그 ① — `safety.0012` 마이그레이션 미적용

#### 증상
이력 캘린더가 빈 데이터를 반환. Network 탭의 `GET /dashboard/api/safety-history/?month=2026-05` 응답이 비어 보임.

#### 원인
docker 컨테이너가 떠 있는 동안 `safety.0012_safetychecksession_vr_completed_at` 마이그레이션 파일이 추가되었다. entrypoint.sh가 컨테이너 **시작 시 1회**만 `migrate`를 실행하므로 컨테이너 라이프사이클 도중 추가된 마이그레이션은 자동 적용되지 않는다.

```
sqlite3.OperationalError: no such column: safety_check_session.vr_completed_at
```

SafetyHistoryAPIView가 컬럼 조회 단계에서 500을 뱉었고, 프런트의 빈 캘린더 fallback이 동작.

#### 진단
```bash
docker compose exec drf python manage.py showmigrations safety
# [ ] 0012_safetychecksession_vr_completed_at   ← 미적용
```

#### 해결
```bash
docker compose exec drf python manage.py migrate safety
# Applying safety.0012_safetychecksession_vr_completed_at... OK
```

#### 재발 방지
- `git pull` / 브랜치 전환 후 새 마이그레이션이 있는지 확인:
  ```bash
  docker compose exec drf python manage.py showmigrations | grep '\[ \]'
  ```
- 또는 컨테이너 재시작으로 entrypoint 재실행:
  ```bash
  docker compose restart drf
  ```
- 팀원 안내문 체크리스트에 **"브랜치 변경 후 migrate 1회"** 항목 추가.

---

### 버그 ② — `Auth.apiFetch` 대신 일반 `fetch` 사용 → JWT 헤더 누락

#### 증상
①을 해결한 뒤에도 이력 캘린더에 ✕ 표시 유지. admin이 다시 체크리스트/VR 완료를 했는데도 DB의 `SafetyCheckSession` 행이 한 건도 생성되지 않음.

#### 원인
[safety_checklist.js:183](drf-server/static/js/detail/safety_checklist.js#L183) / [safety_vr.js:208](drf-server/static/js/detail/safety_vr.js#L208)에서 완료 처리 시 일반 `fetch`를 사용했다.

```js
// 잘못된 코드 (수정 전)
await fetch('/dashboard/api/safety-status/', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ key: 'vr' }),
});
```

본 시스템은 **JWT-only 인증** 환경이라 클라이언트가 `Authorization: Bearer ...` 헤더를 수동으로 부착해야 하지만, 일반 `fetch`는 이 헤더가 자동으로 추가되지 않는다. 결과적으로:

- `MySafetyStatusView`의 `permission_classes = [AllowAny]`라 200 OK는 떨어짐
- 그러나 `request.user`가 `AnonymousUser`로 잡힘
- view 내부의 `if request.user.is_authenticated` 가드 때문에 `_record_completion_to_db`가 **silent skip**
- DB에 SafetyCheckSession이 만들어지지 않음 → 이력 캘린더 영구 ✕

이 패턴은 캘린더만 보면 절대 발견할 수 없다 — API 호출은 200 OK이고, 메인 카드(세션 키 기반)는 완료로 표시되기 때문에 사용자 입장에서는 모든 게 정상으로 보인다.

#### 진단
```python
# DB 상태 확인
SafetyCheckSession.objects.filter(worker__username='admin').count()
# 0  ← 완료 처리를 여러 번 했는데도 0건
```

같은 패턴이 다른 곳에도 있는지 grep:
```bash
grep -rn "fetch.*'/dashboard/api/" drf-server/static/js/ | grep -v "Auth.apiFetch"
# safety_checklist.js:183
# safety_vr.js:208
```

#### 해결
`Auth.apiFetch`로 교체. `Authorization` 헤더와 `Content-Type: application/json`이 자동으로 부착된다.

```js
// 수정 후
await Auth.apiFetch('/dashboard/api/safety-status/', {
  method: 'POST',
  body: JSON.stringify({ key: 'vr' }),
});
```

커밋: `7a0dddc`

#### 재발 방지

| 원칙 | 적용 |
|---|---|
| 인증이 필요한 모든 API 호출은 `Auth.apiFetch` 사용 | 코드 컨벤션에 명문화 |
| 일반 `fetch`는 정적 리소스·외부 API 한정 | grep 검증 가능 |
| `permission_classes` 결정 시 `AllowAny`는 신중하게 | 익명 호출 자체가 의미 있는 경우만. 그 외에는 `IsAuthenticated`로 401 명확히 |

특히 `AllowAny + is_authenticated 가드 + silent skip` 패턴은 **silent failure를 만드는 안티패턴**이다. silent skip 대신 401을 반환하면 클라이언트가 즉시 인지할 수 있었다.

---

### 버그 ③ — 프론트엔드 "VR 미연동" 하드코딩 잔류

#### 증상
②까지 해결되어 DB와 API 응답 모두 `vr_done: True`로 정상 반환되는데도 캘린더에는 12일이 ✓ 안전 체크리스트 / **✕ VR 교육**으로 표시됨.

#### 원인
[safety_history.js:325](drf-server/static/js/detail/safety_history.js#L325)에서 VR 교육 행을 그리는 함수에 **세 번째 인자 `true` (`notLinked`)** 가 박혀 있다.

```js
// 잘못된 코드 (수정 전)
wrap.appendChild(makeIndicatorRow(rec.checklist_done, '안전 체크리스트', false));
wrap.appendChild(makeIndicatorRow(rec.vr_done,        'VR 교육',         true));  // ← 하드코딩

function makeIndicatorRow(done, label, notLinked) {
  ...
  if (notLinked) {
    ic.className = 'ic ic-na';
    ic.textContent = '✕';     // done 값 무시
  } else {
    ic.textContent = done ? '○' : '✕';
  }
  ...
}
```

이력 API의 `vr_done`이 백엔드에서 영구히 `False` 하드코딩이었던 시절(이전 단계)의 **표시 일관성용 잔류 코드**다. 백엔드는 본 PR에서 `SafetyCheckSession.vr_completed_at` 기반으로 연동되었지만, 프론트는 그대로 ✕만 그리고 있었다.

같은 잔류가 다운로드 엑셀 행에도 있었다 (line 231, 358):
```js
rows.push([dateStr, r.checklist_done ? '완료' : '미완료', '미연동']);  // ← '미연동' 하드코딩
```

#### 진단
API 응답을 직접 호출해 확인.

```python
# Django shell
from rest_framework_simplejwt.tokens import RefreshToken
from apps.accounts.models import CustomUser
admin = CustomUser.objects.get(username='admin')
access = str(RefreshToken.for_user(admin).access_token)
import requests
r = requests.get(
    'http://localhost:8000/dashboard/api/safety-history/?month=2026-05',
    headers={'Authorization': f'Bearer {access}'},
)
[rec for rec in r.json()['records'] if rec['date'].endswith('-12')]
# [{'date': '2026-05-12', 'attended': True, 'checklist_done': True, 'vr_done': True}]
```

→ **API는 정상, UI 표시 로직이 범인** 확정.

#### 해결
`makeIndicatorRow` 시그니처에서 `notLinked` 인자 제거 + 다운로드 행의 `'미연동'`을 `r.vr_done ? '완료' : '미완료'`로 교체.

커밋: `714f231`

#### 재발 방지

retrofit(점진적 연동) 작업의 함정:
- 백엔드 하드코딩 → "임시 표시" 프론트 코드가 자연스럽게 만들어짐
- 백엔드 연동 시 그 프론트 코드가 같이 풀려야 화면이 동작
- **백엔드만 연동하고 PR을 닫으면 사용자 입장에서는 변화 없음**

체크리스트:
- [ ] 백엔드 하드코딩이 있다면 그 값을 소비하는 프론트 코드도 같이 grep해서 점검
- [ ] PR Description에 "이 PR로 풀리는 placeholder 표시" 섹션을 명시
- [ ] QA 시나리오에 "캘린더 ✓ 변화 확인"처럼 화면 기반 검증 포함

---

## 4. 진단 흐름 (시간순)

본 트러블슈팅을 처음 받았다고 가정하고 가장 효율적인 진단 순서:

```
사용자: "이력 캘린더가 ✕만 표시됩니다"
  │
  ▼
1. DB 상태 확인 — 가장 빠른 분기점
   docker compose exec drf python manage.py shell -c "
   from apps.safety.models import SafetyCheckSession
   print(SafetyCheckSession.objects.filter(worker__username='admin'))
   "
   │
   ├─ 에러(컬럼 없음)  → 버그 ① 마이그레이션 미적용
   │
   ├─ 빈 QuerySet     → 버그 ② dual-write 실패
   │                     · view·service 로직 점검
   │                     · 클라이언트 호출 방식 grep
   │
   └─ 정상 데이터     → 버그 ③ 프론트 표시 로직
                         · API 응답 직접 확인
                         · UI 렌더 함수 inspect
```

이 분기 트리만 있으면 향후 동일 증상에서 3분 안에 원인 분기를 잡을 수 있다.

---

## 5. 적용된 해결 커밋

| 커밋 | 메시지 | 변경 파일 |
|---|---|---|
| (수동 1회) | `migrate safety` | DB 스키마 |
| `7a0dddc` | fix : 안전 확인 완료 dual-write 누락 — fetch에 JWT 헤더 부착 | `safety_checklist.js`, `safety_vr.js` |
| `714f231` | fix : 이력 캘린더 VR 교육 컬럼이 항상 ✕로 표시되는 프론트 하드코딩 제거 | `safety_history.js` |

---

## 6. 검증

### 시나리오
1. `admin` 계정 로그인 → 브라우저 hard reload(Ctrl+Shift+R)
2. 메인 대시보드 → [나의 안전 확인 바로가기] → 체크리스트 모두 체크 → [다음] → [확인]
3. 자동으로 VR 페이지 이동 → 영상 끝까지 시청 → [완료] → [확인]
4. `/dashboard/safety/history/` 진입

### 기대 결과
- 오늘 날짜 셀에 ✓ 안전 체크리스트 / ✓ VR 교육
- DevTools Network → `safety-history/?month=...` 응답에 `vr_done: true`
- DB 확인:
  ```python
  SafetyCheckSession.objects.get(worker__username='admin', date=date.today())
  # is_completed=True, vr_completed_at IS NOT NULL
  ```

### 다운로드/인쇄
- "VR 교육" 컬럼이 `완료`/`미완료`로 정확히 출력 (이전: `미연동` 고정)

---

## 7. 교훈

### 7-1. Silent skip은 진단을 어렵게 한다
권한 가드를 `AllowAny + is_authenticated 분기 silent skip`로 처리하면 클라이언트는 200 OK를 받고 정상이라고 믿는다. 명확하게 `IsAuthenticated`로 401을 반환하거나, 로깅 레벨을 `warning` 이상으로 올려 운영 환경에서 즉시 탐지 가능하게 해야 한다.

### 7-2. retrofit 작업은 양쪽 코드를 함께 검토한다
백엔드의 "임시 하드코딩"을 풀 때, 그 값을 소비하는 프론트엔드 코드도 함께 검토하지 않으면 사용자 화면은 변하지 않는다. PR 작성 시 다음을 확인:
- `grep`으로 백엔드 키워드를 소비하는 프론트 코드 추적
- "이 PR로 풀리는 placeholder 표시" 섹션 PR 본문에 명시

### 7-3. 마이그레이션은 컨테이너 라이프사이클과 분리
도커 환경에서 `entrypoint.sh`의 자동 `migrate`는 **컨테이너 시작 시 1회**만 동작한다. 라이프사이클 도중 추가된 마이그레이션은 자동 적용되지 않는다. 팀 안내문에 다음을 포함:

```bash
# 새 브랜치 받은 직후 항상
docker compose exec drf python manage.py showmigrations | grep '\[ \]'
# 미적용이 있으면
docker compose exec drf python manage.py migrate
# 또는 컨테이너 재시작 (entrypoint 재실행)
docker compose restart drf
```

### 7-4. 데이터 소스가 둘이면 일관성 잠재 버그
세션 키와 DB라는 두 데이터 소스가 공존하면, 한쪽만 성공하고 다른 쪽이 silent fail해도 사용자 일부 화면은 정상 보인다 (메인 카드는 ✓, 이력은 ✗). dual-write 패턴은 다음을 확보해야 한다:
- 두 쪽 모두 실패하면 명확한 에러 응답
- 한 쪽만 성공하면 어떤 화면이 어긋날 수 있는지 PR 본문에 명시
- 정기 점검 쿼리로 두 소스 간 데이터 정합성 모니터링

---

## 8. 재발 방지 체크리스트

다음 작업에서 본 패턴을 회피하려면:

### 새 마이그레이션 추가 시
- [ ] 호스트에서 `docker compose exec drf python manage.py migrate` 실행해 확인
- [ ] PR 본문에 "마이그레이션 1건 포함 — 팀원은 `migrate` 필요" 명시

### 인증이 필요한 새 API 호출 추가 시
- [ ] 클라이언트는 반드시 `Auth.apiFetch` 사용
- [ ] view의 `permission_classes`는 `[IsAuthenticated, ...]` (AllowAny 신중)
- [ ] grep 검증: `grep -rn "fetch.*'/api/" static/js/ | grep -v Auth.apiFetch`

### 백엔드 하드코딩 풀 때
- [ ] 그 값을 소비하는 프론트 코드를 grep으로 찾아 함께 점검
- [ ] "임시 표시(미연동/준비중 등) 잔류 코드" 섹션 PR 본문에 명시
- [ ] QA 시나리오에 화면 기반 검증 포함 (코드 변경만으로 끝나지 않음)

### 새 dual-write 패턴 도입 시
- [ ] 두 데이터 소스의 silent fail 경로 분석
- [ ] 우선순위: 한쪽만 성공 시 어떤 화면이 어긋나는지 문서화
- [ ] 로그 레벨: 실패 시 최소 `warning` 이상
