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

from django.conf import settings
from django.core.cache import cache

from apps.alerts.services.alarm_dedupe import (
    clear_state,
    confirm_consecutive,
    get_state,
    is_gas_ai_mute_active,
    try_transition,
)
from apps.alerts.tasks import (
    WARNING_DURATION_SEC,
    fire_clear_notification_task,
    fire_danger_alarm_task,
    fire_warning_alarm_task,
)

# AI 추론 대상 가스 — fastapi gas_service co+h2s+co2 다변량 IF 와 일치.
# 이 3종만 mute 가드 적용 (option B). 나머지 6종 (no2/so2/o3/nh3/voc/o2/lel) 은
# AI 추론 범위 밖이라 정적 룰 단독 발화.
_AI_GUARDED_GASES = {"co", "h2s", "co2"}

GAS_FIELDS = ["co", "h2s", "co2", "o2", "no2", "so2", "o3", "nh3", "voc"]

# state_key (`alarm:state:{sensor_id}:{gas}`) 캐시 유지 시간 — 60s.
# settings.ALARM_REPOPUP_COOLDOWN_SEC (event_service 기본 60s) 와 일치시켜
# try_transition / Event 쿨다운 두 dedup 계층의 시간을 정렬한다. 위험 지속 시
# 1분 cadence 가 escalation 트리거 역할도 한다 (동일 센서·구역·위험단계 1분 내 1회).
_CACHE_TTL = 60

# task_key (`alarm:task:{sensor_id}:{gas}`) — WARNING 타이머 진행 신호 키 TTL.
# 카운트다운보다 5초 크게 둬 race 마진 확보. 정상 종료 시는 tasks.py 가 직접
# cache.delete 하고, retry/실패는 자연 만료로 정리된다.
_TASK_KEY_TTL = WARNING_DURATION_SEC + 5


def _state_key(sensor_id: int, gas: str) -> str:
    return f"alarm:state:{sensor_id}:{gas}"


def _task_key(sensor_id: int, gas: str) -> str:
    return f"alarm:task:{sensor_id}:{gas}"


def _dcount_key(sensor_id: int, gas: str) -> str:
    """danger 연속 틱 카운터 키 — _state_key 와 sibling 네임스페이스."""
    return f"alarm:state:{sensor_id}:{gas}:dcount"


def _revoke(task_id: str) -> None:
    """진행 중인 Celery 태스크를 취소한다."""
    from config.celery import app as celery_app

    celery_app.control.revoke(task_id, terminate=True)


def trigger_gas_alarms(gas_data, ingress_ts: float | None = None) -> list[dict]:
    """가스 데이터 수신 시 위험도별로 알람을 라우팅한다.

    GasDataCreateSerializer.create()에서 호출되며,
    반환값은 빈 리스트 — WS 알람은 Celery 태스크가 FastAPI에 직접 푸시한다.
    """
    sensor = gas_data.gas_sensor
    sensor_id = sensor.id
    facility_id = sensor.facility_id
    source_label = sensor.device_name

    cleared_gases: list[str] = []
    for gas in GAS_FIELDS:
        risk = getattr(gas_data, f"{gas}_risk", None)
        value = getattr(gas_data, gas, None)
        if value is None:
            continue

        state_key = _state_key(sensor_id, gas)
        task_key = _task_key(sensor_id, gas)
        dcount_key = _dcount_key(sensor_id, gas)

        if risk == "danger":
            # danger 2틱 confirm — 단일 틱 센서 스파이크 억제. 미확정 틱엔 아무 동작도
            # 안 함(state/타이머 불변)이라 1틱 블립이 경보를 만들지 않는다.
            # settings.DANGER_CONFIRM_TICKS=1 이면 첫 틱 즉시 발화(기존 동작).
            if not confirm_consecutive(
                dcount_key, settings.DANGER_CONFIRM_TICKS, _CACHE_TTL
            ):
                continue

            # 진행 중인 WARNING 타이머가 있으면 취소
            pending_task_id = cache.get(task_key)
            if pending_task_id:
                _revoke(pending_task_id)
                cache.delete(task_key)

            # AI mute 가드 (option B) — 추론 가스 3종에 한해 AI 발화 직후 60s 룰 억제.
            # fastapi mark_gas_ai_recent 와 같은 sensor.device_name (mac) 키 사용.
            if gas in _AI_GUARDED_GASES and is_gas_ai_mute_active(
                sensor.device_name, gas, "danger"
            ):
                continue

            # 원자 천이 — 직전 상태가 danger 아닐 때만 1회 fire (race-safe)
            if try_transition(state_key, "danger", _CACHE_TTL):
                fire_danger_alarm_task.delay(
                    sensor_id,
                    gas,
                    value,
                    facility_id,
                    source_label,
                    ingress_ts=ingress_ts,
                )

        elif risk == "warning":
            cache.delete(dcount_key)  # danger 스트릭 끊김 — confirm 카운터 리셋
            prev_state = get_state(state_key)
            if prev_state in ("warning", "danger"):
                continue
            # AI mute 가드 — danger 와 동일 패턴.
            if gas in _AI_GUARDED_GASES and is_gas_ai_mute_active(
                sensor.device_name, gas, "warning"
            ):
                continue
            # SETNX(cache.add)로 첫 도착자만 타이머 시작 — race 차단.
            # TTL 은 _TASK_KEY_TTL (카운트다운 + 5s) — 정상 종료 시 tasks.py 가
            # cache.delete 로 즉시 정리하고, retry/실패는 자연 만료로 정리된다.
            if not cache.add(task_key, "_pending_", _TASK_KEY_TTL):
                continue
            task = fire_warning_alarm_task.apply_async(
                args=[sensor_id, gas, value, facility_id, source_label],
                kwargs={"ingress_ts": ingress_ts},
                countdown=WARNING_DURATION_SEC,
            )
            cache.set(task_key, task.id, _TASK_KEY_TTL)
            try_transition(state_key, "warning", _CACHE_TTL)

        else:  # normal
            cache.delete(dcount_key)  # danger 스트릭 끊김 — confirm 카운터 리셋
            # 타이머가 있으면 취소
            pending_task_id = cache.get(task_key)
            if pending_task_id:
                _revoke(pending_task_id)
                cache.delete(task_key)

            # 이전에 경보 상태였으면 정상화 대상으로 수집 (루프 후 1회 배치 발송)
            if get_state(state_key) in ("warning", "danger"):
                cleared_gases.append(gas)
                clear_state(state_key)

    # 정상화된 가스가 있으면 1개 메시지로 묶어 발송 — 가스별 9개 팝업 방지
    if cleared_gases:
        fire_clear_notification_task.delay(sensor_id, source_label, cleared_gases)

    # WS 알람은 Celery 태스크가 직접 FastAPI에 푸시하므로 빈 리스트 반환
    return []
