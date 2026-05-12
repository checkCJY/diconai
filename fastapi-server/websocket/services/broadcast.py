# websocket/services/broadcast.py — WebSocket 브로드캐스트 페이로드 조립
#
# /ws/sensors/ 에서 settings.BROADCAST_INTERVAL_SEC 마다 브라우저로 전송하는
# 통합 페이로드를 조립한다. websocket/state.py의 공유 상태를 읽어 아래 데이터를
# 하나의 dict로 합친다.
#   - 전력: build_equipment()로 16채널 설비 현황 + 총 전력(kW) + 증감률
#   - 가스: latest_gas_snapshot (가스 측정값 + 가스별 위험도)
#   - 알람: alarm_flush_loop이 단독 담당 — 주기 broadcast는 빈 alarms[]만 송신
#   - 위치: worker_positions (IoT 장비로부터 갱신된 작업자 좌표)
#
# 파트별 함수로 분리되어 있으므로 단위 테스트 시 개별 호출 가능.
import random
from datetime import datetime, timezone

from core.config import settings
from power.services.power_service import build_equipment
from websocket.state import (
    gas_latest,
    latest_gas_snapshot,
    power_latest,
    worker_positions,
)

# 직전 총 전력값 — 증감률 계산용
_prev_total_kw: float | None = None


# ── 1. stale 판정 ───────────────────────────────────────────
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


# ── 2. AI 예측 더미 필드 ────────────────────────────────────
def build_ai_dummy_fields(total_power_kw: float, equipment: list[dict]) -> dict:
    """AI 예측 영역의 더미 값. 실제 모델 연동 시 교체 예정."""
    ai_eta_min = random.randint(15, 40)
    ai_max_load_kw = round(total_power_kw * random.uniform(1.05, 1.2), 1)
    ai_max_load_pct = round(ai_max_load_kw / max(total_power_kw, 0.001) * 100)
    ai_power_equipment = equipment[0]["name"] if equipment else "압연기"
    return {
        "ai_power_equipment": ai_power_equipment,
        "ai_eta_min": ai_eta_min,
        "ai_max_load_kw": ai_max_load_kw,
        "ai_max_load_pct": ai_max_load_pct,
    }


# ── 3. 통합 페이로드 조립 ─────────────────────────────────────
def build_broadcast_payload(include_alarms: bool = True) -> dict:
    """/ws/sensors/ 틱마다 브라우저로 전송할 통합 페이로드를 반환한다.

    전력/가스 데이터가 stale이면 equipment를 빈 리스트로 처리하고
    *_loading 플래그를 True로 두어 브라우저가 로딩 스켈레톤을 유지하도록 한다.
    알람은 alarm_flush_loop이 Redis 큐에서 별도 즉시 전달 — 주기 broadcast는
    빈 alarms[]만 송신 (호환 모드 — 프론트가 alarms 키 존재를 가정).
    """
    global _prev_total_kw

    is_danger = random.random() < settings.DUMMY_RISK_PROBABILITY

    power_stale = is_stale(power_latest.get("updated_at"))
    gas_stale = is_stale(gas_latest.get("updated_at"))

    equipment, total_kw = ([], 0.0) if power_stale else build_equipment()

    # power_stale(=실데이터 미수신)일 땐 None을 송신해 프론트가 로딩/공백 상태를 유지하도록 한다.
    # 하드코드 더미값(예: 1260kW)을 송신하면 더미 미가동 시에도 KPI에 가짜 숫자가 표시된다.
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

    # AI 더미 필드는 total_power_kw가 있을 때만 생성 (None이면 산술 연산 불가).
    ai_fields = (
        build_ai_dummy_fields(total_power_kw, equipment)
        if total_power_kw is not None
        else {}
    )

    payload = {
        "device_id": "sensor-01",
        "timestamp": datetime.now().isoformat(),
        "level": "위험" if is_danger else "정상",
        "total_power_kw": total_power_kw,
        "power_change_pct": power_change_pct,
        "equipment": equipment,
        "power_loading": len(equipment) == 0,
        "gas_loading": gas_stale,
        **ai_fields,
        "worker_positions": dict(worker_positions),
        "alarms": [],
        **(latest_gas_snapshot if not gas_stale else {}),
    }
    return payload
