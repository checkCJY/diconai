"""
DataRetentionPolicy 보관 배치 (Phase 4-g).

[흐름]
1. Celery beat이 매일 새벽 3시 run_data_retention.delay() 호출
2. DataRetentionPolicy.objects.filter(is_active=True) 순회
3. policy.delete_cycle이 today에 해당하는지 is_cycle_due() 판정
4. 해당하면 data_category 분기로 실제 삭제
   센서 원천
   - GAS_RAW          → GasData (max_risk_level=normal, raw_retention_days 초과)
   - GAS_ANOMALY      → GasData (max_risk_level!=normal, history_retention_days 초과)
   - GAS_HOURLY       → GasDataHourly (Phase 4 모델 신설 전까지 skip)
   - POWER_RAW        → PowerData (raw_retention_days 초과)
   - POWER_AGG        → PowerData (history_retention_days 초과)
   - POWER_HOURLY     → PowerDataHourly (Phase 4 모델 신설 전까지 skip)
   - POSITION_HIST    → WorkerPosition (raw_retention_days 초과)
   AI/ML
   - ML_RESULT        → MLAnomalyResult (evaluated_at, raw_retention_days 초과)
   - ML_MODEL         → MLModel (is_active=False + trained_at 초과) + .pkl 파일 삭제
   시스템 로그
   - SYSTEM_LOG       → SystemLog (created_at, raw_retention_days 초과)
   - INTEGRATION_LOG  → IntegrationLog (created_at, raw_retention_days 초과)
   - APP_LOG          → AppLog (created_at, raw_retention_days 초과)
   - LOGIN_LOG        → LoginLog (timestamp, raw_retention_days 초과)
   - NOTIFICATION     → Notification (created_at, raw_retention_days 초과)

[django_session 정리]
  django_session은 clear_sessions_task.py 에서 별도 관리 (clearsessions 커맨드).
  DataRetentionPolicy 순회 대상에 포함되지 않음.

[dry_run 모드]
실제 삭제 안 하고 대상 row 수만 반환 + 로깅. 운영 적용 전 검증용.

[안전]
정책 적용 전 [logger.info] action=retention policy_id=... 기록.
삭제 후 deleted_count 로깅.
MLModel .pkl 삭제 실패 시 해당 DB row는 건너뜀 (파일-DB 정합성 보존).
"""

import calendar
import logging
from datetime import date, timedelta
from pathlib import Path

from celery import shared_task
from django.conf import settings
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


def _try_delete_pkl(file_path: str) -> bool:
    """
    MLModel .pkl 파일 삭제. 실패 시 False 반환 (예외 전파 안 함).

    file_path는 settings.ML_MODELS_DIR 기준 상대 경로.
    삭제 실패 시 호출자가 DB row 삭제를 건너뜀 → 파일-DB 정합성 유지.
    """
    try:
        abs_path = Path(settings.ML_MODELS_DIR) / file_path
        if abs_path.exists():
            abs_path.unlink()
            logger.info("[retention] action=pkl_deleted path=%s", abs_path)
        return True
    except Exception:
        logger.exception("[retention] action=pkl_delete_failed path=%s", file_path)
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

    # ── 센서 원천 ────────────────────────────────────────────────
    if category == "gas_raw":
        # 정상(normal) 가스 데이터만 삭제 — 이상 감지 이력(max_risk_level != normal)은
        # gas_anomaly 정책이 별도로 더 길게 보관. 두 정책이 겹치지 않도록 조건 분리.
        qs = GasData.objects.filter(measured_at__lt=raw_cutoff, max_risk_level="normal")

    elif category == "gas_anomaly":
        # 이상 감지가 붙은 가스 데이터. gas_raw보다 오래 보관(history_cutoff 사용).
        # 사고 소급 분석용으로 원천 데이터 형태 그대로 보존.
        qs = GasData.objects.filter(measured_at__lt=history_cutoff).exclude(
            max_risk_level="normal"
        )

    elif category in ("gas_hourly", "power_hourly"):
        # GasDataHourly / PowerDataHourly 모델은 Phase 4에서 신설 예정.
        # 정책 행은 미리 DB에 생성해두고, 모델이 없는 기간에는 삭제 없이 skip.
        # Phase 4 이후 여기에 해당 모델 import + qs 추가.
        logger.info(
            "[retention] action=skip_no_model policy_id=%s category=%s",
            policy.id,
            category,
        )
        return 0

    elif category == "power_raw":
        # 전력 원천 데이터 — 채널별 행 정규화 구조. 채널 구분 없이 측정 시각 기준 삭제.
        qs = PowerData.objects.filter(measured_at__lt=raw_cutoff)

    elif category == "power_agg":
        # [H-4 수정] power_agg는 전력 집계 전용 모델(PowerDataAgg)이 신설되면 적용 예정.
        # 기존 코드는 power_raw와 동일한 PowerData 테이블을 history_cutoff로 삭제해서
        # power_raw가 지워야 할 데이터를 power_agg가 다시 건드리는 구조였음.
        # gas_hourly/power_hourly와 동일하게 모델 준비 전까지 skip 처리.
        logger.info(
            "[retention] action=skip_no_model policy_id=%s category=%s",
            policy.id,
            category,
        )
        return 0

    elif category == "position_hist":
        # 작업자 위치 이력. 탈퇴 작업자 행도 worker=NULL 상태로 존재할 수 있음 —
        # worker FK 조건 없이 측정 시각 기준으로만 삭제 (익명화된 이력도 함께 정리).
        qs = WorkerPosition.objects.filter(measured_at__lt=raw_cutoff)

    # ── AI/ML ────────────────────────────────────────────────────
    elif category == "ml_result":
        # MLAnomalyResult(Isolation Forest 추론 결과) 삭제.
        # feature_snapshot_json 포함 — 용량이 크므로 오래 보관할 이유 없음.
        # GasArimaResult(ARIMA 추론 결과)는 Phase 4 신설 예정. 동일 cutoff 적용 예정.
        from apps.ml.models import MLAnomalyResult

        qs = MLAnomalyResult.objects.filter(evaluated_at__lt=raw_cutoff)

    elif category == "ml_model":
        # 비활성 모델(is_active=False)만 대상 — 현재 추론에 쓰이는 활성 모델은 절대 삭제 안 함.
        # trained_at이 raw_retention_days 이전 → "비활성된 지 오래된 것"의 근사 기준.
        # (deactivated_at 필드가 없어서 trained_at으로 대체 — 충분히 안전한 근사값)
        # .pkl 파일 삭제 실패 시 해당 DB row는 건너뜀. 파일이 사라진 상태에서
        # DB row만 남으면 추론 시 404 오류 — 반드시 파일-DB 정합성 유지.
        # 다음 배치 실행 시 재시도.
        from apps.ml.models import MLModel

        qs = MLModel.objects.filter(is_active=False, trained_at__lt=raw_cutoff)

        if dry_run:
            count = qs.count()
            logger.info(
                "[retention] action=dry_run policy_id=%s category=%s count=%s",
                policy.id,
                category,
                count,
            )
            return count

        count = 0
        for ml in qs.iterator():
            if not _try_delete_pkl(ml.file_path):
                # pkl 삭제 실패 — 이 row는 skip, 다음 배치에서 재시도
                logger.warning(
                    "[retention] action=ml_model_skip policy_id=%s model_id=%s "
                    "reason=pkl_delete_failed",
                    policy.id,
                    ml.id,
                )
                continue
            ml.delete()
            count += 1

        logger.info(
            "[retention] action=deleted policy_id=%s category=%s deleted=%s",
            policy.id,
            category,
            count,
        )
        return count

    # ── 시스템 로그 ──────────────────────────────────────────────
    elif category == "system_log":
        # SystemLog는 시스템 로그 / 사용자 활동 로그 / 지도 편집 로그를 단일 테이블에서 관리.
        # action_type 구분 없이 created_at 기준으로 일괄 삭제.
        # 법적 의무 보관 대상 아님 — 운영 감사 목적이므로 1년으로 설정.
        from apps.core.models import SystemLog

        qs = SystemLog.objects.filter(created_at__lt=raw_cutoff)

    elif category == "integration_log":
        # FastAPI→DRF 연동 호출 기록 (drf_client.post_to_drf 자동 기록).
        # 빈도가 높아 용량 누적이 빠름 — 3개월로 짧게 유지.
        from apps.operations.models.integration_log import IntegrationLog

        qs = IntegrationLog.objects.filter(created_at__lt=raw_cutoff)

    elif category == "app_log":
        # Python logging.error/warning 영속화 (DbHandler). 빈도 높음 — 3개월.
        from apps.operations.models.app_log import AppLog

        qs = AppLog.objects.filter(created_at__lt=raw_cutoff)

    elif category == "login_log":
        # LoginLog는 created_at 대신 timestamp 필드 사용 (모델 설계 차이).
        # 보안 감사 목적 — 1년 보관.
        from apps.accounts.models.login_log import LoginLog

        qs = LoginLog.objects.filter(timestamp__lt=raw_cutoff)

    elif category == "notification":
        # 발송 이력(popup/push/sms/email). 운영자 확인 후 불필요 — 3개월.
        from apps.notifications.models import Notification

        qs = Notification.objects.filter(created_at__lt=raw_cutoff)

    else:
        logger.warning(
            "[retention] action=unknown_category policy_id=%s category=%s",
            policy.id,
            category,
        )
        return 0

    # ml_model은 위에서 직접 return — 여기까지 오면 일반 bulk delete 경로
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
