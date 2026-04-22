from fastapi import FastAPI

from power_system.router_cjy import router as power_router
from routers import sensors

app = FastAPI()
app.include_router(power_router)


@app.get("/health/")
async def health_check():
    return {"status": "ok"}


app.include_router(sensors.router)
