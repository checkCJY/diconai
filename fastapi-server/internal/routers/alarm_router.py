# internal/routers/alarm_router.py — Celery → FastAPI WebSocket 브리지
#
# Celery 태스크(DRF 컨텍스트)가 알람을 생성한 뒤 이 엔드포인트를 호출해
# FastAPI의 active_alarms 큐에 추가한다.
# 다음 WebSocket 브로드캐스트 틱(1초)에 브라우저로 전달된다.
#
# 보안: 127.0.0.1 (localhost)에서만 호출 가능.

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from websocket.state import active_alarms, worker_clients

router = APIRouter(prefix="/internal")


class AlarmPayload(BaseModel):
    model_config = {"extra": "allow"}  # 필드가 추가되어도 유연하게 수용

    alarm_type: str
    risk_level: str
    source_label: str
    summary: str
    is_new_event: bool
    event_id: int | None = None
    gas_type: str | None = None
    measured_value: float | None = None
    threshold_value: float | None = None
    worker_id: int | None = None  # 지오펜스 알람 시 타겟 작업자


@router.post("/alarms/push/")
async def push_alarm(request: Request, alarm: AlarmPayload):
    """Celery 태스크에서 WebSocket 브로드캐스트 큐에 알람을 추가한다.

    localhost 전용 — 외부 접근 시 403 반환.
    """
    client_host = request.client.host if request.client else ""
    if client_host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(status_code=403, detail="내부 전용 엔드포인트입니다.")

    payload = alarm.model_dump(exclude_none=True)
    active_alarms.append(payload)

    # 지오펜스 진입 알람은 해당 작업자에게도 개인 전송
    if alarm.alarm_type == "geofence_intrusion" and alarm.worker_id is not None:
        ws = worker_clients.get(alarm.worker_id)
        if ws:
            try:
                await ws.send_json({"type": "worker_alert", **payload})
            except Exception:
                worker_clients.pop(alarm.worker_id, None)

    return {"ok": True}
