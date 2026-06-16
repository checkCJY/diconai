# websocket/routers/ws_router.py — 브라우저/IoT WebSocket 엔드포인트
#
# 두 가지 WebSocket 연결을 처리한다.
#   WS /ws/sensors/  : 브라우저 연결. 단일 브로드캐스터(broadcast_loop)가 모든 클라이언트에
#                      동시 전송해 active_alarms 중복 소비를 방지한다.
#   WS /ws/position/ : IoT 위치 장비 연결. 위치 데이터를 수신해 DRF에 저장하고
#                      Redis worker 상태를 갱신한다.
import asyncio
import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.config import settings
from core.metrics import ALARM_STREAM_LAG, E2E_ALARM_LATENCY, WS_CONNECTIONS
from services.drf_client import post_to_drf
from websocket.auth import verify_jwt_from_ws_query
from websocket.services.alarm_queue import (
    _id_ms,
    read_alarms_blocking,
    stream_tail_id,
)
from websocket.services.broadcast import (
    build_broadcast_payload,
    fetch_broadcast_state,
)
from websocket.snap_store import store_worker_position
from websocket.state import (
    sensor_clients,
    worker_clients,
)

logger = logging.getLogger(__name__)

POSITION_PATH = "/api/positioning/receive/"

router = APIRouter(tags=["websocket"])


async def _send_to_all(payload: dict) -> None:
    """연결된 모든 클라이언트에 페이로드를 병렬 전송하고 끊긴 클라이언트를 정리한다."""
    async def _send(ws: WebSocket) -> WebSocket | None:
        try:
            await ws.send_json(payload)
            return None
        except Exception as exc:
            logger.warning(f"[ws/sensors] action=send_failed error={exc!r}")
            return ws

    results = await asyncio.gather(*[_send(ws) for ws in list(sensor_clients)])
    for ws in results:
        if ws is not None and ws in sensor_clients:
            sensor_clients.remove(ws)


async def alarm_flush_loop():
    """Redis 스트림(diconai:ws:alarms)을 XREAD로 소비해 브로드캐스트한다.

    LIST→Stream 전환 (fan-out 대비): BRPOP(경쟁 소비 — 한 알람을 한 replica만 pop)을
    replica별 독립 XREAD로 바꿔 모든 replica가 모든 알람을 받는다. 커서(last_id)는 이
    루프가 메모리로 보유하고, 부팅 직후 "$"(이후 신규만)에서 시작해 과거 알람 무한
    replay를 막는다. 페이로드 형식은 호환 모드 — `{"alarms": [payload], ...}` shape
    유지로 프론트 무수정.

    [M-1 보존] 클라이언트가 없으면 XREAD를 호출하지 않고 커서를 동결한 채 대기한다.
    스트림은 데이터가 지워지지 않으므로, 클라이언트 재접속 시 last_id 이후 누적분이
    다음 XREAD에서 배치로 한 번에 전달된다 (BRPOP 시절 "pop하면 영구 소실" 문제 해소).

    [배치 처리] XREAD는 커서 이후 쌓인 N건을 배치로 준다. 반환 payload 전부를 순회하며
    각각 broadcast하고, 커서는 배치 마지막 entry ID로 전진한다 (단건 가정 시 누락·순서
    꼬임 — 가장 버그 나기 쉬운 곳).

    [stream lag] iteration 말미에 스트림 말단 ID와 커서의 시간차를 메트릭으로 노출한다.
    평상시 ≈0, 이 replica가 소화 못 하면 증가 → 멀티레플리카 시 뒤처지는 replica 식별.
    """
    last_id = "$"  # 부팅 이후 신규 알람만 (과거 무한 replay 방지)
    while True:
        # [M-1] 클라이언트 없으면 읽지 않고 커서 동결 — 스트림에 알람 보존
        if not sensor_clients:
            await asyncio.sleep(1)
            continue
        new_last_id, payloads = await read_alarms_blocking(last_id, timeout=1)
        if payloads:
            # 배치 broadcast 전 state 1회 조회 (develop 시그니처). Redis 읽기 실패 시
            # 커서 미전진으로 continue → 다음 tick 재처리(알람 보존).
            try:
                state = await fetch_broadcast_state()
            except Exception:
                logger.warning("[alarm_flush_loop] Redis 읽기 실패 — tick 스킵")
                continue
            for payload in payloads:
                ingress_ts = payload.pop("ingress_ts", None)
                if ingress_ts is not None:
                    risk_level = payload.get("risk_level", "unknown")
                    E2E_ALARM_LATENCY.labels(risk_level=risk_level).observe(
                        time.time() - ingress_ts
                    )
                base = build_broadcast_payload(state, include_alarms=False)
                base["alarms"] = [payload]
                await _send_to_all(base)
        last_id = new_last_id  # 배치 마지막 ID로 커서 전진 (빈 결과면 그대로 유지)
        # stream lag — 말단과 커서의 시간차(초). last_id가 아직 "$"(미처리)거나
        # 스트림이 비었으면 0 (ms 파싱 불가).
        tail = await stream_tail_id()
        if tail is not None and last_id != "$":
            ALARM_STREAM_LAG.set((_id_ms(tail) - _id_ms(last_id)) / 1000)
        else:
            ALARM_STREAM_LAG.set(0)


async def broadcast_loop():
    """settings.BROADCAST_INTERVAL_SEC 마다 모든 클라이언트에 센서 통합 데이터를 송신."""
    while True:
        await asyncio.sleep(settings.BROADCAST_INTERVAL_SEC)
        if not sensor_clients:
            continue
        try:  # 이성현 수정 — Redis 읽기 실패 시 tick 스킵
            state = await fetch_broadcast_state()
        except Exception:
            logger.warning("[broadcast_loop] Redis 읽기 실패 — tick 스킵")
            continue
        await _send_to_all(build_broadcast_payload(state))


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
    WS_CONNECTIONS.labels("sensor").inc()
    logger.info(f"[ws/sensors] action=connect total={len(sensor_clients)}")
    try:
        state = await fetch_broadcast_state()  # 이성현 수정
        await websocket.send_json(build_broadcast_payload(state, include_alarms=False))
        await websocket.receive_text()  # 연결 유지 (disconnect까지 대기)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning(f"[ws/sensors] action=stream_error error={exc!r}")
    finally:
        if websocket in sensor_clients:
            sensor_clients.remove(websocket)
        WS_CONNECTIONS.labels("sensor").dec()
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
    WS_CONNECTIONS.labels("worker").inc()
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
        WS_CONNECTIONS.labels("worker").dec()
        logger.info(f"[ws/worker] action=disconnect user_id={user_id}")


@router.websocket("/ws/position/")
async def position_stream(websocket: WebSocket):
    """
    IoT 위치 장비용 수신 스트림.

    [Phase 5 미적용] IoT 장비 인증은 펌웨어 협업 별도 작업.
    분석 06 F2 / 07 G2 — 장비별 cert/secret 도입은 다음 sprint.
    현재는 무인증 유지 (`/ws/sensors/`, `/ws/worker/`와 달리 JWT 적용 안 됨).

    장비로부터 worker_id, facility_id, x, y 를 수신해 DRF에 저장하고
    Redis worker 상태를 갱신한다.
    갱신된 위치는 /ws/sensors/ 다음 틱에 브라우저로 전달된다.
    필수 필드가 누락된 경우 에러 응답을 반환하고 다음 수신을 계속 대기한다.
    """
    await websocket.accept()
    WS_CONNECTIONS.labels("position").inc()
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
            if result["status"] == "ok":  # 이성현 수정 — 메모리 → Redis 이관
                await store_worker_position(
                    worker_id,
                    {
                        "x": payload["x"],
                        "y": payload["y"],
                        "facility_id": payload["facility_id"],
                        "updated_at": payload["measured_at"],
                        "risk_level": "normal",
                        "zone_name": None,
                        "worker_name": None,
                        "movement_status": None,
                    },
                )
            await websocket.send_json(result)
    except WebSocketDisconnect:
        logger.info("[ws/position] action=disconnect")
    except Exception as exc:
        logger.exception(f"[ws/position] action=stream_error error={exc!r}")
        await websocket.close()
    finally:
        WS_CONNECTIONS.labels("position").dec()
