# monitoring/services/power_alarm.py — 전력 알람 라우팅 서비스
#
# PowerData(watt) 수신 시 채널별 위험도로 Celery 태스크를 분기한다.
# gas_alarm.py와 동일한 패턴 — 위험도·타이머 상태는 Redis 캐시에 보관.
#
# ┌──────────────────────────────────────────────────────────────┐
# │  위험도     │  동작                                           │
# ├──────────────────────────────────────────────────────────────┤
# │  DANGER    │  즉각 알람 (fire_power_danger_task.delay)        │
# │  WARNING   │  30초 타이머 (apply_async countdown=30)          │
# │  NORMAL    │  타이머 취소 + 정상화 알림 (이전 경보 시)          │
# └──────────────────────────────────────────────────────────────┘
#
# 캐시 키:
#   alarm:power:state:{device_id}:{channel}  → "normal" | "warning" | "danger"
#   alarm:power:task:{device_id}:{channel}   → Celery task ID (revoke용)

from django.core.cache import cache

from apps.alerts.tasks import (
    WARNING_DURATION_SEC,
    fire_power_clear_task,
    fire_power_danger_task,
    fire_power_warning_task,
)
from apps.core.constants import POWER_THRESHOLDS

# 채널 번호 → 설비명 (power_service.py의 CHANNEL_TO_DEVICE와 동기화)
_CHANNEL_NAME: dict[int, str] = {
    1: "압연기",
    2: "송풍기",
    3: "집진기",
    4: "전자기 교반기",
    5: "냉각펌프",
    6: "유압장치",
    7: "컨베이어",
    8: "분쇄기",
}

_CACHE_TTL = 3600


def _state_key(device_id: int, channel: int) -> str:
    """채널별 현재 알람 상태를 저장하는 Redis 캐시 키를 반환한다."""
    return f"alarm:power:state:{device_id}:{channel}"


def _task_key(device_id: int, channel: int) -> str:
    """WARNING 타이머 Celery task ID를 저장하는 Redis 캐시 키를 반환한다."""
    return f"alarm:power:task:{device_id}:{channel}"


def _revoke(task_id: str) -> None:
    """진행 중인 WARNING 타이머 Celery 태스크를 강제 취소한다."""
    from config.celery import app as celery_app

    celery_app.control.revoke(task_id, terminate=True)


def _channel_label(channel: int) -> str:
    """채널 번호를 설비명 문자열로 변환한다. 미등록 채널은 'CH{n}' 형식으로 반환한다."""
    return _CHANNEL_NAME.get(channel, f"CH{channel}")


def _evaluate(watt: float) -> str:
    """watt 값을 POWER_THRESHOLDS 기준으로 위험도 문자열로 변환한다."""
    if watt > POWER_THRESHOLDS["danger"]:
        return "danger"
    if watt > POWER_THRESHOLDS["caution"]:
        return "warning"
    return "normal"


def trigger_power_alarms(objs: list, device) -> None:
    """
    PowerData 일괄 저장 후 watt 채널에 대해 채널별 위험도로 알람 라우팅한다.

    PowerDataBulkIngestSerializer.create()에서 호출된다.
    watt 데이터 타입이 아닌 경우(current/voltage) 즉시 반환한다.
    """
    if not objs or objs[0].data_type != "watt":
        return

    device_id = device.id
    facility_id = device.facility_id

    for obj in objs:
        channel = obj.channel
        watt = obj.value

        # 통신 불능 채널은 알람 판정 제외
        if watt is None:
            continue

        risk = _evaluate(watt)
        state_key = _state_key(device_id, channel)
        task_key = _task_key(device_id, channel)
        prev_state = cache.get(state_key, "normal")
        label = _channel_label(channel)

        if risk == "danger":
            # 진행 중인 WARNING 타이머가 있으면 취소하고 즉각 DANGER 알람 발화
            pending = cache.get(task_key)
            if pending:
                _revoke(pending)
                cache.delete(task_key)
            if prev_state != "danger":
                fire_power_danger_task.delay(
                    device_id, channel, watt, facility_id, label
                )
                cache.set(state_key, "danger", _CACHE_TTL)

        elif risk == "warning":
            # 이미 타이머가 걸려 있으면 중복 시작 방지
            if prev_state not in ("warning", "danger") and not cache.get(task_key):
                task = fire_power_warning_task.apply_async(
                    args=[device_id, channel, watt, facility_id, label],
                    countdown=WARNING_DURATION_SEC,
                )
                cache.set(task_key, task.id, _CACHE_TTL)
                cache.set(state_key, "warning", _CACHE_TTL)

        else:  # normal
            # WARNING 타이머가 있으면 취소하고 이전 경보 시 정상화 알림 발송
            pending = cache.get(task_key)
            if pending:
                _revoke(pending)
                cache.delete(task_key)
            if prev_state in ("warning", "danger"):
                fire_power_clear_task.delay(device_id, channel, label)
                cache.set(state_key, "normal", _CACHE_TTL)
