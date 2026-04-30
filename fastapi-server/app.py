# app.py — FastAPI 통합 앱 진입점
#
# 도메인별 라우터(gas, power, positioning, websocket)를 한 곳에 등록한다.
# 실행: uvicorn app:app --reload --port 8001
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from gas.routers.gas_router import router as gas_router
from internal.routers.alarm_router import router as internal_alarm_router
from positioning.routers.position_router import router as positioning_router
from power.routers.power_router import router as power_router
from websocket.routers.ws_router import alarm_flush_loop, broadcast_loop, router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    task1 = asyncio.create_task(broadcast_loop())    # 30초 센서 데이터 브로드캐스트
    task2 = asyncio.create_task(alarm_flush_loop())  # 2초 새 이벤트 알람 플러시
    yield
    task1.cancel()
    task2.cancel()


app = FastAPI(title="DiconAI FastAPI Server", lifespan=lifespan)

app.include_router(gas_router)
app.include_router(power_router)
app.include_router(positioning_router)
app.include_router(ws_router)
app.include_router(internal_alarm_router)  # Celery → WS 브리지 (localhost 전용)


@app.get("/health/")
async def health_check():
    """서버 생존 확인용 엔드포인트."""
    return {"status": "ok"}
