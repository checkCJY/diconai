# monitoring/services/gas_alarm.py — 가스 알람 라우팅 서비스
#
# GasData 수신 시 위험도별로 Celery 태스크를 분기한다.
#
# ┌──────────────────────────────────────────────────────────┐
# │  위험도     │  동작                                       │
# ├──────────────────────────────────────────────────────────┤
# │  DANGER    │  즉각 알람 (fire_danger_alarm_task.delay)    │
# │  WARNING   │  30초 타이머 (apply_async countdown=30)      │
# │  NORMAL    │  타이머 취소 + 정상화 알림 (이전 경보 시)     │
# └──────────────────────────────────────────────────────────┘
#
# 알람 상태와 WARNING 타이머 task ID는 Django cache(Redis)에 저장한다.
#   alarm:state:{sensor_id}:{gas}  → "normal" | "warning" | "danger"
#   alarm:task:{sensor_id}:{gas}   → Celery task ID (revoke용)

from django.core.cache import cache

from apps.alerts.tasks import (
    WARNING_DURATION_SEC,
    fire_clear_notification_task,
    fire_danger_alarm_task,
    fire_warning_alarm_task,
)

GAS_FIELDS = ["co", "h2s", "co2", "o2", "no2", "so2", "o3", "nh3", "voc"]

# 알람 상태/task ID 캐시 유지 시간 (1시간)
_CACHE_TTL = 3600


def _state_key(sensor_id: int, gas: str) -> str:
    return f"alarm:state:{sensor_id}:{gas}"


def _task_key(sensor_id: int, gas: str) -> str:
    return f"alarm:task:{sensor_id}:{gas}"


def _revoke(task_id: str) -> None:
    """진행 중인 Celery 태스크를 취소한다."""
    from config.celery import app as celery_app
    celery_app.control.revoke(task_id, terminate=True)


def trigger_gas_alarms(gas_data) -> list[dict]:
    """
    가스 데이터 수신 시 위험도별 알람 라우팅.

    GasDataCreateSerializer.create()에서 호출되며,
    반환값은 빈 리스트 — WS 알람은 Celery 태스크가 FastAPI에 직접 푸시한다.
    """
    sensor       = gas_data.gas_sensor
    sensor_id    = sensor.id
    facility_id  = sensor.facility_id
    source_label = sensor.device_name

    for gas in GAS_FIELDS:
        risk  = getattr(gas_data, f"{gas}_risk", None)
        value = getattr(gas_data, gas, None)
        if value is None:
            continue

        state_key  = _state_key(sensor_id, gas)
        task_key   = _task_key(sensor_id, gas)
        prev_state = cache.get(state_key, "normal")

        if risk == "danger":
            # 진행 중인 WARNING 타이머가 있으면 취소
            pending_task_id = cache.get(task_key)
            if pending_task_id:
                _revoke(pending_task_id)
                cache.delete(task_key)

            # 이미 DANGER 상태면 중복 발송 방지
            if prev_state != "danger":
                fire_danger_alarm_task.delay(
                    sensor_id, gas, value, facility_id, source_label
                )
                cache.set(state_key, "danger", _CACHE_TTL)

        elif risk == "warning":
            # WARNING/DANGER 타이머가 이미 있으면 중복 시작 방지
            if prev_state not in ("warning", "danger") and not cache.get(task_key):
                task = fire_warning_alarm_task.apply_async(
                    args=[sensor_id, gas, value, facility_id, source_label],
                    countdown=WARNING_DURATION_SEC,
                )
                cache.set(task_key, task.id, _CACHE_TTL)
                cache.set(state_key, "warning", _CACHE_TTL)

        else:  # normal
            # 타이머가 있으면 취소
            pending_task_id = cache.get(task_key)
            if pending_task_id:
                _revoke(pending_task_id)
                cache.delete(task_key)

            # 이전에 경보 상태였으면 정상화 알림 발송
            if prev_state in ("warning", "danger"):
                fire_clear_notification_task.delay(sensor_id, source_label, gas)
                cache.set(state_key, "normal", _CACHE_TTL)

    # WS 알람은 Celery 태스크가 직접 FastAPI에 푸시하므로 빈 리스트 반환
    return []
