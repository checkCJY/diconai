"""AI 발화 시 룰 60s mute 가드 단위 테스트 (Step 3).

[검증 대상]
- mark_ai_recent → is_ai_mute_active 흐름 (같은 level 키 set 후 가드 True)
- 격상 bypass — AI=warning 발화 시 룰=danger 가드는 False (자유 통과)
- ttl_sec 인자화 — 짧게 (0.5s) 줘서 만료 후 False 검증
- power_alarm.trigger_power_alarms 통합 — AI mute 상태에서 룰 fire skip + counter +1

[설계 결정]
raw redis (`_redis()`) 패턴 사용. Django cache.get 의 pickle 직렬화 우회 — try_
transition 과 동일 패턴이라 fastapi 가 set 한 키도 그대로 read 가능.

[counter 검증]
RULE_FIRE_SUPPRESSED_BY_AI_TOTAL 의 특정 label 조합 값 변화로 검증. labels(...)._value.get()
로 직접 비교.
"""

import time
from unittest.mock import patch

import pytest
from django.core.cache import cache

from apps.alerts.services.alarm_dedupe import (
    AI_MUTE_TTL_SEC,
    is_ai_mute_active,
    mark_ai_recent,
)
from apps.core.constants import RiskLevel
from apps.core.metrics import RULE_FIRE_SUPPRESSED_BY_AI_TOTAL


@pytest.fixture(autouse=True)
def clear_cache():
    """각 테스트 전후 Redis 캐시 비우기 — ai_fired 키 잔류 방지."""
    cache.clear()
    yield
    cache.clear()


def test_mark_recent_then_is_active_returns_true():
    """warning 마킹 → 같은 level 가드 True."""
    mark_ai_recent(device_id=1, channel=1, rule_level="warning")
    assert is_ai_mute_active(1, 1, "warning") is True


def test_mark_recent_below_level_also_set():
    """warning 마킹 → 'normal' 키도 함께 set (이하 level 모두)."""
    mark_ai_recent(device_id=1, channel=1, rule_level="warning")
    assert is_ai_mute_active(1, 1, "normal") is True
    assert is_ai_mute_active(1, 1, "warning") is True


def test_escalation_bypass_warning_mark_does_not_block_danger():
    """격상 bypass — AI 가 warning 만 mark 했으면 룰 danger 는 통과 (False)."""
    mark_ai_recent(device_id=1, channel=1, rule_level="warning")
    # danger 키는 set 안 됨 → 가드 False → 룰 danger fire 진행
    assert is_ai_mute_active(1, 1, "danger") is False


def test_danger_mark_blocks_all_lower_levels():
    """AI=danger 마킹 → warning/danger 모두 가드 True (강제 suppress)."""
    mark_ai_recent(device_id=1, channel=1, rule_level="danger")
    assert is_ai_mute_active(1, 1, "warning") is True
    assert is_ai_mute_active(1, 1, "danger") is True


def test_different_device_or_channel_isolated():
    """다른 device / 다른 channel 은 mute 격리 — 각 (device, channel) 별 독립 키."""
    mark_ai_recent(device_id=1, channel=1, rule_level="warning")
    assert is_ai_mute_active(2, 1, "warning") is False  # 다른 device
    assert is_ai_mute_active(1, 2, "warning") is False  # 다른 channel


def test_ttl_expiry_releases_mute():
    """ttl_sec 만료 후 자동 해제 — 0.5s 인자화."""
    mark_ai_recent(device_id=1, channel=1, rule_level="warning", ttl_sec=1)
    assert is_ai_mute_active(1, 1, "warning") is True
    time.sleep(1.1)
    assert is_ai_mute_active(1, 1, "warning") is False


def test_default_ttl_matches_module_constant():
    """기본 TTL = AI_MUTE_TTL_SEC (60s, RATE_LIMIT_SEC 와 일치)."""
    assert AI_MUTE_TTL_SEC == 60


@pytest.mark.django_db
def test_power_alarm_rule_fire_skipped_when_ai_mute_active(power_device):
    """power_alarm.trigger_power_alarms — AI mute 활성 시 룰 DANGER fire skip + counter."""
    from apps.monitoring.models import PowerData
    from apps.monitoring.services.power_alarm import trigger_power_alarms

    device_id = power_device.id
    channel = 1
    # AI 가 danger 마크 한 상태로 가정 (실제 운영에선 fastapi 가 마킹)
    mark_ai_recent(device_id=device_id, channel=channel, rule_level="danger")

    # 룰 fire 가 skip 되었는지 카운터로 검증 — label 조합 매칭
    counter_metric = RULE_FIRE_SUPPRESSED_BY_AI_TOTAL.labels(
        device_id=str(device_id),
        channel=str(channel),
        level=RiskLevel.DANGER.value,
    )
    before = counter_metric._value.get()

    # 가짜 PowerData 객체 (DB 저장 없이 list 전달)
    obj = PowerData(
        power_device=power_device,
        channel=channel,
        data_type="watt",
        value=999999.0,  # danger 임계치 이상
        sensor_status="active",
        risk_level=RiskLevel.NORMAL,
    )
    # fire_power_danger_task.delay 가 호출되지 않아야 함 (mute 가드로 skip)
    with patch(
        "apps.monitoring.services.power_alarm.fire_power_danger_task"
    ) as mock_danger:
        trigger_power_alarms([obj], power_device)

    mock_danger.delay.assert_not_called()
    assert counter_metric._value.get() - before == 1


@pytest.mark.django_db
def test_power_alarm_rule_fire_proceeds_when_ai_not_muted(power_device):
    """AI mute 없으면 룰 DANGER 정상 fire — 가드가 정상 통과."""
    from apps.monitoring.models import PowerData
    from apps.monitoring.services.power_alarm import trigger_power_alarms

    # mark_ai_recent 호출 안 함 → mute 없음
    obj = PowerData(
        power_device=power_device,
        channel=2,
        data_type="watt",
        value=999999.0,
        sensor_status="active",
        risk_level=RiskLevel.NORMAL,
    )

    with patch(
        "apps.monitoring.services.power_alarm.fire_power_danger_task"
    ) as mock_danger:
        trigger_power_alarms([obj], power_device)

    # mute 없으니 정상 fire
    mock_danger.delay.assert_called_once()


@pytest.mark.django_db
def test_power_alarm_revokes_pending_warning_before_ai_mute_skip(power_device):
    """회귀 가드 — DANGER 분기에서 AI mute 활성이어도 pending WARNING task 는 revoke.

    회귀 시나리오 (코드 리뷰 §2):
    1. WARNING 타이머 진행 중 (task_key 에 task.id 저장됨)
    2. 같은 채널에 AI DANGER 발화 → mute 키 set
    3. 다음 데이터 도착, aggregate=DANGER → mute 가드 → continue
    4. 만약 pending revoke 안 하면 stale WARNING 타이머가 3s 후 발화 → AI 1순위 위반

    본 테스트는 가드 적용 후 룰 fire 는 skip 되지만 pending revoke 와 cache.delete
    가 수행되는지 검증.
    """
    from apps.monitoring.models import PowerData
    from apps.monitoring.services.power_alarm import (
        _task_key,
        trigger_power_alarms,
    )

    device_id = power_device.id
    channel = 3

    # WARNING 타이머가 진행 중인 상황 시뮬레이션 — task_key 에 fake task ID set
    task_key = _task_key(device_id, channel)
    cache.set(task_key, "fake-pending-task-id-xyz", 30)

    # AI 가 같은 채널에 DANGER 발화 → mute 활성
    mark_ai_recent(device_id=device_id, channel=channel, rule_level="danger")

    obj = PowerData(
        power_device=power_device,
        channel=channel,
        data_type="watt",
        value=999999.0,
        sensor_status="active",
        risk_level=RiskLevel.NORMAL,
    )

    with patch(
        "apps.monitoring.services.power_alarm.fire_power_danger_task"
    ) as mock_danger, patch(
        "apps.monitoring.services.power_alarm._revoke"
    ) as mock_revoke:
        trigger_power_alarms([obj], power_device)

    # 룰 fire 는 mute 로 skip
    mock_danger.delay.assert_not_called()
    # 핵심: pending WARNING task 가 revoke 되었고 task_key 도 정리됨
    mock_revoke.assert_called_once_with("fake-pending-task-id-xyz")
    assert cache.get(task_key) is None
