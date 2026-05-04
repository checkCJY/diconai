"""
전력 임계치 기준 — DRF apps/core/constants.py의 POWER_THRESHOLDS와 동일 값을 유지해야 함.
단위: W (와트), Phase A 기준

값은 core.config.Settings에서 env로 주입되므로 운영 환경별 조정 가능.
"""

from core.config import settings

POWER_THRESHOLDS: dict = {
    "caution": settings.POWER_THRESHOLD_CAUTION,
    "danger": settings.POWER_THRESHOLD_DANGER,
}
