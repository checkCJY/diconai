"""템플릿 컨텍스트에 프론트엔드 노출용 URL을 주입한다.

- FRONTEND_API_BASE_URL: 브라우저 → DRF/FastAPI HTTP 베이스 (빈 문자열이면 same-origin)
- FRONTEND_WS_BASE_URL:  브라우저 → FastAPI WebSocket 베이스

settings.py의 동명 변수를 참조하므로 .env 변경만으로 운영/개발 환경 전환이 가능하다.
"""

from django.conf import settings


def frontend_config(request):
    return {
        "FRONTEND_API_BASE_URL": settings.FRONTEND_API_BASE_URL,
        "FRONTEND_WS_BASE_URL": settings.FRONTEND_WS_BASE_URL,
    }
