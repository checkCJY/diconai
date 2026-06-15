# diconai — 디렉토리 구조

> 기준일: 2026-06-15 / 브랜치: fix/0615_docs

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
├── Dockerfile · entrypoint.sh        # 컨테이너 빌드·기동
├── gunicorn.conf.py                  # gunicorn 워커 설정
├── conftest.py · pytest.ini          # 테스트 설정
├── requirements.txt · requirements-dev.txt
├── config/                           # Django 프로젝트 설정
│   ├── settings/                     # 설정 패키지 (base.py · dev.py · prod.py)
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
│   │   │   ├── role_profile.py       # RoleProfile (역할별 프로필)
│   │   │   └── login_log.py
│   │   ├── serializers/              # admin / auth / org 3개
│   │   ├── views/                    # admin_views (사용자 관리), auth_views (JWT),
│   │   │                             # org_views (조직), internal_views (내부 조회)
│   │   ├── selectors/ · services/
│   │   ├── urls.py                   # page_urlpatterns + api_urlpatterns 분리 export
│   │   └── admin_urls.py             # /api/admin/accounts·organizations·departments/
│   │
│   ├── alerts/                       # 알람·이벤트 (재설계 이후)
│   │   ├── models/
│   │   │   ├── alarm_record.py       # AlarmRecord
│   │   │   ├── event.py              # Event (ACTIVE → RESOLVED)
│   │   │   ├── event_log.py          # EventLog (이력)
│   │   │   ├── event_acknowledgement.py # EventAcknowledgement
│   │   │   ├── alert_policy.py       # AlertPolicy (알림 정책)
│   │   │   └── hazard_type.py · hazard_type_group.py # 위험 유형 분류
│   │   ├── views/
│   │   │   ├── alarm_record.py       # AlarmRecordViewSet, MyStatusView, WorkerSummaryView
│   │   │   ├── anomaly_alarm_record.py # AnomalyAlarmRecordCreateView
│   │   │   ├── event.py              # EventViewSet (+ update_status action)
│   │   │   └── admin_views.py        # AlertPolicy 어드민 (정책 CRUD)
│   │   ├── selectors/ · services/ · serializers/
│   │   ├── tasks.py                  # Celery 태스크 (알람 생성 / Redis Stream XADD)
│   │   └── urls.py                   # /alerts/api/alarms|events|...
│   │
│   ├── core/                         # 공통 유틸·시스템 로그
│   │   ├── models/                   # base.py, system_log.py, risk_level_standard.py
│   │   ├── views/                    # system_log_views (Map/SystemLog 어드민),
│   │   │                             # risk_standard_admin (위험 기준 CRUD)
│   │   ├── selectors/ · services/
│   │   ├── management/commands/seed_dummy_data.py
│   │   ├── prometheus.py             # /metrics view (multiproc 호환)
│   │   ├── authentication.py · metrics.py · sqlite_pragmas.py
│   │   ├── constants.py · context_processors.py
│   │   ├── exceptions.py             # 응답 봉투 표준 핸들러
│   │   ├── mixins.py · pagination.py · permissions.py · validators.py
│   │   └── admin_urls.py             # /api/admin/activity-logs|map-edit-logs|risk-standards/
│   │
│   ├── dashboard/                    # 대시보드 HTML + 사이드바 API
│   │   ├── models/                   # menu.py (Menu), role_menu_visibility.py (RoleMenuVisibility)
│   │   ├── views.py                  # main_dashboard, my_profile_page,
│   │   │                             # safety_*_page, monitoring_*_page,
│   │   │                             # MenuView, MySafetyStatusView, SafetyHistoryAPIView,
│   │   │                             # WorkerListAPIView, DashboardRefreshView,
│   │   │                             # VRProgressView, WorkerVRContentView
│   │   ├── menu.py                   # 사이드바 구조 정의
│   │   ├── signals.py                # 메뉴 캐시 invalidate 시그널
│   │   └── urls.py                   # /dashboard/ 페이지 + /dashboard/api/
│   │
│   ├── facilities/                   # 설비·장치·임계값 마스터
│   │   ├── models/
│   │   │   ├── facility.py
│   │   │   ├── devices.py            # GasSensor, PowerDevice (channel_meta 필드 포함)
│   │   │   ├── equipment.py          # Equipment
│   │   │   ├── thresholds.py
│   │   │   ├── gas_sensor_inspection.py
│   │   │   └── power_device_inspection.py
│   │   ├── views/                    # facility_admin, gas_sensor_admin, map_editor,
│   │   │                             # power_device_admin, threshold_admin (임계치 그룹)
│   │   ├── serializers/              # 동일 5분할
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
│   ├── ml/                           # AI 이상탐지 (STEP A~F)
│   │   ├── models/                   # ml_model.py (MLModel), ml_anomaly_result.py (MLAnomalyResult)
│   │   ├── views.py                  # ActiveMLModelView, MLAnomalyResultCreateView
│   │   ├── services/                 # IF/ARIMA/Z-score/CP feature builder & 5축 정책 엔진
│   │   ├── management/commands/      # train_anomaly_model, train_arima_model,
│   │   │                             # train_arima_power_model, measure_channel_correlation
│   │   └── urls.py                   # /api/ml/models/active/, /api/ml/anomaly-results/
│   │
│   ├── monitoring/                   # 가스·전력 센서 데이터 수집
│   │   ├── models/
│   │   │   ├── gas_data.py           # GasData (9종 가스 wide-table)
│   │   │   ├── power_data.py         # PowerData (long-format)
│   │   │   └── power_event.py        # PowerEvent (ON/OFF 스냅샷)
│   │   ├── views/                    # gas_data, gas_data_admin, power_data, power_data_admin,
│   │   │                             # admin_views (PowerChannelMetaView 포함 — channel_meta 동기화)
│   │   ├── collectors/ · selectors/ · services/ · serializers/
│   │   ├── utils/gas_thresholds.py
│   │   ├── validators.py
│   │   ├── urls.py                   # /api/monitoring/gas|power/{thresholds,event,data,channel-meta}/
│   │   └── admin_urls.py             # /api/admin/gas-data|power-data/{list,export,sensors|devices}/
│   │
│   ├── notices/                      # 공지사항
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
│   ├── operations/                   # 운영 로그 (시스템·통합) + 데이터 보관 정책
│   │   ├── models/                   # AppLog, IntegrationLog, DataRetentionPolicy
│   │   ├── views/
│   │   │   ├── admin/                # log_views (App/IntegrationLog 어드민),
│   │   │   │                         # retention_policy_views (보관 정책 CRUD·실행)
│   │   │   └── internal/             # IntegrationLogInternalCreateView (FastAPI → DRF)
│   │   ├── logging/                  # 구조화 로깅 헬퍼 (db_handler)
│   │   ├── tasks/                    # 비동기 적재
│   │   └── urls.py                   # /api/internal/{integration-logs,workers}/,
│   │                                 # /api/admin/{system,integration}-logs/, /api/admin/retention-policies/
│   │
│   ├── positioning/                  # 작업자 위치
│   │   ├── models/worker_position.py
│   │   ├── views/position_views.py   # WorkerPositionReceiveView
│   │   ├── collectors/ · selectors/ · services/ · serializers/
│   │   └── urls.py                   # /api/positioning/receive/
│   │
│   ├── reference/                    # 참조 데이터 (공통 코드)
│   │   ├── models/                   # code_group.py (CodeGroup), common_code.py (CommonCode)
│   │   ├── views/code_admin.py · serializers/code_admin.py
│   │   ├── fixtures/
│   │   ├── admin.py
│   │   └── admin_urls.py             # /api/admin/code-groups|codes/
│   │
│   ├── safety/                       # 안전 점검 체크리스트 (전면 재구성)
│   │   ├── models/                   # safety, safety_check_section, safety_check_session,
│   │   │                             # safety_checklist_revision
│   │   ├── views/
│   │   │   └── admin_views.py        # ActiveChecklistView (운영자) +
│   │   │                             # Section/Item/Publish/Revision CRUD 어드민 뷰 11종
│   │   ├── selectors/ · services/ · serializers/
│   │   ├── urls.py                   # /api/safety/checklist/active/
│   │   └── admin_urls.py             # /api/admin/safety/{checklist,sections,items}/...
│   │
│   └── training/                     # VR 교육 콘텐츠 관리
│       ├── models/                   # vr_training_content (VRTrainingContent), vr_training_revision
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
├── logs/                             # RotatingFileHandler 출력 — .gitignore
├── prometheus_multiproc/             # Prometheus 멀티프로세스 레지스트리
│
├── templates/
│   ├── auth/login.html
│   ├── base/snb_base.html
│   ├── components/                   # 공통 컴포넌트
│   │   ├── header.html · admin_sidebar.html
│   │   ├── alarm_popup.html · alarm_stack.html
│   │   ├── geofence_modal.html
│   │   ├── app_config.html           # window.APP_CONFIG 주입
│   │   └── ws_conn_banner.html
│   ├── dashboard/
│   │   ├── main.html
│   │   └── panels/                   # event/gas/map/power/safety/scenario
│   ├── snb_details/                  # 사이드바 상세 페이지
│   │   ├── monitoring_realtime|gas|power|workers|events.html
│   │   ├── event_detail.html
│   │   ├── safety_checklist|history|vr.html
│   │   └── my_profile.html
│   ├── admin/geofence/geofence_list.html  # (DRF admin 연계)
│   └── admin_panel/                  # 어드민 패널
│       ├── base.html
│       ├── accounts/ · organizations/ · geofence/
│       ├── map_editor/ · gas_sensor/ · facility/ · power_system/
│       ├── data/                     # gas_data · power_data · retention_policy
│       ├── safety/                   # checklist_main · vr_training_main + _modal_edit/_history
│       ├── notices/                  # notices_main · notice_detail · notice_form
│       ├── alerts/                   # policies_main · _modal_form
│       ├── thresholds/ · risk_standards/ · common_codes/
│       ├── events/                   # event_history
│       └── logs/                     # system_log · activity_log · integration_log · map_edit_log
│
└── static/
    ├── css/
    │   ├── alarm-popup.css
    │   ├── admin.css · dashboard.css · dashboard_CJY.css
    │   ├── auth/login.css
    │   ├── components/header.css
    │   ├── shared/chart-helpers.css
    │   ├── admin/                    # 어드민 패널 스타일
    │   │   ├── accounts · organizations · facility · gas_sensor · geofence
    │   │   ├── map_editor · gas_data · power_data · power_system
    │   │   ├── logs · notices · safety_checklist · safety_vr_training
    │   │   ├── alert_policy · thresholds · risk_standards · common_codes
    │   │   └── event_history · retention_policy
    │   ├── detail/                   # SNB 상세 페이지 스타일
    │   └── snb_details/              # my_profile, safety_checklist|history|vr
    │
    └── js/
        ├── auth/login.js
        ├── dashboard/                # 메인 대시보드
        │   ├── app.js · charts.js · websocket.js
        │   └── panels/{event,gas,map,scenario,worker}-panel.js
        ├── shared/                   # 전 페이지 공통 모듈
        │   ├── alarm-popup.js · alarm-ws.js
        │   ├── alarm-badge.js · alarm-mapper.js
        │   ├── level-mapper.js · time-format.js · chart-helpers.js
        │   ├── ws-client.js · ws-conn-banner.js
        │   ├── app-sub.js · auth.js · config.js · layout.js · util.js
        │   └── worker-ws.js
        ├── detail/                   # SNB 상세 페이지
        │   ├── event_detail · event_list · gas_monitoring · map_detail
        │   ├── monitoring_workers · my_profile · power_system
        │   ├── safety_checklist · safety_history · safety_vr
        │   ├── ui-exception · websocket_gas · websocket_power
        └── admin/                    # 어드민 패널 JS
            ├── main.js
            ├── accounts · organizations · facility · gas · gas_sensor
            ├── geofence · map_editor · power · power_system
            ├── alerts · thresholds · risk_standards · common_codes
            ├── events · data(retention_policy) · safety
            ├── logs/ (system_log, integration_log 등)
            └── notices/
```

---

## §2. fastapi-server/ (FastAPI, 포트 8001)

```
fastapi-server/
├── app.py                            # 진입점 — uvicorn app:app --port 8001
│                                     # 라우터 등록: gas, power, positioning, ws,
│                                     # internal_alarm, internal_scenario, ai
│                                     # lifespan: broadcast_loop / alarm_flush_loop /
│                                     #           channel_meta_refresh_loop / threshold_sync_loop
│
├── core/
│   ├── config.py                     # Pydantic Settings (DRF_BASE_URL, ML_MODELS_DIR,
│   │                                 # BROADCAST_INTERVAL_SEC, JWT_SIGNING_KEY 등)
│   ├── gas_thresholds.py · power_thresholds.py
│   ├── constants.py
│   ├── logging.py                    # 구조화 로깅 설정
│   ├── metrics.py                    # Prometheus 메트릭 (E2E_ALARM_LATENCY,
│   │                                 # WS_CONNECTIONS, SENSOR_LAST_RECEIVED)
│   └── redis_client.py               # 비동기 Redis 풀
│
├── ai/                               # IF/ARIMA 추론
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
│       ├── channel_meta_cache.py     # PowerDevice.channel_meta 5분 주기 동기화
│       └── threshold_sync.py         # 정격 % 임계치(power_facility_default) 5분 동기화
│
├── positioning/                      # 작업자 위치
│   ├── routers/position_router.py    # POST /api/positioning/receive,
│   │                                 # WS /ws/positions/ (브라우저 1초 스트림)
│   ├── schemas/position.py
│   └── services/position_service.py  # DRF 비동기 저장
│
├── websocket/                        # WebSocket 브로드캐스트
│   ├── routers/ws_router.py          # WS /ws/sensors/ · /ws/worker/{user_id}/ · /ws/position/
│   │                                 # broadcast_loop · alarm_flush_loop (XREAD)
│   ├── state.py                      # 프로세스 공유 상태 (WebSocket 연결 목록만)
│   │                                 #   sensor_clients · worker_clients
│   ├── snap_store.py                 # broadcast 스냅샷 Redis 키 (계층 1 이관)
│   │                                 #   gas/power/worker 스냅샷 · scenario_mode
│   ├── services/
│   │   ├── broadcast.py              # build_broadcast_payload()
│   │   └── alarm_queue.py            # Redis Stream XADD/XREAD (diconai:ws:alarms)
│   └── auth.py                       # WS query string JWT 검증 (Phase 5 옵트인)
│
├── internal/                         # 내부 전용 (localhost / 서비스 토큰)
│   └── routers/
│       ├── alarm_router.py           # POST /internal/alarms/push/
│       │                             #   Celery → Redis XADD → alarm_flush_loop XREAD
│       └── scenario_router.py        # GET/POST /internal/scenario/mode
│                                     #   modes: mixed/normal/warning/danger +
│                                     #   power: overload/voltage_drop/phase_loss/degradation/
│                                     #           night_abnormal/motor_stuck
│                                     #   gas:   co_leak/h2s_leak/fire/chemical_spill/
│                                     #          o2_depletion/sensor_fault
│
├── services/                         # 외부 호출
│   ├── drf_client.py                 # post_to_drf 비동기 헬퍼
│   ├── ai_mute.py                    # AI mute 상태 관리
│   └── anomaly_alarm.py              # 이상 알람 전송
│
├── docs/                             # fastapi-server 전용 문서
├── tests/
├── dummies/                          # 더미 데이터 송신
│   ├── gas_dummy.py · power_dummy.py · position_dummy.py
│   ├── _scenario.py                  # 시나리오 모드 공통 정의
│   └── _state_machine.py · iot_load_test.py · ws_load_test.py
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
알람 흐름: **DRF Celery → POST :8001/internal/alarms/push/ → Redis Stream XADD → alarm_flush_loop XREAD → /ws/sensors/ broadcast**
