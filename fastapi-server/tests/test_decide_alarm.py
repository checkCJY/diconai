"""T4 D2 — decide_alarm 6 매트릭스 분기 + evaluate_static_risk_from_cache 검증.

[검증 대상]
- decide_alarm — 6 매트릭스 분기 + fail-safe (ai_state=None)
- evaluate_static_risk_from_cache — sync 캐시 read + 정격 % 환산 + fail-safe

[설계]
decide_alarm 은 순수 함수 — I/O mock 불요. 입력 (state, combined, static) 만 변경.
evaluate_static_risk_from_cache 는 threshold_sync 모듈 캐시·channel_meta_cache 패치.
"""

from unittest.mock import patch

from power.services.decide_alarm import AlarmDecision, decide_alarm
from power.services.threshold_eval import evaluate_static_risk_from_cache
from services.ai_mute import AIInferenceState


# ── decide_alarm 매트릭스 분기 ─────────────────────────────────────────────


def test_fired_ai_returns_ai_source_warning():
    """FIRED + caution → source=ai, risk_level=warning (combined→3단계 매핑)."""
    result = decide_alarm(
        AIInferenceState.FIRED, ai_combined_risk="caution", static_risk="normal"
    )
    assert isinstance(result, AlarmDecision)
    assert result.source == "ai"
    assert result.alarm_type == "power_anomaly_ai"
    assert result.risk_level == "warning"
    assert result.reason is None


def test_fired_ai_returns_ai_source_danger():
    """FIRED + danger → risk_level=danger. 정적 결과는 무시 (AI 단독 결정)."""
    result = decide_alarm(
        AIInferenceState.FIRED, ai_combined_risk="danger", static_risk="warning"
    )
    assert result.source == "ai"
    assert result.risk_level == "danger"


def test_fired_ai_with_predict_warn_maps_to_warning():
    """combined='predict_warn' → risk_level='warning' (UI 3단계 한계 매핑)."""
    result = decide_alarm(
        AIInferenceState.FIRED, ai_combined_risk="predict_warn", static_risk="normal"
    )
    assert result.risk_level == "warning"


def test_inferred_normal_and_static_fired_returns_miss():
    """AI 정상 + 정적 발화 → static_cover_miss (AI 미탐 의심)."""
    result = decide_alarm(
        AIInferenceState.INFERRED_NORMAL,
        ai_combined_risk="normal",
        static_risk="warning",
    )
    assert result.source == "static_cover_miss"
    assert result.alarm_type == "power_overload"
    assert result.risk_level == "warning"
    assert result.reason == "AI 미탐 의심 — 정적 임계치 초과"


def test_inferred_normal_and_static_normal_returns_none():
    """AI 정상 + 정적 정상 → 알람 없음 (가장 흔한 케이스)."""
    result = decide_alarm(
        AIInferenceState.INFERRED_NORMAL,
        ai_combined_risk="normal",
        static_risk="normal",
    )
    assert result is None


def test_inferred_failed_and_static_fired_returns_inference_fail():
    """AI 추론 실패 + 정적 발화 → static_cover_inference_fail."""
    result = decide_alarm(
        AIInferenceState.INFERRED_FAILED,
        ai_combined_risk="normal",
        static_risk="danger",
    )
    assert result.source == "static_cover_inference_fail"
    assert result.risk_level == "danger"
    assert result.reason == "AI 추론 실패 보완"


def test_disabled_and_static_fired_returns_no_ai_available():
    """AI 비활성 채널 + 정적 발화 → static_no_ai_available (일반 룰)."""
    result = decide_alarm(
        AIInferenceState.DISABLED, ai_combined_risk="normal", static_risk="warning"
    )
    assert result.source == "static_no_ai_available"
    assert result.reason is None  # 일반 룰 알람 — 별도 사유 없음


def test_warming_up_and_static_fired_returns_warmup():
    """AI 워밍업 + 정적 발화 → static_cover_warmup (safety net)."""
    result = decide_alarm(
        AIInferenceState.WARMING_UP, ai_combined_risk="normal", static_risk="danger"
    )
    assert result.source == "static_cover_warmup"
    assert result.reason == "AI 윈도우 빌드 중 — 정적룰 보완"


def test_ai_state_none_with_static_fired_falls_back_to_no_ai_available():
    """ai_state=None (Redis 장애·만료) → DISABLED 동등 fail-safe 분기."""
    result = decide_alarm(
        ai_state=None, ai_combined_risk="normal", static_risk="warning"
    )
    assert result.source == "static_no_ai_available"
    assert result.alarm_type == "power_overload"


def test_ai_state_none_with_static_normal_returns_none():
    """ai_state=None + 정적 정상 → 알람 없음 (fail-safe 측 보수)."""
    result = decide_alarm(
        ai_state=None, ai_combined_risk="normal", static_risk="normal"
    )
    assert result is None


# ── evaluate_static_risk_from_cache — sync 캐시 기반 정적 평가 ──────────────


def test_evaluate_static_returns_normal_when_value_none():
    """value None — fail-safe normal."""
    assert evaluate_static_risk_from_cache(None, "watt", "dev_1", 1) == "normal"


def test_evaluate_static_returns_normal_when_data_type_unknown():
    """data_type 미인식 (예: 'humidity') — fail-safe normal."""
    assert evaluate_static_risk_from_cache(100.0, "humidity", "dev_1", 1) == "normal"


def test_evaluate_static_returns_normal_when_cache_empty():
    """threshold_sync 캐시 미존재 — fail-safe normal."""
    with patch("power.services.threshold_eval.get_threshold_meta", return_value={}):
        assert evaluate_static_risk_from_cache(900.0, "watt", "dev_1", 1) == "normal"


def test_evaluate_static_returns_normal_when_rated_missing():
    """channel_meta 의 rated_w 없음 — fail-safe normal."""
    cache_meta = {"warning_max": 80.0, "danger_max": 100.0, "unit": "%"}
    with (
        patch(
            "power.services.threshold_eval.get_threshold_meta", return_value=cache_meta
        ),
        patch("power.services.threshold_eval.get_channel_entry", return_value={}),
    ):
        assert evaluate_static_risk_from_cache(900.0, "watt", "dev_1", 1) == "normal"


def test_evaluate_static_watt_warning_at_80pct():
    """watt 정격 1000W, 측정 850W (85%) → warning (80%≤ <100%)."""
    cache_meta = {"warning_max": 80.0, "danger_max": 100.0, "unit": "%"}
    with (
        patch(
            "power.services.threshold_eval.get_threshold_meta", return_value=cache_meta
        ),
        patch(
            "power.services.threshold_eval.get_channel_entry",
            return_value={"rated_w": 1000},
        ),
    ):
        assert evaluate_static_risk_from_cache(850.0, "watt", "dev_1", 1) == "warning"


def test_evaluate_static_watt_danger_at_100pct():
    """watt 측정 1100W (110%) → danger."""
    cache_meta = {"warning_max": 80.0, "danger_max": 100.0, "unit": "%"}
    with (
        patch(
            "power.services.threshold_eval.get_threshold_meta", return_value=cache_meta
        ),
        patch(
            "power.services.threshold_eval.get_channel_entry",
            return_value={"rated_w": 1000},
        ),
    ):
        assert evaluate_static_risk_from_cache(1100.0, "watt", "dev_1", 1) == "danger"


def test_evaluate_static_voltage_bidirectional_low():
    """voltage 정격 220V, 측정 198V (90%) → danger (양방향 — danger_min)."""
    cache_meta = {
        "warning_min": 95.0,
        "warning_max": 105.0,
        "danger_min": 90.0,
        "danger_max": 110.0,
        "unit": "%",
    }
    with (
        patch(
            "power.services.threshold_eval.get_threshold_meta", return_value=cache_meta
        ),
        patch(
            "power.services.threshold_eval.get_channel_entry",
            return_value={"rated_v": 220},
        ),
    ):
        assert evaluate_static_risk_from_cache(198.0, "voltage", "dev_1", 1) == "danger"


def test_evaluate_static_voltage_normal_inside_range():
    """voltage 측정 218V (99%) → normal (warning_min·max 안)."""
    cache_meta = {
        "warning_min": 95.0,
        "warning_max": 105.0,
        "danger_min": 90.0,
        "danger_max": 110.0,
        "unit": "%",
    }
    with (
        patch(
            "power.services.threshold_eval.get_threshold_meta", return_value=cache_meta
        ),
        patch(
            "power.services.threshold_eval.get_channel_entry",
            return_value={"rated_v": 220},
        ),
    ):
        assert evaluate_static_risk_from_cache(218.0, "voltage", "dev_1", 1) == "normal"


def test_evaluate_static_unidirectional_missing_threshold_returns_normal():
    """단방향 watt — warning_max 또는 danger_max None 이면 fail-safe normal."""
    cache_meta = {"warning_max": None, "danger_max": 100.0, "unit": "%"}
    with (
        patch(
            "power.services.threshold_eval.get_threshold_meta", return_value=cache_meta
        ),
        patch(
            "power.services.threshold_eval.get_channel_entry",
            return_value={"rated_w": 1000},
        ),
    ):
        assert evaluate_static_risk_from_cache(900.0, "watt", "dev_1", 1) == "normal"
