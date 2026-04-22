"""
더미 데이터 → Pydantic 검증 확인 스크립트.

실행:
    .venv/bin/python power_system/test_schemas.py
"""

from pydantic import ValidationError

from power_dummy_sender import (
    generate_power_onoff_data,
    generate_power_current_data,
    generate_power_voltage_data,
    generate_power_watt_data,
)
from schemas import (
    PowerOnOffPayload,
    PowerCurrentPayload,
    PowerVoltagePayload,
    PowerWattPayload,
)


def test_power_onoff():
    raw = generate_power_onoff_data()
    print("\n[POWER ON/OFF] 원본 데이터")
    print(raw)

    try:
        validated = PowerOnOffPayload(**raw)
        print("[POWER ON/OFF] 검증 통과 ✓")
        snapshot = validated.to_snapshot()
        print(f"  to_snapshot(): {snapshot}")
    except ValidationError as e:
        print("[POWER ON/OFF] 검증 실패 ✗")
        print(e)


def test_power_current():
    raw = generate_power_current_data()
    print("\n[POWER CURRENT] 원본 데이터")
    print(raw)

    try:
        validated = PowerCurrentPayload(**raw)
        print("[POWER CURRENT] 검증 통과 ✓")
        channel_values = validated.to_channel_values()
        print(f"  to_channel_values(): {channel_values}")
    except ValidationError as e:
        print("[POWER CURRENT] 검증 실패 ✗")
        print(e)


def test_power_voltage():
    raw = generate_power_voltage_data()
    print("\n[POWER VOLTAGE] 원본 데이터")
    print(raw)

    try:
        validated = PowerVoltagePayload(**raw)
        print("[POWER VOLTAGE] 검증 통과 ✓")
        channel_values = validated.to_channel_values()
        print(f"  to_channel_values(): {channel_values}")
    except ValidationError as e:
        print("[POWER VOLTAGE] 검증 실패 ✗")
        print(e)


def test_power_watt():
    raw = generate_power_watt_data()
    print("\n[POWER WATT] 원본 데이터")
    print(raw)

    try:
        validated = PowerWattPayload(**raw)
        print("[POWER WATT] 검증 통과 ✓")
        channel_values = validated.to_channel_values()
        print(f"  to_channel_values(): {channel_values}")
    except ValidationError as e:
        print("[POWER WATT] 검증 실패 ✗")
        print(e)


def test_power_current_with_disconnected_channel():
    """통신 불능 채널(-1) 포함 데이터 검증."""

    raw = generate_power_current_data()
    raw["slave01"] = -1  # 통신 불능 강제 주입
    print("\n[POWER CURRENT - 통신 불능 채널 포함] 원본 데이터")
    print(raw)

    try:
        validated = PowerCurrentPayload(**raw)
        print("[POWER CURRENT - 통신 불능] 검증 통과 ✓")
        ch = validated.to_channel_values()
        disconnected = [k for k, v in ch.items() if v == -1]
        print(f"  통신 불능 채널: {disconnected}")
    except ValidationError as e:
        print("[POWER CURRENT - 통신 불능] 검증 실패 ✗")
        print(e)


if __name__ == "__main__":
    test_power_onoff()
    test_power_current()
    test_power_voltage()
    test_power_watt()
    test_power_current_with_disconnected_channel()
