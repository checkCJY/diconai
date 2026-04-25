# websocket/services/broadcast.py — 브로드캐스트 페이로드 조립
import random
from datetime import datetime, timezone

from power.services.power_service import build_equipment
from websocket.state import (
    active_alarms,
    latest_gas_snapshot,
    power_latest,
    worker_positions,
)

_prev_total_kw: float | None = None

DATA_STALE_SEC = 8


def build_broadcast_payload() -> dict:
    global _prev_total_kw

    is_danger = random.random() < 0.1

    updated_at = power_latest.get("updated_at")
    if updated_at is not None:
        last_dt = datetime.fromisoformat(updated_at).replace(tzinfo=timezone.utc)
        data_age_sec = (datetime.now(timezone.utc) - last_dt).total_seconds()
    else:
        data_age_sec = None

    data_stale = (data_age_sec is None) or (data_age_sec > DATA_STALE_SEC)
    equipment, total_kw = build_equipment() if not data_stale else ([], 0.0)

    if not equipment:
        total_power_kw = round(1200 + random.uniform(-50, 100))
        power_change_pct = 0.0
    else:
        total_power_kw = total_kw
        if _prev_total_kw is not None and _prev_total_kw > 0:
            power_change_pct = round(
                (total_power_kw - _prev_total_kw) / _prev_total_kw * 100, 1
            )
        else:
            power_change_pct = 0.0
        _prev_total_kw = total_power_kw

    ai_eta_min = random.randint(15, 40)
    ai_max_load_kw = round(total_power_kw * random.uniform(1.05, 1.2), 1)
    ai_max_load_pct = round(ai_max_load_kw / max(total_power_kw, 0.001) * 100)
    ai_power_equipment = equipment[0]["name"] if equipment else "압연기"

    payload = {
        "device_id": "sensor-01",
        "timestamp": datetime.now().isoformat(),
        "level": "위험" if is_danger else "정상",
        "total_power_kw": total_power_kw,
        "power_change_pct": power_change_pct,
        "equipment": equipment,
        "power_loading": len(equipment) == 0,
        "ai_power_equipment": ai_power_equipment,
        "ai_eta_min": ai_eta_min,
        "ai_max_load_kw": ai_max_load_kw,
        "ai_max_load_pct": ai_max_load_pct,
        "worker_positions": dict(worker_positions),
        "alarms": list(active_alarms),
        **latest_gas_snapshot,
    }
    active_alarms.clear()
    return payload
