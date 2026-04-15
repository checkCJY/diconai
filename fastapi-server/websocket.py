import asyncio
import random
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI()


def get_temp_sensor_data():
    is_danger = random.random() < 0.1  # 10% 확률로 위험 데이터 발생
    return {
        "device_id": "sensor-01",
        "timestamp": datetime.now().isoformat(),
        "co": random.randint(200, 300) if is_danger else random.randint(5, 20),
        "h2s": random.randint(15, 30) if is_danger else random.randint(0, 5),
        "o2": round(random.uniform(18.0, 19.0), 1)
        if is_danger
        else round(random.uniform(20.5, 21.0), 1),
        "level": "위험" if is_danger else "정상",
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
