"""
운영 환경 설정 — docker compose up 으로 시연/배포할 때 사용.
환경변수는 docker-compose.yml의 env_file(.env.docker)에서 주입받는다.
이 파일에서는 read_env()를 호출하지 않는다 (Docker가 직접 주입).

사용법:
    DJANGO_SETTINGS_MODULE=config.settings.prod  (docker-compose에서 자동 설정)
"""

from .base import *  # noqa: F401, F403

# ── 운영 핵심 설정 ────────────────────────────────────────────

# DEBUG는 환경변수와 무관하게 항상 False — 실수로 .env에 True를 써도 적용 안 됨
DEBUG = False

# ALLOWED_HOSTS: 기본값 없음. 환경변수 미설정 시 서버 기동 실패 (의도된 동작)
# docker-compose의 DJANGO_ALLOWED_HOSTS 에 실제 도메인/IP 반드시 명시
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")  # noqa: F405

# ── 정적 파일 (운영 모드) ─────────────────────────────────────
# 해시 매니페스트 + gzip 압축으로 캐시 버스팅·CDN 친화 서빙
# collectstatic 실행 필요 (docker entrypoint 또는 배포 스크립트에서 처리)
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# ── 보안 헤더 (HTTPS 도입 시 주석 해제) ──────────────────────
# 현재 데모 환경은 HTTP이므로 비활성. 실 서비스 전환 시 아래 항목 활성화 필요.
#
# SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# SESSION_COOKIE_SECURE = True   # 세션 쿠키를 HTTPS에서만 전송
# CSRF_COOKIE_SECURE = True      # CSRF 쿠키를 HTTPS에서만 전송
# SECURE_HSTS_SECONDS = 31536000 # 브라우저에 1년간 HTTPS 강제 지시
