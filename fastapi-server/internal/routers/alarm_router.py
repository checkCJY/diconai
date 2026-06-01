# internal/routers/alarm_router.py — Celery → FastAPI WebSocket 브리지
#
# Celery 태스크(DRF 컨텍스트)가 알람을 생성한 뒤 이 엔드포인트를 호출해
# Redis 알람 스트림(`diconai:ws:alarms`)에 XADD한다 (Phase 1 C4 → Stream 전환).
# alarm_flush_loop이 XREAD로 즉시 소비해 브라우저로 전달.
#
# 보안: 127.0.0.1 (localhost)에서만 호출 가능 — 또는 INTERNAL_SERVICE_TOKEN 검증.

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.config import settings
from websocket.services.alarm_queue import push_alarm
from websocket.state import worker_clients

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])


class AnomalyMeta(BaseModel):
    """ANOMALY 알람 전용 ML 메타 — AlarmPayload.anomaly_meta 에 nested.

    [확장 정책]
    §3 multi-variate IF / CPD / spike detection 추가 시 본 모델에만 필드 추가
    (combined_risk/anomaly_score 외에 cpd_change_score, ar_residual 등). 외부
    AlarmPayload 는 그대로 유지 → 다른 alarm_type · 브라우저 처리 영향 0.
    """

    combined_risk: str  # normal | caution | predict_warn | danger
    anomaly_score: float  # IF decision_function 결과 (음수=이상)
    device_id: str | None = None  # PowerDevice 식별
    channel: int | None = None  # 1~16
    data_type: str | None = None  # watt | current | voltage


class AlarmPayload(BaseModel):
    # 미정의 필드는 통과시키지 않음 — DRF Celery 측이 명시 필드만 보내야 함.
    # T4 D3 — extra=ignore 유지 (시연 후 staged forbid 전환, plan §1 #5). 본 commit
    # 에서는 push_alarm_handler 가 unknown 키 WARN 로깅으로 silent drop 가시화.
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
    # 가스/전력 DANGER 대피 알림 수신 작업자 id 목록 — DRF가 소속 시설 기준으로
    # 계산해 전달. FastAPI는 이 목록의 worker_clients 에만 전송(전체 broadcast 아님).
    # 브라우저 broadcast 엔 불필요·민감하므로 스트림 push 전 pop 한다.
    target_worker_ids: list[int] = []
    # 서버(DRF Celery) 발신 시각 — 클라이언트가 우선 사용 (JS 03 R3).
    # 누락 시 클라이언트는 도착 시각(new Date())으로 fallback.
    created_at: str | None = None
    # AlarmRecord.get_short_message() 결과 — 패널·Toast 의 한 줄 표시용.
    # summary(긴 운영자 안내문) 와 구분되는 도메인 사실. DRF API 응답의 message
    # 필드와 동일 텍스트 (single source of truth). 누락 시 프론트는 summary fallback.
    message: str | None = None
    # ANOMALY 알람 전용 nested 메타 (다른 alarm_type 에선 None)
    anomaly_meta: AnomalyMeta | None = None
    # 2026-05-15 알람 재설계: Event 가 RESOLVED 로 전이된 시각.
    # 운영자가 update_status 를 RESOLVED 로 호출하면 drf 가 이 필드를 채워서 broadcast.
    # 클라는 이 필드가 박혀있으면 같은 event_id 로 떠있는 팝업을 close + "위험 해소" 토스트.
    # 일반 알람에선 None.
    event_resolved_at: str | None = None
    # T3 (2026-05-19) — 다중 관리자 환경 ack 시그널. 활성 Event 의 EventAck 한 사용자명 list.
    # 토스트·모달 본문에 "(N 확인 중)" 시그널 표시용 (dedup 과 분리 — 안전망 유지).
    # AlarmPayload.model_config="extra:ignore" 라 명시 정의 필수 (누락 시 silent drop).
    event_ack_users: list[str] = []
    # E2E latency 측정용 — IoT 수신 시각(Unix time). alarm_flush_loop에서 소비.
    ingress_ts: float | None = None
    # T4 D3 — 검출 주체 (ai / static_cover_* / static_no_ai_available / static_legacy).
    # decide_alarm 매트릭스 (D2) 결과 또는 DRF tasks.py fallback. 프론트가 시각 톤·
    # 배지 분기 (D4). None 허용 — 옛 발신자 호환.
    source: str | None = None
    # T4 D3 — source 별 운영자 친화 사유 문구 (ALARM_SOURCE_REASON lookup 결과).
    # 모달·토스트 보조 텍스트. ai / static_no_ai_available / static_legacy 는 None.
    reason: str | None = None


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
async def push_alarm_handler(request: Request, alarm: AlarmPayload):
    # T4 D3 — AlarmPayload.model_config=extra:ignore 라 미정의 필드는 silent drop.
    # T3 (event_ack_users 누락) 같은 사고 재발 방지를 위해 raw body 의 키를 모델
    # 정의 필드와 비교해 차이를 WARN. forbid 전환 (시연 후) 전 1단계 가시화.
    try:
        raw_body = await request.json()
        if isinstance(raw_body, dict):
            unknown = set(raw_body) - set(AlarmPayload.model_fields)
            if unknown:
                logger.warning(
                    "[alarm_router] unknown payload keys=%s alarm_type=%s "
                    "— silent drop (extra=ignore)",
                    sorted(unknown),
                    raw_body.get("alarm_type"),
                )
    except Exception:
        # raw body 파싱 실패는 본 흐름 비차단 — Pydantic 검증 단계에서 422 처리.
        pass

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
    # target_worker_ids 는 작업자 개인 분배 계산에만 쓰고 스트림(브라우저 broadcast)
    # 에는 싣지 않는다 — 대상 id 목록 노출·payload bloat 방지.
    payload.pop("target_worker_ids", None)

    # Phase 1 C4 → Stream — Redis Stream에 XADD. 장애 시 503으로 Celery retry 유도.
    try:
        await push_alarm(payload)
    except Exception as exc:
        logger.warning(f"[alarm_router] action=redis_push_failed error={exc!r}")
        raise HTTPException(status_code=503, detail="알람 큐 일시 장애. 재시도 필요.")

    # 지오펜스 진입 알람은 해당 작업자에게도 개인 전송
    if alarm.alarm_type == "geofence_intrusion" and alarm.worker_id is not None:
        ws = worker_clients.get(alarm.worker_id)
        if ws:
            try:
                await ws.send_json({"type": "worker_alert", **payload})
            except Exception:
                worker_clients.pop(alarm.worker_id, None)

    # 가스/전력 DANGER 는 소속 시설 작업자에게도 대피 알림 — DRF가 시설 기준으로
    # 계산한 target_worker_ids 중 접속 작업자에게만 전송(전체 broadcast 아님).
    # 동일 event_id 는 프론트(alarm-popup) dedup 이 관리자 대시보드 중복 표시 흡수.
    elif alarm.alarm_type in ("gas_threshold", "power_overload") and (
        alarm.risk_level == "danger"
    ):
        for worker_id in alarm.target_worker_ids:
            ws = worker_clients.get(worker_id)
            if ws:
                try:
                    await ws.send_json({"type": "worker_alert", **payload})
                except Exception:
                    worker_clients.pop(worker_id, None)

    return {"ok": True}
