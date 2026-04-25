# app.py — FastAPI 통합 앱 진입점
# 실행: uvicorn app:app --reload --port 8001
from fastapi import FastAPI

from gas.routers.gas_router import router as gas_router
from positioning.routers.position_router import router as positioning_router
from power.routers.power_router import router as power_router
from websocket.routers.ws_router import router as ws_router

app = FastAPI(title="DiconAI FastAPI Server")

app.include_router(gas_router)
app.include_router(power_router)
app.include_router(positioning_router)
app.include_router(ws_router)


@app.get("/health/")
async def health_check():
    return {"status": "ok"}
