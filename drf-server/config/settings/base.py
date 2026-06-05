"""
공통 설정 — dev/prod 양쪽에서 공유하는 값만 여기에 둔다.
DEBUG, ALLOWED_HOSTS, STORAGES는 dev.py / prod.py에서 각각 정의.
"""

import logging as _logging
import environ
from datetime import timedelta
from pathlib import Path

# BASE_DIR: drf-server/ 루트 (settings/ 폴더 기준 3단계 위)
BASE_DIR = Path(__file__).resolve().parent.parent.parent
env = environ.Env()

# SECRET_KEY는 반드시 환경변수에서만. 기본값 없음 — 미설정 시 서버 기동 실패.
SECRET_KEY = env("DJANGO_SECRET_KEY")

# ALLOWED_HOSTS: 기본값은 로컬 개발용. prod.py에서 환경변수 필수로 덮어씀.
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["127.0.0.1", "localhost"])

# ── 앱 목록 ──────────────────────────────────────────────────
INSTALLED_APPS = [
    # 서드파티
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    # Django 기본
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # 프로젝트 앱
    "apps.accounts",
    "apps.facilities",
    "apps.geofence",
    "apps.positioning",
    "apps.monitoring",
    "apps.alerts",
    "apps.notifications",
    "apps.safety",
    "apps.core",
    "apps.dashboard",
    "apps.operations",
    "apps.reference",
    "apps.notices",
    "apps.training",
    "apps.ml",
]

MIDDLEWARE = [
    "apps.core.prometheus.PrometheusMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.frontend_config",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── 데이터베이스 ───────────────────────────────────────────────
# POSTGRES_HOST 환경변수가 있으면 PostgreSQL, 없으면 로컬 SQLite 폴백.
if env("POSTGRES_HOST", default=""):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("POSTGRES_DB"),
            "USER": env("POSTGRES_USER"),
            "PASSWORD": env("POSTGRES_PASSWORD"),
            "HOST": env("POSTGRES_HOST"),
            "PORT": env("POSTGRES_PORT", default="5432"),
            # 이성현 추가 — 연결 60초 재사용 (매 요청 새 PG 연결 비용 제거)
            "CONN_MAX_AGE": 60,
            # 이성현 추가 — 재사용 전 죽은 연결 자동 감지 (끊긴 연결로 인한 에러 방지)
            "CONN_HEALTH_CHECKS": True,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(BASE_DIR / "db.sqlite3"),
        }
    }

# SQLite 전용 락 완화 옵션 (PostgreSQL 사용 시 자동 무시)
# - timeout=30: 락 대기 30초 (기본 5초)
# - transaction_mode=IMMEDIATE: write lock 선점으로 Celery 동시 쓰기 충돌 방지
if DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3":
    DATABASES["default"].setdefault("OPTIONS", {})
    DATABASES["default"]["OPTIONS"].setdefault("timeout", 30)
    DATABASES["default"]["OPTIONS"].setdefault("transaction_mode", "IMMEDIATE")

# ── 비밀번호 검증 ─────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTH_USER_MODEL = "accounts.CustomUser"

# ── DRF 기본 설정 ─────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    # 4xx/5xx 응답을 {error: {code, message}} 표준 봉투로 변환
    "EXCEPTION_HANDLER": "apps.core.exceptions.standard_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

# ── OpenAPI 스키마 (Swagger) ──────────────────────────────────
SPECTACULAR_SETTINGS = {
    "TITLE": "diconai API",
    "DESCRIPTION": "산재 예방 통합 관제 시스템 — drf-server REST API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/",
    "COMPONENT_SPLIT_REQUEST": True,
}

# ── JWT 토큰 설정 ─────────────────────────────────────────────
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        hours=env.int("JWT_ACCESS_TOKEN_LIFETIME_HOURS", default=1)
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=env.int("JWT_REFRESH_TOKEN_LIFETIME_DAYS", default=30)
    ),
    "AUTH_HEADER_TYPES": ("Bearer",),
    "ROTATE_REFRESH_TOKENS": True,  # refresh 사용 시 새 토큰 발급 (1회용)
    "BLACKLIST_AFTER_ROTATION": True,  # 회전된 refresh 재사용 차단
    # JWT_SIGNING_KEY 미설정 시 SECRET_KEY 폴백 — 운영에서는 반드시 독립 키 사용
    "SIGNING_KEY": env("JWT_SIGNING_KEY", default=SECRET_KEY),
}

# JWT_SIGNING_KEY 미설정 시 기동 로그에 경고 출력
if not env("JWT_SIGNING_KEY", default=""):
    _logging.getLogger(__name__).warning(
        "[security] JWT_SIGNING_KEY 미설정 — DJANGO_SECRET_KEY 로 폴백 중. "
        "운영 환경에서는 독립된 JWT_SIGNING_KEY 를 env 에 반드시 설정하세요."
    )

# ── 기타 서비스 설정 ──────────────────────────────────────────
ADMIN_BACKOFFICE_URL = env(
    "ADMIN_BACKOFFICE_URL", default="/admin-panel/accounts-management/"
)

# 알림 "지연" 판정 임계값 (분)
NOTIFICATION_DELAY_THRESHOLD_MINUTES = env.int(
    "NOTIFICATION_DELAY_THRESHOLD_MINUTES", default=5
)

# Celery → FastAPI WS 브리지 호출용 내부 URL
FASTAPI_INTERNAL_URL = env("FASTAPI_INTERNAL_URL", default="http://127.0.0.1:8001")

# 서비스 간 인증 토큰 (빈 문자열이면 인증 비활성)
INTERNAL_SERVICE_TOKEN = env("INTERNAL_SERVICE_TOKEN", default="")

# True 시 정적 임계값 판정을 FastAPI에 위임
STATIC_THRESHOLD_AT_FASTAPI = env.bool("STATIC_THRESHOLD_AT_FASTAPI", default=False)

# 브라우저가 FastAPI에 접속할 때 사용하는 공개 주소
FRONTEND_API_BASE_URL = env("FRONTEND_API_BASE_URL", default="")
FRONTEND_WS_BASE_URL = env("FRONTEND_WS_BASE_URL", default="ws://127.0.0.1:8001")

# ── Discord 알람 연동 ─────────────────────────────────────────
# 알람을 외부 Discord 채널로도 발송. 미설정(기본 False / 빈 webhook)이면 미발송.
DISCORD_ALARM_ENABLED = env.bool("DISCORD_ALARM_ENABLED", default=False)
DISCORD_WEBHOOK_ADMIN = env("DISCORD_WEBHOOK_ADMIN", default="")  # 관리자 채널
DISCORD_WEBHOOK_WORKER = env("DISCORD_WEBHOOK_WORKER", default="")  # 작업자 채널

# ── 파일 경로 ─────────────────────────────────────────────────
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ML 모델(.pkl) 저장 경로 — 웹 서버가 직접 서빙하지 못하도록 MEDIA_ROOT 밖에 위치
ML_MODELS_DIR = env("ML_MODELS_DIR", default=str(BASE_DIR / "ml_models"))

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# ── 국제화 ────────────────────────────────────────────────────
LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_TZ = True

# ── 로깅 ──────────────────────────────────────────────────────
LOG_LEVEL = env("DJANGO_LOG_LEVEL", default="INFO")

# 파일 로깅용 디렉토리 — settings 로드 시 자동 생성 (로컬·컨테이너 모두 보장)
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "diconai": {
            "format": "{asctime} {levelname:<7} {name}: {message}",
            "datefmt": "%Y-%m-%d %H:%M:%S",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "diconai",
        },
        # ERROR 이상만 DB에 영속화 (AppLog 모델)
        "applog_db": {
            "class": "apps.operations.logging.db_handler.DBLogHandler",
            "level": "ERROR",
            "formatter": "diconai",
        },
        # ERROR 로그 파일 (100MB × 10 = 1GB 캡) — Docker 재시작 후에도 흔적 보존
        "file_error": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOGS_DIR / "error.log"),
            "maxBytes": 100 * 1024 * 1024,
            "backupCount": 10,
            "level": "ERROR",
            "formatter": "diconai",
            "encoding": "utf-8",
        },
        # INFO 로그 파일 (50MB × 5 = 250MB 캡) — 알람·운영 태스크 화이트리스트만
        "file_app": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOGS_DIR / "app.log"),
            "maxBytes": 50 * 1024 * 1024,
            "backupCount": 5,
            "level": "INFO",
            "formatter": "diconai",
            "encoding": "utf-8",
        },
    },
    "root": {
        # file_app은 root 제외 — 모든 INFO 잡히면 라이브러리 노이즈 폭증
        # file_error는 root 유지 — ERROR는 어디서 터져도 흔적 남아야 안전
        "handlers": ["console", "applog_db", "file_error"],
        "level": LOG_LEVEL,
    },
    "loggers": {
        "django.request": {
            "handlers": ["console", "file_error"],
            "level": "WARNING",
            "propagate": False,
        },
        # 알람 흐름 — app.log 화이트리스트
        "apps.alerts": {
            "handlers": ["console", "file_app", "file_error"],
            "level": "INFO",
            "propagate": False,
        },
        # Celery beat 태스크 — app.log 화이트리스트
        "apps.operations.tasks": {
            "handlers": ["console", "file_app", "file_error"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

# ── Redis & Celery ────────────────────────────────────────────
REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")

CELERY_BROKER_URL = REDIS_URL  # 태스크 전달 채널
CELERY_RESULT_BACKEND = REDIS_URL  # 태스크 결과 저장
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True

# 큐 분리: alarm(실시간 알람) / metric(주기적 수집) — 알람이 메트릭에 밀리지 않도록
CELERY_TASK_ROUTES = {
    "apps.alerts.tasks.*": {"queue": "alarm"},
    "apps.operations.tasks.*": {"queue": "metric"},
}

from celery.schedules import crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
    # 매일 09:30 데이터 보관 정책 실행 (WSL2 환경에서 03:00는 PC 꺼짐 문제)
    "data_retention_daily": {
        "task": "apps.operations.tasks.data_retention_task.run_data_retention",
        "schedule": crontab(hour=9, minute=30),
        "args": (False,),  # dry_run=False
    },
    # 30초마다 Celery 큐 길이를 Prometheus Gauge에 기록
    "celery_queue_length_metrics": {
        "task": "apps.operations.tasks.queue_metrics_task.record_celery_queue_length",
        "schedule": timedelta(seconds=30),
    },
    # 60초마다 DB 상태(파일 크기 등) 기록
    "db_health_metrics": {
        "task": "apps.operations.tasks.db_health_task.record_db_health",
        "schedule": timedelta(seconds=60),
    },
    # 매주 일요일 03:00 만료된 세션 정리
    "clear_expired_sessions": {
        "task": "apps.operations.tasks.clear_sessions_task.clear_expired_sessions",
        "schedule": crontab(hour=3, minute=0, day_of_week=0),
    },
}

# ── Cache (Redis) ─────────────────────────────────────────────
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

# 동일 활성 Event에 알람 재팝업 최소 간격 (초)
# 운영: 60초, 시연: 15초 (짧은 데모 시간 안에 재팝업 동작을 보여주기 위함)
ALARM_REPOPUP_COOLDOWN_SEC = env.int("ALARM_REPOPUP_COOLDOWN_SEC", default=60)

# DANGER 발화 전 연속 초과 틱 수 — 단일 틱 센서 스파이크/전력 인러시의 false danger
# 억제. 1=즉시 발화(기존 동작), 2=2틱 confirm(≈송신주기×2). 시연 직전 1로 되돌리면
# 즉시성 복원. 가스/전력 룰 danger 분기(gas_alarm/power_alarm)에서 사용.
DANGER_CONFIRM_TICKS = env.int("DANGER_CONFIRM_TICKS", default=2)
