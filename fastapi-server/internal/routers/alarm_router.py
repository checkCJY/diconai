# internal/routers/alarm_router.py — Celery → FastAPI WebSocket 브리지
#
# Celery 태스크(DRF 컨텍스트)가 알람을 생성한 뒤 이 엔드포인트를 호출해
# FastAPI의 active_alarms 큐에 추가한다.
# 다음 WebSocket 브로드캐스트 틱(1초)에 브라우저로 전달된다.
#
# 보안: 127.0.0.1 (localhost)에서만 호출 가능.

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.config import settings
from websocket.state import active_alarms, alarm_signal, worker_clients

router = APIRouter(prefix="/internal", tags=["internal"])


class AlarmPayload(BaseModel):
    # 미정의 필드는 통과시키지 않음 — DRF Celery 측이 명시 필드만 보내야 함
    model_config = {"extra": "ignore"}

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
    # 서버(DRF Celery) 발신 시각 — 클라이언트가 우선 사용 (JS 03 R3).
    # 누락 시 클라이언트는 도착 시각(new Date())으로 fallback.
    created_at: str | None = None


@router.post(
    "/alarms/push/",
    summary="Celery → WebSocket 알람 브리지 (localhost 전용)",
    description=(
        "DRF Celery 태스크가 알람을 생성한 뒤 이 엔드포인트를 호출하면 "
        "FastAPI의 `active_alarms` 큐에 추가되어 다음 broadcast tick(1초)에 브라우저로 전달된다.\n\n"
        "**보안**: 127.0.0.1/::1/localhost에서만 호출 가능. 외부 호출은 403.\n\n"
        "**개인 알림**: `alarm_type=geofence_intrusion` + `worker_id` 지정 시 해당 작업자의 "
        "`/ws/worker/{user_id}/` 채널로도 즉시 push."
    ),
    responses={
        403: {"description": "localhost 외부에서 호출"},
        422: {"description": "AlarmPayload 검증 실패"},
    },
)
async def push_alarm(request: Request, alarm: AlarmPayload):
    # 인증 정책:
    #   - INTERNAL_SERVICE_TOKEN 설정 시 → Bearer 토큰으로만 검증 (IP 체크 생략).
    #     도커 네트워크에선 celery-worker가 컨테이너 IP(예: 172.x.x.x)로 접속하므로
    #     localhost-only 화이트리스트와 호환되지 않는다.
    #   - 미설정(레거시) 시 → localhost-only로 폴백.
    expected_token = settings.INTERNAL_SERVICE_TOKEN
    if expected_token:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="서비스 토큰이 필요합니다.")
        if auth_header[7:].strip() != expected_token:
            raise HTTPException(
                status_code=403, detail="유효하지 않은 서비스 토큰입니다."
            )
    else:
        client_host = request.client.host if request.client else ""
        if client_host not in ("127.0.0.1", "::1", "localhost"):
            raise HTTPException(status_code=403, detail="내부 전용 엔드포인트입니다.")

    payload = alarm.model_dump(exclude_none=True)
    active_alarms.append(payload)
    alarm_signal.set()

    # 지오펜스 진입 알람은 해당 작업자에게도 개인 전송
    if alarm.alarm_type == "geofence_intrusion" and alarm.worker_id is not None:
        ws = worker_clients.get(alarm.worker_id)
        if ws:
            try:
                await ws.send_json({"type": "worker_alert", **payload})
            except Exception:
                worker_clients.pop(alarm.worker_id, None)

    return {"ok": True}
