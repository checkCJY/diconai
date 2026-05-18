# monitoring/services/power_alarm.py — 전력 알람 라우팅 서비스
#
# PowerData(watt/current/voltage) 수신 시 채널별 3축(W·A·V) 위험도를 통합한 종합
# 위험도(max-of-3)로 Celery 태스크를 분기한다. 한 채널 = 한 알람 유지.
#
# ┌──────────────────────────────────────────────────────────────┐
# │  종합 위험도 │  동작                                            │
# ├──────────────────────────────────────────────────────────────┤
# │  DANGER     │  즉각 알람 (fire_power_danger_task.delay)         │
# │  WARNING    │  3초 타이머 (apply_async countdown=3)             │
# │  NORMAL     │  타이머 취소 + 정상화 알림 (이전 경보 시)           │
# └──────────────────────────────────────────────────────────────┘
#
# 캐시 키:
#   alarm:power:state:{device_id}:{channel}           → 종합 위험도 (Phase 1 계약, 변경 금지)
#   alarm:power:task:{device_id}:{channel}            → Celery task ID (revoke용)
#   alarm:power:risk:{device_id}:{channel}:{axis}     → 축별 마지막 위험도 (5분 TTL)
#
# 채널 라벨: PowerDevice.channel_meta[str(ch)]["name"] 우선, 미지정 시 "CH{n}".

from django.core.cache import cache

from apps.alerts.services.alarm_dedupe import (
    clear_state,
    get_state,
    is_ai_mute_active,
    try_transition,
)
from apps.alerts.tasks import (
    WARNING_DURATION_SEC,
    fire_power_clear_task,
    fire_power_danger_task,
    fire_power_warning_task,
)
from apps.core.constants import RiskLevel
from apps.core.metrics import RULE_FIRE_SUPPRESSED_BY_AI_TOTAL
from apps.facilities.services.threshold_service import (
    evaluate_current_risk,
    evaluate_power_risk,
    evaluate_voltage_risk,
)

# state_key 캐시 유지 시간. [Step 4 — 1시간 → 1분 단축, 5번 문서 §9 정렬]
# settings.ALARM_REPOPUP_COOLDOWN_SEC (기본 60s) 와 일치시켜 try_transition / Event cooldown 두 dedup
# 계층 시간 정렬. 가스 측 동일 변경과 짝. 위험 지속 시 1분 cadence 는 escalation
# 트리거 역할 — 운영자가 1분째 대응 안 하면 같은 알람 재푸시로 인지 유도.
# 추후 1~2주 운영 데이터 후 재평가.
_CACHE_TTL = 60
_AXIS_TTL = 300  # 축별 위험도 캐시 (송신 주기 1초 대비 충분)

# task_key (`alarm:power:task:{device_id}:{channel}`) — WARNING 타이머 진행 신호.
# [Step 5 — TTL 분리] WARNING_DURATION_SEC + 5s 마진. 정상 종료 시 tasks.py 가
# cache.delete 로 즉시 정리. retry/실패는 자연 만료.
_TASK_KEY_TTL = WARNING_DURATION_SEC + 5

# data_type → (평가 함수, 축 이름)
_EVALUATORS = {
    "watt": (evaluate_power_risk, "watt"),
    "current": (evaluate_current_risk, "current"),
    "voltage": (evaluate_voltage_risk, "voltage"),
}

_RISK_ORDER = {
    RiskLevel.NORMAL: 0,
    RiskLevel.WARNING: 1,
    RiskLevel.DANGER: 2,
}


def _state_key(device_id: int, channel: int) -> str:
    """Phase 1 계약 — 변경 금지. 종합 위험도 dedupe 단일 경계."""
    return f"alarm:power:state:{device_id}:{channel}"


def _task_key(device_id: int, channel: int) -> str:
    """WARNING 타이머 Celery task ID 저장 키."""
    return f"alarm:power:task:{device_id}:{channel}"


def _axis_risk_key(device_id: int, channel: int, axis: str) -> str:
    """축(W/A/V)별 마지막 위험도 캐시 키. _state_key와 sibling 네임스페이스."""
    return f"alarm:power:risk:{device_id}:{channel}:{axis}"


def _revoke(task_id: str) -> None:
    """진행 중인 WARNING 타이머 Celery 태스크를 강제 취소한다."""
    from config.celery import app as celery_app

    celery_app.control.revoke(task_id, terminate=True)


def _channel_label(device, channel: int) -> str:
    """PowerDevice.channel_meta[str(ch)]["name"] → 미지정 시 "CH{n}"."""
    meta = (device.channel_meta or {}).get(str(channel)) or {}
    return meta.get("name") or f"CH{channel}"


def _max_risk(levels: list[str]) -> str:
    """[normal, warning, danger] 중 가장 높은 위험도를 반환."""
    return max(levels, key=lambda lv: _RISK_ORDER.get(lv, 0))


def _aggregate_risk(device_id: int, channel: int, axis: str, this_risk: str) -> str:
    """이번 축 위험도를 캐시에 기록하고, 3축 최댓값을 반환."""
    cache.set(_axis_risk_key(device_id, channel, axis), this_risk, _AXIS_TTL)
    keys_by_axis = {
        ax: _axis_risk_key(device_id, channel, ax)
        for ax in ("watt", "current", "voltage")
    }
    cached = cache.get_many(list(keys_by_axis.values()))
    levels = [cached.get(keys_by_axis[ax], RiskLevel.NORMAL) for ax in keys_by_axis]
    return _max_risk(levels)


def trigger_power_alarms(objs: list, device) -> None:
    """
    PowerData 일괄 저장 후 채널별 종합 위험도(W·A·V max)로 알람 라우팅한다.

    PowerDataBulkIngestSerializer.create()에서 호출된다.
    objs[0].data_type에 따라 해당 축만 평가하고, 다른 두 축의 마지막 위험도와 max 산출.
    """
    if not objs:
        return
    axis = objs[0].data_type
    if axis not in _EVALUATORS:
        return  # onoff 등 알람 대상이 아닌 타입

    eval_fn, axis_name = _EVALUATORS[axis]
    device_id = device.id  # PK — try_transition / state_key / fire_*_task 인자
    # AI mute 키는 fastapi 가 IoT raw id (PowerDevice.device_id) 로 set 하므로
    # 가드 read 시도 같은 식별자 사용 필수 (PK 로 read 하면 키 mismatch → 중복 발화).
    device_iot_id = device.device_id
    facility_id = device.facility_id

    for obj in objs:
        channel = obj.channel
        value = obj.value

        # 통신 불능 채널은 알람 판정 제외 (해당 축은 캐시 미갱신 → 다른 축에 영향 없음)
        if value is None:
            continue

        this_risk = eval_fn(value, channel=channel, device_id=device_id)
        aggregate = _aggregate_risk(device_id, channel, axis_name, this_risk)

        state_key = _state_key(device_id, channel)
        task_key = _task_key(device_id, channel)
        label = _channel_label(device, channel)

        if aggregate == RiskLevel.DANGER:
            # 진행 중인 WARNING 타이머가 있으면 먼저 취소 — AI mute 가드 이전에 수행.
            # 그렇지 않으면 AI mute 가 활성일 때 룰 fire 만 suppress 되고 stale WARNING
            # 타이머가 카운트다운 끝나면 발화해 화면에 룰 알람이 등장 (AI 1순위 위반).
            pending = cache.get(task_key)
            if pending:
                _revoke(pending)
                cache.delete(task_key)

            # [Step 3] AI 가 같은 채널에 최근 발화한 경우 룰 fire 를 60s suppress.
            # 격상 (AI=warning, 룰=danger) 은 danger 키 부재로 자연 통과.
            # device_iot_id 사용 — fastapi 마킹 키와 식별자 일치 (PK 쓰면 mismatch).
            if is_ai_mute_active(device_iot_id, channel, RiskLevel.DANGER):
                RULE_FIRE_SUPPRESSED_BY_AI_TOTAL.labels(
                    device_id=str(device_iot_id),
                    channel=str(channel),
                    level=RiskLevel.DANGER.value,
                ).inc()
                continue

            # 원자 천이 — 직전 상태가 danger 아닐 때만 1회 fire (race-safe)
            if try_transition(state_key, RiskLevel.DANGER, _CACHE_TTL):
                fire_power_danger_task.delay(
                    device_id, channel, value, facility_id, label
                )

        elif aggregate == RiskLevel.WARNING:
            prev_state = get_state(state_key)
            if prev_state in (RiskLevel.WARNING, RiskLevel.DANGER):
                continue
            # [Step 3] AI mute 가드. WARNING 의 경우 AI 가 같은 또는 더 높은 레벨로
            # 발화했으면 룰 fire suppress (단계 일치 또는 격상 케이스). 격상은 AI 가
            # 더 높은 키 set → 모두 부재 → 통과 (방향 반대라 fire 진행 정상).
            # device_iot_id — fastapi 마킹 키 식별자와 일치.
            if is_ai_mute_active(device_iot_id, channel, RiskLevel.WARNING):
                RULE_FIRE_SUPPRESSED_BY_AI_TOTAL.labels(
                    device_id=str(device_iot_id),
                    channel=str(channel),
                    level=RiskLevel.WARNING.value,
                ).inc()
                continue
            # SETNX(cache.add)로 첫 도착자만 타이머 시작 — race 차단.
            # TTL 은 _TASK_KEY_TTL (카운트다운 + 5s) — 정상 종료 시 tasks.py 가
            # cache.delete 로 즉시 정리하고, retry/실패는 자연 만료로 정리된다.
            if not cache.add(task_key, "_pending_", _TASK_KEY_TTL):
                continue
            task = fire_power_warning_task.apply_async(
                args=[device_id, channel, value, facility_id, label],
                countdown=WARNING_DURATION_SEC,
            )
            cache.set(task_key, task.id, _TASK_KEY_TTL)
            try_transition(state_key, RiskLevel.WARNING, _CACHE_TTL)

        else:  # normal
            # WARNING 타이머가 있으면 취소하고 이전 경보 시 정상화 알림 발송
            pending = cache.get(task_key)
            if pending:
                _revoke(pending)
                cache.delete(task_key)
            if get_state(state_key) in (RiskLevel.WARNING, RiskLevel.DANGER):
                fire_power_clear_task.delay(device_id, channel, label)
                clear_state(state_key)
