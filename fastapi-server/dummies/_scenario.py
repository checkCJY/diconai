# dummies/_scenario.py — 시연 시나리오 모드 polling 공통 헬퍼
#
# FastAPI(/internal/scenario/mode)에 GET 요청해 현재 모드를 읽어온다.
# 매 틱 호출되므로 _CACHE_TTL_SEC 동안 결과를 캐시한다.
# 네트워크 실패 시 환경변수 fallback("mixed").

import logging
import time

import requests

from core.config import settings

logger = logging.getLogger(__name__)

_CACHE_TTL_SEC = 1.0
_cache: dict = {"mode": settings.DUMMY_SCENARIO_MODE, "fetched_at": 0.0}

_FASTAPI_BASE_URL = f"http://{settings.DUMMY_TARGET_HOST}:{settings.DUMMY_TARGET_PORT}"
_MODE_URL = f"{_FASTAPI_BASE_URL}/internal/scenario/mode"

ALLOWED_MODES = {"mixed", "normal", "warning", "danger"}


def get_scenario_mode() -> str:
    """현재 시나리오 모드를 반환한다. 1초 TTL 캐시 + 실패 시 직전 값 유지."""
    now = time.time()
    if now - _cache["fetched_at"] < _CACHE_TTL_SEC:
        return _cache["mode"]
    try:
        res = requests.get(_MODE_URL, timeout=1.0)
        mode = res.json().get("mode", "mixed")
        if mode in ALLOWED_MODES:
            _cache["mode"] = mode
    except Exception as exc:
        logger.debug("[scenario] polling 실패 (직전 값 유지): %s", exc)
    _cache["fetched_at"] = now
    return _cache["mode"]
