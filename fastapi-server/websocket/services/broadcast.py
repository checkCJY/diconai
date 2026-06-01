# websocket/services/broadcast.py — WebSocket 브로드캐스트 페이로드 조립
#
# /ws/sensors/ 에서 settings.BROADCAST_INTERVAL_SEC 마다 브라우저로 전송하는
# 통합 페이로드를 조립한다. Redis(snap_store)에서 상태를 읽어 아래 데이터를
# 하나의 dict로 합친다.
# 이성현 수정 — websocket/state.py 메모리 참조 → Redis(snap_store) 이관
#   - 전력: build_equipment(power_state)로 16채널 설비 현황 + 총 전력(kW) + 증감률
#   - 가스: Redis snap:gas (가스 측정값 + 가스별 위험도)
#   - 알람: alarm_flush_loop이 단독 담당 — 주기 broadcast는 빈 alarms[]만 송신
# 이성현 수정 — worker_positions 제거: /ws/positions/ 전용 채널이 1초 주기로 처리.
#   broadcast(5초)에 포함 시 1초 업데이트 위에 5초마다 덮어써 순간이동 발생.
import asyncio
from datetime import datetime, timezone

from core.config import settings
from power.services.power_service import build_equipment
from websocket.snap_store import (  # 이성현 수정 — Redis 읽기 함수로 교체
    load_gas_snapshot,
    load_power_snapshot,
)  # 여기까지 통으로 교체
# load_worker_positions 제거 — /ws/positions/ 전용 채널이 담당 (이성현 수정)

# 직전 총 전력값 — 증감률 계산용
_prev_total_kw: float | None = None

# 가스 페이로드 키 — stale 시 null 로 채워 프론트가 key 부재로 깨지지 않게 한다.
# gas/services/gas_service.py 의 gas_snapshot 빌더와 키 목록이 1:1 로 일치해야 하며,
# 필드 추가·제거 시 gas/constants.py 한 곳만 수정한다.
from gas.constants import GAS_FIELDS as _GAS_VALUE_KEYS  # noqa: E402

_GAS_RISK_KEYS = tuple(f"{g}_risk" for g in _GAS_VALUE_KEYS)
_GAS_NULL_PAYLOAD = {k: None for k in _GAS_VALUE_KEYS + _GAS_RISK_KEYS}


# 1. stale 판정
def is_stale(updated_at_iso: str | None, threshold_sec: float | None = None) -> bool:
    """ISO8601 문자열 기준으로 stale 여부를 반환한다.

    None이거나 settings.DATA_STALE_THRESHOLD_SEC 초과 시 True.
    threshold_sec를 명시하면 settings 값을 무시한다.
    """
    if updated_at_iso is None:
        return True
    threshold = (
        threshold_sec
        if threshold_sec is not None
        else settings.DATA_STALE_THRESHOLD_SEC
    )
    last_dt = datetime.fromisoformat(updated_at_iso).replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - last_dt).total_seconds()
    return age > threshold


# 2. AI 예측 필드
def build_ai_prediction_fields(equipment: list[dict]) -> dict:
    """AI 예측 영역. 실제 모델 연동 전까지 수치는 None 송신.

    프론트는 None 케이스를 "예측 준비 중" 또는 "-"로 표시한다.
    ai_power_equipment 라벨만 equipment 첫 채널 기준으로 채워 시각 일관성을
    유지하고, 데이터 미수신 시(equipment 빈 리스트)에는 None.
    전력 AI 예측 연동 시 세 수치 필드를 실제 예측값으로 교체한다.
    """
    return {
        "ai_power_equipment": equipment[0]["name"] if equipment else None,
        "ai_eta_min": None,
        "ai_max_load_kw": None,
        "ai_max_load_pct": None,
    }


# 이성현 추가 — broadcast에 필요한 상태를 Redis에서 일괄 읽는 async 함수
async def fetch_broadcast_state() -> dict:
    """broadcast 페이로드 조립에 필요한 상태를 Redis에서 한 번에 읽어 반환한다.

    asyncio.gather로 3종 병렬 조회 — 순차 조회 대비 RTT 1/3.
    반환값을 build_broadcast_payload(state)에 그대로 넘긴다.
    """
    # 이성현 수정 — worker_positions 제거, 가스/전력만 조회
    (gas_snapshot, gas_ts), power_state = await asyncio.gather(
        load_gas_snapshot(),
        load_power_snapshot(),
    )
    return {
        "gas_snapshot": gas_snapshot,
        "gas_ts": gas_ts,
        "power_state": power_state,
    }


# 3. Redis 상태 일괄 로드 + 통합 페이로드 조립
def build_broadcast_payload(state: dict, include_alarms: bool = True) -> dict:
    # 이성현 수정 — state를 인자로 받는 순수 함수로 변경 (Redis 직접 참조 제거)
    """/ws/sensors/ 틱마다 브라우저로 전송할 통합 페이로드를 반환한다.

    전력/가스 데이터가 stale이면 equipment를 빈 리스트로 처리하고
    *_loading 플래그를 True로 두어 브라우저가 로딩 스켈레톤을 유지하도록 한다.
    알람은 alarm_flush_loop이 Redis 큐에서 별도 즉시 전달 — 주기 broadcast는
    빈 alarms[]만 송신 (호환 모드 — 프론트가 alarms 키 존재를 가정).
    """
    global _prev_total_kw

    power_state = state["power_state"]
    gas_snapshot = state["gas_snapshot"]
    gas_ts = state["gas_ts"]

    power_stale = is_stale(power_state.get("updated_at"))
    gas_stale = is_stale(gas_ts)

    equipment, total_kw = ([], 0.0) if power_stale else build_equipment(power_state)

    if power_stale:
        total_power_kw = None
        power_change_pct = None
    else:
        total_power_kw = total_kw
        if _prev_total_kw is not None and _prev_total_kw > 0:
            power_change_pct = round(
                (total_power_kw - _prev_total_kw) / _prev_total_kw * 100, 1
            )
        else:
            power_change_pct = 0.0
        _prev_total_kw = total_power_kw

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_power_kw": total_power_kw,
        "power_change_pct": power_change_pct,
        "equipment": equipment,
        # power_loading = 전력 데이터 도착 여부(stale). 채널 ON/OFF 와는 별개.
        "power_loading": power_stale,
        "gas_loading": gas_stale,
        **build_ai_prediction_fields(equipment),
        # worker_positions 제거 — /ws/positions/ 전용 채널(1초 주기)이 담당 (이성현 수정)
        # 5초 broadcast에 포함 시 1초 업데이트 위에 덮어써 순간이동 발생했음
        "alarms": [],
        # gas_stale 이어도 가스 키는 항상 유지 (값만 None). 프론트가 키 부재로 깨지지 않도록.
        **(gas_snapshot if not gas_stale else _GAS_NULL_PAYLOAD),
    }
    return payload
