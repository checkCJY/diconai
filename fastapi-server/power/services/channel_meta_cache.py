# power/services/channel_meta_cache.py — DRF PowerDevice.channel_meta 캐시
#
# 운영자가 어드민에서 채널 라벨/정격을 변경할 수 있도록, 코드 하드코딩 대신
# DRF에서 주기적으로 fetch한 channel_meta를 메모리에 캐싱한다.
# build_equipment()가 채널 라벨과 정격 % 환산에 사용.
#
# 동기화 주기: REFRESH_INTERVAL_SEC (기본 300s). 어드민 수정 후 최대 5분 지연.
# fetch 실패 시 직전 캐시 유지 (운영 중단 회피).

import asyncio
import logging
from typing import Any

import httpx

from core.config import settings

logger = logging.getLogger(__name__)

REFRESH_INTERVAL_SEC = 300
FAILURE_INITIAL_BACKOFF_SEC = 5
FAILURE_MAX_BACKOFF_SEC = 60
DRF_CHANNEL_META_PATH = "/api/monitoring/power/channel-meta/"

# {device_id_str: {"1": {"name": ..., "rated_w": ..., "rated_a": ..., "rated_v": ...}, ...}}
_channel_meta_by_device: dict[str, dict[str, dict[str, Any]]] = {}


def get_channel_entry(device_id: str | None, channel: int) -> dict[str, Any]:
    """device_id + 채널 번호로 채널 메타 entry 반환. 미존재 시 빈 dict."""
    if device_id is None:
        return _first_channel_entry(channel)
    return (_channel_meta_by_device.get(device_id) or {}).get(str(channel)) or {}


def _first_channel_entry(channel: int) -> dict[str, Any]:
    """device_id 미지정 시 첫 디바이스의 entry 반환 (단일 디바이스 운영 환경 호환)."""
    for meta in _channel_meta_by_device.values():
        entry = (meta or {}).get(str(channel))
        if entry:
            return entry
    return {}


async def refresh_channel_meta() -> bool:
    """DRF에서 channel_meta를 가져와 모듈 캐시 갱신. 성공/실패 bool 반환."""
    url = f"{settings.DRF_BASE_URL}{DRF_CHANNEL_META_PATH}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            payload = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(f"[channel_meta_cache] fetch failed: {exc!r}")
        return False

    _channel_meta_by_device.clear()
    _channel_meta_by_device.update(payload)
    logger.info(
        f"[channel_meta_cache] refreshed devices={len(payload)} "
        f"channels={sum(len(m or {}) for m in payload.values())}"
    )
    return True


async def channel_meta_refresh_loop() -> None:
    """lifespan background task.

    [정책]
    - 성공 시 REFRESH_INTERVAL_SEC(5분) 주기
    - 실패 시 지수 backoff (5s → 10s → 20s → 40s → 60s 상한) — 부팅 순서로 DRF가
      아직 안 뜬 경우에도 1분 내 복구.
    """
    backoff = FAILURE_INITIAL_BACKOFF_SEC
    while True:
        ok = await refresh_channel_meta()
        if ok:
            backoff = FAILURE_INITIAL_BACKOFF_SEC
            await asyncio.sleep(REFRESH_INTERVAL_SEC)
        else:
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, FAILURE_MAX_BACKOFF_SEC)
