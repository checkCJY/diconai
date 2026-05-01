# websocket/routers/ws_router.py — 브라우저/IoT WebSocket 엔드포인트
#
# 두 가지 WebSocket 연결을 처리한다.
#   WS /ws/sensors/  : 브라우저 연결. 단일 브로드캐스터(broadcast_loop)가 모든 클라이언트에
#                      동시 전송해 active_alarms 중복 소비를 방지한다.
#   WS /ws/position/ : IoT 위치 장비 연결. 위치 데이터를 수신해 DRF에 저장하고
#                      worker_positions 공유 상태를 갱신한다.
import asyncio
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.config import settings
from websocket.services.broadcast import build_broadcast_payload
from websocket.state import (
    active_alarms,
    alarm_signal,
    sensor_clients,
    worker_clients,
    worker_positions,
)

POSITION_ENDPOINT = f"{settings.DRF_BASE_URL}/api/positioning/receive/"
BROADCAST_INTERVAL = 5  # 센서 데이터 브로드캐스트 주기(초)

router = APIRouter()


async def _send_to_all(payload: dict) -> None:
    """연결된 모든 클라이언트에 페이로드를 전송하고 끊긴 클라이언트를 정리한다."""
    dead: list[WebSocket] = []
    for ws in list(sensor_clients):
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in sensor_clients:
            sensor_clients.remove(ws)


async def alarm_flush_loop():
    """새 알람이 active_alarms에 추가되는 즉시 브로드캐스트한다.

    폴링 대신 asyncio.Event로 신호를 받아 대기 없이 즉각 전달한다.
    alarm_router의 push_alarm이 alarm_signal.set()을 호출하면 이 루프가 깨어난다.
    """
    while True:
        await alarm_signal.wait()
        alarm_signal.clear()
        if not sensor_clients:
            continue
        if not any(a.get("is_new_event") for a in active_alarms):
            continue
        await _send_to_all(build_broadcast_payload())


async def broadcast_loop():
    """30초마다 모든 클라이언트에 센서 통합 데이터를 브로드캐스트한다."""
    while True:
        await asyncio.sleep(BROADCAST_INTERVAL)
        if not sensor_clients:
            continue
        await _send_to_all(build_broadcast_payload())


async def _forward_to_drf(payload: dict) -> dict:
    """
    IoT 장비로부터 수신한 위치 데이터를 DRF에 저장한다.

    성공 시 {"status": "ok", ...DRF 응답} 을 반환하고,
    타임아웃·예외 발생 시 {"status": "error", "message": ...} 를 반환한다.
    """
    headers = {"Content-Type": "application/json"}
    if settings.DRF_SERVICE_TOKEN:
        headers["Authorization"] = f"Bearer {settings.DRF_SERVICE_TOKEN}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.post(POSITION_ENDPOINT, json=[payload], headers=headers)
            print(
                f"[position] DRF {res.status_code}: worker={payload['worker_id']} ({payload['x']}, {payload['y']})"
            )
            if res.status_code == 201:
                return {"status": "ok", **res.json()}
            return {"status": "error", "message": f"DRF {res.status_code}: {res.text}"}
    except httpx.TimeoutException:
        return {"status": "error", "message": "DRF 응답 타임아웃"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.websocket("/ws/sensors/")
async def sensor_stream(websocket: WebSocket):
    """
    브라우저용 실시간 통합 데이터 스트림.

    연결 즉시 첫 페이로드를 전송하고, 이후 broadcast_loop 가 주기적으로 전송한다.
    클라이언트별 루프를 두지 않아 active_alarms 중복 소비를 방지한다.
    """
    await websocket.accept()
    sensor_clients.append(websocket)
    print(f"[ws/sensors] 브라우저 연결됨 (총 {len(sensor_clients)}개)")
    try:
        await websocket.send_json(build_broadcast_payload(include_alarms=False))
        await websocket.receive_text()  # 연결 유지 (disconnect까지 대기)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if websocket in sensor_clients:
            sensor_clients.remove(websocket)
        print(f"[ws/sensors] 브라우저 연결 종료 (총 {len(sensor_clients)}개)")


@router.websocket("/ws/worker/{user_id}/")
async def worker_stream(websocket: WebSocket, user_id: int):
    """
    작업자 개인 알림 전용 WebSocket.

    작업자가 로그인 후 본인 user_id로 연결한다.
    지오펜스 진입 알람 발생 시 해당 작업자에게만 전송된다.
    """
    await websocket.accept()
    worker_clients[user_id] = websocket
    print(f"[ws/worker] 작업자 연결됨 user_id={user_id}")
    try:
        await websocket.receive_text()  # 연결 유지
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        worker_clients.pop(user_id, None)
        print(f"[ws/worker] 작업자 연결 종료 user_id={user_id}")


@router.websocket("/ws/position/")
async def position_stream(websocket: WebSocket):
    """
    IoT 위치 장비용 수신 스트림.

    장비로부터 worker_id, facility_id, x, y 를 수신해 DRF에 저장하고
    worker_positions 공유 상태를 갱신한다.
    갱신된 위치는 /ws/sensors/ 다음 틱에 브라우저로 전달된다.
    필수 필드가 누락된 경우 에러 응답을 반환하고 다음 수신을 계속 대기한다.
    """
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
            result = await _forward_to_drf(payload)
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
