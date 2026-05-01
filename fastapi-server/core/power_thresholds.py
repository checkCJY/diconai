"""
전력 임계치 기준 — DRF constants.py의 POWER_THRESHOLDS와 동일 값을 유지해야 함.
단위: W (와트), Phase A 기준
"""

POWER_THRESHOLDS: dict = {
    "caution": 2200,
    "danger": 2860,
}
