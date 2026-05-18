# websocket/routers/ws_router.py — 브라우저/IoT WebSocket 엔드포인트
#
# 두 가지 WebSocket 연결을 처리한다.
#   WS /ws/sensors/  : 브라우저 연결. 단일 브로드캐스터(broadcast_loop)가 모든 클라이언트에
#                      동시 전송해 active_alarms 중복 소비를 방지한다.
#   WS /ws/position/ : IoT 위치 장비 연결. 위치 데이터를 수신해 DRF에 저장하고
#                      worker_positions 공유 상태를 갱신한다.
import asyncio
import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.config import settings
from core.metrics import E2E_ALARM_LATENCY
from services.drf_client import post_to_drf
from websocket.auth import verify_jwt_from_ws_query
from websocket.services.alarm_queue import pop_alarm_blocking
from websocket.services.broadcast import build_broadcast_payload
from websocket.state import (
    sensor_clients,
    worker_clients,
    worker_positions,
)

logger = logging.getLogger(__name__)

POSITION_PATH = "/api/positioning/receive/"

router = APIRouter(tags=["websocket"])


async def _send_to_all(payload: dict) -> None:
    """연결된 모든 클라이언트에 페이로드를 전송하고 끊긴 클라이언트를 정리한다."""
    dead: list[WebSocket] = []
    for ws in list(sensor_clients):
        try:
            await ws.send_json(payload)
        except Exception as exc:
            logger.warning(f"[ws/sensors] action=send_failed error={exc!r}")
            dead.append(ws)
    for ws in dead:
        if ws in sensor_clients:
            sensor_clients.remove(ws)


async def alarm_flush_loop():
    """Redis 큐(diconai:ws:alarms)에서 알람을 즉시 소비해 브로드캐스트한다.

    Phase 1 C4 — 기존 asyncio.Event 신호는 set/clear race로 알람 손실 가능했고,
    is_new_event 필터로 정상화 알림이 silent drop되었다. BRPOP은 큐에 원소가
    들어오는 순간 깨어나며 pop과 소비가 한 연산이라 race가 구조적으로 제거된다.
    페이로드 형식은 호환 모드 — `{"alarms": [payload], ...}` shape 유지로 프론트 무수정.
    """
    while True:
        payload = await pop_alarm_blocking(timeout=0)
        if payload is None:
            # Redis 일시 장애 — 짧게 대기 후 재시도 (busy-loop 방지)
            await asyncio.sleep(1)
            continue
        ingress_ts = payload.pop("ingress_ts", None)
        if ingress_ts is not None:
            E2E_ALARM_LATENCY.observe(time.time() - ingress_ts)
        if not sensor_clients:
            # 큐에서 pop했으나 연결된 클라 없음 → drop (의도, 큐에 다시 넣지 않음)
            continue
        base = build_broadcast_payload(include_alarms=False)
        base["alarms"] = [payload]
        await _send_to_all(base)


async def broadcast_loop():
    """settings.BROADCAST_INTERVAL_SEC 마다 모든 클라이언트에 센서 통합 데이터를 송신."""
    while True:
        await asyncio.sleep(settings.BROADCAST_INTERVAL_SEC)
        if not sensor_clients:
            continue
        await _send_to_all(build_broadcast_payload())


async def _save_iot_position(payload: dict) -> dict:
    """IoT 장비로부터 수신한 위치 데이터를 DRF에 저장.

    성공: {"status": "ok", ...DRF 응답}
    실패: {"status": "error", "message": ...}
    """
    res = await post_to_drf(
        POSITION_PATH, [payload], raise_on_error=False, log_category="ws_position"
    )
    if res is None:
        return {"status": "error", "message": "DRF 통신 실패"}
    if res.status_code == 201:
        return {"status": "ok", **res.json()}
    return {"status": "error", "message": f"DRF {res.status_code}"}


@router.websocket("/ws/sensors/")
async def sensor_stream(websocket: WebSocket):
    """
    브라우저용 실시간 통합 데이터 스트림.

    연결 즉시 첫 페이로드를 전송하고, 이후 broadcast_loop 가 주기적으로 전송한다.
    클라이언트별 루프를 두지 않아 active_alarms 중복 소비를 방지한다.

    [Phase 5] settings.JWT_SIGNING_KEY 설정 시 query string의 ?token=<access>로 JWT 검증.
    빈 값(미설정)이면 인증 비활성 (옵트인 — 기존 동작 유지).
    """
    await websocket.accept()
    payload = verify_jwt_from_ws_query(websocket)
    if payload is None:
        await websocket.close(code=1008, reason="unauthenticated")
        return
    sensor_clients.append(websocket)
    logger.info(f"[ws/sensors] action=connect total={len(sensor_clients)}")
    try:
        await websocket.send_json(build_broadcast_payload(include_alarms=False))
        await websocket.receive_text()  # 연결 유지 (disconnect까지 대기)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning(f"[ws/sensors] action=stream_error error={exc!r}")
    finally:
        if websocket in sensor_clients:
            sensor_clients.remove(websocket)
        logger.info(f"[ws/sensors] action=disconnect total={len(sensor_clients)}")


@router.websocket("/ws/worker/{user_id}/")
async def worker_stream(websocket: WebSocket, user_id: int):
    """
    작업자 개인 알림 전용 WebSocket.

    작업자가 로그인 후 본인 user_id로 연결한다.
    지오펜스 진입 알람 발생 시 해당 작업자에게만 전송된다.

    [Phase 5] settings.JWT_SIGNING_KEY 설정 시:
      1) query string의 token으로 JWT 검증
      2) 토큰 payload의 user_id가 path의 user_id와 일치하는지 검증
         (다른 사용자의 알람 가로채기 차단 — 분석 04 D2 / 07 G1)
    빈 값(미설정)이면 인증 비활성 (옵트인 — 기존 동작 유지).
    """
    await websocket.accept()
    payload = verify_jwt_from_ws_query(websocket)
    if payload is None:
        await websocket.close(code=1008, reason="unauthenticated")
        return

    # 옵트인 활성 시 (payload truthy) path user_id 일치 확인.
    # 비활성 시 payload는 빈 dict라 user_id 검증 skip (기존 동작).
    # JWT payload 의 user_id 는 string ("13"), path user_id 는 FastAPI 가 int 변환 (13).
    # type mismatch 로 항상 forbidden 되던 사전 버그 fix (2026-05-15) — str 양쪽 비교.
    if payload and str(payload.get("user_id")) != str(user_id):
        logger.warning(
            f"[ws/worker] action=forbidden token_user={payload.get('user_id')} "
            f"path_user={user_id}"
        )
        await websocket.close(code=1008, reason="forbidden")
        return

    worker_clients[user_id] = websocket
    logger.info(f"[ws/worker] action=connect user_id={user_id}")
    try:
        await websocket.receive_text()  # 연결 유지
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning(
            f"[ws/worker] action=stream_error user_id={user_id} error={exc!r}"
        )
    finally:
        worker_clients.pop(user_id, None)
        logger.info(f"[ws/worker] action=disconnect user_id={user_id}")


@router.websocket("/ws/position/")
async def position_stream(websocket: WebSocket):
    """
    IoT 위치 장비용 수신 스트림.

    [Phase 5 미적용] IoT 장비 인증은 펌웨어 협업 별도 작업.
    분석 06 F2 / 07 G2 — 장비별 cert/secret 도입은 다음 sprint.
    현재는 무인증 유지 (`/ws/sensors/`, `/ws/worker/`와 달리 JWT 적용 안 됨).

    장비로부터 worker_id, facility_id, x, y 를 수신해 DRF에 저장하고
    worker_positions 공유 상태를 갱신한다.
    갱신된 위치는 /ws/sensors/ 다음 틱에 브라우저로 전달된다.
    필수 필드가 누락된 경우 에러 응답을 반환하고 다음 수신을 계속 대기한다.
    """
    await websocket.accept()
    logger.info("[ws/position] action=connect")
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
            result = await _save_iot_position(payload)
            if result["status"] == "ok":
                worker_positions[worker_id] = {
                    "x": payload["x"],
                    "y": payload["y"],
                    "facility_id": payload["facility_id"],
                    "updated_at": payload["measured_at"],
                }
            await websocket.send_json(result)
    except WebSocketDisconnect:
        logger.info("[ws/position] action=disconnect")
    except Exception as exc:
        logger.exception(f"[ws/position] action=stream_error error={exc!r}")
        await websocket.close()
