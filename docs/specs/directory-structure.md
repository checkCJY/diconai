# diconai — 디렉토리 구조

> 기준일: 2026-05-19 / 브랜치: feature/power_zscore_cp

---

```
diconai/                              # 프로젝트 루트
│
├── docker-compose.yml                # 7-서비스 오케스트레이션 (drf + fastapi + redis + celery×2 + prom + grafana)
├── docker/                           # 인프라 자산
│   ├── grafana/provisioning/         # 대시보드·데이터소스 프로비저닝
│   └── prometheus/                   # prometheus.yml 등
│
├── Makefile                          # 컨테이너 lifecycle / lint / test 헬퍼
├── pyproject.toml · uv.lock          # 루트 가상환경 (관리용 only — 런타임은 컨테이너)
├── requirements.txt
├── main.py
├── .env.docker · .env.docker.example · .dockerignore
├── .pre-commit-config.yaml           # ruff + ruff-format (drf-server, fastapi-server `.py` 한정)
│
├── docs/                             # 프로젝트 전체 공통 문서
│   ├── specs/                        # 명세 (본 문서, URL 구조, API, JSON 필드)
│   ├── conventions/                  # dev/github/api response/docstring 컨벤션 + COMMANDS
│   ├── features/                     # 기능 정의서 (전력/가스/안전/공지 등)
│   ├── phases/                       # 단계별 plan & report (Phase 1~4, Post-Phase 4 B-track)
│   ├── changelog/                    # 단일 기능·웨이브 단위 변경 이력
│   ├── codereviews/                  # 코드리뷰 보고서 (날짜별)
│   ├── incidents/                    # 장애 리포트 (e.g. SQLite 락·DB 폭증)
│   ├── infra/                        # docker_setup, troubleshooting 등
│   └── refactor/                     # JS·웨이브 리팩토링 가이드
│
├── skill/                            # Claude Code skill (plan, ISH, CJY 등 — 메모리/플랜 보관)
│
├── drf-server/                       # Django REST Framework (포트 8000) — [§1 상세]
└── fastapi-server/                   # FastAPI 비동기 서버 (포트 8001) — [§2 상세]
```

---

## §1. drf-server/ (Django, 포트 8000)

```
drf-server/
├── manage.py
├── config/                           # Django 프로젝트 설정
│   ├── settings.py
│   ├── urls.py                       # 루트 URL 라우터
│   ├── admin_panel_urls.py           # 어드민 패널 HTML 페이지 라우터 (TemplateView 모음)
│   ├── asgi.py · wsgi.py
│   └── celery.py                     # Celery 설정
│
├── apps/                             # 15개 도메인 앱
│   │
│   ├── accounts/                     # 사용자 인증·조직
│   │   ├── models/
│   │   │   ├── user.py               # CustomUser
│   │   │   ├── company.py · department.py · position.py
│   │   │   ├── user_department.py
│   │   │   └── login_log.py
│   │   ├── serializers/              # admin / auth / org 3개
│   │   ├── views/                    # admin_views (사용자 관리), auth_views (JWT), org_views (조직)
│   │   ├── selectors/ · services/
│   │   ├── urls.py                   # page_urlpatterns + api_urlpatterns 분리 export
│   │   └── admin_urls.py             # /api/admin/accounts·organizations·departments/
│   │
│   ├── alerts/                       # 알람·이벤트 (재설계 이후)
│   │   ├── models/
│   │   │   ├── alarm_record.py       # AlarmRecord
│   │   │   ├── event.py              # Event (ACTIVE → RESOLVED)
│   │   │   └── event_log.py          # EventLog (이력)
│   │   ├── views/
│   │   │   ├── alarm_record.py       # AlarmRecordViewSet, MyStatusView,
│   │   │   │                         # WorkerSummaryView, AnomalyAlarmRecordCreateView ★
│   │   │   └── event.py              # EventViewSet (+ resolve action)
│   │   ├── selectors/ · services/ · serializers/
│   │   ├── tasks.py                  # Celery 태스크 (알람 생성 / Redis LPUSH)
│   │   └── urls.py                   # /alerts/api/alarms|events|...
│   │
│   ├── core/                         # 공통 유틸·시스템 로그
│   │   ├── models/                   # base.py, system_log.py
│   │   ├── views/                    # MapEditLogAdminListView, SystemLogAdminListView
│   │   ├── selectors/ · services/
│   │   ├── management/commands/seed_dummy_data.py
│   │   ├── prometheus.py             # /metrics view (multiproc 호환)
│   │   ├── constants.py · context_processors.py
│   │   ├── exceptions.py             # 응답 봉투 표준 핸들러
│   │   ├── mixins.py · pagination.py · permissions.py · validators.py
│   │   └── admin_urls.py             # /api/admin/activity-logs|map-edit-logs/
│   │
│   ├── dashboard/                    # 대시보드 HTML + 사이드바 API
│   │   ├── views.py                  # main_dashboard, my_profile_page,
│   │   │                             # safety_*_page, monitoring_*_page,
│   │   │                             # MenuView, MySafetyStatusView, SafetyHistoryAPIView,
│   │   │                             # WorkerListAPIView, DashboardRefreshView,
│   │   │                             # VRProgressView, WorkerVRContentView ★
│   │   ├── menu.py                   # 사이드바 구조 정의
│   │   └── urls.py                   # /dashboard/ 페이지 + /dashboard/api/
│   │
│   ├── facilities/                   # 설비·장치·임계값 마스터
│   │   ├── models/
│   │   │   ├── facility.py
│   │   │   ├── devices.py            # GasSensor, PowerDevice (channel_meta 필드 포함)
│   │   │   ├── equipment.py          # Equipment ★
│   │   │   ├── thresholds.py
│   │   │   ├── gas_sensor_inspection.py
│   │   │   └── power_device_inspection.py
│   │   ├── views/                    # facility_admin, gas_sensor_admin, map_editor, power_device_admin
│   │   ├── serializers/              # 동일 4분할
│   │   ├── selectors/ · services/
│   │   └── urls.py                   # /api/facilities|equipments|gas-sensors|power-devices|map-editor/
│   │
│   ├── geofence/                     # 지오펜스 관리
│   │   ├── models/geofence.py
│   │   ├── views/
│   │   │   ├── geofence_views.py     # GeoFenceViewSet
│   │   │   └── admin_views.py        # GeoFenceAdminPageView/ListView/DetailView
│   │   ├── selectors/ · services/ · serializers/
│   │   ├── validators.py
│   │   └── urls.py                   # /api/geofences/, /api/admin/geofences/
│   │
│   ├── ml/                           # AI 이상탐지 ★ (STEP A~F)
│   │   ├── models/                   # MLModel, MLAnomalyResult, MLTrainingDataset 등
│   │   ├── views.py                  # ActiveMLModelView, MLAnomalyResultCreateView
│   │   ├── serializers/ · services/  # IF/ARIMA/Z-score/CP feature builder & 5축 정책 엔진
│   │   ├── tasks/                    # Celery 학습/추론 태스크
│   │   ├── management/commands/      # train_if_model, train_arima_*, run_*_baseline 등
│   │   └── urls.py                   # /api/ml/models/active/, /api/ml/anomaly-results/
│   │
│   ├── monitoring/                   # 가스·전력 센서 데이터 수집
│   │   ├── models/
│   │   │   ├── gas_data.py           # GasData (9종 가스 wide-table)
│   │   │   ├── power_data.py         # PowerData (long-format)
│   │   │   └── power_event.py        # PowerEvent (ON/OFF 스냅샷)
│   │   ├── views/                    # gas_data, gas_data_admin, power_data, power_data_admin, admin_views
│   │   │                             # PowerChannelMetaView ★ (channel_meta 동기화)
│   │   ├── collectors/ · selectors/ · services/ · serializers/
│   │   ├── utils/gas_thresholds.py
│   │   ├── validators.py
│   │   ├── urls.py                   # /api/monitoring/gas|power/{thresholds,event,data,channel-meta}/
│   │   └── admin_urls.py             # /api/admin/gas-data|power-data/{list,export,sensors|devices}/
│   │
│   ├── notices/                      # 공지사항 ★
│   │   ├── models/                   # Notice, NoticeAttachment
│   │   ├── views/                    # NoticeListView, NoticeDetailView, NoticeAttachmentView
│   │   ├── serializers/
│   │   └── urls.py                   # /api/admin/notices/[<id>/[attachments/[<att_id>/]]]
│   │
│   ├── notifications/                # 알림 발송 (팝업·푸시·SMS)
│   │   ├── models/notification.py
│   │   ├── selectors/ · services/
│   │   │   └── delivery/             # popup_delivery, push_delivery, sms_delivery
│   │   └── serializers/ · views/
│   │
│   ├── operations/                   # 운영 로그 (시스템·통합) ★
│   │   ├── models/                   # AppLog, IntegrationLog
│   │   ├── views/
│   │   │   ├── admin/                # AppLogAdminListView, IntegrationLogAdminListView
│   │   │   └── internal/             # IntegrationLogInternalCreateView (FastAPI → DRF)
│   │   ├── logging/                  # 구조화 로깅 헬퍼
│   │   ├── tasks/                    # 비동기 적재
│   │   └── urls.py                   # /api/internal/integration-logs/, /api/admin/{system,integration}-logs/
│   │
│   ├── positioning/                  # 작업자 위치
│   │   ├── models/worker_position.py
│   │   ├── views/position_views.py   # WorkerPositionReceiveView
│   │   ├── collectors/ · selectors/ · services/ · serializers/
│   │   └── urls.py                   # /api/positioning/receive/
│   │
│   ├── reference/                    # 참조 데이터 (코드/상수) ★
│   │   ├── models/
│   │   ├── fixtures/
│   │   └── admin.py
│   │
│   ├── safety/                       # 안전 점검 체크리스트 (전면 재구성)
│   │   ├── models/                   # ChecklistSection, ChecklistItem, SafetyChecklistRevision 등
│   │   ├── views/
│   │   │   └── admin_views.py        # ActiveChecklistView (운영자) +
│   │   │                             # Section/Item/Publish/Revision CRUD 어드민 뷰 11종
│   │   ├── selectors/ · services/ · serializers/
│   │   ├── urls.py                   # /api/safety/checklist/active/
│   │   └── admin_urls.py             # /api/admin/safety/{checklist,sections,items}/...
│   │
│   └── training/                     # VR 교육 콘텐츠 관리 ★
│       ├── models/                   # VRTraining, VRTrainingRevision
│       ├── views/admin_views.py      # VRTrainingDetailView, ReplaceView,
│       │                             # MetaUpdateView, RevisionListView
│       ├── serializers/ · services/
│       └── admin_urls.py             # /api/admin/training/vr-training/...
│
├── docs/                             # drf-server 전용 문서 (known-issues 등)
├── media/                            # 업로드 파일 (Notice 첨부, VR 콘텐츠)
├── staticfiles/                      # collectstatic 출력
├── ml_models/                        # IF/ARIMA .pkl (docker volume → fastapi 와 공유) — .gitignore
├── ml_datasets/                      # 학습용 CSV — .gitignore
├── db_backups/                       # SQLite 백업 디렉토리
├── prometheus_multiproc/             # Prometheus 멀티프로세스 레지스트리
│
├── templates/
│   ├── auth/login.html
│   ├── base/snb_base.html
│   ├── components/                   # 공통 컴포넌트
│   │   ├── header.html · admin_sidebar.html
│   │   ├── alarm_popup.html · alarm_stack.html ★
│   │   ├── geofence_modal.html
│   │   ├── app_config.html ★         # window.APP_CONFIG 주입
│   │   └── ws_conn_banner.html ★
│   ├── dashboard/
│   │   ├── main.html
│   │   └── panels/                   # event/gas/map/power/safety/worker
│   ├── snb_details/                  # 사이드바 상세 페이지 10종
│   │   ├── monitoring_realtime|gas|power|workers|events.html
│   │   ├── event_detail.html
│   │   ├── safety_checklist|history|vr.html
│   │   └── my_profile.html
│   └── admin_panel/                  # 어드민 패널 (확장됨)
│       ├── base.html
│       ├── accounts/accounts_main.html
│       ├── organizations/organizations_main.html
│       ├── geofence/geofence_list.html
│       ├── map_editor/map_editor.html
│       ├── gas_sensor/gas_sensor.html
│       ├── facility/facility.html
│       ├── data/{gas_data,power_data}.html
│       ├── safety/                   # ★
│       │   ├── checklist_main.html
│       │   ├── vr_training_main.html
│       │   ├── _modal_edit.html · _modal_history.html
│       ├── notices/                  # ★
│       │   ├── notices_main.html · notice_detail.html · notice_form.html
│       └── logs/                     # ★
│           ├── system_log.html · activity_log.html
│           ├── integration_log.html · map_edit_log.html
│
└── static/
    ├── css/
    │   ├── alarm-popup.css ★
    │   ├── admin.css · dashboard.css · dashboard_CJY.css
    │   ├── auth/login.css
    │   ├── components/header.css
    │   ├── admin/                    # 어드민 패널 스타일
    │   │   ├── accounts · organizations · facility · gas_sensor · geofence
    │   │   ├── map_editor · gas_data · power_data · power_system
    │   │   ├── logs ★ · notices ★ · safety_checklist · safety_vr_training ★
    │   ├── detail/                   # SNB 상세 페이지 스타일
    │   └── snb_details/              # my_profile, safety_checklist|history|vr
    │
    └── js/
        ├── auth/login.js
        ├── dashboard/                # 메인 대시보드
        │   ├── app.js · charts.js · websocket.js
        │   └── panels/{event,gas,map,worker}-panel.js
        ├── shared/                   # 전 페이지 공통 모듈
        │   ├── alarm-popup.js · alarm-ws.js
        │   ├── alarm-badge.js ★ · alarm-mapper.js ★
        │   ├── level-mapper.js ★ · time-format.js ★
        │   ├── ws-client.js ★ · ws-conn-banner.js ★
        │   ├── app-sub.js · auth.js · config.js · layout.js · util.js
        │   └── worker-ws.js
        ├── detail/                   # SNB 상세 페이지 13종
        │   ├── event_detail · event_list · gas_monitoring · map_detail
        │   ├── monitoring_workers · my_profile · power_system
        │   ├── safety_checklist · safety_history · safety_vr
        │   ├── ui-exception · websocket_gas · websocket_power
        └── admin/                    # 어드민 패널 JS
            ├── main.js
            ├── accounts · organizations · facility · gas · gas_sensor
            ├── geofence · map_editor · power · power_system
            ├── logs/ ★ (system_log, integration_log 등)
            └── notices/ ★
```

---

## §2. fastapi-server/ (FastAPI, 포트 8001)

```
fastapi-server/
├── app.py                            # 진입점 — uvicorn app:app --port 8001
│                                     # 라우터 등록: gas, power, positioning, ws,
│                                     # internal_alarm, internal_scenario, ai
│                                     # lifespan: broadcast_loop / alarm_flush_loop /
│                                     #           channel_meta_refresh_loop / close_redis
│
├── core/
│   ├── config.py                     # Pydantic Settings (DRF_BASE_URL, ML_MODELS_DIR,
│   │                                 # BROADCAST_INTERVAL_SEC, JWT_SIGNING_KEY 등)
│   ├── gas_thresholds.py
│   ├── logging.py                    # 구조화 로깅 설정
│   ├── metrics.py ★                  # Prometheus 메트릭 (E2E_ALARM_LATENCY,
│   │                                 # WS_CONNECTIONS, SENSOR_LAST_RECEIVED)
│   └── redis_client.py ★             # 비동기 Redis 풀 (Phase 1 C4)
│
├── ai/                               # IF/ARIMA 추론 ★
│   └── router.py                     # POST /ai/predict, /ai/reload
│                                     # 모델 캐시 (sensor_type, algorithm, sensor_identifier) 3축
│
├── gas/                              # 가스 센서 도메인
│   ├── routers/gas_router.py         # POST /api/sensors/{info,gas}
│   ├── schemas/gas.py
│   └── services/gas_service.py       # DRF 전송 + 공유 상태 갱신 + Z-score 발화
│
├── power/                            # 전력 센서 도메인
│   ├── routers/power_router.py       # POST /api/power/{onoff,current,voltage,watt}
│   ├── schemas/power.py
│   └── services/
│       ├── power_service.py          # 5축 정책 엔진 (combined_risk) 호출 + DRF 저장
│       └── channel_meta_cache.py ★   # PowerDevice.channel_meta 5분 주기 동기화
│
├── positioning/                      # 작업자 위치
│   ├── routers/position_router.py    # POST /api/positioning/receive,
│   │                                 # WS /ws/positions/ (브라우저 1초 스트림)
│   ├── schemas/position.py
│   └── services/position_service.py  # DRF 비동기 저장
│
├── websocket/                        # WebSocket 브로드캐스트
│   ├── routers/ws_router.py          # WS /ws/sensors/ · /ws/worker/{user_id}/ · /ws/position/
│   │                                 # broadcast_loop · alarm_flush_loop (BRPOP)
│   ├── state.py                      # 프로세스 공유 상태
│   │                                 #   worker_positions · sensor_clients · worker_clients
│   │                                 #   latest_gas_snapshot · power_latest · scenario_mode
│   ├── services/
│   │   ├── broadcast.py              # build_broadcast_payload()
│   │   └── alarm_queue.py ★          # Redis BRPOP/LPUSH (diconai:ws:alarms)
│   └── auth.py ★                     # WS query string JWT 검증 (Phase 5 옵트인)
│
├── internal/                         # 내부 전용 (localhost / 서비스 토큰)
│   └── routers/
│       ├── alarm_router.py ★         # POST /internal/alarms/push/
│       │                             #   Celery → Redis LPUSH → alarm_flush_loop BRPOP
│       └── scenario_router.py        # GET/POST /internal/scenario/mode
│                                     #   modes: mixed/normal/warning/danger +
│                                     #   power: overload/voltage_drop/phase_loss/degradation/
│                                     #           night_abnormal/motor_stuck
│                                     #   gas:   co_leak/h2s_leak/fire/chemical_spill
│
├── services/                         # 외부 호출
│   └── drf_client.py                 # post_to_drf 비동기 헬퍼
│
├── docs/                             # fastapi-server 전용 문서
├── tests/
├── dummies/                          # 더미 데이터 송신
│   ├── gas_dummy.py · power_dummy.py · position_dummy.py
│   └── _scenario.py ★                # 시나리오 모드 공통 정의
└── ml_models/                        # IF/ARIMA .pkl 마운트 지점 (drf-server 와 공유 volume)
```

---

## §3. Django 앱 레이어 (공통)

| 레이어 | 역할 |
|--------|------|
| `models/` | DB 스키마 정의 (도메인별 파일 분리) |
| `selectors/` | 읽기 전용 조회 (단순 쿼리) |
| `services/` | 비즈니스 로직·트랜잭션 (복잡한 계산, 외부 호출) |
| `serializers/` | API 입출력 변환·검증 |
| `views/` | 요청 수신 → 서비스 호출 → 응답 (로직 금지) |

규칙: **view는 service만 호출**, 비즈니스 로직 직접 작성 금지.

---

## §4. 서버 역할 요약

| 서버 | 포트 | 주요 역할 |
|------|------|----------|
| `drf-server` | 8000 | 인증, HTML 렌더링, 데이터 영속성(DB), REST API, Celery 태스크 발행 |
| `fastapi-server` | 8001 | 센서 데이터 수신·검증, WebSocket 브로드캐스트, AI 추론, Celery → WS 알람 브리지 |

데이터 흐름: **IoT → fastapi-server(:8001) → drf-server(:8000) (영속화) / 브라우저(WS)**
알람 흐름: **DRF Celery → POST :8001/internal/alarms/push/ → Redis LPUSH → alarm_flush_loop BRPOP → /ws/sensors/ broadcast**
