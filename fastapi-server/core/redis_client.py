# core/redis_client.py — Redis 클라이언트 싱글톤
#
# Phase 1 C4 — 알람 큐(diconai:ws:alarms)를 비롯해 향후 IF rate limit,
# 메트릭 등에서 재사용할 단일 redis.asyncio.Redis 인스턴스를 제공한다.
# 이벤트 루프를 막지 않도록 동기 클라이언트가 아닌 비동기 변종(`redis.asyncio`)을 사용.

import redis.asyncio as aioredis

from core.config import settings

_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    """프로세스 단일 Redis 클라이언트를 반환한다. 최초 호출 시 lazy 생성."""
    global _client
    if _client is None:
        _client = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,  # str/bytes 자동 디코딩 — json.loads 직접 사용 가능
        )
    return _client


async def close_redis() -> None:
    """lifespan shutdown에서 호출. 연결 풀 정리."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
