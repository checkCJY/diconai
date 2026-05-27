"""
개발 환경 설정 — 로컬에서 python manage.py runserver 로 실행할 때 사용.
.env.dev 파일을 읽어 환경변수를 주입한다.

사용법:
    DJANGO_SETTINGS_MODULE=config.settings.dev python manage.py runserver
    (manage.py 기본값이 이미 dev로 설정돼 있음)
"""

# .env.dev를 base 임포트 전에 먼저 읽어야 함
# base.py에서 SECRET_KEY 등을 env()로 즉시 읽기 때문
import environ
from pathlib import Path

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_env_file = _BASE_DIR / ".env.dev"
if _env_file.exists():
    environ.Env.read_env(_env_file)

from .base import *  # noqa: F401, F403

# ── 개발 전용 설정 ────────────────────────────────────────────

# DEBUG=True: 에러 발생 시 상세 traceback 화면 표시 (로컬 개발 편의용)
# 절대 운영 서버에서 True로 두면 안 됨 — 소스코드/환경변수가 브라우저에 노출됨
DEBUG = True

# 로컬에서는 어떤 호스트로 접속해도 허용
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["*"])

# ── 정적 파일 (개발 모드) ─────────────────────────────────────
# DEBUG=True일 때: 파일 변경 시 collectstatic 없이 즉시 반영
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}
WHITENOISE_USE_FINDERS = True    # STATICFILES_DIRS에서 직접 서빙
WHITENOISE_AUTOREFRESH = True    # 매 요청마다 파일 재스캔
