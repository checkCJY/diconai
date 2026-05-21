# power/services/night_escalation.py — KST 야간 가동 격상 게이트
#
# 데이터 흐름:
#   IN  : measured_at ISO 8601 문자열 (anomaly_inference 가 호출)
#   OUT : 야간 시간대 여부 bool + 격상 매핑 dict (_NIGHT_ESCALATION)
#
# 운영 의도: 야간 + 정격 30% 초과 시 combined_risk 한 단계 격상.
#   SARIMA seasonal 학습 전 휴리스틱 보강 — 야간 비정상 가동 검출.
from datetime import datetime, timezone

_KST_OFFSET_HOURS = 9
_NIGHT_GATE_KST = (22, 5)  # 22:00 시작, 05:00 미만 (자정 넘어가는 wrap)
_NIGHT_THRESHOLD_RATIO = 0.30  # 정격의 30% 초과 시 격상 (휴리스틱)

# 야간 격상 매핑 — danger / warning 은 이미 최상위라 격상 대상 아님.
_NIGHT_ESCALATION = {
    "normal": "caution",
    "caution": "warning",
    "predict_warn": "warning",
}


def _is_night_kst_iso(measured_at_iso: str) -> bool:
    """measured_at 의 KST hour 가 야간 시간대(22:00~05:00)에 속하는지 판정.

    naive datetime 은 UTC 로 간주. 파싱 실패 시 False (안전 fallback —
    야간 격상 미적용).
    """
    try:
        dt = datetime.fromisoformat(measured_at_iso)
    except (ValueError, TypeError):
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    utc_hour = dt.astimezone(timezone.utc).hour
    kst_hour = (utc_hour + _KST_OFFSET_HOURS) % 24
    start, end = _NIGHT_GATE_KST
    if start <= end:
        return start <= kst_hour < end
    return kst_hour >= start or kst_hour < end
