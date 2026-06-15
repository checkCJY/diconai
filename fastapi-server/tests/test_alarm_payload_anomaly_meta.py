"""AlarmPayload + AnomalyMeta nested schema validation 테스트."""

import pytest
from pydantic import ValidationError

from internal.routers.alarm_router import AlarmPayload, AnomalyMeta


def _base_payload():
    return {
        "alarm_type": "power_anomaly_ai",
        "risk_level": "warning",
        "source_label": "ch1",
        "summary": "test",
        "is_new_event": True,
    }


def test_alarm_payload_without_anomaly_meta_ok():
    """다른 alarm_type (예: gas_threshold) 은 anomaly_meta 없어도 통과."""
    p = AlarmPayload(**_base_payload())
    assert p.anomaly_meta is None


# T4 D3 — source / reason 필드 검증.


def test_alarm_payload_source_reason_default_none():
    """source / reason 미지정 시 None — 옛 발신자 호환."""
    p = AlarmPayload(**_base_payload())
    assert p.source is None
    assert p.reason is None


def test_alarm_payload_accepts_source_reason():
    """T4 신규 — source / reason 명시 지정 통과."""
    p = AlarmPayload(
        **_base_payload(),
        source="static_cover_miss",
        reason="AI 미탐 의심 — 정적 임계치 초과",
    )
    assert p.source == "static_cover_miss"
    assert p.reason == "AI 미탐 의심 — 정적 임계치 초과"


def test_alarm_payload_silent_drops_unknown_key():
    """extra=ignore — 미정의 키 통과하되 모델에 안 들어감."""
    p = AlarmPayload(**_base_payload(), surprise_field="dropped")
    # 알 수 없는 키는 무시됨 (T3 silent drop 패턴 — push_alarm_handler 에서 WARN 로깅)
    assert not hasattr(p, "surprise_field")


def test_alarm_payload_with_anomaly_meta_ok():
    """anomaly_meta nested dict 가 AnomalyMeta 로 파싱·필드 보존."""
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
