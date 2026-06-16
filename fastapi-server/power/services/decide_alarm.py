# power/services/decide_alarm.py — fastapi 단일 정책 결정
#
# AI 추론 5 state + 정적 평가 결과 → source 6 매트릭스 분기 → AlarmDecision.
# 호출자 (power_service.process_anomaly_inference) 가 본 결정을 받아 push_payload
# 조립 + push_alarm 직접 호출.
#
# [순수 함수]
# decide_alarm 은 I/O 없는 분기 로직만 — AI state·정적 risk 결과를 인자로 받음.
# get_ai_state / evaluate_static_risk_from_cache 호출은 호출자 책임 — 분기 로직
# 격리 → 단위 테스트 단순화 (mock 불요).

from dataclasses import dataclass

from core.constants import ALARM_SOURCE_REASON
from services.ai_mute import AIInferenceState


@dataclass
class AlarmDecision:
    """decide_alarm 출력 — 호출자가 push_payload 조립에 사용.

    Attributes:
        source: AlarmSource 6종 중 하나 — `ai` / `static_cover_miss` /
            `static_cover_inference_fail` / `static_cover_warmup` /
            `static_no_ai_available` / `static_legacy` (DRF fallback, 본 경로 미사용).
        alarm_type: `power_anomaly_ai` (source=ai) 또는 `power_overload` (그 외).
        risk_level: `warning` | `danger` — UI 색상·prefix 분기.
        reason: ALARM_SOURCE_REASON[source] — push_payload.reason 그대로 동봉.
    """

    source: str
    alarm_type: str
    risk_level: str
    reason: str | None


def _ai_combined_to_risk_level(combined: str) -> str:
    """AI 5단계 → UI 3단계 RiskLevel 매핑 (RiskLevel 3단계 한계로 합침).

    combine_risk_5axis 출력 도메인:
        normal / caution / predict_warn / warning / danger
    "warning" 누락 시 silent fallback "normal" → 시연 알람 미발화 회귀.
    """
    return {
        "normal": "normal",
        "caution": "warning",
        "predict_warn": "warning",
        "warning": "warning",
        "danger": "danger",
    }.get(combined, "normal")


def _static_to_risk_level(static_risk: str) -> str:
    """정적 결과 → RiskLevel (이미 'normal'|'warning'|'danger' 형식)."""
    return static_risk if static_risk in ("warning", "danger") else "normal"


def decide_alarm(
    ai_state: AIInferenceState | None,
    ai_combined_risk: str,
    static_risk: str,
) -> AlarmDecision | None:
    """AI 상태 × 정적 결과 6 매트릭스로 알람 source 를 분기한다.

    | AI 상태             | 정적 결과   | source                          |
    |---------------------|------------|---------------------------------|
    | FIRED               | *          | ai                              |
    | INFERRED_NORMAL     | fired      | static_cover_miss               |
    | INFERRED_FAILED     | fired      | static_cover_inference_fail     |
    | DISABLED            | fired      | static_no_ai_available          |
    | WARMING_UP          | fired      | static_cover_warmup             |
    | None (장애·만료)    | fired      | static_no_ai_available (fail-safe) |
    | *                   | not fired  | None (알람 없음)                 |

    Args:
        ai_state: get_ai_state 결과. None 은 Redis 장애·만료 — DISABLED 동등 분기.
        ai_combined_risk: combine_risk_5axis 결과 ('normal' / 'caution' /
            'predict_warn' / 'warning' / 'danger'). FIRED 일 때 risk_level 환산용.
        static_risk: evaluate_static_risk_from_cache 결과
            ('normal' / 'warning' / 'danger'). 'warning'|'danger' = fired.

    Returns:
        AlarmDecision (발화 결정) 또는 None (알람 없음).
    """
    static_fired = static_risk in ("warning", "danger")

    if ai_state == AIInferenceState.FIRED:
        return AlarmDecision(
            source="ai",
            alarm_type="power_anomaly_ai",
            risk_level=_ai_combined_to_risk_level(ai_combined_risk),
            reason=ALARM_SOURCE_REASON["ai"],
        )

    # 이하 분기는 모두 정적 fired 가 전제 — not fired 면 알람 없음.
    if not static_fired:
        return None

    if ai_state == AIInferenceState.INFERRED_NORMAL:
        source = "static_cover_miss"
    elif ai_state == AIInferenceState.INFERRED_FAILED:
        source = "static_cover_inference_fail"
    elif ai_state == AIInferenceState.WARMING_UP:
        source = "static_cover_warmup"
    elif ai_state == AIInferenceState.DISABLED:
        source = "static_no_ai_available"
    else:
        # None (Redis 장애·만료) — DISABLED 동등 fail-safe 분기.
        # 정적이 fired 라 알람은 띄우되 source 는 "AI 미지" 의미로 분류.
        source = "static_no_ai_available"

    return AlarmDecision(
        source=source,
        alarm_type="power_overload",
        risk_level=_static_to_risk_level(static_risk),
        reason=ALARM_SOURCE_REASON[source],
    )
