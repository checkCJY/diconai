"""
DataRetentionPolicy 보관 배치 (Phase 4-g).

[흐름]
1. Celery beat이 매일 새벽 3시 run_data_retention.delay() 호출
2. DataRetentionPolicy.objects.filter(is_active=True) 순회
3. policy.delete_cycle이 today에 해당하는지 is_cycle_due() 판정
4. 해당하면 device_type + data_category 분기로 실제 삭제
   - GAS_RAW          → GasData (max_risk_level=normal, raw_retention_days 초과)
   - GAS_ANOMALY      → GasData (max_risk_level!=normal, history_retention_days 초과)
   - POWER_RAW        → PowerData (raw_retention_days 초과)
   - POWER_AGG        → PowerData (history_retention_days 초과)
   - POSITION_HIST    → WorkerPosition (raw_retention_days 초과)

[dry_run 모드]
실제 삭제 안 하고 대상 row 수만 반환 + 로깅. 운영 적용 전 검증용.

[안전]
정책 적용 전 [logger.info] action=retention policy_id=... 기록.
삭제 후 deleted_count 로깅.
"""

import calendar
import logging
from datetime import date, timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


def is_cycle_due(delete_cycle: str, today: date) -> bool:
    """
    delete_cycle이 today에 해당하는지 판정.

    DAILY        : 매일 True
    MONTHLY_1    : 매월 1일
    MONTHLY_15   : 매월 15일
    MONTHLY_LAST : 매월 말일
    QUARTERLY    : 분기 말 (3/31, 6/30, 9/30, 12/31)
    """
    if delete_cycle == "daily":
        return True
    if delete_cycle == "monthly_1":
        return today.day == 1
    if delete_cycle == "monthly_15":
        return today.day == 15
    if delete_cycle == "monthly_last":
        last_day = calendar.monthrange(today.year, today.month)[1]
        return today.day == last_day
    if delete_cycle == "quarterly":
        # 분기 말: 3/31, 6/30, 9/30, 12/31
        if today.month not in (3, 6, 9, 12):
            return False
        last_day = calendar.monthrange(today.year, today.month)[1]
        return today.day == last_day
    return False


def _delete_for_policy(policy, dry_run: bool = False) -> int:
    """
    단일 정책에 대해 삭제 실행 또는 dry_run 카운트.

    반환: 삭제된 (또는 삭제 예정) row 수.
    """
    from apps.monitoring.models import GasData, PowerData
    from apps.positioning.models import WorkerPosition

    raw_cutoff = timezone.now() - timedelta(days=policy.raw_retention_days)
    history_cutoff = timezone.now() - timedelta(days=policy.history_retention_days)

    category = policy.data_category
    if category == "gas_raw":
        qs = GasData.objects.filter(measured_at__lt=raw_cutoff, max_risk_level="normal")
    elif category == "gas_anomaly":
        qs = GasData.objects.filter(measured_at__lt=history_cutoff).exclude(
            max_risk_level="normal"
        )
    elif category == "power_raw":
        qs = PowerData.objects.filter(measured_at__lt=raw_cutoff)
    elif category == "power_agg":
        qs = PowerData.objects.filter(measured_at__lt=history_cutoff)
    elif category == "position_hist":
        qs = WorkerPosition.objects.filter(measured_at__lt=raw_cutoff)
    else:
        logger.warning(
            "[retention] action=unknown_category policy_id=%s category=%s",
            policy.id,
            category,
        )
        return 0

    count = qs.count()
    if dry_run:
        logger.info(
            "[retention] action=dry_run policy_id=%s category=%s count=%s",
            policy.id,
            category,
            count,
        )
        return count

    deleted, _ = qs.delete()
    logger.info(
        "[retention] action=deleted policy_id=%s category=%s deleted=%s",
        policy.id,
        category,
        deleted,
    )
    return deleted


@shared_task
def run_data_retention(dry_run: bool = False) -> dict:
    """
    Celery 진입점 — 활성 DataRetentionPolicy 모두 순회.

    Args:
        dry_run: True면 실제 삭제 안 함, 대상 row 수만 로깅.

    Returns:
        {policy_id: deleted_count} dict — 운영 모니터링용.
    """
    from apps.operations.models import DataRetentionPolicy

    today = timezone.now().date()
    policies = DataRetentionPolicy.objects.filter(is_active=True)

    summary: dict[int, int] = {}
    for policy in policies:
        if not is_cycle_due(policy.delete_cycle, today):
            continue
        try:
            count = _delete_for_policy(policy, dry_run=dry_run)
            summary[policy.id] = count
        except Exception as exc:
            logger.error(
                "[retention] action=failed policy_id=%s error=%s",
                policy.id,
                exc,
            )

    logger.info(
        "[retention] action=run_complete dry_run=%s policies_run=%s",
        dry_run,
        len(summary),
    )
    return summary
