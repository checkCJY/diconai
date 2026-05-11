"""apps/core/authentication.py — 서비스 간 호출용 인증.

서비스 간 호출(예: fastapi → drf 인입 엔드포인트)에서 사용한다.
브라우저용 JWT 인증과는 별도 — view의 ``authentication_classes``로 명시 적용.

토큰 정책 (Phase 5):
- ``settings.INTERNAL_SERVICE_TOKEN``이 빈 문자열이면 인증 비활성 (기존 동작 유지).
- 값이 설정되면 ``Authorization: Bearer <token>`` 헤더 검증.

옵트인 패턴이라 토큰 미설정 환경(개발·기존 운영)에서도 그대로 작동한다.
"""

from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed


class ServiceTokenAuthentication(BaseAuthentication):
    """``Authorization: Bearer <INTERNAL_SERVICE_TOKEN>`` 헤더 검증."""

    def authenticate(self, request):
        expected = getattr(settings, "INTERNAL_SERVICE_TOKEN", "") or ""
        if not expected:
            # 토큰 미설정 → 인증 비활성 (다음 인증 클래스로 위임)
            return None

        header = request.META.get("HTTP_AUTHORIZATION", "")
        if not header.startswith("Bearer "):
            raise AuthenticationFailed("서비스 토큰이 필요합니다.")

        provided = header[7:].strip()
        if provided != expected:
            raise AuthenticationFailed("유효하지 않은 서비스 토큰입니다.")

        # 시스템 호출이라 User 객체는 None. (None, None)을 반환하면 DRF는
        # request.user를 AnonymousUser로 두지만 인증은 통과로 인식한다.
        return (None, None)

    def authenticate_header(self, request):
        return "Bearer"
