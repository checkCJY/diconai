"""가스 임계치 기준 및 상태 판정 로직.

수신 검증(schemas)과 더미 생성(gas_dummy) 양쪽에서 공유하는 단일 공급원.
임계치 출처: 가스별 임계치 기준 이미지 문서 (디코나이 내부 문서)
"""

# 임계치 기준
# o2는 낮을수록 위험 → normal_min / warning_min 별도 기재
# lel은 임계치 미정의 → 상태 판정 제외, 수집만 함
GAS_THRESHOLDS: dict[str, dict] = {
    "co": {"normal_max": 25, "warning_max": 200},  # ppm
    "h2s": {"normal_max": 10, "warning_max": 15},  # ppm
    "co2": {"normal_max": 1000, "warning_max": 5000},  # ppm
    "o2": {
        "normal_min": 18.0,
        "normal_max": 23.5,  # %
        "warning_min": 16.0,
    },
    "no2": {"normal_max": 3, "warning_max": 5},  # ppm
    "so2": {"normal_max": 2, "warning_max": 5},  # ppm
    "o3": {"normal_max": 0.06, "warning_max": 0.12},  # ppm
    "nh3": {"normal_max": 25, "warning_max": 35},  # ppm
    "voc": {"normal_max": 0.5, "warning_max": 1.0},  # ppm
}


# 상태 판정
def evaluate_single_gas(gas: str, value: float) -> str:
    """단일 가스값에 대한 위험도를 반환한다. lel은 임계치 미정의이므로 항상 normal."""
    thresholds = GAS_THRESHOLDS.get(gas)
    if thresholds is None:
        return "normal"

    if gas == "o2":
        if value < thresholds["warning_min"]:
            return "danger"
        if value < thresholds["normal_min"] or value > thresholds["normal_max"]:
            return "warning"
        return "normal"

    if value >= thresholds["warning_max"]:
        return "danger"
    if value >= thresholds["normal_max"]:
        return "warning"
    return "normal"


def calculate_individual_risks(gas_values: dict[str, float]) -> dict[str, str]:
    """각 가스별 위험도 딕셔너리를 반환한다. lel은 임계치 미정의이므로 제외."""
    return {
        f"{gas}_risk": evaluate_single_gas(gas, value)
        for gas, value in gas_values.items()
        if gas != "lel"
    }


def calculate_gas_status(gas_values: dict[str, float]) -> str:
    """가스 측정값 딕셔너리를 받아 전체 상태를 판정한다.

    - danger가 하나라도 있으면 즉시 반환
    - warning이 하나라도 있으면 warning 반환
    - 전체 정상이면 normal 반환
    - lel은 임계치 미정의이므로 판정 제외

    Args:
        gas_values: 가스 필드 딕셔너리 (o2, co, co2, h2s, lel, no2, so2, o3, nh3, voc)

    Returns:
        "normal" | "warning" | "danger"
    """
    overall = "normal"

    for gas, value in gas_values.items():
        level = evaluate_single_gas(gas, value)
        if level == "danger":
            return "danger"
        if level == "warning":
            overall = "warning"

    return overall
