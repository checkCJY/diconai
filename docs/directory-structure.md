# diconai — 디렉토리 구조

> 기준일: 2026-04-25 / 브랜치: devleop
> Phase 3 리팩토링 완료 + Phase 4 P0·P1 수정 반영

---

```
diconai/                              # 프로젝트 루트
│
├── docs/                             # 프로젝트 전체 공통 문서
│   ├── directory-structure.md        # 디렉토리 구조 (현재 파일)
│   ├── url-structure.md              # URL 설계 구조
│   ├── dev_convention.md             # 개발 컨벤션
│   └── github_convention.md          # GitHub 협업 컨벤션
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
├── requirements.txt
├── db.sqlite3                        # 개발용 SQLite (Git 제외)
├── .env                              # 환경변수 — SECRET_KEY, DB 등 (Git 제외)
├── .env.example
│
├── config/                           # Django 프로젝트 설정
│   ├── settings.py                   # 전역 설정
│   ├── urls.py                       # 루트 URL 라우터
│   ├── asgi.py
│   └── wsgi.py
│
├── apps/                             # Django 앱 모음
│   │
│   ├── accounts/                     # 사용자 인증
│   │   ├── models/
│   │   │   ├── user.py               # CustomUser, UserProfile
│   │   │   └── login_log.py          # LoginLog
│   │   ├── selectors/
│   │   ├── services/
│   │   ├── serializers.py
│   │   ├── views.py
│   │   └── urls.py
│   │
│   ├── alerts/                       # 알람·이벤트
│   │   ├── models/
│   │   │   ├── alarm_record.py       # 알람 레코드
│   │   │   ├── event.py              # 이벤트 (ACTIVE → RESOLVED 상태 관리)
│   │   │   └── event_log.py          # 이벤트 히스토리
│   │   ├── selectors/
│   │   │   ├── active_events.py
│   │   │   ├── alarm_timeline.py
│   │   │   └── event_history.py
│   │   ├── services/
│   │   │   ├── alarm_service.py
│   │   │   ├── event_service.py      # create_alarm_and_event, resolve_event
│   │   │   └── merge_policy.py       # 이벤트 병합 정책
│   │   ├── serializers/
│   │   │   └── alarm_record.py
│   │   ├── views/
│   │   │   └── alarm_record.py       # AlarmRecordViewSet, EventResolveView
│   │   └── urls.py
│   │
│   ├── core/                         # 공통 유틸·시스템 로그
│   │   ├── models/
│   │   │   └── system_log.py
│   │   ├── selectors/
│   │   │   └── audit_trail.py
│   │   ├── services/
│   │   │   └── audit_service.py
│   │   ├── constants.py
│   │   ├── mixins.py
│   │   └── validators.py
│   │
│   ├── dashboard/                    # 대시보드 HTML 렌더링
│   │   ├── menu.py                   # 사이드바 메뉴 구조
│   │   ├── views.py
│   │   └── urls.py
│   │
│   ├── facilities/                   # 설비·장치·임계값 마스터
│   │   ├── models/
│   │   │   ├── facility.py
│   │   │   ├── devices.py            # GasSensor, PowerDevice
│   │   │   └── thresholds.py
│   │   ├── selectors/
│   │   ├── services/
│   │   │   ├── device_service.py
│   │   │   └── threshold_service.py
│   │   ├── serializers/
│   │   └── views/
│   │
│   ├── geofence/                     # 지오펜스 관리
│   │   ├── models/
│   │   │   └── geofence.py
│   │   ├── selectors/
│   │   │   └── geofence_candidates.py
│   │   ├── services/
│   │   │   └── geofence_service.py
│   │   ├── serializers/
│   │   ├── views/
│   │   │   ├── geofence_views.py     # GeoFenceViewSet
│   │   │   └── admin_views.py        # GeoFenceAdminPageView
│   │   ├── urls.py                   # /api/geofences/
│   │   ├── admin_urls.py             # /admin-panel/geofence/
│   │   └── validators.py
│   │
│   ├── monitoring/                   # 가스·전력 센서 데이터 수집
│   │   ├── models/
│   │   │   ├── gas_data.py           # GasData (9종 가스 wide-table)
│   │   │   ├── power_data.py         # PowerData (채널 정규화, long-format)
│   │   │   └── power_event.py        # PowerEvent (ON/OFF 스냅샷)
│   │   ├── collectors/
│   │   │   ├── gas_collector.py
│   │   │   └── power_collector.py
│   │   ├── selectors/
│   │   │   ├── latest_readings.py
│   │   │   └── time_range_data.py
│   │   ├── services/
│   │   │   ├── aggregation_service.py
│   │   │   └── gas_alarm.py
│   │   ├── serializers/
│   │   │   ├── gas_data.py
│   │   │   └── power_data.py         # PowerEventIngestSerializer, PowerDataBulkIngestSerializer
│   │   ├── views/
│   │   │   ├── gas_data.py           # GasDataCreateView
│   │   │   └── power_data.py         # PowerEventIngestView, PowerDataBulkIngestView
│   │   ├── utils/
│   │   │   └── gas_thresholds.py
│   │   ├── validators.py
│   │   └── urls.py                   # /api/monitoring/gas|power/*
│   │
│   ├── notifications/                # 알림 발송 (팝업·푸시·SMS)
│   │   ├── models/
│   │   │   └── notification.py
│   │   ├── selectors/
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
│   │   ├── models/
│   │   │   └── worker_position.py
│   │   ├── collectors/
│   │   │   └── position_collector.py
│   │   ├── selectors/
│   │   │   └── latest_positions.py
│   │   ├── services/
│   │   │   └── position_service.py   # 지오펜스 근접 시만 DB 저장
│   │   ├── serializers/
│   │   ├── views/
│   │   │   └── position_views.py     # WorkerPositionReceiveView
│   │   └── urls.py                   # /api/positioning/receive/
│   │
│   └── safety/                       # 안전 점검 체크리스트
│       ├── models/
│       │   └── safety.py
│       ├── selectors/
│       │   └── completion_stats.py
│       ├── services/
│       │   └── check_service.py
│       ├── serializers/
│       └── views/
│
├── templates/                        # Django HTML 템플릿
│   ├── main_dashboard.html           # ✅ 활성 메인 대시보드
│   ├── alarm_panel.html
│   ├── auth/
│   │   └── login.html
│   ├── components/
│   │   ├── header.html
│   │   └── alarm_popup.html
│   ├── snb_details/                  # 사이드바 상세 패널
│   │   ├── monitoring_realtime.html
│   │   ├── monitoring_gas.html
│   │   ├── monitoring_power.html
│   │   ├── monitoring_workers.html
│   │   ├── monitoring_events.html
│   │   ├── safety_checklist.html
│   │   ├── safety_history.html
│   │   └── safety_vr.html
│   ├── admin/
│   │   ├── main.html
│   │   └── geofence/
│   │       └── geofence_list.html
│   │
│   ├── main_dashboard_CJY.html       # ⚠️ 미사용 — Phase 4 삭제 예정
│   └── main_dashboard_jhh.html       # ⚠️ 미사용 — Phase 4 삭제 예정
│
└── static/                           # 정적 파일
    ├── css/
    │   ├── dashboard.css             # ✅ 활성
    │   ├── admin.css
    │   ├── auth/login.css
    │   ├── components/header.css
    │   ├── snb_details/
    │   │   ├── safety_checklist.css
    │   │   └── safety_vr.css
    │   ├── admin/geofence.css
    │   ├── detail/power_system.css   # ⚠️ 구 JS 전용 — Phase 4 검토 예정
    │   └── dashboard_CJY.css         # ⚠️ 미사용 — Phase 4 삭제 예정
    │
    └── js/
        ├── refactors/                # ✅ 활성 JS 모듈
        │   ├── app.js                # 앱 진입점
        │   ├── app-sub.js
        │   ├── auth.js               # 인증 처리
        │   ├── websocket.js          # WebSocket 연결 관리
        │   ├── charts.js             # 차트 렌더링
        │   ├── gas-panel.js          # 가스 센서 패널
        │   ├── map-panel.js          # 공장 지도 패널
        │   ├── worker-panel.js       # 작업자 위치 패널
        │   ├── event-panel.js        # 이벤트 패널
        │   ├── alarm-popup.js        # 알람 팝업 (확인 시 Event RESOLVED)
        │   ├── layout.js
        │   ├── util.js
        │   │
        │   ├── websocket_CJY.js      # ⚠️ 미사용 — Phase 4 삭제 예정
        │   ├── websocket_jhh.js      # ⚠️ 미사용 — Phase 4 삭제 예정
        │   ├── charts_CJY.js         # ⚠️ 미사용 — Phase 4 삭제 예정
        │   └── gas-panel_jhh.js      # ⚠️ 미사용 — Phase 4 삭제 예정
        │
        └── detail/                   # ⚠️ 구 구조 — Phase 4 검토 예정
            ├── power_system.js
            ├── websocket_power.js
            └── ui-exception.js
```

---

## fastapi-server/ (FastAPI, 포트 8001)

```
fastapi-server/
├── app.py                            # 진입점 — uvicorn app:app --port 8001
├── requirements.txt
│
├── core/                             # 서버 공통 설정·유틸
│   ├── config.py                     # Pydantic Settings (DRF_BASE_URL, DRF_SERVICE_TOKEN)
│   └── gas_thresholds.py             # 가스 임계치 계산 함수
│
├── gas/                              # 가스 센서 도메인
│   ├── routers/
│   │   └── gas_router.py             # POST /api/sensors/info, /api/sensors/gas
│   ├── schemas/
│   │   └── gas.py                    # GasDataPayload, DeviceInfoPayload
│   └── services/
│       └── gas_service.py            # DRF 전송 + state 직접 갱신
│
├── power/                            # 전력 센서 도메인
│   ├── routers/
│   │   └── power_router.py           # POST /api/power/onoff|current|voltage|watt
│   ├── schemas/
│   │   └── power.py                  # PowerOnOffPayload, PowerCurrentPayload 등
│   └── services/
│       └── power_service.py          # DRF 전송(BackgroundTask) + state 갱신
│                                     # build_equipment() — 채널 → 설비 조립
│
├── positioning/                      # 작업자 위치 도메인
│   ├── routers/
│   │   └── position_router.py        # WS /ws/positions/ — 더미 위치 브로드캐스트
│   ├── schemas/
│   │   └── position.py               # WorkerPositionSchema
│   └── services/
│       └── position_service.py       # DRF 저장 + 더미 작업자 시뮬레이션
│
├── websocket/                        # WebSocket 브로드캐스트 도메인
│   ├── state.py                      # 프로세스 공유 상태
│   │                                 #   worker_positions, active_alarms,
│   │                                 #   latest_gas_snapshot, power_latest
│   ├── routers/
│   │   └── ws_router.py              # WS /ws/sensors/ (브라우저)
│   │                                 # WS /ws/position/ (IoT 수신)
│   └── services/
│       └── broadcast.py              # build_broadcast_payload() 조립
│
└── dummies/                          # 더미 데이터 전송 스크립트
    ├── gas_dummy.py                  # python -m dummies.gas_dummy
    └── power_dummy.py                # python -m dummies.power_dummy
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
| `fastapi-server` | 8001 | 센서 데이터 수신, WebSocket 브로드캐스트 |

---

> ⚠️ **Phase 4 수정 예정 항목** (templates/css/js)
>
> 아래 파일은 현재 미사용 상태이며 Phase 4에서 삭제 또는 통합 예정입니다.
> - `templates/main_dashboard_CJY.html`
> - `templates/main_dashboard_jhh.html`
> - `static/js/refactors/websocket_CJY.js`
> - `static/js/refactors/websocket_jhh.js`
> - `static/js/refactors/charts_CJY.js`
> - `static/js/refactors/gas-panel_jhh.js`
> - `static/css/dashboard_CJY.css`
> - `static/js/detail/` 폴더 전체 (구 구조)
