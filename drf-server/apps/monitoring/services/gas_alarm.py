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

from apps.alerts.services.alarm_dedupe import (
    clear_state,
    get_state,
    try_transition,
)
from apps.alerts.tasks import (
    WARNING_DURATION_SEC,
    fire_clear_notification_task,
    fire_danger_alarm_task,
    fire_warning_alarm_task,
)

GAS_FIELDS = ["co", "h2s", "co2", "o2", "no2", "so2", "o3", "nh3", "voc"]

# state_key (`alarm:state:{sensor_id}:{gas}`) 캐시 유지 시간.
#
# [Step 4 — 1시간 → 1분 단축, 5번 문서 §9 정렬]
# 기존 3600s 는 한 번 danger 천이 후 1시간 동안 같은 (sensor, gas) 의 동일 상태
# 천이를 모두 skip → 운영에서 "한 번 뜨고 그 뒤 1시간 안 뜸" 누락의 직접 원인.
# settings.ALARM_REPOPUP_COOLDOWN_SEC (event_service, 기본 60s) 와 일치시켜 두 dedup
# 계층 (try_transition / Event 쿨다운) 시간이 합치되도록 정렬. 산업 안전 도메인에서 위험
# 지속 시 1분 cadence 는 escalation 트리거 역할도 함 (5번 문서 §9 의 "동일 작업자
# +센서+구역+위험단계 1분 내 1회"). 추후 1~2주 운영 데이터 보고 재평가.
_CACHE_TTL = 60

# task_key (`alarm:task:{sensor_id}:{gas}`) — WARNING 타이머 진행 신호 키.
#
# [Step 5 — TTL 분리·축소]
# 기존엔 state_key 와 동일한 _CACHE_TTL (1시간) 을 썼다. task 실행 끝나도 키가
# 잔류해 다음 WARNING 의 cache.add(SETNX) 가 False → 새 타이머 시작 안 됨 → 누락.
# 카운트다운보다 5초 큰 값으로 두면 race 마진 확보, 정상 종료 시는 tasks.py 가
# 직접 cache.delete 한다.
_TASK_KEY_TTL = WARNING_DURATION_SEC + 5


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
    sensor = gas_data.gas_sensor
    sensor_id = sensor.id
    facility_id = sensor.facility_id
    source_label = sensor.device_name

    for gas in GAS_FIELDS:
        risk = getattr(gas_data, f"{gas}_risk", None)
        value = getattr(gas_data, gas, None)
        if value is None:
            continue

        state_key = _state_key(sensor_id, gas)
        task_key = _task_key(sensor_id, gas)

        if risk == "danger":
            # 진행 중인 WARNING 타이머가 있으면 취소
            pending_task_id = cache.get(task_key)
            if pending_task_id:
                _revoke(pending_task_id)
                cache.delete(task_key)

            # 원자 천이 — 직전 상태가 danger 아닐 때만 1회 fire (race-safe)
            if try_transition(state_key, "danger", _CACHE_TTL):
                fire_danger_alarm_task.delay(
                    sensor_id, gas, value, facility_id, source_label
                )

        elif risk == "warning":
            prev_state = get_state(state_key)
            if prev_state in ("warning", "danger"):
                continue
            # SETNX(cache.add)로 첫 도착자만 타이머 시작 — race 차단.
            # TTL 은 _TASK_KEY_TTL (카운트다운 + 5s) — 정상 종료 시 tasks.py 가
            # cache.delete 로 즉시 정리하고, retry/실패는 자연 만료로 정리된다.
            if not cache.add(task_key, "_pending_", _TASK_KEY_TTL):
                continue
            task = fire_warning_alarm_task.apply_async(
                args=[sensor_id, gas, value, facility_id, source_label],
                countdown=WARNING_DURATION_SEC,
            )
            cache.set(task_key, task.id, _TASK_KEY_TTL)
            try_transition(state_key, "warning", _CACHE_TTL)

        else:  # normal
            # 타이머가 있으면 취소
            pending_task_id = cache.get(task_key)
            if pending_task_id:
                _revoke(pending_task_id)
                cache.delete(task_key)

            # 이전에 경보 상태였으면 정상화 알림 발송
            if get_state(state_key) in ("warning", "danger"):
                fire_clear_notification_task.delay(sensor_id, source_label, gas)
                clear_state(state_key)

    # WS 알람은 Celery 태스크가 직접 FastAPI에 푸시하므로 빈 리스트 반환
    return []
