"""
websocket_CJY.py — 전력 데이터 실시간 통합 테스트 서버

websocket.py 베이스에 전력 데이터 수신·공유·브로드캐스트를 통합.

[추가된 패턴 — websocket.py의 position 패턴과 동일]
  더미 센더 → POST /api/power/* (Pydantic 검증)
                ├── power_latest 즉시 갱신  ← WebSocket이 여기서 읽음
                └── DRF 비동기 저장 (BackgroundTask, 응답 블로킹 없음)

  /ws/sensors/ 1초마다 → power_latest에서 equipment[] 조립 → 브라우저 송출

[테스트 실행]
    터미널 A:
        cd fastapi-server
        uvicorn websocket_CJY:app --reload --port 8002

    터미널 B (전력 더미):
        cd fastapi-server
        python -c "
        from power_system.power_dummy_sender import *
        import time
        while True:
            send_data('http://localhost:8002/api/power/onoff',   generate_power_onoff_data(),   'ONOFF')
            send_data('http://localhost:8002/api/power/current', generate_power_current_data(), 'CURRENT')
            send_data('http://localhost:8002/api/power/voltage', generate_power_voltage_data(), 'VOLTAGE')
            send_data('http://localhost:8002/api/power/watt',    generate_power_watt_data(),    'WATT')
            time.sleep(3)
        "

    터미널 C (DRF 서버):
        cd drf-server
        python manage.py runserver

    브라우저 콘솔 확인:
        const ws = new WebSocket('ws://localhost:8002/ws/sensors/');
        ws.onmessage = e => console.log(JSON.parse(e.data));
"""

import asyncio
import os
import random
from datetime import datetime, timezone

import httpx
from fastapi import BackgroundTasks, FastAPI, WebSocket, WebSocketDisconnect

from positioning.routers.position_router import router as positioning_router
from power_system.schemas import (
    PowerCurrentPayload,
    PowerOnOffPayload,
    PowerVoltagePayload,
    PowerWattPayload,
)

# ──────────────────────────────────────────────────────────────
# DRF 연동 설정
# ──────────────────────────────────────────────────────────────
DRF_BASE_URL = os.getenv("DRF_BASE_URL", "http://localhost:8000")
DRF_SERVICE_TOKEN = os.getenv("DRF_SERVICE_TOKEN", "")
DRF_POWER_EVENT_URL = f"{DRF_BASE_URL}/monitoring/api/power/event/"
DRF_POWER_DATA_URL = f"{DRF_BASE_URL}/monitoring/api/power/data/"
POSITION_ENDPOINT = f"{DRF_BASE_URL}/positioning/api/receive/"

app = FastAPI(title="전력 WebSocket 통합 테스트 서버 (CJY)")
app.include_router(positioning_router)

# ──────────────────────────────────────────────────────────────
# 공유 상태 1: 작업자 위치 (websocket.py 동일)
# ──────────────────────────────────────────────────────────────
worker_positions: dict[int, dict] = {}

# ──────────────────────────────────────────────────────────────
# 공유 상태 3: 이전 신호 총 전력 — 증감률 계산용
# None: 첫 신호 수신 전, 첫 신호에서는 0% 반환
# ──────────────────────────────────────────────────────────────
_prev_total_kw: float | None = None

# ──────────────────────────────────────────────────────────────
# 공유 상태 2: 전력 최신값
#   onoff   : {"1": bool, ..., "16": bool}
#   current : {1: float|None, ..., 16: float|None}  None = 통신 불능
#   voltage : {1: float|None, ..., 16: float|None}
#   watt    : {1: float|None, ..., 16: float|None}
# ──────────────────────────────────────────────────────────────
power_latest: dict = {
    "onoff": {},
    "current": {},
    "voltage": {},
    "watt": {},
    "updated_at": None,
}

# ──────────────────────────────────────────────────────────────
# 채널 → 설비명 매핑 (테스트용 하드코딩)
# 운영 시: device_id → DRF PowerDevice.channel_meta 조회로 교체
# ──────────────────────────────────────────────────────────────
CHANNEL_TO_DEVICE: dict[int, str] = {
    1: "압연기",
    2: "송풍기",
    3: "집진기",
    4: "전자기 교반기",
    5: "냉각펌프",
    6: "유압장치",
    7: "컨베이어",
    8: "분쇄기",
    9: "CH9",
    10: "CH10",
    11: "CH11",
    12: "CH12",
    13: "CH13",
    14: "CH14",
    15: "CH15",
    16: "CH16",
}


# ──────────────────────────────────────────────────────────────
# DRF 비동기 전송 헬퍼 (BackgroundTask에서 실행)
# ──────────────────────────────────────────────────────────────
def _auth_headers() -> dict:
    headers = {"Content-Type": "application/json"}
    if DRF_SERVICE_TOKEN:
        headers["Authorization"] = f"Bearer {DRF_SERVICE_TOKEN}"
    return headers


async def _post_to_drf(url: str, payload: dict) -> None:
    """DRF에 비동기 전송. 실패해도 WebSocket 흐름을 막지 않는다."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.post(url, json=payload, headers=_auth_headers())
            if res.status_code not in (200, 201):
                print(f"[DRF] 저장 실패 {res.status_code}: {res.text[:80]}")
    except httpx.TimeoutException:
        print("[DRF] 응답 타임아웃")
    except Exception as e:
        print(f"[DRF] 전송 오류: {e}")


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ──────────────────────────────────────────────────────────────
# 전력 HTTP 수신 엔드포인트
# 흐름: Pydantic 검증 → power_latest 즉시 갱신 → DRF 저장 (BackgroundTask)
# ──────────────────────────────────────────────────────────────
@app.post("/api/power/onoff", status_code=201)
async def recv_onoff(payload: PowerOnOffPayload, bg: BackgroundTasks):
    power_latest["onoff"] = payload.to_snapshot()
    power_latest["updated_at"] = _now_utc_iso()

    drf_payload = {
        "device_id": payload.device_id,
        "measured_at": power_latest["updated_at"],
        "snapshot": power_latest["onoff"],
    }
    bg.add_task(_post_to_drf, DRF_POWER_EVENT_URL, drf_payload)
    return {"status": "ok", "updated": "onoff"}


@app.post("/api/power/current", status_code=201)
async def recv_current(payload: PowerCurrentPayload, bg: BackgroundTasks):
    power_latest["current"] = payload.to_channel_values()
    power_latest["updated_at"] = _now_utc_iso()

    drf_payload = {
        "device_id": payload.device_id,
        "measured_at": power_latest["updated_at"],
        "data_type": "current",
        "channels": _to_channel_list(power_latest["current"]),
    }
    bg.add_task(_post_to_drf, DRF_POWER_DATA_URL, drf_payload)
    return {"status": "ok", "updated": "current"}


@app.post("/api/power/voltage", status_code=201)
async def recv_voltage(payload: PowerVoltagePayload, bg: BackgroundTasks):
    power_latest["voltage"] = payload.to_channel_values()
    power_latest["updated_at"] = _now_utc_iso()

    drf_payload = {
        "device_id": payload.device_id,
        "measured_at": power_latest["updated_at"],
        "data_type": "voltage",
        "channels": _to_channel_list(power_latest["voltage"]),
    }
    bg.add_task(_post_to_drf, DRF_POWER_DATA_URL, drf_payload)
    return {"status": "ok", "updated": "voltage"}


@app.post("/api/power/watt", status_code=201)
async def recv_watt(payload: PowerWattPayload, bg: BackgroundTasks):
    power_latest["watt"] = payload.to_channel_values()
    power_latest["updated_at"] = _now_utc_iso()

    drf_payload = {
        "device_id": payload.device_id,
        "measured_at": power_latest["updated_at"],
        "data_type": "watt",
        "channels": _to_channel_list(power_latest["watt"]),
    }
    bg.add_task(_post_to_drf, DRF_POWER_DATA_URL, drf_payload)
    return {"status": "ok", "updated": "watt"}


def _to_channel_list(channel_values: dict) -> list[dict]:
    """DRF channels 리스트 형식으로 변환. None = 통신 불능."""
    return [
        {
            "channel": ch,
            "value": val,
            "sensor_status": "comm_failure" if val is None else "active",
            "risk_level": "normal",
        }
        for ch, val in channel_values.items()
    ]


# ──────────────────────────────────────────────────────────────
# power_latest → equipment[] 조립
# websocket_CJY.js 수신 형식:
#   { name, watt, voltage, current, onoff, sensor_status, risk_level }
# ──────────────────────────────────────────────────────────────
def _build_equipment() -> tuple[list[dict], float]:
    """
    power_latest(채널 기반) → equipment[] + total_power_mw 반환.

    power_latest가 비어있으면 빈 리스트 반환 (로딩 중 상태 유지).
    """
    if not any(
        [power_latest["watt"], power_latest["current"], power_latest["voltage"]]
    ):
        return [], 0.0

    equipment = []
    total_w = 0.0

    for ch in range(1, 17):
        watt = power_latest["watt"].get(ch)
        voltage = power_latest["voltage"].get(ch)
        current = power_latest["current"].get(ch)
        onoff = power_latest["onoff"].get(str(ch))  # onoff 키는 문자열

        is_comm = watt is None and voltage is None and current is None
        sensor_status = "comm_failure" if is_comm else "active"

        if not is_comm and watt is not None:
            if watt > 4000:
                risk_level = "danger"
            elif watt > 2500:
                risk_level = "warning"
            else:
                risk_level = "normal"
            total_w += watt
        else:
            risk_level = "normal"

        equipment.append(
            {
                "name": CHANNEL_TO_DEVICE.get(ch, f"CH{ch}"),
                "watt": watt,
                "voltage": voltage,
                "current": current,
                "onoff": onoff,
                "sensor_status": sensor_status,
                "risk_level": risk_level,
            }
        )

    total_kw = round(total_w / 1000, 3)  # W → kW
    return equipment, total_kw


# ──────────────────────────────────────────────────────────────
# 브라우저 송출 페이로드 조립 (websocket.py get_temp_sensor_data 대응)
# 가스 더미 + 실제 전력 데이터 결합
# ──────────────────────────────────────────────────────────────
def _build_broadcast_payload() -> dict:
    global _prev_total_kw

    is_danger = random.random() < 0.1

    # 가스 더미 (websocket.py 동일)
    co = random.randint(200, 300) if is_danger else random.randint(5, 20)
    h2s = random.randint(15, 30) if is_danger else random.randint(0, 5)
    o2 = round(
        random.uniform(18.0, 19.0) if is_danger else random.uniform(20.5, 21.0), 1
    )

    # 마지막 실제 데이터 수신으로부터 경과 시간 (초)
    DATA_STALE_SEC = 8  # 더미 발신기 주기 3초 × 2.5 사이클
    updated_at = power_latest.get("updated_at")
    if updated_at is not None:
        last_dt = datetime.fromisoformat(updated_at).replace(tzinfo=timezone.utc)
        data_age_sec = (datetime.now(timezone.utc) - last_dt).total_seconds()
    else:
        data_age_sec = None

    data_stale = (data_age_sec is None) or (data_age_sec > DATA_STALE_SEC)

    # 전력 실제 데이터 (stale이면 빈 equipment 반환으로 처리)
    equipment, total_kw = _build_equipment() if not data_stale else ([], 0.0)

    # power_latest 미수신 또는 stale 시 더미 유지 (UI 로딩 스켈레톤)
    if not equipment:
        total_power_kw = round(1200 + random.uniform(-50, 100))
        power_change_pct = 0.0
    else:
        total_power_kw = total_kw
        # 이전 신호 대비 증감률 — 첫 신호는 0%, 이후 직전 값과 비교
        if _prev_total_kw is not None and _prev_total_kw > 0:
            power_change_pct = round(
                (total_power_kw - _prev_total_kw) / _prev_total_kw * 100, 1
            )
        else:
            power_change_pct = 0.0
        _prev_total_kw = total_power_kw

    # AI 예측 더미 (websocket.py 동일)
    ai_eta_min = random.randint(15, 40)
    ai_max_load_kw = round(total_power_kw * random.uniform(1.05, 1.2), 1)  # kW 그대로
    ai_max_load_pct = round(ai_max_load_kw / max(total_power_kw, 0.001) * 100)
    ai_power_equipment = equipment[0]["name"] if equipment else "압연기"

    return {
        "device_id": "sensor-01",
        "timestamp": datetime.now().isoformat(),
        "co": co,
        "h2s": h2s,
        "o2": o2,
        "level": "위험" if is_danger else "정상",
        "total_power_kw": total_power_kw,
        "power_change_pct": power_change_pct,
        "equipment": equipment,
        "power_loading": len(equipment) == 0,  # 더미 센더 미수신 → 스켈레톤 유지 신호
        "ai_power_equipment": ai_power_equipment,
        "ai_eta_min": ai_eta_min,
        "ai_max_load_kw": ai_max_load_kw,
        "ai_max_load_pct": ai_max_load_pct,
        "worker_positions": dict(worker_positions),
    }


# ──────────────────────────────────────────────────────────────
# 브라우저용 센서 스트림 (websocket.py 동일 경로)
# ──────────────────────────────────────────────────────────────
@app.websocket("/ws/sensors/")
async def sensor_stream(websocket: WebSocket):
    """브라우저 연결. 1초마다 가스+전력 통합 페이로드 송출."""
    await websocket.accept()
    print("[ws/sensors] 브라우저 연결됨")
    try:
        while True:
            await websocket.send_json(_build_broadcast_payload())
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        print("[ws/sensors] 브라우저 연결 종료")


# ──────────────────────────────────────────────────────────────
# IoT 위치 수신 스트림 (websocket.py 동일)
# ──────────────────────────────────────────────────────────────
async def _forward_position_to_drf(payload: dict) -> dict:
    try:
        headers = {"Content-Type": "application/json"}
        if DRF_SERVICE_TOKEN:
            headers["Authorization"] = f"Bearer {DRF_SERVICE_TOKEN}"
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.post(POSITION_ENDPOINT, json=payload, headers=headers)
            if res.status_code == 201:
                return {"status": "ok", **res.json()}
            return {"status": "error", "message": f"DRF {res.status_code}: {res.text}"}
    except httpx.TimeoutException:
        return {"status": "error", "message": "DRF 응답 타임아웃"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.websocket("/ws/position/")
async def position_stream(websocket: WebSocket):
    """IoT 디바이스 연결. 위치 수신 → DRF 저장 → worker_positions 갱신."""
    await websocket.accept()
    print("[ws/position] IoT 디바이스 연결됨")
    try:
        while True:
            data = await websocket.receive_json()
            required = ["worker_id", "facility_id", "x", "y"]
            missing = [f for f in required if f not in data]
            if missing:
                await websocket.send_json(
                    {"status": "error", "message": f"필수 필드 누락: {missing}"}
                )
                continue

            worker_id = int(data["worker_id"])
            payload = {
                "worker_id": worker_id,
                "facility_id": int(data["facility_id"]),
                "x": float(data["x"]),
                "y": float(data["y"]),
                "measured_at": datetime.now(timezone.utc).isoformat(),
            }
            result = await _forward_position_to_drf(payload)
            if result["status"] == "ok":
                worker_positions[worker_id] = {
                    "x": payload["x"],
                    "y": payload["y"],
                    "facility_id": payload["facility_id"],
                    "updated_at": payload["measured_at"],
                }
            await websocket.send_json(result)
    except WebSocketDisconnect:
        print("[ws/position] IoT 디바이스 연결 종료")
    except Exception as e:
        print(f"[ws/position] 예외: {e}")
        await websocket.close()
