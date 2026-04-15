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
│   └── directory-structure.md     # 디렉토리 구조 설명 (현재 파일)
│
├── drf-server/                     # Django REST Framework 백엔드 서버
│   ├── .venv/                      # DRF 전용 Python 가상환경
│   ├── .env                        # 환경변수 (SECRET_KEY, DB 등) - Git 제외
│   ├── .env.example                # 환경변수 예시 파일 (Git 포함)
│   ├── manage.py                   # Django 관리 CLI 진입점
│   ├── requirements.txt            # DRF 서버 전용 패키지 목록
│   │
│   ├── config/                     # Django 프로젝트 설정 패키지
│   │   ├── __init__.py
│   │   ├── settings.py             # 전역 설정 (DB, 앱 목록, 미들웨어 등)
│   │   ├── urls.py                 # 루트 URL 라우터
│   │   ├── asgi.py                 # ASGI 서버 진입점 (비동기)
│   │   └── wsgi.py                 # WSGI 서버 진입점 (동기)
│   │
│   ├── apps/                       # Django 앱 모음
│   │   └── accounts/               # 사용자 계정 및 인증 앱
│   │       ├── __init__.py
│   │       ├── admin.py            # Django Admin 설정
│   │       ├── apps.py             # 앱 설정 클래스
│   │       ├── models.py           # DB 모델 (CustomUser, UserProfile, LoginLog)
│   │       ├── views.py            # API 뷰 (로그인, 로그아웃 등)
│   │       ├── tests.py            # 단위 테스트
│   │       └── migrations/         # DB 마이그레이션 파일 모음
│   │           ├── __init__.py
│   │           ├── 0001_initial.py
│   │           └── 0002_*.py
│   │
│   ├── templates/                  # Django HTML 템플릿
│   │   └── dashboard.html          # 대시보드 페이지 템플릿
│   │
│   ├── static/                     # 정적 파일 (CSS, JS, 이미지)
│   │   ├── css/
│   │   │   └── style.css
│   │   └── js/
│   │       └── main.js
│   │
│   ├── media/                      # 사용자 업로드 파일 저장 경로 (런타임 생성)
│   ├── db.sqlite3                  # SQLite DB 파일 (개발용, Git 제외)
│   └── docs/
│       └── COMMANDS.md             # DRF 서버 전용 명령어 모음
│
└── fastapi-server/                 # FastAPI 비동기 API 서버
    ├── .venv/                      # FastAPI 전용 Python 가상환경
    ├── requirements.txt            # FastAPI 서버 전용 패키지 목록
    ├── main.py                     # FastAPI 앱 진입점 (라우터, 미들웨어 등록)
    └── docs/
        └── COMMANDS.md             # FastAPI 서버 전용 명령어 모음
```

---

## 서버 역할 요약

| 서버 | 포트 | 역할 |
|------|------|------|
| `drf-server` | 8000 | Django Admin, 세션 기반 인증, HTML 렌더링, REST API |
| `fastapi-server` | 8001 | 고성능 비동기 API, 외부 연동, AI 처리 등 |

## 가상환경 구조 참고

각 서버는 독립적인 `.venv`를 가지며, 루트 `.venv`는 공통 스크립트용입니다.
서버별 작업 시 반드시 해당 폴더에서 가상환경을 활성화하세요.
