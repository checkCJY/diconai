from fastapi import FastAPI

from routers import sensors

app = FastAPI()


@app.get("/health/")
async def health_check():
    return {"status": "ok"}


app.include_router(sensors.router)
