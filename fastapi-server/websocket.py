import asyncio
import random
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

# 4/22 추가
from positioning.routers.position_router import router as positioning_router

app = FastAPI()
app.include_router(positioning_router)  # 4/22 추가

EQUIPMENT_LIST = [
    {"name": "압연기", "base_mwh": 15.2, "base_temp": 125},
    {"name": "송풍기", "base_mwh": 15.0, "base_temp": 125},
    {"name": "집진기", "base_mwh": 5.2, "base_temp": 125},
    {"name": "전자기 교반기", "base_mwh": 3.4, "base_temp": 125},
]


def get_power_level(mwh: float, name: str) -> str:
    if name in ("압연기", "송풍기") and mwh > 14:
        return "danger"
    if mwh > 4.5:
        return "caution"
    return "safe"


def get_temp_sensor_data():
    is_danger = random.random() < 0.1  # 10% 확률로 위험 데이터 발생

    # 전력 설비 더미 데이터
    equipment = []
    total_power = 0.0
    for eq in EQUIPMENT_LIST:
        fluctuation = round(random.uniform(-0.5, 0.5), 1)
        mwh = round(eq["base_mwh"] + fluctuation, 1)
        temp = eq["base_temp"] + random.randint(-3, 5)
        level = get_power_level(mwh, eq["name"])
        total_power += mwh
        equipment.append(
            {
                "name": eq["name"],
                "mwh": mwh,
                "temp": temp,
                "level": level,
            }
        )

    total_power_mw = round(1200 + random.uniform(-50, 100))
    power_change_pct = round((total_power_mw - 1076) / 1076 * 100, 1)

    # AI 예측: 가장 위험한 설비 기준
    danger_eq = next((e for e in equipment if e["level"] == "danger"), equipment[0])
    ai_eta_min = random.randint(15, 40)
    ai_max_load_kw = round(danger_eq["mwh"] * 1000 * random.uniform(1.05, 1.2))
    ai_max_load_pct = round(ai_max_load_kw / (danger_eq["mwh"] * 1000) * 100)

    return {
        "device_id": "sensor-01",
        "timestamp": datetime.now().isoformat(),
        "co": random.randint(200, 300) if is_danger else random.randint(5, 20),
        "h2s": random.randint(15, 30) if is_danger else random.randint(0, 5),
        "o2": round(random.uniform(18.0, 19.0), 1)
        if is_danger
        else round(random.uniform(20.5, 21.0), 1),
        "level": "위험" if is_danger else "정상",
        # 전력 시스템 데이터
        "total_power_mw": total_power_mw,
        "power_change_pct": power_change_pct,
        "equipment": equipment,
        # AI 예측 데이터
        "ai_power_equipment": danger_eq["name"],
        "ai_eta_min": ai_eta_min,
        "ai_max_load_kw": ai_max_load_kw,
        "ai_max_load_pct": ai_max_load_pct,
    }


@app.websocket("/ws/sensors/")
async def sensor_stream(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(get_temp_sensor_data())
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        print("Client disconnected")
