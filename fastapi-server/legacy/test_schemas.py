"""
더미 데이터 → Pydantic 검증 확인 스크립트.

실행:
    .venv/bin/python test_schemas.py
"""

from pydantic import ValidationError

from dummy_sender import generate_device_info, generate_gas_data
from schemas import DeviceInfoPayload, GasDataPayload


def test_device_info():
    raw = generate_device_info()
    print("\n[DEVICE INFO] 원본 데이터")
    print(raw)

    try:
        validated = DeviceInfoPayload(**raw)
        print("[DEVICE INFO] 검증 통과 ✓")
        print(validated.model_dump())
    except ValidationError as e:
        print("[DEVICE INFO] 검증 실패 ✗")
        print(e)


def test_gas_data_normal():
    raw = generate_gas_data(is_danger_event=False)
    print("\n[GAS DATA - 정상] 원본 데이터")
    print(raw)

    try:
        validated = GasDataPayload(**raw)
        print("[GAS DATA - 정상] 검증 통과 ✓")
        print(validated.model_dump())
    except ValidationError as e:
        print("[GAS DATA - 정상] 검증 실패 ✗")
        print(e)


def test_gas_data_danger():
    raw = generate_gas_data(is_danger_event=True)
    print("\n[GAS DATA - 위험] 원본 데이터")
    print(raw)

    try:
        validated = GasDataPayload(**raw)
        print("[GAS DATA - 위험] 검증 통과 ✓")
        print(f"  status: {validated.status}")
        print(validated.model_dump())
    except ValidationError as e:
        print("[GAS DATA - 위험] 검증 실패 ✗")
        print(e)


if __name__ == "__main__":
    test_device_info()
    test_gas_data_normal()
    test_gas_data_danger()
