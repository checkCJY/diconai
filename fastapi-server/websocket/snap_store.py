# websocket/snap_store.py — 계층 1 broadcast 상태 Redis I/O
# 이성현 추가 — 프로세스 메모리(state.py)에 있던 broadcast 스냅샷 4종을 Redis 키로 이관.
#
# 배경: fastapi replicas>1 시 각 pod가 독립 메모리를 들고 있어 broadcast 데이터가
# 분산됨. Redis를 단일 공유 저장소로 삼으면 모든 pod가 동일한 최신값을 읽을 수 있음.
# 현재는 replicas=1 유지 — 이관 자체가 아키텍처 정리 목적.
#
# 키 네임스페이스:
#   diconai:snap:gas              — 가스 9종 값 + 9종 위험도 (JSON blob)
#   diconai:snap:gas:ts           — 가스 마지막 수신 시각 (ISO 문자열, stale 판정용)
#   diconai:snap:power:{data_type} — 전력 data_type별 채널 dict (JSON blob)
#   diconai:snap:power:ts         — 전력 마지막 수신 시각
#   diconai:snap:worker_ids       — Redis Set, 수신된 worker_id 목록
#   diconai:snap:workers:{wid}    — 작업자 위치·위험도 (HSET)
#   diconai:snap:scenario         — 시연 시나리오 모드 문자열
#
# [주의] onoff 채널 키는 str ("1", "2", …), watt/current/voltage는 int (1, 2, …).
# Redis 왕복 후에도 동일 타입으로 복원한다 (_int_key / _str_key 분기).
import json
import logging

from core.redis_client import get_redis

logger = logging.getLogger(__name__)

# ── 키 상수 ────────────────────────────────────────────────────────────────────
_GAS_KEY = "diconai:snap:gas"
_GAS_TS_KEY = "diconai:snap:gas:ts"
_PWR_TS_KEY = "diconai:snap:power:ts"
_WORKER_IDS = "diconai:snap:worker_ids"
_SCENARIO_KEY = "diconai:snap:scenario"

# 작업자 위치 TTL — 더미 미가동 시 오래된 위치가 계속 화면에 남는 것을 방지.
# 더미 송출 주기(DUMMY_SEND_INTERVAL_SEC=1~3s)보다 충분히 길게 설정.
_WORKER_TTL_SEC = 60


# ── 가스 스냅샷 ────────────────────────────────────────────────────────────────
async def store_gas_snapshot(snapshot: dict, updated_at: str) -> None:
    """가스 9종 값 + 위험도를 Redis에 저장한다.

    snapshot은 gas_service.py의 gas_snapshot dict
    (co/h2s/co2/o2/no2/so2/o3/nh3/voc + 각 _risk 필드 포함).
    """
    r = get_redis()
    await r.set(_GAS_KEY, json.dumps(snapshot, ensure_ascii=False))
    await r.set(_GAS_TS_KEY, updated_at)


async def load_gas_snapshot() -> tuple[dict, str | None]:
    """(snapshot_dict, updated_at_iso) 반환. 데이터 없으면 ({}, None)."""
    r = get_redis()
    raw, ts = await r.mget(_GAS_KEY, _GAS_TS_KEY)
    return (json.loads(raw) if raw else {}, ts)


# ── 전력 스냅샷 ────────────────────────────────────────────────────────────────
async def store_power_snapshot(data_type: str, values: dict, updated_at: str) -> None:
    """전력 data_type 1종(watt/current/voltage/onoff)을 Redis에 저장한다.

    data_type별 독립 키를 사용해 동시 partial 갱신 race를 방지한다.
    (whole-blob SET은 두 pod가 동시에 쓸 때 한 쪽 data_type을 덮어씀)
    """
    r = get_redis()
    await r.set(
        f"diconai:snap:power:{data_type}",
        json.dumps(values, ensure_ascii=False),
    )
    await r.set(_PWR_TS_KEY, updated_at)


async def load_power_snapshot() -> dict:
    """power_latest와 동일한 구조의 dict를 반환한다.

    반환 형태:
        {
            "watt":     {int channel: float value, ...},   # int 키
            "current":  {int channel: float value, ...},
            "voltage":  {int channel: float value, ...},
            "onoff":    {str channel: bool value, ...},    # str 키 (원본 동일)
            "updated_at": str | None,
        }
    데이터 없는 data_type은 빈 dict.
    """
    r = get_redis()
    # mget 순서 = 언패킹 순서 — 변경 시 반드시 함께 수정
    raws = await r.mget(
        "diconai:snap:power:watt",
        "diconai:snap:power:current",
        "diconai:snap:power:voltage",
        "diconai:snap:power:onoff",
        _PWR_TS_KEY,
    )
    watt_r, curr_r, volt_r, onoff_r, ts = raws

    def _int_key(raw: str | None) -> dict:
        """JSON 역직렬화 후 키를 int로 변환 (watt/current/voltage용)."""
        if not raw:
            return {}
        return {int(k): v for k, v in json.loads(raw).items()}

    def _str_key(raw: str | None) -> dict:
        """JSON 역직렬화, 키를 str 그대로 유지 (onoff용)."""
        return json.loads(raw) if raw else {}

    return {
        "watt": _int_key(watt_r),
        "current": _int_key(curr_r),
        "voltage": _int_key(volt_r),
        "onoff": _str_key(onoff_r),
        "updated_at": ts,
    }


# ── 작업자 위치 ────────────────────────────────────────────────────────────────
async def store_worker_position(worker_id: int, position: dict) -> None:
    """작업자 위치 전체(좌표 + 상태)를 Redis HSET에 저장한다.

    position 예시:
        {"x": 3.0, "y": 5.0, "facility_id": 1, "worker_name": "홍길동",
         "movement_status": "moving", "updated_at": "...", "risk_level": "normal",
         "zone_name": None}

    None 값은 HSET이 저장 불가라 빈 문자열("")로 치환해 저장.
    load_worker_positions에서 "" → None으로 복원한다.
    """
    r = get_redis()
    await r.sadd(_WORKER_IDS, str(worker_id))
    mapping = {
        k: ("" if v is None else str(v) if not isinstance(v, str) else v)
        for k, v in position.items()
    }
    key = f"diconai:snap:workers:{worker_id}"
    await r.hset(key, mapping=mapping)
    await r.expire(key, _WORKER_TTL_SEC)


async def update_worker_risk(
    worker_id: int, risk_level: str, zone_name: str | None
) -> None:
    """DRF 응답 후 작업자의 risk_level·zone_name만 부분 갱신한다.

    position_router.py의 2단계 write 패턴 — 좌표 저장 후 DRF 응답 도착 시 호출.
    full read-modify-write 불필요 — risk_level 단독 writer이므로 HSET 부분 갱신 안전.
    """
    r = get_redis()
    key = f"diconai:snap:workers:{worker_id}"
    await r.hset(
        key,
        mapping={
            "risk_level": risk_level,
            "zone_name": zone_name or "",
        },
    )
    await r.expire(key, _WORKER_TTL_SEC)


async def load_worker_positions() -> dict[int, dict]:
    """전체 작업자 위치 dict를 반환한다.

    반환 형태: {worker_id (int): {x, y, facility_id, worker_name, ...}}
    빈 문자열("") 필드는 None으로 복원. x/y는 float, facility_id는 int.
    """
    r = get_redis()
    wids = await r.smembers(_WORKER_IDS)
    if not wids:
        return {}

    result: dict[int, dict] = {}
    for wid_str in wids:
        wid = int(wid_str)
        data = await r.hgetall(f"diconai:snap:workers:{wid}")
        if not data:
            # TTL 만료로 키가 없어진 경우 — Set에서 제거
            await r.srem(_WORKER_IDS, wid_str)
            continue
        # "" → None 복원
        parsed: dict = {k: (None if v == "" else v) for k, v in data.items()}
        # 숫자 타입 복원 (Redis는 모든 값을 str로 저장)
        for field in ("x", "y"):
            if parsed.get(field) is not None:
                parsed[field] = float(parsed[field])
        if parsed.get("facility_id") is not None:
            parsed["facility_id"] = int(parsed["facility_id"])
        result[wid] = parsed
    return result


# ── 시나리오 모드 ──────────────────────────────────────────────────────────────
async def store_scenario_mode(mode: str) -> None:
    """시연 시나리오 모드를 Redis에 저장한다."""
    r = get_redis()
    await r.set(_SCENARIO_KEY, mode)


async def load_scenario_mode(default: str = "mixed") -> str:
    """현재 시나리오 모드를 반환한다. Redis에 값이 없으면 default 반환."""
    r = get_redis()
    value = await r.get(_SCENARIO_KEY)
    return value if value else default
