# alerts/tasks.py — 가스 알람 Celery 태스크
#
# 3종 알람 태스크:
#   fire_danger_alarm_task  : DANGER 즉각 알람 (gas_alarm.py가 즉시 실행)
#   fire_warning_alarm_task : WARNING 30초 지속 후 알람 (countdown=30으로 지연 실행)
#   fire_clear_notification_task : 정상화 알림 (gas_alarm.py가 즉시 실행)
#
# 각 태스크는 AlarmRecord/Event를 DB에 기록한 뒤,
# FastAPI /internal/alarms/push/ 엔드포인트로 WebSocket 브로드캐스트 큐에 알람을 추가한다.
import logging

import httpx
from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

# Prometheus 메트릭 — 선언은 apps/core/metrics.py 에 중앙화. Celery worker
# 프로세스에서도 multiprocess 파일 기반으로 gunicorn과 공유된다.
from apps.core.metrics import ALARM_FIRED_TOTAL, ALARM_WS_PUSH_FAILED_TOTAL

logger = logging.getLogger(__name__)

# WARNING 타이머 — gas_alarm.py / power_alarm.py가 import해서 쓰므로 이 값만
# 바꾸면 두 도메인의 countdown이 함께 변경된다. 더미 시나리오에서 WARNING 구간이
# 빠르게 DANGER로 점프해 거의 발화되지 않아 3초로 짧게 둔다.
WARNING_DURATION_SEC = 3

# FastAPI 내부 알람 푸시 엔드포인트.
# 호스트는 settings.FASTAPI_INTERNAL_URL (env 주입) — 도커에선 `http://fastapi:8001`,
# 로컬에선 기본값 `http://127.0.0.1:8001`. 컨테이너 안에서 localhost로 붙으면
# Connection refused 가 나기 때문에 반드시 settings를 거쳐 가져온다.
_ALARM_PUSH_PATH = "/internal/alarms/push/"

# 가스 종류별 한글 표시명
_GAS_NAME = {
    "co": "CO (일산화탄소)",
    "h2s": "H₂S (황화수소)",
    "co2": "CO₂ (이산화탄소)",
    "o2": "O₂ (산소)",
    "no2": "NO₂ (이산화질소)",
    "so2": "SO₂ (이산화황)",
    "o3": "O₃ (오존)",
    "nh3": "NH₃ (암모니아)",
    "voc": "VOC (휘발성유기화합물)",
}


def _get_event_ack_names(event_id: int | None) -> list[str]:
    """활성 Event 의 EventAck 사용자명 list 를 반환한다.

    push_payload 의 `event_ack_users` 필드용. 다중 관리자 환경에서 운영자 A 가
    이미 "확인 완료" 클릭한 알람이 재발화 시 다른 운영자 B 의 토스트에
    "(A 확인 중)" 시그널 표시. ack 와 dedup 은 분리 유지 (안전망) + 시그널만 보강.

    Returns: [user.name, ...] 빈 list 면 시그널 미표시.
    """
    if not event_id:
        return []
    from apps.alerts.models import EventAcknowledgement

    return list(
        EventAcknowledgement.objects.filter(event_id=event_id)
        .select_related("user")
        .values_list("user__name", flat=True)
    )


def _push_to_ws(alarm_data: dict, *, raise_on_failure: bool = True) -> None:
    """FastAPI WebSocket 브로드캐스트 큐에 알람을 추가한다.

    timeout 10초로 도커 네트워크 마진을 두고, 5xx 및 네트워크 오류는 raise 해서
    호출자(fire_*_task)의 self.retry(exc=exc)에 흡수되도록 한다 — 일시 장애 시
    silent fail로 알람이 영구 누락되지 않게.

    raise_on_failure=False는 fire_clear_*_task에서만 사용 — 정상화 알림은
    critical하지 않아 retry로 인한 중복 발송보다 손실 허용이 합리적.

    IntegrationLog: 호출 결과(성공/실패)를 Celery task delay()로 비동기 INSERT.
    broker 다운 시 silent fail — 본 흐름 비차단.

    created_at: 호출자가 명시하지 않으면 이 시점(UTC ISO-8601)을 알람 생성 시각으로
    기록. 클라이언트는 매퍼에서 이 값을 우선 사용 (fallback: new Date()).
    """
    from datetime import datetime, timezone

    alarm_data.setdefault("created_at", datetime.now(timezone.utc).isoformat())

    headers = {}
    token = getattr(settings, "INTERNAL_SERVICE_TOKEN", "") or ""
    if token:
        headers["Authorization"] = f"Bearer {token}"

    base = getattr(settings, "FASTAPI_INTERNAL_URL", "") or "http://127.0.0.1:8001"
    url = base.rstrip("/") + _ALARM_PUSH_PATH

    result = "success"
    pushed = True
    try:
        resp = httpx.post(url, json=alarm_data, headers=headers, timeout=10.0)
        # 5xx는 재시도 가치가 있는 일시 장애로 간주 (FastAPI 503=Redis 일시 장애 포함)
        # 4xx는 페이로드 검증 실패라 retry해도 의미 없음 → raise 안 함
        if resp.status_code >= 500:
            raise httpx.HTTPStatusError(
                f"upstream {resp.status_code}",
                request=resp.request,
                response=resp,
            )
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        logger.warning("FastAPI WS 알람 푸시 실패: %s", e)
        result = "failure"
        pushed = False
        ALARM_WS_PUSH_FAILED_TOTAL.labels(
            alarm_type=alarm_data.get("alarm_type", "unknown")
        ).inc()

    try:
        from apps.operations.tasks.integration_log_task import (
            integration_log_create_task,
        )

        integration_log_create_task.delay(
            integration_type="transmit",
            target_system="DRF→FastAPI",
            result=result,
            description=f"alarm_type={alarm_data.get('alarm_type', '')}",
        )
    except Exception:
        pass  # broker 다운 silent fail — 본 흐름 비차단

    # WS 푸시 성공 시에만 Discord 미러 — 실패 시 retry 가 같은 알람을 재발송하면
    # Discord 엔 dedup 이 없어 중복되므로, 성공 tick 1회만 발송한다.
    if pushed:
        try:
            from apps.notifications.services.discord_service import (
                send_alarm_to_discord,
            )

            send_alarm_to_discord(alarm_data)
        except Exception:
            pass  # Discord 실패는 알람 본류 비차단

    if not pushed and raise_on_failure:
        # 호출자(fire_*_task)의 except에서 self.retry(exc=exc)로 흡수
        raise RuntimeError("FastAPI WS push failed")


@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def fire_danger_alarm_task(
    self,
    sensor_id: int,
    gas_type: str,
    value: float,
    facility_id: int,
    source_label: str,
    ingress_ts: float | None = None,
):
    """DANGER 즉각 알람 — AlarmRecord/Event 생성 후 FastAPI WS 큐에 푸시."""
    from apps.alerts.selectors.alarm_targets import get_facility_worker_ids
    from apps.alerts.services.event_service import create_alarm_and_event
    from apps.core.constants import AlarmType
    from apps.monitoring.utils.gas_thresholds import GAS_UNITS, get_threshold_value

    # DB 쓰기(create_alarm_and_event)와 WS 푸시를 별도 try 블록으로 분리한다 —
    # _push_to_ws 실패 시 retry 가 create_alarm_and_event 를 재실행하면 AlarmRecord
    # 가 중복 생성되기 때문. DB 쓰기 성공 후 WS 푸시 실패는 retry 없이 경고 로그만
    # 남긴다 (alarm 은 DB에 보존되므로 유실 없음).
    try:
        gas_name = _GAS_NAME.get(gas_type, gas_type.upper())
        unit = GAS_UNITS.get(gas_type, "")
        threshold = get_threshold_value(gas_type, "danger")
        summary = (
            f"[긴급] {gas_name} 위험 수준 초과 ({value} {unit})"
            " — 즉시 대피하고 관리자에게 보고하세요."
        )

        event, alarm = create_alarm_and_event(
            facility_id=facility_id,
            alarm_type=AlarmType.GAS_THRESHOLD,
            sensor_id=sensor_id,
            gas_type=gas_type,
            measured_value=value,
            threshold_value=threshold,
            risk_level="danger",
            source_label=source_label,
            summary=summary,
            detected_at=timezone.now(),
        )
    except Exception as exc:
        logger.error("DANGER 알람 DB 저장 실패: %s", exc)
        raise self.retry(exc=exc)

    if event is not None and alarm is not None:
        ALARM_FIRED_TOTAL.labels(alarm_type="gas_threshold", risk_level="danger").inc()
        try:
            _push_to_ws(
                {
                    "event_id": event.id,
                    "alarm_type": AlarmType.GAS_THRESHOLD,
                    "gas_type": gas_type,
                    "risk_level": "danger",
                    "measured_value": value,
                    "threshold_value": threshold,
                    "source_label": source_label,
                    "summary": summary,
                    "message": alarm.get_short_message(),
                    # 소속 시설 작업자에게도 대피 알림 — FastAPI가 이 목록으로만
                    # worker_clients 분배(전체 broadcast 아님). 누락 시 작업자 미전송.
                    "target_worker_ids": get_facility_worker_ids(facility_id),
                    # T3 (2026-05-19) — 활성 Event 의 EventAck 사용자명 list.
                    # 다중 관리자 환경에서 토스트에 "(N 확인 중)" 시그널 표시용.
                    "event_ack_users": _get_event_ack_names(event.id),
                    "is_new_event": alarm is not None,
                    "ingress_ts": ingress_ts,
                    # DRF 룰 단독 fire (레거시 경로) — 활성화 모드에서는 fastapi 가
                    # 직접 push 하므로 본 fallback 미사용.
                    "source": "static_legacy",
                    "reason": None,
                }
            )
        except Exception as exc:
            # DB 저장 완료 후 WS 푸시 실패 — retry 하면 AlarmRecord 중복 생성됨.
            # fingerprint dedup(alarm_queue.py)이 동일 event_id 재전송을 30s 안에 차단하므로
            # 재발화 필요 시 직접 push 재시도보다 다음 Celery tick 을 기다리는 게 안전.
            logger.warning("DANGER 알람 WS 푸시 실패 (DB 저장은 완료): %s", exc)
            return
        logger.info(
            "DANGER 알람 푸시 | sensor=%s gas=%s value=%s new_event=%s",
            sensor_id,
            gas_type,
            value,
            alarm is not None,
        )


@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def fire_warning_alarm_task(
    self,
    sensor_id: int,
    gas_type: str,
    value: float,
    facility_id: int,
    source_label: str,
    ingress_ts: float | None = None,
):
    """WARNING 30초 지속 후 알람 — AlarmRecord/Event 생성 후 FastAPI WS 큐에 푸시.

    gas_alarm.py에서 apply_async(countdown=WARNING_DURATION_SEC)로 호출되므로
    이 태스크가 실행될 시점에는 이미 30초가 경과한 상태.
    """
    from apps.alerts.services.event_service import create_alarm_and_event
    from apps.core.constants import AlarmType
    from apps.monitoring.utils.gas_thresholds import GAS_UNITS, get_threshold_value

    # DB 쓰기와 WS 푸시를 별도 try 블록으로 분리 (fire_danger_alarm_task 참고).
    try:
        gas_name = _GAS_NAME.get(gas_type, gas_type.upper())
        unit = GAS_UNITS.get(gas_type, "")
        threshold = get_threshold_value(gas_type, "warning")
        summary = (
            f"[주의] {gas_name} 주의 수준 {WARNING_DURATION_SEC}초 지속 ({value} {unit})"
            " — 작업을 중단하고 환기 후 관리자에게 보고하세요."
        )

        event, alarm = create_alarm_and_event(
            facility_id=facility_id,
            alarm_type=AlarmType.GAS_THRESHOLD,
            sensor_id=sensor_id,
            gas_type=gas_type,
            measured_value=value,
            threshold_value=threshold,
            risk_level="warning",
            source_label=source_label,
            summary=summary,
            detected_at=timezone.now(),
        )
    except Exception as exc:
        logger.error("WARNING 알람 DB 저장 실패: %s", exc)
        raise self.retry(exc=exc)

    if event is not None and alarm is not None:
        ALARM_FIRED_TOTAL.labels(alarm_type="gas_threshold", risk_level="warning").inc()
        try:
            _push_to_ws(
                {
                    "event_id": event.id,
                    "alarm_type": AlarmType.GAS_THRESHOLD,
                    "gas_type": gas_type,
                    "risk_level": "warning",
                    "measured_value": value,
                    "threshold_value": threshold,
                    "source_label": source_label,
                    "summary": summary,
                    "message": alarm.get_short_message(),
                    # 활성 Event 의 EventAck 사용자명 list — 다중 관리자 환경에서
                    # 토스트에 "(N 확인 중)" 시그널 표시용.
                    "event_ack_users": _get_event_ack_names(event.id),
                    "is_new_event": alarm is not None,
                    "ingress_ts": ingress_ts,
                    # DRF 룰 단독 fire (레거시 경로) — 활성화 모드에서는 fastapi 가
                    # 직접 push 하므로 본 fallback 미사용.
                    "source": "static_legacy",
                    "reason": None,
                }
            )
        except Exception as exc:
            logger.warning("WARNING 알람 WS 푸시 실패 (DB 저장은 완료): %s", exc)
        else:
            logger.info(
                "WARNING 알람 푸시 | sensor=%s gas=%s value=%s new_event=%s",
                sensor_id,
                gas_type,
                value,
                alarm is not None,
            )

    # 정상 종료 시 task_key 즉시 정리 — normal 처리(gas_alarm.py)의 cache.delete 에
    # 의존하지 않고 task 가 직접 책임진다. normal 천이가 안 들어와도 잔류 키로 다음
    # WARNING 이 막히지 않게. retry 경로는 위 except(DB 실패)에서 raise 후 여기까지
    # 미도달 → 잔류 허용 (_TASK_KEY_TTL 로 자연 정리).
    cache.delete(f"alarm:task:{sensor_id}:{gas_type}")


@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def fire_geofence_alarm_task(
    self,
    worker_id: int,
    facility_id: int,
    geofence_id: int,
    geofence_name: str,
    risk_level: str,
    sensor_source_label: str,
):
    """위험구역 진입 알람 — AlarmRecord/Event 생성 후 FastAPI WS 큐에 푸시."""
    from apps.alerts.services.event_service import create_alarm_and_event
    from apps.core.constants import AlarmType

    label = {"danger": "긴급", "warning": "주의"}.get(risk_level, "")
    summary = (
        f"[{label}] 작업자가 위험구역 '{geofence_name}'에 진입했습니다."
        f" ({sensor_source_label} 임계치 초과)"
    )

    try:
        event, alarm = create_alarm_and_event(
            facility_id=facility_id,
            alarm_type=AlarmType.GEOFENCE_INTRUSION,
            geofence_id=geofence_id,
            worker_id=worker_id,
            risk_level=risk_level,
            source_label=geofence_name,
            summary=summary,
            detected_at=timezone.now(),
        )
        if event is not None and alarm is not None:
            ALARM_FIRED_TOTAL.labels(
                alarm_type="geofence_intrusion", risk_level=risk_level
            ).inc()
            _push_to_ws(
                {
                    "event_id": event.id,
                    "alarm_type": AlarmType.GEOFENCE_INTRUSION,
                    "risk_level": risk_level,
                    "source_label": geofence_name,
                    "summary": summary,
                    "message": alarm.get_short_message(),
                    # 활성 Event 의 EventAck 사용자명 list — 다중 관리자 환경에서
                    # 토스트에 "(N 확인 중)" 시그널 표시용.
                    "event_ack_users": _get_event_ack_names(event.id),
                    "is_new_event": alarm is not None,
                    # fastapi alarm_router 가 alarm.worker_id 기반으로 worker_clients
                    # 개인 전송 분기 — broadcast 외 타겟 작업자 개인 push 용.
                    "worker_id": worker_id,
                }
            )
            logger.info(
                "지오펜스 알람 푸시 | geofence=%s worker=%s risk=%s new_event=%s",
                geofence_name,
                worker_id,
                risk_level,
                alarm is not None,
            )
    except Exception as exc:
        logger.error("지오펜스 알람 생성 실패: %s", exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def fire_clear_notification_task(
    self,
    sensor_id: int,
    source_label: str,
    gas_types: list[str],
):
    """정상화 알림 — 복귀한 가스 목록을 1개 메시지로 묶어 발송. 9개 팝업 방지."""
    from apps.alerts.models import AlarmRecord

    try:
        # 정상화된 가스 이름 목록을 콤마로 연결 (예: "CO, H₂S")
        gas_names = ", ".join(_GAS_NAME.get(g, g.upper()) for g in gas_types)
        summary = (
            f"[안전] {source_label} — {gas_names} 농도가 정상 범위로 복귀했습니다."
            " 관리자 확인 후 작업을 재개하세요."
        )
        # AlarmRecord 객체는 생성 안 함 (정상화는 record 안 남김). 모델 메서드를
        # ephemeral 인스턴스로 호출 — short message single source of truth 유지.
        short_message = AlarmRecord(alarm_type="gas_clear").get_short_message()

        # 정상화 알림은 critical 아님 — push 실패해도 retry 안 함 (중복 발송 회피)
        _push_to_ws(
            {
                "alarm_type": "gas_clear",
                "gas_type": ",".join(gas_types),
                "risk_level": "normal",
                "source_label": source_label,
                "summary": summary,
                "message": short_message,
                "is_new_event": False,
            },
            raise_on_failure=False,
        )
        # 관련 ACTIVE 가스 Event 자동 RESOLVED — 운영자 수동 클릭 없이 정리.
        from apps.alerts.services.event_service import auto_resolve_active_events

        resolved = auto_resolve_active_events(
            event_type_prefix="gas",
            sensor_id=sensor_id,
            cleared_gases=gas_types,
        )
        logger.info(
            "정상화 알림 발송 | sensor=%s gases=%s resolved=%d",
            sensor_id,
            gas_types,
            resolved,
        )

    except Exception as exc:
        logger.error("정상화 알림 실패: %s", exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def fire_power_danger_task(
    self,
    device_id: int,
    channel: int,
    value: float,
    facility_id: int,
    source_label: str,
    ingress_ts: float | None = None,
):
    """전력 DANGER 즉각 알람 — AlarmRecord/Event 생성 후 FastAPI WS 큐에 푸시."""
    from apps.alerts.selectors.alarm_targets import get_facility_worker_ids
    from apps.alerts.services.event_service import create_alarm_and_event
    from apps.core.constants import AlarmType
    from apps.facilities.services.threshold_service import get_threshold

    # DB 쓰기와 WS 푸시를 별도 try 블록으로 분리 (gas alarm 과 동일 패턴).
    try:
        power_threshold = get_threshold("power_default", "power_w") or {}
        danger_max = power_threshold.get("danger_max")
        threshold = float(danger_max) if danger_max is not None else None
        summary = (
            f"[긴급] {source_label} 전력 과부하 ({value}W)"
            " — 즉시 확인하고 관리자에게 보고하세요."
        )
        event, alarm = create_alarm_and_event(
            facility_id=facility_id,
            alarm_type=AlarmType.POWER_OVERLOAD,
            power_device_id=device_id,
            measured_value=value,
            threshold_value=threshold,
            risk_level="danger",
            source_label=source_label,
            summary=summary,
            detected_at=timezone.now(),
            channel=channel,
        )
    except Exception as exc:
        logger.error("전력 DANGER 알람 DB 저장 실패: %s", exc)
        raise self.retry(exc=exc)

    if event is not None and alarm is not None:
        ALARM_FIRED_TOTAL.labels(alarm_type="power_overload", risk_level="danger").inc()
        try:
            _push_to_ws(
                {
                    "event_id": event.id,
                    "alarm_type": AlarmType.POWER_OVERLOAD,
                    "channel": channel,
                    "risk_level": "danger",
                    "measured_value": value,
                    "threshold_value": threshold,
                    "source_label": source_label,
                    "summary": summary,
                    "message": alarm.get_short_message(),
                    # 소속 시설 작업자에게도 대피 알림 — FastAPI가 이 목록으로만
                    # worker_clients 분배(전체 broadcast 아님). 누락 시 작업자 미전송.
                    "target_worker_ids": get_facility_worker_ids(facility_id),
                    # T3 (2026-05-19) — 활성 Event 의 EventAck 사용자명 list.
                    # 다중 관리자 환경에서 토스트에 "(N 확인 중)" 시그널 표시용.
                    "event_ack_users": _get_event_ack_names(event.id),
                    "is_new_event": alarm is not None,
                    "ingress_ts": ingress_ts,
                    # DRF 룰 단독 fire (레거시 경로) — 활성화 모드에서는 fastapi 가
                    # 직접 push 하므로 본 fallback 미사용.
                    "source": "static_legacy",
                    "reason": None,
                }
            )
        except Exception as exc:
            logger.warning("전력 DANGER 알람 WS 푸시 실패 (DB 저장은 완료): %s", exc)
            return
        logger.info(
            "전력 DANGER 알람 | device=%s ch=%s value=%sW new_event=%s",
            device_id,
            channel,
            value,
            alarm is not None,
        )


@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def fire_power_warning_task(
    self,
    device_id: int,
    channel: int,
    value: float,
    facility_id: int,
    source_label: str,
    ingress_ts: float | None = None,
):
    """전력 WARNING 30초 지속 후 알람 — AlarmRecord/Event 생성 후 FastAPI WS 큐에 푸시."""
    from apps.alerts.services.event_service import create_alarm_and_event
    from apps.core.constants import AlarmType
    from apps.facilities.services.threshold_service import get_threshold

    # DB 쓰기와 WS 푸시를 별도 try 블록으로 분리 (gas alarm 과 동일 패턴).
    try:
        power_threshold = get_threshold("power_default", "power_w") or {}
        warning_max = power_threshold.get("warning_max")
        threshold = float(warning_max) if warning_max is not None else None
        summary = (
            f"[주의] {source_label} 전력 경고 수준 {WARNING_DURATION_SEC}초 지속 ({value}W)"
            " — 설비 상태를 확인하세요."
        )
        event, alarm = create_alarm_and_event(
            facility_id=facility_id,
            alarm_type=AlarmType.POWER_OVERLOAD,
            power_device_id=device_id,
            measured_value=value,
            threshold_value=threshold,
            risk_level="warning",
            source_label=source_label,
            summary=summary,
            detected_at=timezone.now(),
            channel=channel,
        )
    except Exception as exc:
        logger.error("전력 WARNING 알람 DB 저장 실패: %s", exc)
        raise self.retry(exc=exc)

    if event is not None and alarm is not None:
        ALARM_FIRED_TOTAL.labels(
            alarm_type="power_overload", risk_level="warning"
        ).inc()
        try:
            _push_to_ws(
                {
                    "event_id": event.id,
                    "alarm_type": AlarmType.POWER_OVERLOAD,
                    "channel": channel,
                    "risk_level": "warning",
                    "measured_value": value,
                    "threshold_value": threshold,
                    "source_label": source_label,
                    "summary": summary,
                    "message": alarm.get_short_message(),
                    # 활성 Event 의 EventAck 사용자명 list — 다중 관리자 환경에서
                    # 토스트에 "(N 확인 중)" 시그널 표시용.
                    "event_ack_users": _get_event_ack_names(event.id),
                    "is_new_event": alarm is not None,
                    "ingress_ts": ingress_ts,
                    # DRF 룰 단독 fire (레거시 경로) — 활성화 모드에서는 fastapi 가
                    # 직접 push 하므로 본 fallback 미사용.
                    "source": "static_legacy",
                    "reason": None,
                }
            )
        except Exception as exc:
            logger.warning("전력 WARNING 알람 WS 푸시 실패 (DB 저장은 완료): %s", exc)
        else:
            logger.info(
                "전력 WARNING 알람 | device=%s ch=%s value=%sW new_event=%s",
                device_id,
                channel,
                value,
                alarm is not None,
            )

    # 정상 종료 시 task_key 즉시 정리 (가스 task 와 동일 패턴). retry 경로는 DB 실패
    # except 에서 raise → 여기 미도달 (잔류 허용, TTL 자연 만료).
    cache.delete(f"alarm:power:task:{device_id}:{channel}")


@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def fire_power_clear_task(
    self,
    device_id: int,
    channel: int,
    source_label: str,
):
    """전력 정상화 알림 — WS 알림 + 관련 ACTIVE Event 자동 RESOLVED."""
    from apps.alerts.models import AlarmRecord

    try:
        summary = (
            f"[안전] {source_label} — 전력이 정상 범위로 복귀했습니다."
            " 관리자 확인 후 작업을 재개하세요."
        )
        short_message = AlarmRecord(alarm_type="power_clear").get_short_message()
        # 정상화 알림은 critical 아님 — push 실패해도 retry 안 함 (중복 발송 회피)
        _push_to_ws(
            {
                "alarm_type": "power_clear",
                "channel": channel,
                "risk_level": "normal",
                "source_label": source_label,
                "summary": summary,
                "message": short_message,
                "is_new_event": False,
            },
            raise_on_failure=False,
        )
        # 관련 ACTIVE 전력 Event 자동 RESOLVED — 단, 마지막 활성 채널이 정상화될
        # 때만. 한 채널 정상복귀가 디바이스 공유 Event 를 RESOLVE 하면 아직 위험한
        # 다른 채널의 Event 까지 닫혀, 다음 발화가 새 event_id 로 생성돼 프론트 60s
        # dedup(event_id 키)을 통과 → 폭주. 가스 cleared_gases 가 막는 race 의 전력판.
        from apps.alerts.services.event_service import auto_resolve_active_events
        from apps.facilities.models import PowerDevice
        from apps.monitoring.services.power_alarm import has_other_active_channel

        device = PowerDevice.objects.filter(pk=device_id).first()
        channel_count = device.channel_count if device else 16
        if has_other_active_channel(device_id, channel, channel_count):
            resolved = 0  # 다른 채널 위험 지속 → Event 유지 (마지막 채널이 닫는다)
        else:
            resolved = auto_resolve_active_events(
                event_type_prefix="power", power_device_id=device_id
            )
        logger.info(
            "전력 정상화 알림 | device=%s ch=%s resolved=%d",
            device_id,
            channel,
            resolved,
        )
    except Exception as exc:
        logger.error("전력 정상화 알림 실패: %s", exc)
        raise self.retry(exc=exc)
