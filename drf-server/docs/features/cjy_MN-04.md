# MN-04 작업자 현황 패널 — 변경사항 기록

## 개요
작업자/관리자 분기 뷰, 30초 폴링, 에러 처리를 포함한 작업자 현황 패널 구현.

---

## 신규 파일

### `apps/alarms/urls.py`
```python
from django.urls import path
from .views import MyStatusView, WorkerSummaryView

urlpatterns = [
    path('my-status/',       MyStatusView.as_view(),      name='alarm-my-status'),
    path('worker-summary/',  WorkerSummaryView.as_view(), name='alarm-worker-summary'),
]
```

---

### `apps/alarms/views.py`
**핵심 로직:**
- `MyStatusView` (GET `/api/alarms/my-status/`): 요청자의 활성 알람 중 최고 위험도 반환. `(is_active, alarm_level)` 복합 인덱스 활용.
- `WorkerSummaryView` (GET `/api/alarms/worker-summary/`): 관리자 소속 공장 전체 집계. `worker_id__in` 단일 쿼리 후 파이썬 레벨 집계(N+1 방지).

```python
from collections import defaultdict
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from .models import AlarmRecord
from apps.accounts.models import CustomUser

LEVEL_PRIORITY = {'danger': 2, 'warning': 1}

class MyStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        active_levels = list(
            AlarmRecord.objects.filter(worker=request.user, is_active=True)
            .values_list('alarm_level', flat=True)
        )
        if not active_levels:
            status, active_alarm_level = 'normal', None
        elif 'danger' in active_levels:
            status, active_alarm_level = 'danger', 'danger'
        else:
            status, active_alarm_level = 'warning', 'warning'

        return Response({'status': 'success', 'code': 200, 'data': {
            'worker_id': request.user.id,
            'status': status,
            'active_alarm_level': active_alarm_level,
        }})


class WorkerSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.user_type != 'admin':
            raise PermissionDenied('접근 권한이 없습니다.')

        facility = request.user.facility
        facility_id = facility.id if facility else None
        if not facility_id:
            return Response({'status': 'success', 'code': 200, 'data': {
                'facility_id': None, 'total_count': 0,
                'normal_count': 0, 'warning_count': 0, 'danger_count': 0,
            }})

        worker_ids = list(
            CustomUser.objects.filter(facility_id=facility_id, user_type='worker')
            .values_list('id', flat=True)
        )
        total_count = len(worker_ids)
        if total_count == 0:
            return Response({'status': 'success', 'code': 200, 'data': {
                'facility_id': facility_id, 'total_count': 0,
                'normal_count': 0, 'warning_count': 0, 'danger_count': 0,
            }})

        active_alarms = AlarmRecord.objects.filter(
            worker_id__in=worker_ids, is_active=True
        ).values('worker_id', 'alarm_level')

        worker_max = defaultdict(lambda: None)
        for a in active_alarms:
            wid, lvl = a['worker_id'], a['alarm_level']
            if worker_max[wid] is None or LEVEL_PRIORITY[lvl] > LEVEL_PRIORITY.get(worker_max[wid], 0):
                worker_max[wid] = lvl

        danger_count  = sum(1 for wid in worker_ids if worker_max[wid] == 'danger')
        warning_count = sum(1 for wid in worker_ids if worker_max[wid] == 'warning')
        normal_count  = total_count - danger_count - warning_count

        return Response({'status': 'success', 'code': 200, 'data': {
            'facility_id': facility_id, 'total_count': total_count,
            'normal_count': normal_count, 'warning_count': warning_count,
            'danger_count': danger_count,
        }})
```

---

### `static/css/CJY.css`
MN-04 패널 전용 스타일. 주요 클래스:
- `.mn04-status-bar-wrap` / `.mn04-status-bar` / `.mn04-marker` — 작업자 가로 상태 바
- `.mn04-kpi-grid` / `.mn04-kpi-card` — 관리자 KPI 카드 2×2 그리드
- `.mn04-kpi-danger` — 위험 카드 상시 강조 (`#FCEBEB` bg, `#F7C1C1` border, `#A32D2D` text, `26px` font)
- `.mn04-ratio-bar` — 미니 비율 바 (flex 비율 동적 변경)

---

### `static/js/CJY.js`
MN-04 패널 동작 로직. 주요 사항:
- `localStorage.user_type` → `'worker'`면 B View, `'admin'`이면 D View 렌더링
- `fetch('/api/alarms/my-status/')` / `fetch('/api/alarms/worker-summary/')` — `credentials: 'same-origin'`
- `setInterval(fetch, 30_000)` — 30초 폴링, 에러 시에도 유지
- `403` 응답 → "접근 권한이 없습니다" 표시
- 네트워크 오류 → "데이터를 불러오지 못했습니다" + 수치 `-`
- 상세 보기 클릭 → `window.location.href = '/snb-09/'`
- 미니 비율 바: `element.style.flex = count` (zero state 시 바 숨김)
- 마커 위치: `normal → left:16%`, `warning → left:50%`, `danger → left:84%`

---

## 변경된 파일

### `config/urls.py`
추가된 내용:
```python
from django.urls import path, include

# 추가된 URL 패턴
path("dashboard-cjy/", dashboard_cjy),          # CJY 대시보드 뷰
path("api/alarms/", include("apps.alarms.urls")), # MN-04 API 연결
```

---

### `templates/dashboard_CJY.html`

#### 1. `<head>` — CJY.css 추가
```html
<link rel="stylesheet" href="{% static 'css/CJY.css' %}">
```

#### 2. 패널 11 교체 (기존 도넛 차트 → MN-04 분기 뷰)
기존:
```html
<div class="panel">
  <div class="panel-title">작업자 현황 <span class="more">+ 상세 보기</span></div>
  <div class="donut-wrap"> ... </div>
</div>
```
변경 후: B View(가로 상태 바) + D View(KPI 카드) 구조로 교체.
ID 목록: `mn04-btn-detail`, `mn04-view-worker`, `mn04-marker`, `mn04-status-text`,
`mn04-worker-error`, `mn04-view-admin`, `mn04-kpi-total/normal/warning/danger`,
`mn04-ratio-bar`, `mn04-ratio-normal/warning/danger`, `mn04-admin-error`

#### 3. `</body>` 직전 — CJY.js 추가
```html
<script src="{% static 'js/CJY.js' %}"></script>
```
