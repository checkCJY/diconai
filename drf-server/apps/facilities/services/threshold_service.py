# facilities/services/threshold_service.py
"""
Threshold DB 조회 + Redis 캐시 (Phase 4-d + PR-G).

[단일 진실 공급원]
이전: core/constants.py POWER_THRESHOLDS + facilities LEGAL_THRESHOLDS 상수
이후: facilities.Threshold DB 모델 + Redis 캐시 (group_code, item, facility_id) 키.

[PR-G facility 우선순위]
가스 임계치는 facility specific(gas_facility_default 그룹) > 전사(gas_legal) fallback.
- get_threshold(group, item, facility_id=N): facility=N row 조회 → 없으면 facility=NULL row
- evaluate_gas_risk(gas, value, facility_id=N): facility specific(gas_facility_default 그룹) 우선
  매칭 → 없으면 gas_legal fallback → 둘 다 없으면 NORMAL
- 전력은 power_default 1개 그룹 (facility 무관, 전사) 그대로 — facility_id 매개변수 무시

[캐시 정책]
- 키: f"threshold:{group_code}:{item}:{facility_id}" (facility None은 "all")
- TTL: 1시간
- invalidate: Threshold post_save / post_delete signal에서 cache.delete

[fallback]
DB에 Threshold가 없으면 RiskLevel.NORMAL 반환 (graceful degradation).
"""

from decimal import Decimal

from django.core.cache import cache

from apps.core.constants import RiskLevel

_CACHE_PREFIX = "threshold"
_CACHE_TTL = 3600  # 1시간


def _cache_key(group_code: str, item: str, facility_id: int | None = None) -> str:
    fac = facility_id if facility_id is not None else "all"
    return f"{_CACHE_PREFIX}:{group_code}:{item}:{fac}"


def get_threshold(
    group_code: str, item: str, facility_id: int | None = None
) -> dict | None:
    """
    Threshold DB 조회 + Redis 캐시.

    facility_id가 지정되면 해당 facility row 우선 조회. 없으면 facility=NULL (전사) row.

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
    key = _cache_key(group_code, item, facility_id)
    cached = cache.get(key)
    if cached is not None:
        return cached

    from apps.facilities.models import Threshold

    qs = Threshold.objects.filter(
        group__code=group_code, measurement_item=item, is_active=True
    ).select_related("group")

    threshold = None
    if facility_id is not None:
        threshold = qs.filter(facility_id=facility_id).first()
    if threshold is None:
        threshold = qs.filter(facility__isnull=True).first()

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


def evaluate_gas_risk(
    gas: str, value: float | None, facility_id: int | None = None
) -> str:
    """
    가스 측정값 → RiskLevel 문자열 (PR-G facility 우선순위).

    [정책]
    - facility specific(gas_facility_default 그룹) 우선 → 없으면 gas_legal fallback
    - O2는 낮을수록 위험: warning_min/danger_min 사용
    - 그 외는 높을수록 위험: warning_max/danger_max 사용
    - DB에 미존재 시 NORMAL (graceful)
    """
    if value is None:
        return RiskLevel.NORMAL

    threshold = None
    if facility_id is not None:
        threshold = get_threshold("gas_facility_default", gas, facility_id)
    if threshold is None:
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
    power_default 그룹은 전사 1개 정책 (facility 무관) — facility_id 매개변수 미지원.
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


def invalidate_threshold_cache(
    group_code: str, item: str | None = None, facility_id: int | None = None
) -> None:
    """
    Threshold 변경 시 캐시 invalidate.
    item=None이면 group 전체 invalidate (드물게 사용).
    facility_id 미지정 시 모든 facility 차원 invalidate (signal 권장).
    """
    if item is not None and facility_id is not None:
        cache.delete(_cache_key(group_code, item, facility_id))
        return

    from apps.facilities.models import Threshold

    qs = Threshold.objects.filter(group__code=group_code, is_active=True)
    if item is not None:
        qs = qs.filter(measurement_item=item)
    pairs = qs.values_list("measurement_item", "facility_id")
    for it, fac in pairs:
        cache.delete(_cache_key(group_code, it, fac))
    # facility=NULL 전사 row도 invalidate
    cache.delete(_cache_key(group_code, item or "*", None))
