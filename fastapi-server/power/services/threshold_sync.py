# power/services/threshold_sync.py — DRF Threshold 5분 sync (T4 D1b)
#
# 운영자가 어드민에서 정격 % 임계치 (power_facility_default 그룹) 를 변경할 수
# 있도록, 코드 하드코딩 대신 DRF 에서 주기적으로 fetch 한 threshold 를 메모리에
# 캐싱한다. T4 sub-plan §3.1 — fastapi 가 단일 결정자가 되려면 DRF 가 진실
# 공급원인 정적 임계치를 5분 주기로 sync 해야 한다.
#
# [패턴 차용]
# channel_meta_cache.py 와 동일 구조 (5분 polling + 지수 backoff + lifespan task).
# fetch 실패 시 직전 캐시 유지 — 운영 중단 회피.
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
DRF_THRESHOLD_META_PATH = "/api/monitoring/power/threshold-meta/"

# {item_name: {warning_min, warning_max, danger_min, danger_max, unit}}
# item_name ∈ {"power_w", "current", "voltage"}.
# decide_alarm 매트릭스 (D2 commit) 의 정적 평가 입력. None 값은 단방향 임계치를
# 의미 (예: power_w 의 warning_min/danger_min = None — 상한만 평가).
_threshold_meta: dict[str, dict[str, Any]] = {}


def get_threshold_meta(item: str) -> dict[str, Any]:
    """item 명 ("power_w" | "current" | "voltage") 으로 임계치 dict 반환.

    미존재 시 빈 dict. decide_alarm 호출자는 빈 dict 를 "임계치 미설정 (fail-safe
    NORMAL 처리)" 로 해석.
    """
    return _threshold_meta.get(item) or {}


def get_all_threshold_meta() -> dict[str, dict[str, Any]]:
    """현재 캐시 전체를 얕은 copy 로 반환 — 단위 테스트·디버깅용."""
    return dict(_threshold_meta)


async def refresh_threshold_meta() -> bool:
    """DRF 에서 threshold-meta 를 가져와 모듈 캐시 갱신. 성공/실패 bool 반환.

    실패 시 직전 캐시는 그대로 유지 (clear 안 함) — 운영 중 일시 장애에도
    fastapi 가 마지막 값으로 알람 판정 계속 가능.
    """
    url = f"{settings.DRF_BASE_URL}{DRF_THRESHOLD_META_PATH}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            payload = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(f"[threshold_sync] fetch failed: {exc!r}")
        return False

    _threshold_meta.clear()
    _threshold_meta.update(payload)
    logger.info(
        f"[threshold_sync] refreshed items={list(payload.keys())} count={len(payload)}"
    )
    return True


async def threshold_sync_loop() -> None:
    """lifespan background task.

    [정책]
    - 성공 시 REFRESH_INTERVAL_SEC(5분) 주기
    - 실패 시 지수 backoff (5s → 10s → 20s → 40s → 60s 상한) — 부팅 순서로 DRF 가
      아직 안 뜬 경우에도 1분 내 복구.

    channel_meta_refresh_loop 와 동일 구조 — 두 sync 가 같은 cadence·복구 정책.
    """
    backoff = FAILURE_INITIAL_BACKOFF_SEC
    while True:
        ok = await refresh_threshold_meta()
        if ok:
            backoff = FAILURE_INITIAL_BACKOFF_SEC
            await asyncio.sleep(REFRESH_INTERVAL_SEC)
        else:
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, FAILURE_MAX_BACKOFF_SEC)
