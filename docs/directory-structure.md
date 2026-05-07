# diconai — 디렉토리 구조

> 기준일: 2026-05-07 / 브랜치: feature/project_4_refactoring_docstring

---

```
diconai/                              # 프로젝트 루트
│
├── docs/                             # 프로젝트 전체 공통 문서
│   ├── directory-structure.md        # 디렉토리 구조 (현재 파일)
│   ├── url-structure.md              # URL 설계 구조
│   ├── dev_convention.md             # 개발 컨벤션
│   ├── github_convention.md          # GitHub 컨벤션
│   └── COMMANDS.md
│
├── drf-server/                       # Django REST Framework 서버 (포트 8000)
│   └── [하단 상세 참조]
│
└── fastapi-server/                   # FastAPI 비동기 서버 (포트 8001)
    └── [하단 상세 참조]
```

---

## drf-server/ (Django, 포트 8000)

```
drf-server/
├── manage.py
├── config/                           # Django 프로젝트 설정
│   ├── settings.py
│   ├── urls.py                       # 루트 URL 라우터
│   ├── admin_panel_urls.py           # 어드민 패널 HTML 페이지 라우터
│   ├── asgi.py
│   ├── celery.py
│   └── wsgi.py
│
├── apps/
│   │
│   ├── accounts/                     # 사용자 인증·조직
│   │   ├── models/
│   │   │   ├── user.py               # CustomUser
│   │   │   ├── company.py
│   │   │   ├── department.py
│   │   │   ├── position.py
│   │   │   ├── user_department.py
│   │   │   └── login_log.py
│   │   ├── serializers/
│   │   │   ├── admin_serializers.py
│   │   │   ├── auth_serializers.py
│   │   │   └── org_serializers.py
│   │   ├── views/
│   │   │   ├── admin_views.py        # 사용자 관리 어드민 API
│   │   │   ├── auth_views.py         # 로그인/로그아웃/JWT
│   │   │   └── org_views.py          # 조직 관리 API
│   │   ├── selectors/
│   │   ├── services/
│   │   ├── admin_urls.py             # /api/admin/accounts|organizations|departments/
│   │   └── urls.py                   # /accounts/login/, /api/auth/
│   │
│   ├── alerts/                       # 알람·이벤트
│   │   ├── models/
│   │   │   ├── alarm_record.py       # AlarmRecord
│   │   │   ├── event.py              # Event (ACTIVE → RESOLVED)
│   │   │   └── event_log.py          # EventLog (이력)
│   │   ├── selectors/
│   │   │   ├── active_events.py
│   │   │   ├── alarm_timeline.py
│   │   │   └── event_history.py
│   │   ├── services/
│   │   │   ├── alarm_service.py
│   │   │   ├── event_service.py      # create_alarm_and_event, resolve_event
│   │   │   └── merge_policy.py
│   │   ├── serializers/
│   │   │   ├── alarm_record.py
│   │   │   ├── event.py
│   │   │   └── responses.py          # 응답 전용 시리얼라이저
│   │   ├── views/
│   │   │   ├── alarm_record.py       # AlarmRecordViewSet, MyStatusView, WorkerSummaryView
│   │   │   └── event.py              # EventViewSet
│   │   ├── tasks.py                  # Celery 태스크 (알람 생성 등)
│   │   └── urls.py                   # /alerts/api/alarms|events/
│   │
│   ├── core/                         # 공통 유틸·시스템 로그
│   │   ├── models/
│   │   │   ├── base.py
│   │   │   └── system_log.py
│   │   ├── selectors/audit_trail.py
│   │   ├── services/audit_service.py
│   │   ├── management/commands/
│   │   │   └── seed_dummy_data.py    # 더미 데이터 시드
│   │   ├── constants.py
│   │   ├── context_processors.py     # 템플릿 공통 컨텍스트
│   │   ├── exceptions.py             # 커스텀 예외
│   │   ├── mixins.py
│   │   ├── pagination.py
│   │   ├── permissions.py
│   │   └── validators.py
│   │
│   ├── dashboard/                    # 대시보드 HTML 렌더링
│   │   ├── menu.py
│   │   ├── views.py
│   │   └── urls.py                   # /dashboard/
│   │
│   ├── facilities/                   # 설비·장치·임계값 마스터
│   │   ├── models/
│   │   │   ├── facility.py
│   │   │   ├── devices.py            # GasSensor, PowerDevice
│   │   │   ├── equipment.py
│   │   │   ├── thresholds.py
│   │   │   ├── gas_sensor_inspection.py
│   │   │   └── power_device_inspection.py
│   │   ├── selectors/
│   │   │   ├── active_devices.py
│   │   │   └── admin_devices.py
│   │   ├── services/
│   │   │   ├── device_service.py
│   │   │   └── threshold_service.py
│   │   ├── serializers/
│   │   │   ├── facility_admin.py
│   │   │   ├── gas_sensor_admin.py
│   │   │   ├── map_editor.py
│   │   │   └── power_device_admin.py
│   │   ├── views/
│   │   │   ├── facility_admin.py
│   │   │   ├── gas_sensor_admin.py
│   │   │   ├── map_editor.py
│   │   │   └── power_device_admin.py
│   │   └── urls.py                   # /api/facilities|gas-sensors|power-devices|map-editor/
│   │
│   ├── geofence/                     # 지오펜스 관리
│   │   ├── models/geofence.py
│   │   ├── selectors/geofence_candidates.py
│   │   ├── services/geofence_service.py
│   │   ├── serializers/
│   │   │   ├── serializers.py
│   │   │   └── admin_serializers.py
│   │   ├── views/
│   │   │   ├── geofence_views.py     # GeoFenceViewSet
│   │   │   └── admin_views.py        # GeoFenceAdminPageView, GeoFenceAdminListView
│   │   ├── admin_urls.py             # (Django admin 전용 — 미사용 가능성)
│   │   ├── urls.py                   # /api/geofences/, /api/admin/geofences/
│   │   └── validators.py
│   │
│   ├── monitoring/                   # 가스·전력 센서 데이터 수집
│   │   ├── models/
│   │   │   ├── gas_data.py           # GasData (9종 가스 wide-table)
│   │   │   ├── power_data.py         # PowerData (long-format)
│   │   │   └── power_event.py        # PowerEvent (ON/OFF 스냅샷)
│   │   ├── collectors/
│   │   │   ├── gas_collector.py
│   │   │   └── power_collector.py
│   │   ├── selectors/
│   │   │   ├── latest_readings.py
│   │   │   └── time_range_data.py
│   │   ├── services/
│   │   │   ├── aggregation_service.py
│   │   │   ├── gas_alarm.py
│   │   │   └── power_alarm.py
│   │   ├── serializers/
│   │   │   ├── gas_data.py
│   │   │   └── power_data.py
│   │   ├── views/
│   │   │   ├── admin_views.py        # 어드민 공통 뷰
│   │   │   ├── gas_data.py           # GasDataCreateView
│   │   │   ├── gas_data_admin.py     # GasDataAdminListView, Export, SensorList
│   │   │   ├── power_data.py         # PowerEventIngestView, PowerDataBulkIngestView
│   │   │   └── power_data_admin.py   # PowerDataAdminListView, Export, DeviceList
│   │   ├── utils/gas_thresholds.py
│   │   ├── validators.py
│   │   ├── admin_urls.py             # /api/admin/gas-data|power-data/
│   │   └── urls.py                   # /api/monitoring/gas|power/
│   │
│   ├── notifications/                # 알림 발송 (팝업·푸시·SMS)
│   │   ├── models/notification.py
│   │   ├── selectors/
│   │   │   ├── notification_history.py
│   │   │   └── unread_notifications.py
│   │   ├── services/
│   │   │   ├── notification_service.py
│   │   │   └── delivery/
│   │   │       ├── popup_delivery.py
│   │   │       ├── push_delivery.py
│   │   │       └── sms_delivery.py
│   │   ├── serializers/
│   │   └── views/
│   │
│   ├── positioning/                  # 작업자 위치 추적
│   │   ├── models/worker_position.py
│   │   ├── collectors/position_collector.py
│   │   ├── selectors/latest_positions.py
│   │   ├── services/position_service.py  # 지오펜스 근접 시만 DB 저장
│   │   ├── serializers/serializers.py
│   │   ├── views/position_views.py   # WorkerPositionReceiveView
│   │   └── urls.py                   # /api/positioning/receive/
│   │
│   └── safety/                       # 안전 점검 체크리스트
│       ├── models/safety.py
│       ├── selectors/completion_stats.py
│       ├── services/check_service.py
│       ├── serializers/
│       └── views/
│
├── docs/                             # drf-server 전용 문서 (리팩토링·기능 정의 등)
│
├── templates/
│   ├── auth/login.html
│   ├── components/
│   │   ├── header.html
│   │   ├── alarm_popup.html
│   │   ├── geofence_modal.html
│   │   └── admin_sidebar.html
│   ├── dashboard/
│   │   ├── main.html                 # ✅ 메인 대시보드
│   │   └── panels/
│   │       ├── event_panel.html
│   │       ├── gas_panel.html
│   │       ├── map_panel.html
│   │       ├── power_panel.html
│   │       └── safety_panel.html
│   ├── snb_details/
│   │   ├── monitoring_realtime.html
│   │   ├── monitoring_gas.html
│   │   ├── monitoring_power.html
│   │   ├── monitoring_workers.html
│   │   ├── monitoring_events.html
│   │   ├── event_detail.html
│   │   ├── safety_checklist.html
│   │   ├── safety_history.html
│   │   ├── safety_vr.html
│   │   └── my_profile.html
│   └── admin_panel/
│       ├── base.html
│       ├── accounts/accounts_main.html
│       ├── organizations/organizations_main.html
│       ├── data/
│       │   ├── gas_data.html
│       │   └── power_data.html
│       ├── facility/facility.html
│       ├── gas_sensor/gas_sensor.html
│       ├── geofence/geofence_list.html
│       ├── map_editor/map_editor.html
│       └── power_system/power_system.html
│
└── static/
    ├── css/
    │   ├── admin.css
    │   ├── dashboard.css
    │   ├── dashboard_CJY.css
    │   ├── auth/login.css
    │   ├── components/header.css
    │   ├── admin/
    │   │   ├── accounts.css
    │   │   ├── facility.css
    │   │   ├── gas_data.css
    │   │   ├── gas_sensor.css
    │   │   ├── geofence.css
    │   │   ├── map_editor.css
    │   │   ├── organizations.css
    │   │   ├── power_data.css
    │   │   └── power_system.css
    │   ├── detail/
    │   │   ├── event_monitoring.css
    │   │   ├── gas_monitoring.css
    │   │   ├── map_detail.css
    │   │   ├── monitoring_workers.css
    │   │   └── power_system.css
    │   └── snb_details/
    │       ├── my_profile.css
    │       ├── safety_checklist.css
    │       ├── safety_history.css
    │       └── safety_vr.css
    │
    └── js/
        ├── dashboard/                # 메인 대시보드
        │   ├── app.js                # 진입점
        │   ├── charts.js
        │   ├── websocket.js          # /ws/sensors/ 연결
        │   └── panels/
        │       ├── event-panel.js
        │       ├── gas-panel.js
        │       ├── map-panel.js
        │       └── worker-panel.js
        ├── shared/                   # 전 페이지 공통 모듈
        │   ├── alarm-popup.js
        │   ├── alarm-ws.js
        │   ├── app-sub.js
        │   ├── auth.js
        │   ├── layout.js
        │   ├── util.js
        │   └── worker-ws.js
        ├── detail/                   # SNB 상세 페이지
        │   ├── event_detail.js
        │   ├── event_list.js
        │   ├── gas_monitoring.js
        │   ├── map_detail.js
        │   ├── monitoring_workers.js
        │   ├── my_profile.js
        │   ├── power_system.js
        │   ├── safety_checklist.js
        │   ├── safety_history.js
        │   ├── safety_vr.js
        │   ├── ui-exception.js
        │   ├── websocket_gas.js
        │   └── websocket_power.js
        └── admin/                    # 어드민 패널
            ├── main.js
            ├── accounts/accounts.js
            ├── facility/facility.js
            ├── gas/gas_data.js
            ├── gas_sensor/gas_sensor.js
            ├── geofence/geofence.js
            ├── map_editor/map_editor.js
            ├── organizations/organizations.js
            ├── power/power_data.js
            └── power_system/power_system.js
```

---

## fastapi-server/ (FastAPI, 포트 8001)

```
fastapi-server/
├── app.py                            # 진입점 — uvicorn app:app --port 8001
│                                     # broadcast_loop: 5초마다 센서 브로드캐스트
│                                     # import alarm_flush_loop: 5초마다 새 알람 플러시
├── core/
│   ├── config.py                     # Pydantic Settings (DRF_BASE_URL 등)
│   └── gas_thresholds.py
│
├── gas/                              # 가스 센서 도메인
│   ├── routers/gas_router.py         # POST /api/sensors/info, /api/sensors/gas
│   ├── schemas/gas.py
│   └── services/gas_service.py       # DRF 전송 + state 갱신
│
├── power/                            # 전력 센서 도메인
│   ├── routers/power_router.py       # POST /api/power/onoff|current|voltage|watt
│   ├── schemas/power.py
│   └── services/power_service.py
│
├── positioning/                      # 작업자 위치 도메인
│   ├── routers/position_router.py    # POST /api/positioning/receive
│   │                                 # WS   /ws/positions/ (브라우저 스트리밍)
│   ├── schemas/position.py
│   └── services/position_service.py  # DRF 비동기 저장
│
├── websocket/                        # WebSocket 브로드캐스트 도메인
│   ├── state.py                      # 프로세스 공유 상태
│   │                                 #   worker_positions, active_alarms,
│   │                                 #   latest_gas_snapshot, power_latest
│   │                                 #   sensor_clients, worker_clients
│   ├── routers/ws_router.py          # WS /ws/sensors/ (브라우저)
│   │                                 # WS /ws/position/ (IoT 위치 장비)
│   └── services/broadcast.py         # build_broadcast_payload()
│
├── internal/                         # 내부 전용 (localhost only)
│   └── routers/
│       ├── alarm_router.py           # POST /internal/alarms/push/
│       │                             # Celery → FastAPI WS 브리지
│       └── scenario_router.py        # GET/POST /internal/scenario/mode
│                                     # 시나리오 모드 제어 (데모용)
│
├── services/                         # 외부 호출 클라이언트
│   └── drf_client.py                 # DRF 비동기 호출 헬퍼
│
├── docs/                             # fastapi-server 전용 문서
│
└── dummies/                          # 더미 데이터 전송 스크립트
    ├── gas_dummy.py
    ├── power_dummy.py
    └── position_dummy.py
```

---

## 앱 레이어 구조 (Django 앱 공통)

| 레이어 | 역할 |
|--------|------|
| `models/` | DB 스키마 정의 |
| `selectors/` | 읽기 전용 DB 조회 |
| `services/` | 비즈니스 로직·트랜잭션 |
| `serializers/` | API 입출력 변환·검증 |
| `views/` | 요청 수신 → 서비스 호출 → 응답 |

---

## 서버 역할 요약

| 서버 | 포트 | 주요 역할 |
|------|------|----------|
| `drf-server` | 8000 | 인증, HTML 렌더링, 데이터 영속성(DB), REST API |
| `fastapi-server` | 8001 | 센서 데이터 수신, WebSocket 브로드캐스트, Celery 브리지 |
