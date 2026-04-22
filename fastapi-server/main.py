from fastapi import FastAPI

from power_system.router_cjy import router as power_router

app = FastAPI()
app.include_router(power_router)


@app.get("/health/")
async def health_check():
    return {"status": "ok"}
