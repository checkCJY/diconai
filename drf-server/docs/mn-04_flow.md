# MN-04 작업자 현황 패널 — 데이터 흐름도

---

## 전체 흐름 (공통 진입)

```
[브라우저]
  사용자가 /dashboard-cjy/ 접속
        ⬇
[config/urls.py]
  URL 매칭 → dashboard_cjy 뷰 함수 호출
        ⬇
[templates/dashboard_CJY.html]
  HTML 렌더링 (패널 11 포함)
  CSS / JS 로드
        ⬇
[static/js/CJY.js]  ← 진입점
  localStorage.user_type 읽기
        ⬇
  ┌─────────────────────────────────┐
  │  user_type == 'worker' ?        │
  └──────────┬──────────────┬───────┘
           YES              NO (admin)
             ⬇                ⬇
       [B View 흐름]     [D View 흐름]
```

---

## B View — 작업자 흐름

```
[static/js/CJY.js]
  #mn04-view-worker → display:flex 표시
  GET /api/alarms/my-status/ 호출
        ⬇
[config/urls.py]
  path("api/alarms/") → apps.alarms.urls include
        ⬇
[apps/alarms/urls.py]
  path("my-status/") → MyStatusView.as_view()
        ⬇
[apps/alarms/views.py — MyStatusView.get()]
  ① 권한 확인: IsAuthenticated (세션 쿠키)
  ② AlarmRecord 쿼리
       WHERE worker = request.user
         AND is_active = True
       → alarm_level 목록 반환
  ③ 우선순위 판단 (파이썬)
       alarm_level 목록이 비어있음 → status = 'normal'
       'danger' 포함됨            → status = 'danger'
       'warning' 만 있음          → status = 'warning'
        ⬇
[JSON 응답]
  {
    "status": "success",
    "code": 200,
    "data": {
      "worker_id": 1,
      "status": "normal" | "warning" | "danger",
      "active_alarm_level": null | "warning" | "danger"
    }
  }
        ⬇
[static/js/CJY.js — renderWorkerStatus()]
  data.status 값에 따라 DOM 업데이트
  ┌─────────────────────────────────────────┐
  │  status     마커 위치  색상     텍스트   │
  │  normal  →  left:16%  #2d9e75  정상     │
  │  warning →  left:50%  #ef9f27  경고     │
  │  danger  →  left:84%  #e24b4a  위험     │
  └─────────────────────────────────────────┘
  #mn04-marker     → left, color 변경
  #mn04-status-text → 텍스트, 색상 변경
        ⬇
[브라우저 화면]
  가로 상태 바 + 마커 위치로 현재 상태 시각화
        ⬇
[30초 후 반복]
  setInterval(fetchWorkerStatus, 30000)
```

---

## D View — 관리자 흐름

```
[static/js/CJY.js]
  #mn04-view-admin → display:flex 표시
  GET /api/alarms/worker-summary/ 호출
        ⬇
[config/urls.py]
  path("api/alarms/") → apps.alarms.urls include
        ⬇
[apps/alarms/urls.py]
  path("worker-summary/") → WorkerSummaryView.as_view()
        ⬇
[apps/alarms/views.py — WorkerSummaryView.get()]
  ① 권한 확인: IsAuthenticated
  ② user_type 확인
       != 'admin' → 403 PermissionDenied 즉시 반환
  ③ request.user.facility 조회
       facility is None → total_count: 0 반환
  ④ 작업자 목록 조회 (CustomUser)
       WHERE facility_id = 관리자.facility_id
         AND user_type = 'worker'
       → worker_ids = [1, 2, 3, ...]
       → total_count = len(worker_ids)
  ⑤ 활성 알람 일괄 조회 (AlarmRecord) ← N+1 방지
       WHERE worker_id IN worker_ids
         AND is_active = True
       → [(worker_id, alarm_level), ...] 전체 한 번에
  ⑥ 파이썬 레벨 집계 (defaultdict)
       작업자별 최고 위험도 산출
         danger  우선순위 2
         warning 우선순위 1
         없음    → normal
       danger_count  = danger  인원수
       warning_count = warning 인원수
       normal_count  = total - danger - warning
        ⬇
[JSON 응답]
  {
    "status": "success",
    "code": 200,
    "data": {
      "facility_id": 1,
      "total_count":   10,
      "normal_count":   6,
      "warning_count":  2,
      "danger_count":   2
    }
  }
        ⬇
[static/js/CJY.js — renderAdminSummary()]
  KPI 카드 텍스트 업데이트
  ┌──────────────────────────────────┐
  │  #mn04-kpi-total   → 10         │
  │  #mn04-kpi-normal  →  6         │
  │  #mn04-kpi-warning →  2         │
  │  #mn04-kpi-danger  →  2         │
  └──────────────────────────────────┘
  미니 비율 바 업데이트
    total == 0 → 바 숨김 (zero state)
    total  > 0 → 각 구간 flex 비율 설정
      .mn04-ratio-normal  → style.flex = 6
      .mn04-ratio-warning → style.flex = 2
      .mn04-ratio-danger  → style.flex = 2
        ⬇
[브라우저 화면]
  KPI 카드 4개 + 미니 비율 바 시각화
  위험 카드는 수치 무관 항상 강조 표시 (CSS)
        ⬇
[30초 후 반복]
  setInterval(fetchWorkerSummary, 30000)
```

---

## 에러 처리 흐름

```
[fetch 호출]
        ⬇
  ┌──────────────────────────────────────┐
  │  응답 상태 코드 분기                  │
  │                                      │
  │  200 OK  → 정상 렌더링               │
  │                                      │
  │  403     → "접근 권한이 없습니다"    │
  │            수치를 '-' 로 표시         │
  │                                      │
  │  그 외 / 네트워크 오류               │
  │          → "데이터를 불러오지        │
  │             못했습니다"              │
  │            수치를 '-' 로 표시         │
  └──────────────────────────────────────┘
        ⬇
  에러 상태에서도 setInterval 유지
  → 30초마다 자동 재시도
```

---

## 관련 파일 목록

| 순서 | 파일 | 역할 |
|------|------|------|
| 1 | `config/urls.py` | URL 라우팅 진입점 |
| 2 | `apps/alarms/urls.py` | API 엔드포인트 등록 |
| 3 | `apps/alarms/views.py` | 비즈니스 로직 + DB 조회 |
| 4 | `apps/alarms/models.py` | `AlarmRecord` (is_active, alarm_level) |
| 5 | `apps/accounts/models.py` | `CustomUser` (user_type, facility) |
| 6 | `templates/dashboard_CJY.html` | 패널 11 HTML 골격 |
| 7 | `static/css/CJY.css` | 패널 스타일 (마커, KPI 카드, 비율 바) |
| 8 | `static/js/CJY.js` | 뷰 분기 + API 호출 + DOM 업데이트 + 폴링 |
