# facilities/services/threshold_service.py
from core.constants import GasTypeChoices

LEGAL_THRESHOLDS = {
    GasTypeChoices.CO: {"limit": 30.0, "unit": "ppm"},
    GasTypeChoices.H2S: {"limit": 10.0, "unit": "ppm"},
    GasTypeChoices.CO2: {"limit": 5000.0, "unit": "ppm"},
    GasTypeChoices.O2: {"limit": 18.0, "unit": "%", "direction": "min"},
    # O2만 최소값 기준 (18% 이상 유지)
    GasTypeChoices.NO2: {"limit": 3.0, "unit": "ppm"},
    GasTypeChoices.SO2: {"limit": 2.0, "unit": "ppm"},
    GasTypeChoices.O3: {"limit": 0.1, "unit": "ppm"},
    GasTypeChoices.NH3: {"limit": 25.0, "unit": "ppm"},
    GasTypeChoices.VOC: {"limit": 50.0, "unit": "ppm"},
    GasTypeChoices.LEL: {"limit": 10.0, "unit": "%"},
}

# 미완성
FACILITY_THRESHOLDS = {
    # 기본값: 법정값의 80% / 90% 수준
    "default": {
        GasTypeChoices.CO: {"warning": 24.0, "danger": 30.0},
        GasTypeChoices.H2S: {"warning": 8.0, "danger": 10.0},
        # ...
    },
}


def get_legal_threshold(gas_type: str) -> dict | None:
    return LEGAL_THRESHOLDS.get(gas_type)


"""
# facilities/models/thresholds.py (4차)
class LegalThreshold(models.Model):
    gas_type = models.CharField(
        max_length=10, unique=True,
        choices=GasTypeChoices.choices
    )
    legal_limit = models.FloatField()
    unit = models.CharField(max_length=10, default='ppm')
    direction = models.CharField(
        max_length=10,
        choices=[('max', '최대값'), ('min', '최소값')],
        default='max'
    )
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'legal_threshold'
"""
