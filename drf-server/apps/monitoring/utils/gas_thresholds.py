# monitoring/utils/gas_thresholds.py
# FastAPI core/gas_thresholds.py 와 동일한 임계치 기준
GAS_THRESHOLDS: dict[str, dict] = {
    "co": {"normal_max": 25, "warning_max": 200},
    "h2s": {"normal_max": 10, "warning_max": 15},
    "co2": {"normal_max": 1000, "warning_max": 5000},
    "o2": {"normal_min": 18.0, "normal_max": 23.5, "warning_min": 16.0},
    "no2": {"normal_max": 3, "warning_max": 5},
    "so2": {"normal_max": 2, "warning_max": 5},
    "o3": {"normal_max": 0.06, "warning_max": 0.12},
    "nh3": {"normal_max": 25, "warning_max": 35},
    "voc": {"normal_max": 0.5, "warning_max": 1.0},
}

GAS_UNITS: dict[str, str] = {
    "co": "ppm",
    "h2s": "ppm",
    "co2": "ppm",
    "o2": "%",
    "no2": "ppm",
    "so2": "ppm",
    "o3": "ppm",
    "nh3": "ppm",
    "voc": "ppm",
}

GAS_LABELS: dict[str, str] = {
    "co": "CO",
    "h2s": "H2S",
    "co2": "CO2",
    "o2": "O2",
    "no2": "NO2",
    "so2": "SO2",
    "o3": "O3",
    "nh3": "NH3",
    "voc": "VOC",
}


def get_threshold_value(gas: str, risk: str) -> float | None:
    """위험도에 해당하는 임계치 값을 반환한다."""
    t = GAS_THRESHOLDS.get(gas)
    if not t:
        return None
    if gas == "o2":
        return t["warning_min"] if risk == "danger" else t["normal_min"]
    return t["warning_max"] if risk == "danger" else t["normal_max"]
