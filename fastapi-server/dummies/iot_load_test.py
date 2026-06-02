# dummies/iot_load_test.py — IoT 기기 수 증가 부하 테스트
#
# N개의 가상 IoT 기기가 동시에 FastAPI로 센서 데이터를 전송하는 상황을 시뮬레이션한다.
# 기기 수를 단계별로 올리며 FastAPI가 몇 대까지 처리할 수 있는지 확인한다.
#
# 사전 조건:
#   make iot-seed-devices gas=N power=N  # 테스트 기기 DB 등록
#
# 사용:
#   make exec s=fastapi cmd="python -m dummies.iot_load_test --gas 5 --power 5 --duration 60"
#   make exec s=fastapi cmd="python -m dummies.iot_load_test --gas 5 5 10 20 --power 5 5 10 20 --duration 60"
#
# 각 가스 기기: 1초마다 POST /api/sensors/gas  (1 req/s)
# 각 전력 기기: 1초마다 POST /api/power/watt   (1 req/s, watt만 — 핵심 부하)

import argparse
import asyncio
import statistics
import time

import httpx

from core.config import settings

_BASE = f"http://{settings.DUMMY_TARGET_HOST}:{settings.DUMMY_TARGET_PORT}"
_GAS_URL = f"{_BASE}/api/sensors/gas"
_POWER_WATT_URL = f"{_BASE}/api/power/watt"
_INTERVAL = 1.0
_PREFIX = "test_iot_"


def _gas_payload(device_id: str) -> dict:
    from datetime import datetime, timezone
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "device_id": device_id,
        "device_name": device_id,
        "location": {"x": 200.0, "y": 200.0},
        "o2": 20.9,
        "co": 5.0,
        "co2": 400.0,
        "h2s": 1.0,
        "lel": 0.0,
        "no2": 0.0,
        "so2": 0.0,
        "o3": 0.0,
        "nh3": 0.0,
        "voc": 0.0,
    }


def _power_payload(device_id: str) -> dict:
    return {
        "device_id": device_id,
        "slave01": 1000.0, "slave02": 1000.0,
        "slave11": 1000.0, "slave12": 1000.0,
        "slave21": 1000.0, "slave22": 1000.0,
        "slave31": 1000.0, "slave32": 1000.0,
        "slave41": 1000.0, "slave42": 1000.0,
        "slave51": 1000.0, "slave52": 1000.0,
        "slave61": 1000.0, "slave62": 1000.0,
        "slave71": 1000.0, "slave72": 1000.0,
    }


class _Stats:
    def __init__(self):
        self.total = 0
        self.errors = 0
        self.latencies_ms: list[float] = []


async def _device_loop(url: str, payload: dict, duration: float, stats: _Stats) -> None:
    deadline = time.perf_counter() + duration
    async with httpx.AsyncClient(timeout=5.0) as client:
        while time.perf_counter() < deadline:
            t0 = time.perf_counter()
            try:
                r = await client.post(url, json=payload)
                stats.latencies_ms.append((time.perf_counter() - t0) * 1000)
                stats.total += 1
                if r.status_code >= 400:
                    stats.errors += 1
            except Exception:
                stats.errors += 1
                stats.total += 1
            remaining = deadline - time.perf_counter()
            if remaining > 0:
                await asyncio.sleep(min(_INTERVAL, remaining))


def _report(gas_n: int, power_n: int, gas_stats: _Stats, power_stats: _Stats, elapsed: float) -> None:
    sep = "=" * 55
    print(f"\n{sep}")
    print(f"  IoT 부하 테스트 결과 — 가스 {gas_n}대 / 전력 {power_n}대")
    print(sep)
    print(f"  테스트 시간: {elapsed:.1f}s")

    for label, stats in [("가스", gas_stats), ("전력(watt)", power_stats)]:
        print(f"\n  [{label}]")
        print(f"    총 요청  : {stats.total}건  에러: {stats.errors}건")
        if stats.latencies_ms:
            lats = sorted(stats.latencies_ms)
            p95 = lats[int(len(lats) * 0.95)]
            print(f"    응답시간 평균: {statistics.mean(lats):.1f}ms")
            print(f"    응답시간 p95 : {p95:.1f}ms")
            print(f"    응답시간 최대: {max(lats):.1f}ms")
        rps = stats.total / elapsed if elapsed > 0 else 0
        print(f"    RPS          : {rps:.1f}")

    print(f"\n  Grafana → FastAPI 응답시간 p95 / 에러율 5xx / stream_lag 확인")
    print(sep)


async def _run(gas_n: int, power_n: int, duration: float) -> None:
    print(f"\n[IoT 부하 테스트] 가스 {gas_n}대 / 전력 {power_n}대 시작")
    print(f"  전송 주기: {_INTERVAL}s  유지: {duration}s")

    gas_stats = _Stats()
    power_stats = _Stats()
    tasks = []

    for i in range(1, gas_n + 1):
        device_id = f"{_PREFIX}gas_{i:03d}"
        tasks.append(asyncio.create_task(
            _device_loop(_GAS_URL, _gas_payload(device_id), duration, gas_stats)
        ))

    for i in range(1, power_n + 1):
        device_id = f"{_PREFIX}pwr_{i:03d}"
        tasks.append(asyncio.create_task(
            _device_loop(_POWER_WATT_URL, _power_payload(device_id), duration, power_stats)
        ))

    t0 = time.perf_counter()
    await asyncio.gather(*tasks)
    _report(gas_n, power_n, gas_stats, power_stats, time.perf_counter() - t0)


async def main(gas_counts: list[int], power_counts: list[int], duration: float) -> None:
    for i, (g, p) in enumerate(zip(gas_counts, power_counts)):
        try:
            await _run(g, p, duration)
        except KeyboardInterrupt:
            print("\n[중단]")
            break
        if i < len(gas_counts) - 1:
            print("  다음 단계까지 10초 대기...")
            await asyncio.sleep(10)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="IoT 기기 수 증가 부하 테스트")
    parser.add_argument("--gas", nargs="+", type=int, default=[1], metavar="N")
    parser.add_argument("--power", nargs="+", type=int, default=[1], metavar="N")
    parser.add_argument("--duration", type=float, default=60.0)
    args = parser.parse_args()

    gas_counts = args.gas
    power_counts = args.power
    if len(power_counts) == 1:
        power_counts = power_counts * len(gas_counts)

    try:
        asyncio.run(main(gas_counts, power_counts, args.duration))
    except KeyboardInterrupt:
        print("\n[종료]")
