"""AlarmRecord short message — drift 가드 단위 테스트.

[목적]
`AlarmRecord.get_short_message()` 는 이벤트 패널·WS push payload 의 한 줄 message
single source of truth. DRF `AlarmRecordSerializer.get_message` 와 Celery
`_push_to_ws` 양쪽이 본 메서드를 호출하므로 같은 AlarmRecord 에 대해 API 응답과
실시간 push 가 같은 텍스트를 노출해야 한다.

[자명 통과 의도]
serializer.get_message 가 `obj.get_short_message()` 한 줄 위임이라 본 테스트는
"자명하게 통과" 한다. 그 자명함 자체가 미래에 누군가 serializer 안 분기를
재분산 (drift) 하지 못하게 막는 가드 — fail 시 의도 위반의 명확한 신호.

[DB 미사용]
unsaved AlarmRecord 인스턴스로 직접 메서드 호출만 검증. FK 접근 안 함.
"""

import pytest

from apps.alerts.models import AlarmRecord
from apps.alerts.serializers import AlarmRecordSerializer


@pytest.mark.parametrize(
    "kwargs,expected",
    [
        (
            {
                "alarm_type": "gas_threshold",
                "gas_type": "co",
                "measured_value": 200.0,
            },
            "CO 임계치 초과 (200.0 ppm)",
        ),
        (
            {
                "alarm_type": "power_overload",
                "power_device_id": 1,
                "measured_value": 15.8,
            },
            "임계치 초과 (15.8 W)",
        ),
        (
            {
                "alarm_type": "power_anomaly_ai",
                "power_device_id": 1,
                "measured_value": 7768.8,
                "algorithm_source": "isolation_forest",
            },
            "이상 수치 탐지 (7,768.8 W)",
        ),
        (
            {
                "alarm_type": "power_anomaly_ai",
                "power_device_id": 1,
                "measured_value": 820.5,
                "algorithm_source": "arima",
            },
            "이상 패턴 탐지 (820.5 W)",
        ),
        (
            {
                "alarm_type": "power_anomaly_ai",
                "power_device_id": 1,
                "measured_value": 12500.0,
                "algorithm_source": "combined",
            },
            "이상 수치·패턴 동시 탐지 (12,500.0 W)",
        ),
        (
            {
                "alarm_type": "power_anomaly_ai",
                "power_device_id": 1,
                "measured_value": 3611.3,
                "algorithm_source": "zscore",
            },
            "통계 이상 수치 (3,611.3 W)",
        ),
        (
            {
                "alarm_type": "power_anomaly_ai",
                "power_device_id": 1,
                "measured_value": 500.0,
                "algorithm_source": "change_point",
            },
            "패턴 변화 탐지 (500.0 W)",
        ),
        (
            {
                "alarm_type": "power_anomaly_ai",
                "power_device_id": 1,
                "measured_value": 350.2,
                "algorithm_source": "night_abnormal",
            },
            "야간 이상 가동 (350.2 W)",
        ),
        (
            {
                "alarm_type": "power_anomaly_ai",
                "power_device_id": 1,
                "measured_value": 100.0,
            },
            "AI 이상 탐지 (100.0 W)",
        ),
        ({"alarm_type": "geofence_intrusion", "geofence_id": 1}, "위험구역 진입"),
        ({"alarm_type": "sensor_fault"}, "센서 통신 이상"),
        ({"alarm_type": "gas_clear"}, "정상 복귀"),
        ({"alarm_type": "power_clear"}, "정상 복귀"),
    ],
)
def test_get_short_message_returns_expected(kwargs, expected):
    """모델 메서드 단위 — alarm_type 별 짧은 메시지 패턴 검증."""
    alarm = AlarmRecord(risk_level="danger", **kwargs)
    assert alarm.get_short_message() == expected


@pytest.mark.parametrize(
    "kwargs",
    [
        {
            "alarm_type": "gas_threshold",
            "gas_type": "co",
            "measured_value": 200.0,
        },
        {
            "alarm_type": "power_overload",
            "power_device_id": 1,
            "measured_value": 15.8,
        },
        {"alarm_type": "geofence_intrusion", "geofence_id": 1},
        {"alarm_type": "sensor_fault"},
        {"alarm_type": "gas_clear"},
        {"alarm_type": "power_clear"},
    ],
)
def test_api_serializer_message_matches_model_method(kwargs):
    """drift 가드 — DRF serializer.get_message 가 모델 메서드 결과와 일치.

    serializer 가 `obj.get_short_message()` 를 직접 호출하는 한 자명 통과.
    분기를 serializer 로 다시 흩뿌리는 변경이 들어오면 본 테스트가 깨져 의도 위반을
    PR 단계에서 잡는다.
    """
    alarm = AlarmRecord(risk_level="danger", **kwargs)
    serializer = AlarmRecordSerializer()
    # .data 접근 시 다른 SerializerMethodField (sensor_name 등) 가 FK lazy load 를
    # 시도할 수 있어 unsaved 인스턴스로는 위험. message 단일 메서드만 호출 검증.
    api_message = serializer.get_message(alarm)
    model_message = alarm.get_short_message()
    assert api_message == model_message
