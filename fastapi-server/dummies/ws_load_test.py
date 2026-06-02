# dummies/ws_load_test.py — WebSocket + HTTP 동시 접속 부하 테스트
#
# Grafana/Prometheus 모니터링 검증용.
# N명이 동시에 WS 연결을 유지하면서 HTTP 요청도 주기적으로 보내는 상황을 시뮬레이션한다.
#
# 사용:
#   make exec s=fastapi cmd="python -m dummies.ws_load_test --users 10"
#   make exec s=fastapi cmd="python -m dummies.ws_load_test --users 50 --duration 120"
#   make exec s=fastapi cmd="python -m dummies.ws_load_test --users 10 30 50"
#
# Grafana 확인 포인트:
#   Overview 대시보드
#     FastAPI — 요청 수 (RPS)         ← HTTP 요청 반영
#     FastAPI — 응답시간 p95           ← HTTP 레이턴시
#     FastAPI — 에러율 5xx             ← HTTP 에러
#     DRF    — 요청 수 / 응답시간 p95  ← DRF HTTP 반영
#   알람 대시보드
#     fastapi_ws_connections{type="sensor"}  ← 실시간 접속자 수
#     fastapi_alarm_queue_length             ← 알람 큐 밀림 여부

import argparse
import asyncio
import statistics
import time

import httpx
import jwt
import websockets
from websockets.exceptions import ConnectionClosed

from core.config import settings

_FASTAPI_BASE = f"http://{settings.DUMMY_TARGET_HOST}:{settings.DUMMY_TARGET_PORT}"
_DRF_BASE = settings.DRF_BASE_URL

# 브라우저가 주기적으로 호출하는 엔드포인트 (실제 사용 패턴 반영)
_HTTP_TARGETS = [
    (_FASTAPI_BASE, "/health/"),
    (_DRF_BASE,     "/health/"),
]

# 유저당 HTTP 요청 간격 (초) — 실제 브라우저 폴링 주기
_HTTP_INTERVAL = 5.0


def _make_token() -> str:
    """JWT_SIGNING_KEY가 설정된 경우 테스트용 토큰을 생성한다."""
    if not settings.JWT_SIGNING_KEY:
        return ""
    payload = {"user_id": 0, "exp": int(time.time()) + 3600}
    return jwt.encode(payload, settings.JWT_SIGNING_KEY, algorithm=settings.JWT_ALGORITHM)


def _ws_url() -> str:
    base = f"ws://{settings.DUMMY_TARGET_HOST}:{settings.DUMMY_TARGET_PORT}/ws/sensors/"
    token = _make_token()
    return f"{base}?token={token}" if token else base


WS_URL = _ws_url()


class _Stats:
    def __init__(self, cid: int):
        self.cid = cid
        self.connect_ms: float | None = None
        self.msgs: int = 0
        self.error: str | None = None
        self._start: float | None = None
        self._end: float | None = None

    @property
    def duration(self) -> float:
        if self._start is None:
            return 0.0
        return (self._end or time.perf_counter()) - self._start


class _HttpStats:
    def __init__(self):
        self.total: int = 0
        self.errors: int = 0
        self.latencies_ms: list[float] = []


async def _http_worker(duration: float, stats: _HttpStats) -> None:
    """WS 연결이 유지되는 동안 주기적으로 HTTP 요청을 보낸다."""
    deadline = time.perf_counter() + duration
    async with httpx.AsyncClient(timeout=5.0) as client:
        while time.perf_counter() < deadline:
            for base, path in _HTTP_TARGETS:
                t0 = time.perf_counter()
                try:
                    r = await client.get(f"{base}{path}")
                    stats.latencies_ms.append((time.perf_counter() - t0) * 1000)
                    stats.total += 1
                    if r.status_code >= 500:
                        stats.errors += 1
                except Exception:
                    stats.errors += 1
                    stats.total += 1
            remaining = deadline - time.perf_counter()
            if remaining > 0:
                await asyncio.sleep(min(_HTTP_INTERVAL, remaining))


async def _client(cid: int, duration: float, out: list, ready: asyncio.Event) -> None:
    s = _Stats(cid)
    out[cid] = s
    t0 = time.perf_counter()
    try:
        async with websockets.connect(WS_URL, open_timeout=10) as ws:
            s._start = time.perf_counter()
            s.connect_ms = (s._start - t0) * 1000
            ready.set()
            deadline = s._start + duration
            while time.perf_counter() < deadline:
                remain = deadline - time.perf_counter()
                try:
                    await asyncio.wait_for(ws.recv(), timeout=min(remain, 1.0))
                    s.msgs += 1
                except asyncio.TimeoutError:
                    pass
                except ConnectionClosed:
                    break
    except Exception as exc:
        s.error = str(exc)
        ready.set()
    finally:
        s._end = time.perf_counter()


def _report(n: int, stats: list[_Stats], http: _HttpStats, elapsed: float) -> None:
    ok = [s for s in stats if s.error is None]
    fail = [s for s in stats if s.error is not None]
    latencies = [s.connect_ms for s in ok if s.connect_ms is not None]
    total_msgs = sum(s.msgs for s in ok)

    sep = "=" * 55
    print(f"\n{sep}")
    print(f"  부하 테스트 결과 — {n}명 동시 접속")
    print(sep)
    print(f"  테스트 시간  : {elapsed:.1f}s")

    print(f"\n  [WebSocket]")
    print(f"    성공 접속  : {len(ok)} / {n}")
    print(f"    실패 접속  : {len(fail)}")
    if latencies:
        print(f"    연결 레이턴시 평균 : {statistics.mean(latencies):.1f} ms")
        print(f"    연결 레이턴시 최대 : {max(latencies):.1f} ms")
    if ok:
        print(f"    수신 메시지  : {total_msgs}건 ({total_msgs / elapsed:.2f} msg/s)")

    print(f"\n  [HTTP]")
    print(f"    총 요청 수   : {http.total}건")
    print(f"    에러 수      : {http.errors}건")
    if http.latencies_ms:
        p95 = sorted(http.latencies_ms)[int(len(http.latencies_ms) * 0.95)]
        print(f"    응답시간 평균 : {statistics.mean(http.latencies_ms):.1f} ms")
        print(f"    응답시간 최대 : {max(http.latencies_ms):.1f} ms")
        print(f"    응답시간 p95  : {p95:.1f} ms")
    print(f"    대상         : {[p for _, p in _HTTP_TARGETS]}")

    if fail:
        print(f"\n  [WS 실패]")
        for s in fail[:5]:
            print(f"    client#{s.cid}: {s.error}")
        if len(fail) > 5:
            print(f"    ... 외 {len(fail) - 5}건")

    print(f"\n  Grafana Overview → FastAPI/DRF 요청 수·응답시간 패널 확인")
    print(sep)


async def _run(n: int, duration: float) -> None:
    print(f"\n[부하 테스트] {n}명 접속 시작")
    print(f"  WS   → {WS_URL[:70]}...")
    print(f"  HTTP → {[b + p for b, p in _HTTP_TARGETS]}")
    print(f"  유지 시간: {duration}s  (Ctrl+C 로 중단)")

    stats: list[_Stats] = [_Stats(i) for i in range(n)]
    ready_events = [asyncio.Event() for _ in range(n)]
    http_stats = _HttpStats()

    t0 = time.perf_counter()
    tasks = [
        asyncio.create_task(_client(i, duration, stats, ready_events[i]))
        for i in range(n)
    ]
    http_task = asyncio.create_task(_http_worker(duration, http_stats))

    try:
        await asyncio.wait_for(
            asyncio.gather(*[e.wait() for e in ready_events]),
            timeout=15.0,
        )
    except asyncio.TimeoutError:
        pass

    ok = sum(1 for s in stats if s.error is None and s.connect_ms is not None)
    print(f"  [{time.perf_counter() - t0:.1f}s] WS 접속 완료: {ok}/{n}명 연결")

    try:
        await asyncio.gather(*tasks, http_task)
    except asyncio.CancelledError:
        for t in [*tasks, http_task]:
            t.cancel()
        await asyncio.gather(*tasks, http_task, return_exceptions=True)

    _report(n, stats, http_stats, time.perf_counter() - t0)


async def main(user_counts: list[int], duration: float) -> None:
    for i, n in enumerate(user_counts):
        try:
            await _run(n, duration)
        except KeyboardInterrupt:
            print("\n[중단]")
            break
        if i < len(user_counts) - 1:
            print("  다음 단계까지 5초 대기...")
            await asyncio.sleep(5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WebSocket 동시 접속 부하 테스트")
    parser.add_argument("--users", nargs="+", type=int, default=[10], metavar="N")
    parser.add_argument("--duration", type=float, default=30.0)
    args = parser.parse_args()
    try:
        asyncio.run(main(args.users, args.duration))
    except KeyboardInterrupt:
        print("\n[종료]")
