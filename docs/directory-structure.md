# diconai - 디렉토리 구조

```
diconai/                            # 프로젝트 루트
│
├── .venv/                          # 루트 Python 가상환경 (uv 관리)
├── .gitignore                      # Git 추적 제외 파일 목록
├── .pre-commit-config.yaml         # pre-commit 훅 설정 (코드 품질 자동화)
├── .python-version                 # Python 버전 고정 파일 (uv 참조)
├── pyproject.toml                  # 루트 프로젝트 메타데이터 및 의존성 설정
├── requirements.txt                # 루트 레벨 Python 패키지 목록
├── uv.lock                         # uv 패키지 잠금 파일 (의존성 버전 고정)
├── main.py                         # 루트 진입점 (공통 스크립트 등)
├── README.md                       # 프로젝트 소개 및 초기 세팅 가이드
│
├── docs/                           # 프로젝트 전체 공통 문서
│   ├── COMMANDS.md                 # 자주 쓰는 명령어 모음
│   ├── dev_convention.md           # 개발 컨벤션 가이드
│   ├── github_convention.md        # GitHub 협업 컨벤션
│   ├── url-structure.md            # URL 설계 구조 문서
│   └── directory-structure.md     # 디렉토리 구조 설명 (현재 파일)
│
├── skill/                          # AI 보조 작업용 스킬/참고 문서
│   ├── MN-04.md
│   ├── check_model.md
│   ├── check_schema.md
│   ├── diconai_data_modeling.md
│   ├── github_PR_comments.md
│   ├── textflow.md
│   ├── trouble_shooting.md
│   └── 센서별 데이터구조 및 임계치 정의서_㈜디코나이_260401.pdf
│
├── drf-server/                     # Django REST Framework 백엔드 서버
│   ├── .venv/                      # DRF 전용 Python 가상환경
│   ├── .env                        # 환경변수 (SECRET_KEY, DB 등) - Git 제외
│   ├── .env.example                # 환경변수 예시 파일 (Git 포함)
│   ├── manage.py                   # Django 관리 CLI 진입점
│   ├── requirements.txt            # DRF 서버 전용 패키지 목록
│   ├── db.sqlite3                  # SQLite DB 파일 (개발용, Git 제외)
│   │
│   ├── config/                     # Django 프로젝트 설정 패키지
│   │   ├── __init__.py
│   │   ├── settings.py             # 전역 설정 (DB, 앱 목록, 미들웨어 등)
│   │   ├── urls.py                 # 루트 URL 라우터
│   │   ├── asgi.py                 # ASGI 서버 진입점 (비동기)
│   │   └── wsgi.py                 # WSGI 서버 진입점 (동기)
│   │
│   ├── apps/                       # Django 앱 모음
│   │   │
│   │   ├── accounts/               # 사용자 계정 및 인증
│   │   │   ├── models/
│   │   │   │   ├── user.py         # CustomUser, UserProfile
│   │   │   │   └── login_log.py    # LoginLog
│   │   │   ├── selectors/          # DB 조회 전용 레이어
│   │   │   ├── services/           # 비즈니스 로직 레이어
│   │   │   ├── serializers.py
│   │   │   ├── views.py
│   │   │   ├── urls.py
│   │   │   ├── admin.py
│   │   │   ├── apps.py
│   │   │   ├── tests.py
│   │   │   └── migrations/
│   │   │
│   │   ├── alerts/                 # 이벤트 알람 및 기록
│   │   │   ├── models/
│   │   │   │   ├── alarm_record.py # 알람 레코드
│   │   │   │   ├── event.py        # 이벤트 정의
│   │   │   │   └── event_log.py    # 이벤트 로그
│   │   │   ├── selectors/
│   │   │   │   ├── active_events.py
│   │   │   │   ├── alarm_timeline.py
│   │   │   │   └── event_history.py
│   │   │   ├── services/
│   │   │   │   ├── alarm_service.py
│   │   │   │   ├── event_service.py
│   │   │   │   └── merge_policy.py
│   │   │   ├── serializers/
│   │   │   │   └── alarm_record.py
│   │   │   ├── views/
│   │   │   │   └── alarm_record.py
│   │   │   ├── urls.py
│   │   │   ├── admin.py
│   │   │   ├── apps.py
│   │   │   └── migrations/
│   │   │
│   │   ├── core/                   # 공통 유틸리티 및 시스템 로그
│   │   │   ├── models/
│   │   │   │   └── system_log.py
│   │   │   ├── selectors/
│   │   │   │   └── audit_trail.py
│   │   │   ├── services/
│   │   │   │   └── audit_service.py
│   │   │   ├── constants.py        # 프로젝트 공통 상수
│   │   │   ├── mixins.py           # 공통 Mixin 클래스
│   │   │   ├── validators.py       # 공통 유효성 검사
│   │   │   ├── views.py
│   │   │   ├── admin.py
│   │   │   ├── apps.py
│   │   │   ├── tests.py
│   │   │   └── migrations/
│   │   │
│   │   ├── dashboard/              # 대시보드 뷰 (HTML 렌더링)
│   │   │   ├── menu.py             # 사이드바 메뉴 구조 정의
│   │   │   ├── views.py
│   │   │   ├── urls.py
│   │   │   └── apps.py
│   │   │
│   │   ├── facilities/             # 설비·장치·임계값 관리
│   │   │   ├── models/
│   │   │   │   ├── facility.py     # 설비(구역) 모델
│   │   │   │   ├── devices.py      # 장치 모델
│   │   │   │   └── thresholds.py   # 임계값 모델
│   │   │   ├── selectors/
│   │   │   │   └── active_devices.py
│   │   │   ├── services/
│   │   │   │   ├── device_service.py
│   │   │   │   └── threshold_service.py
│   │   │   ├── serializers/
│   │   │   ├── views/
│   │   │   ├── urls.py (예정)
│   │   │   ├── admin.py
│   │   │   ├── apps.py
│   │   │   ├── tests.py
│   │   │   └── migrations/
│   │   │
│   │   ├── geofence/               # 지오펜스(구역 진입/이탈) 관리
│   │   │   ├── models/
│   │   │   │   └── geofence.py
│   │   │   ├── selectors/
│   │   │   │   └── geofence_candidates.py
│   │   │   ├── services/
│   │   │   │   └── geofence_service.py
│   │   │   ├── serializers/
│   │   │   ├── views/
│   │   │   ├── validators.py
│   │   │   ├── urls.py (예정)
│   │   │   ├── admin.py
│   │   │   ├── apps.py
│   │   │   ├── tests.py
│   │   │   └── migrations/
│   │   │
│   │   ├── monitoring/             # 가스·전력 센서 데이터 수집 및 조회
│   │   │   ├── models/
│   │   │   │   ├── gas_data.py
│   │   │   │   ├── power_data.py
│   │   │   │   └── power_event.py
│   │   │   ├── collectors/         # 센서 데이터 수집기
│   │   │   │   ├── gas_collector.py
│   │   │   │   └── power_collector.py
│   │   │   ├── selectors/
│   │   │   │   ├── latest_readings.py
│   │   │   │   └── time_range_data.py
│   │   │   ├── services/
│   │   │   │   └── aggregation_service.py
│   │   │   ├── serializers/
│   │   │   ├── views/
│   │   │   ├── validators.py
│   │   │   ├── urls.py (예정)
│   │   │   ├── admin.py
│   │   │   ├── apps.py
│   │   │   ├── tests.py
│   │   │   └── migrations/
│   │   │
│   │   ├── notifications/          # 알림 발송 (팝업·푸시·SMS)
│   │   │   ├── models/
│   │   │   │   └── notification.py
│   │   │   ├── selectors/
│   │   │   │   ├── notification_history.py
│   │   │   │   └── unread_notifications.py
│   │   │   ├── services/
│   │   │   │   ├── notification_service.py
│   │   │   │   └── delivery/       # 채널별 발송 구현체
│   │   │   │       ├── popup_delivery.py
│   │   │   │       ├── push_delivery.py
│   │   │   │       └── sms_delivery.py
│   │   │   ├── serializers/
│   │   │   ├── views/
│   │   │   ├── urls.py (예정)
│   │   │   ├── admin.py
│   │   │   ├── apps.py
│   │   │   ├── tests.py
│   │   │   └── migrations/
│   │   │
│   │   ├── positioning/            # 작업자 위치 추적
│   │   │   ├── models/
│   │   │   │   └── worker_position.py
│   │   │   ├── collectors/
│   │   │   │   └── position_collector.py
│   │   │   ├── selectors/
│   │   │   │   └── latest_positions.py
│   │   │   ├── services/
│   │   │   │   └── position_service.py
│   │   │   ├── serializers/
│   │   │   ├── views/
│   │   │   ├── urls.py (예정)
│   │   │   ├── admin.py
│   │   │   ├── apps.py
│   │   │   ├── tests.py
│   │   │   └── migrations/
│   │   │
│   │   └── safety/                 # 안전 점검 체크리스트
│   │       ├── models/
│   │       │   └── safety.py
│   │       ├── selectors/
│   │       │   └── completion_stats.py
│   │       ├── services/
│   │       │   └── check_service.py
│   │       ├── serializers/
│   │       ├── views/
│   │       ├── urls.py (예정)
│   │       ├── admin.py
│   │       ├── apps.py
│   │       ├── tests.py
│   │       └── migrations/
│   │
│   ├── templates/                  # Django HTML 템플릿
│   │   ├── main_dashboard.html     # 메인 대시보드
│   │   ├── alarm_panel.html        # 알람 패널
│   │   ├── auth/
│   │   │   └── login.html          # 로그인 페이지
│   │   ├── components/             # 재사용 템플릿 조각
│   │   │   ├── header.html
│   │   │   └── alarm_popup.html
│   │   └── snb_details/            # 사이드바 상세 패널
│   │       └── safety_checklist.html
│   │
│   ├── static/                     # 정적 파일 (CSS, JS, 이미지)
│   │   ├── css/
│   │   │   ├── dashboard.css
│   │   │   └── header.css
│   │   ├── js/
│   │   │   └── refactors/          # 모듈화된 JS 파일
│   │   │       ├── app.js          # 앱 진입점
│   │   │       ├── auth.js         # 인증 처리
│   │   │       ├── websocket.js    # WebSocket 연결 관리
│   │   │       ├── charts.js       # 차트 렌더링
│   │   │       ├── map-panel.js    # 공장 지도 패널
│   │   │       ├── gas-panel.js    # 가스 센서 패널
│   │   │       ├── worker-panel.js # 작업자 위치 패널
│   │   │       ├── event-panel.js  # 이벤트 패널
│   │   │       ├── alarm-popup.js  # 알람 팝업
│   │   │       ├── layout.js       # 레이아웃 제어
│   │   │       └── util.js         # 공통 유틸 함수
│   │   └── img/
│   │       └── factory_map.svg     # 공장 평면도 SVG
│   │
│   └── docs/                       # DRF 서버 전용 문서
│       ├── COMMANDS.md             # DRF 서버 명령어 모음
│       ├── CJY/                    # 팀원별 작업 문서
│       │   ├── MN-04.md
│       │   ├── mn-04_flow.md
│       │   └── refactoring_report_v*.md
│       ├── HJH/
│       │   ├── CM-01_CM-02_SNB-01.md
│       │   └── login.md
│       ├── ISH/
│       └── JHH/
│
└── fastapi-server/                 # FastAPI 비동기 API 서버
    ├── .venv/                      # FastAPI 전용 Python 가상환경
    ├── requirements.txt            # FastAPI 서버 전용 패키지 목록
    ├── main.py                     # FastAPI 앱 진입점
    ├── websocket.py                # WebSocket 엔드포인트 (실시간 센서 데이터)
    └── docs/
        ├── COMMANDS.md             # FastAPI 서버 명령어 모음
        └── websocket.md            # WebSocket API 설계 문서
```

---

## 앱 레이어 구조 (모든 Django 앱 공통)

각 앱은 책임 분리를 위해 아래 레이어로 구성됩니다.

| 레이어 | 위치 | 역할 |
|--------|------|------|
| `models/` | DB 스키마 정의 | 테이블 구조, 관계, 제약 조건 |
| `selectors/` | DB 조회 전용 | 복잡한 쿼리 함수 (읽기 전용) |
| `services/` | 비즈니스 로직 | 상태 변경, 외부 연동, 트랜잭션 |
| `serializers/` | 직렬화/역직렬화 | API 입출력 데이터 변환 및 검증 |
| `views/` | HTTP 처리 | 요청 수신 → 서비스 호출 → 응답 반환 |

---

## 서버 역할 요약

| 서버 | 포트 | 역할 |
|------|------|------|
| `drf-server` | 8000 | Django Admin, 세션 인증, HTML 렌더링, REST API |
| `fastapi-server` | 8001 | 실시간 WebSocket, 고성능 비동기 API, AI 처리 |

## 가상환경 구조 참고

각 서버는 독립적인 `.venv`를 가지며, 루트 `.venv`는 공통 스크립트용입니다.
서버별 작업 시 반드시 해당 폴더에서 가상환경을 활성화하세요.
