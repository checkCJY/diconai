"""서비스 간 토큰 인증 회귀 가드 (P1 신규).

ServiceTokenAuthentication(core/authentication.py)은 fastapi→drf 내부 호출용
옵트인 인증이다. INTERNAL_SERVICE_TOKEN 설정 시 `Authorization: Bearer <token>`
검증, 미설정 시 비활성(다음 인증으로 위임). 토큰 누락/오류는 AuthenticationFailed.
"""

from types import SimpleNamespace

import pytest
from django.test import override_settings
from rest_framework.exceptions import AuthenticationFailed

from apps.core.authentication import ServiceTokenAuthentication


def _request(auth_header=None):
    """META 만 갖춘 최소 request 스텁."""
    meta = {}
    if auth_header is not None:
        meta["HTTP_AUTHORIZATION"] = auth_header
    return SimpleNamespace(META=meta)


@override_settings(INTERNAL_SERVICE_TOKEN="s3cret")
def test_valid_token_authenticates():
    """올바른 Bearer 토큰 → (None, None) 인증 통과."""
    result = ServiceTokenAuthentication().authenticate(_request("Bearer s3cret"))
    assert result == (None, None)


@override_settings(INTERNAL_SERVICE_TOKEN="s3cret")
def test_wrong_token_rejected():
    """틀린 토큰 → AuthenticationFailed."""
    with pytest.raises(AuthenticationFailed):
        ServiceTokenAuthentication().authenticate(_request("Bearer wrong"))


@override_settings(INTERNAL_SERVICE_TOKEN="s3cret")
def test_missing_authorization_header_rejected():
    """Authorization 헤더 없음 → AuthenticationFailed."""
    with pytest.raises(AuthenticationFailed):
        ServiceTokenAuthentication().authenticate(_request())


@override_settings(INTERNAL_SERVICE_TOKEN="")
def test_disabled_when_token_unset_returns_none():
    """토큰 미설정(옵트인 비활성) → None (다음 인증 클래스로 위임)."""
    result = ServiceTokenAuthentication().authenticate(_request("Bearer anything"))
    assert result is None
