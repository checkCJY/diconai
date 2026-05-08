# facilities/services/threshold_service.py
"""
Threshold DB 조회 + Redis 캐시 (Phase 4-d).

[단일 진실 공급원]
이전: core/constants.py POWER_THRESHOLDS + facilities LEGAL_THRESHOLDS 상수
이후: facilities.Threshold DB 모델 + Redis 캐시 (group_code, item) 키.

[캐시 정책]
- 키: f"threshold:{group_code}:{item}"
- TTL: 1시간 (Threshold 변경 잦지 않음)
- invalidate: Threshold post_save / post_delete signal에서 cache.delete()

[fallback]
DB에 Threshold가 없으면 RiskLevel.NORMAL 반환 (graceful degradation).
운영자가 시드를 누락한 케이스 보호.
"""

from decimal import Decimal

from django.core.cache import cache

from apps.core.constants import RiskLevel

_CACHE_PREFIX = "threshold"
_CACHE_TTL = 3600  # 1시간


def _cache_key(group_code: str, item: str) -> str:
    return f"{_CACHE_PREFIX}:{group_code}:{item}"


def get_threshold(group_code: str, item: str) -> dict | None:
    """
    Threshold DB 조회 + Redis 캐시.

    반환 형식:
        {
            "warning_min": Decimal | None,
            "warning_max": Decimal | None,
            "danger_min":  Decimal | None,
            "danger_max":  Decimal | None,
            "chart_max":   Decimal | None,
            "unit": str,
        }
    또는 미존재 시 None.
    """
    key = _cache_key(group_code, item)
    cached = cache.get(key)
    if cached is not None:
        return cached

    from apps.facilities.models import Threshold

    threshold = (
        Threshold.objects.filter(
            group__code=group_code, measurement_item=item, is_active=True
        )
        .select_related("group")
        .first()
    )
    if threshold is None:
        return None

    payload = {
        "warning_min": threshold.warning_min,
        "warning_max": threshold.warning_max,
        "danger_min": threshold.danger_min,
        "danger_max": threshold.danger_max,
        "chart_max": threshold.chart_max,
        "unit": threshold.unit,
    }
    cache.set(key, payload, _CACHE_TTL)
    return payload


def evaluate_gas_risk(gas: str, value: float | None) -> str:
    """
    가스 측정값 → RiskLevel 문자열.

    [정책]
    - O2는 낮을수록 위험: warning_min/danger_min 사용
    - 그 외는 높을수록 위험: warning_max/danger_max 사용
    - DB에 미존재 시 NORMAL (graceful)
    """
    if value is None:
        return RiskLevel.NORMAL

    threshold = get_threshold("gas_legal", gas)
    if threshold is None:
        return RiskLevel.NORMAL

    val = Decimal(str(value))

    # O2: 낮을수록 위험
    if gas == "o2":
        if threshold["danger_min"] is not None and val < threshold["danger_min"]:
            return RiskLevel.DANGER
        if (
            threshold["warning_min"] is not None and val < threshold["warning_min"]
        ) or (threshold["warning_max"] is not None and val > threshold["warning_max"]):
            return RiskLevel.WARNING
        return RiskLevel.NORMAL

    # 그 외: 높을수록 위험
    if threshold["danger_max"] is not None and val >= threshold["danger_max"]:
        return RiskLevel.DANGER
    if threshold["warning_max"] is not None and val >= threshold["warning_max"]:
        return RiskLevel.WARNING
    return RiskLevel.NORMAL


def evaluate_power_risk(watt: float | None) -> str:
    """
    전력 watt → RiskLevel 문자열.
    이전: power_alarm.py의 _evaluate(watt) 로직.
    """
    if watt is None:
        return RiskLevel.NORMAL

    threshold = get_threshold("power_default", "power_w")
    if threshold is None:
        return RiskLevel.NORMAL

    val = Decimal(str(watt))
    if threshold["danger_max"] is not None and val > threshold["danger_max"]:
        return RiskLevel.DANGER
    if threshold["warning_max"] is not None and val > threshold["warning_max"]:
        return RiskLevel.WARNING
    return RiskLevel.NORMAL


def invalidate_threshold_cache(group_code: str, item: str | None = None) -> None:
    """
    Threshold 변경 시 캐시 invalidate.
    item=None이면 group 전체 invalidate (드물게 사용).
    """
    if item is not None:
        cache.delete(_cache_key(group_code, item))
    else:
        from apps.facilities.models import Threshold

        items = Threshold.objects.filter(
            group__code=group_code, is_active=True
        ).values_list("measurement_item", flat=True)
        for it in items:
            cache.delete(_cache_key(group_code, it))
