"""AlarmPayload + AnomalyMeta nested schema validation 테스트."""

import pytest
from pydantic import ValidationError

from internal.routers.alarm_router import AlarmPayload, AnomalyMeta


def _base_payload():
    return {
        "alarm_type": "anomaly",
        "risk_level": "warning",
        "source_label": "ch1",
        "summary": "test",
        "is_new_event": True,
    }


def test_alarm_payload_without_anomaly_meta_ok():
    """다른 alarm_type (예: gas_threshold) 은 anomaly_meta 없어도 통과."""
    p = AlarmPayload(**_base_payload())
    assert p.anomaly_meta is None


def test_alarm_payload_with_anomaly_meta_ok():
    p = AlarmPayload(
        **_base_payload(),
        anomaly_meta={
            "combined_risk": "predict_warn",
            "anomaly_score": -0.0292,
            "device_id": "63200c3afd12",
            "channel": 1,
            "data_type": "watt",
        },
    )
    assert p.anomaly_meta is not None
    assert p.anomaly_meta.combined_risk == "predict_warn"
    assert p.anomaly_meta.anomaly_score == -0.0292
    assert p.anomaly_meta.channel == 1


def test_anomaly_meta_required_fields_missing():
    """combined_risk / anomaly_score 는 필수."""
    with pytest.raises(ValidationError) as exc:
        AnomalyMeta(combined_risk="predict_warn")  # anomaly_score 누락
    assert "anomaly_score" in str(exc.value)


def test_anomaly_meta_optional_fields_default_none():
    """device_id/channel/data_type 은 선택 — 없어도 OK."""
    m = AnomalyMeta(combined_risk="predict_warn", anomaly_score=-0.05)
    assert m.device_id is None
    assert m.channel is None
    assert m.data_type is None


def test_alarm_payload_extra_fields_ignored():
    """기존 extra=ignore 정책 유지 — 모르는 필드 통과."""
    p = AlarmPayload(**_base_payload(), unknown_field="should_be_ignored")
    assert not hasattr(p, "unknown_field")
