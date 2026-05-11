"""websocket/auth.py — WebSocket JWT 인증 헬퍼.

WS 표준은 핸드셰이크에 Authorization 헤더를 보낼 수 없어 query string으로 토큰 전송:
    ws://host/ws/sensors/?token=<access_token>

drf-server의 SimpleJWT가 발급한 access 토큰을 같은 SIGNING_KEY로 검증한다.

옵트인 활성화 (Phase 5):
- ``settings.JWT_SIGNING_KEY``가 빈 문자열이면 인증 비활성 (기존 동작 유지)
- 값이 설정되면 query에서 token 추출 → PyJWT 검증 → payload 반환

호출 패턴:
    payload = verify_jwt_from_ws_query(websocket)
    if payload is None:
        await websocket.close(code=1008, reason="unauthenticated")
        return

옵트인 비활성 시는 ``{}`` (빈 dict, truthy) 반환 — 호출자는 ``is None`` 체크만으로 통과 분기.
"""

import logging

import jwt
from fastapi import WebSocket

from core.config import settings

logger = logging.getLogger(__name__)


def verify_jwt_from_ws_query(websocket: WebSocket) -> dict | None:
    """WebSocket 핸드셰이크의 query string에서 JWT 토큰을 추출·검증한다.

    Returns:
        - payload dict: 검증 성공 (또는 옵트인 비활성 시 빈 dict ``{}``)
        - None: 토큰 누락·무효·만료
    """
    expected_key = settings.JWT_SIGNING_KEY
    if not expected_key:
        # 옵트인 비활성 — 통과 (기존 동작 유지)
        return {}

    token = websocket.query_params.get("token", "")
    if not token:
        logger.warning("[ws-auth] action=token_missing path=%s", websocket.url.path)
        return None

    try:
        payload = jwt.decode(
            token,
            expected_key,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except jwt.ExpiredSignatureError:
        logger.warning("[ws-auth] action=token_expired path=%s", websocket.url.path)
        return None
    except jwt.InvalidTokenError as exc:
        logger.warning(
            "[ws-auth] action=token_invalid path=%s error=%s",
            websocket.url.path,
            exc,
        )
        return None

    return payload
