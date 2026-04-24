# monitoring/services/gas_alarm.py
from apps.alerts.services.event_service import create_alarm_and_event
from apps.core.constants import AlarmType
from apps.monitoring.utils.gas_thresholds import GAS_LABELS, GAS_UNITS, get_threshold_value

GAS_FIELDS = ["co", "h2s", "co2", "o2", "no2", "so2", "o3", "nh3", "voc"]


def trigger_gas_alarms(gas_data) -> list[dict]:
    """
    GasData 저장 후 각 가스 위험도를 확인하여 AlarmRecord/Event를 생성한다.

    warning 또는 danger 인 가스마다 create_alarm_and_event() 호출.
    새 Event가 생성된 경우에만 알람 정보를 반환 리스트에 포함.
    """
    sensor = gas_data.gas_sensor
    facility_id = sensor.facility_id
    sensor_id = sensor.id
    source_label = sensor.device_name
    detected_at = gas_data.measured_at

    results = []

    for gas in GAS_FIELDS:
        risk = getattr(gas_data, f"{gas}_risk", None)
        if risk not in ("warning", "danger"):
            continue

        measured_value = getattr(gas_data, gas, None)
        threshold_value = get_threshold_value(gas, risk)
        label = GAS_LABELS.get(gas, gas.upper())
        unit = GAS_UNITS.get(gas, "")
        summary = f"{label} 임계치 초과 ({measured_value} {unit})"

        event, alarm = create_alarm_and_event(
            facility_id=facility_id,
            alarm_type=AlarmType.GAS_THRESHOLD,
            sensor_id=sensor_id,
            gas_type=gas,
            measured_value=measured_value,
            threshold_value=threshold_value,
            risk_level=risk,
            source_label=source_label,
            summary=summary,
            detected_at=detected_at,
        )

        # alarm이 None이면 기존 Event에 병합된 것 → 프론트 재알림 없음
        if alarm is not None:
            results.append({
                "event_id": event.id,
                "alarm_type": AlarmType.GAS_THRESHOLD,
                "gas_type": gas,
                "risk_level": risk,
                "measured_value": measured_value,
                "threshold_value": threshold_value,
                "source_label": source_label,
                "summary": summary,
                "is_new_event": True,
            })

    return results
