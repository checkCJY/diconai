"""IoT 수신 라우터 Pydantic 검증 회귀 가드 (P1 신규).

가스/전력 수신 엔드포인트는 Pydantic 스키마로 payload 를 검증한 뒤에야 service 로
위임한다(검증 실패 시 422, 파이프라인 미진입). 센서가 깨진 값을 보내도 DRF·WS 로
전파되지 않도록 경계값을 못박는다. (gas/schemas/gas.py, power/schemas/power.py)
"""

from fastapi.testclient import TestClient

from app import app

# with 없이 생성 — lifespan(백그라운드 루프) 미가동, 라우트 검증만 동기로 호출.
client = TestClient(app)

_SLAVE_KEYS = [
    "slave01",
    "slave02",
    "slave11",
    "slave12",
    "slave21",
    "slave22",
    "slave31",
    "slave32",
    "slave41",
    "slave42",
    "slave51",
    "slave52",
    "slave61",
    "slave62",
    "slave71",
    "slave72",
]


def _valid_gas(**override) -> dict:
    payload = {
        "timestamp": "2026-06-15T00:00:00Z",
        "device_id": "GAS-TEST-1",
        "device_name": "00:11:22:33:44:55",
        "location": {"x": 1.0, "y": 2.0},
        "o2": 20.9,
        "co": 0,
        "co2": 400,
        "h2s": 0,
        "lel": 0,
        "no2": 0,
        "so2": 0,
        "o3": 0,
        "nh3": 0,
        "voc": 0,
    }
    payload.update(override)
    return payload


def _valid_watt(**override) -> dict:
    payload = {"device_id": "POW-TEST-1", **{k: 100.0 for k in _SLAVE_KEYS}}
    payload.update(override)
    return payload


def test_gas_o2_above_100_rejected():
    """o2 > 100 → 422 (ge=0, le=100 경계 초과)."""
    res = client.post("/api/sensors/gas", json=_valid_gas(o2=150))
    assert res.status_code == 422


def test_gas_negative_concentration_rejected():
    """co < 0 → 422 (농도는 ge=0)."""
    res = client.post("/api/sensors/gas", json=_valid_gas(co=-5))
    assert res.status_code == 422


def test_gas_missing_required_field_rejected():
    """필수 필드(device_id) 누락 → 422."""
    payload = _valid_gas()
    del payload["device_id"]
    res = client.post("/api/sensors/gas", json=payload)
    assert res.status_code == 422


def test_power_slave_below_minus_one_rejected():
    """slave 값 < -1 → 422 (ge=-1, -1은 통신 불능 허용값이라 그 미만만 거부)."""
    res = client.post("/api/power/watt", json=_valid_watt(slave01=-2))
    assert res.status_code == 422


def test_power_missing_required_field_rejected():
    """필수 slave 필드 누락 → 422."""
    payload = _valid_watt()
    del payload["slave01"]
    res = client.post("/api/power/watt", json=payload)
    assert res.status_code == 422
