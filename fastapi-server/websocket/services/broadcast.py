# websocket/services/broadcast.py — WebSocket 브로드캐스트 페이로드 조립
#
# /ws/sensors/ 에서 1초마다 브라우저로 전송하는 통합 페이로드를 조립한다.
# websocket/state.py의 공유 상태를 읽어 아래 데이터를 하나의 dict로 합친다.
#   - 전력: build_equipment()로 16채널 설비 현황 + 총 전력(kW) + 증감률
#   - 가스: latest_gas_snapshot (가스 측정값 + 가스별 위험도)
#   - 알람: active_alarms (송출 후 즉시 비워 중복 전달 방지)
#   - 위치: worker_positions (IoT 장비로부터 갱신된 작업자 좌표)
#
# 전력 데이터가 8초 이상 수신되지 않으면 stale로 판단해 더미 전력값을 사용한다.
import random
from datetime import datetime, timezone

from power.services.power_service import build_equipment
from websocket.state import (
    active_alarms,
    latest_gas_snapshot,
    power_latest,
    worker_positions,
)

_prev_total_kw: float | None = None  # 직전 총 전력값 — 증감률 계산용
DATA_STALE_SEC = 8  # 전력 데이터 갱신 없이 이 시간이 지나면 더미값으로 대체


def build_broadcast_payload() -> dict:
    """
    /ws/sensors/ 틱마다 브라우저로 전송할 통합 페이로드를 조립해 반환한다.

    전력 데이터가 stale(8초 초과)이면 equipment를 빈 리스트로 처리하고
    power_loading: True 플래그를 포함해 브라우저가 로딩 스켈레톤을 유지하도록 한다.
    active_alarms는 송출 직후 clear해 다음 틱에 중복 전달되지 않도록 한다.
    ai_* 필드는 현재 더미값으로, 실제 AI 모델 연동 시 교체 예정이다.
    """
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
