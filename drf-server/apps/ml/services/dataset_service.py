# apps/ml/services/dataset_service.py
"""
ML 학습/평가 데이터셋 추출 — 전력/가스 두 도메인 시계열을 numpy array 로.

- 전력 (long-format): `extract_*_power_series(device_id, channel, data_type, ...)`
- 가스 (wide-format):  `extract_*_gas_series(sensor_id, gas_name, ...)`

설계 선택:
- pandas 의존성을 피하기 위해 numpy + dataclass 만 사용 (feature_service 의 계산도 numpy)
- 채널·축별 분리 시계열 — 멀티변수 IF 가 필요하면 호출자가 column-merge
- value=None 또는 -1 (통신 불능) 은 제외 (학습 노이즈)

전력/가스 두 도메인 함수 시그니처:
- 전력: `extract_*_power_series(device_id, channel, data_type, since, until)`
        sensor_identifier 예: "power:device_1:ch3:watt"
- 가스: `extract_*_gas_series(sensor_id, gas_name, since, until)`
        sensor_identifier 예: "gas:sensor_1:co"

가스는 wide-format 이라 한 row 에 9종 가스가 함께 있다. ORM .values_list 에
가스명 컬럼을 직접 지정해 시계열을 분리한다 (_gas_to_arrays 헬퍼).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np

from apps.monitoring.models import GasData, PowerData

# 가스 9종 화이트리스트 — GasData 컬럼명과 1:1.
# lel 은 GasData 모델 컬럼 없음(원본은 raw_payload JSONField 에만 보관) → 학습 대상 외.
# fire 시나리오는 lel↑ 가 핵심이지만 co/co2/o2/voc 동반 영향으로 우회 학습 가능.
_GAS_NAMES = ("co", "h2s", "co2", "o2", "no2", "so2", "o3", "nh3", "voc")


@dataclass
class TimeSeries:
    """1개 (device, channel, data_type) 시계열 — numpy 1D 배열."""

    sensor_identifier: str  # 예: "power:device_1:ch3:watt"
    measured_at: np.ndarray  # datetime64[ns] 1D
    values: np.ndarray  # float64 1D
    is_anomaly: np.ndarray  # bool 1D
    anomaly_type: np.ndarray  # object 1D (str|None)

    def __len__(self) -> int:
        return int(self.values.shape[0])


def _build_identifier(
    sensor_type: str, device_id: int, channel: int, data_type: str
) -> str:
    return f"{sensor_type}:device_{device_id}:ch{channel}:{data_type}"


def _to_arrays(qs) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """QuerySet → (measured_at, values, is_anomaly, anomaly_type) numpy 배열.

    numpy datetime64 는 timezone-naive 강제 — 변환 시 UserWarning 발생하나 무해.
    UTC 기준이므로 시계열 순서/간격 계산은 정확.
    """
    rows = list(
        qs.values_list("measured_at", "value", "is_anomaly", "anomaly_type").order_by(
            "measured_at"
        )
    )
    if not rows:
        empty = np.array([], dtype="datetime64[ns]")
        return empty, np.array([]), np.array([], dtype=bool), np.array([])
    measured_at = np.array([r[0] for r in rows], dtype="datetime64[ns]")
    values = np.array([r[1] for r in rows], dtype=np.float64)
    is_anomaly = np.array([r[2] for r in rows], dtype=bool)
    anomaly_type = np.array([r[3] for r in rows], dtype=object)
    return measured_at, values, is_anomaly, anomaly_type


def extract_normal_power_series(
    device_id: int,
    channel: int,
    data_type: str,
    since: datetime,
    until: datetime,
) -> TimeSeries:
    """is_anomaly=False · 통신 정상 PowerData 시계열을 반환한다 (학습용)."""
    qs = PowerData.objects.filter(
        power_device_id=device_id,
        channel=channel,
        data_type=data_type,
        measured_at__gte=since,
        measured_at__lt=until,
        is_anomaly=False,
        value__isnull=False,
    ).exclude(value=-1)
    arrays = _to_arrays(qs)
    return TimeSeries(
        sensor_identifier=_build_identifier("power", device_id, channel, data_type),
        measured_at=arrays[0],
        values=arrays[1],
        is_anomaly=arrays[2],
        anomaly_type=arrays[3],
    )


def extract_labeled_power_series(
    device_id: int,
    channel: int,
    data_type: str,
    since: datetime,
    until: datetime,
) -> TimeSeries:
    """is_anomaly=True 라벨 PowerData 시계열을 반환한다 (평가용)."""
    qs = PowerData.objects.filter(
        power_device_id=device_id,
        channel=channel,
        data_type=data_type,
        measured_at__gte=since,
        measured_at__lt=until,
        is_anomaly=True,
        value__isnull=False,
    ).exclude(value=-1)
    arrays = _to_arrays(qs)
    return TimeSeries(
        sensor_identifier=_build_identifier("power", device_id, channel, data_type),
        measured_at=arrays[0],
        values=arrays[1],
        is_anomaly=arrays[2],
        anomaly_type=arrays[3],
    )


# ---------------------------------------------------------------------------
# 가스 도메인 — wide-format (한 row 에 9종 가스 동시 저장)
#
# 전력은 (device, channel, data_type) 세 키로 시계열을 분리하지만, 가스는
# 가스명만 선택해 (sensor_id, gas_name) 두 키로 분리한다.
# ---------------------------------------------------------------------------


def _gas_to_arrays(qs, gas_name: str) -> tuple:
    """GasData QuerySet → (measured_at, values, is_anomaly, anomaly_type) numpy 배열.

    PowerData 와 달리 wide-format 이라 ORM .values_list 에 가스명 컬럼을 직접 지정.
    """
    rows = list(
        qs.values_list("measured_at", gas_name, "is_anomaly", "anomaly_type").order_by(
            "measured_at"
        )
    )
    if not rows:
        empty = np.array([], dtype="datetime64[ns]")
        return empty, np.array([]), np.array([], dtype=bool), np.array([])
    measured_at = np.array([r[0] for r in rows], dtype="datetime64[ns]")
    values = np.array([r[1] for r in rows], dtype=np.float64)
    is_anomaly = np.array([r[2] for r in rows], dtype=bool)
    anomaly_type = np.array([r[3] for r in rows], dtype=object)
    return measured_at, values, is_anomaly, anomaly_type


def extract_normal_gas_series(
    sensor_id: int,
    gas_name: str,
    since: datetime,
    until: datetime,
) -> TimeSeries:
    """is_anomaly=False · 가스값 not None 인 GasData 시계열을 반환한다 (학습용).

    주의: `is_anomaly=False` 필터는 운영 정상 row 와 시뮬레이터 정상 row 를 구분 못한다.
    학습 기간에 시뮬레이터만 동작했음을 가정 — 운영 진입 시 별도 출처 식별 필드 도입 검토.
    """
    if gas_name not in _GAS_NAMES:
        raise ValueError(f"unknown gas_name: {gas_name} (allowed: {_GAS_NAMES})")
    qs = GasData.objects.filter(
        gas_sensor_id=sensor_id,
        measured_at__gte=since,
        measured_at__lt=until,
        is_anomaly=False,
        **{f"{gas_name}__isnull": False},
    )
    arrays = _gas_to_arrays(qs, gas_name)
    return TimeSeries(
        sensor_identifier=f"gas:sensor_{sensor_id}:{gas_name}",
        measured_at=arrays[0],
        values=arrays[1],
        is_anomaly=arrays[2],
        anomaly_type=arrays[3],
    )


def extract_labeled_gas_series(
    sensor_id: int,
    gas_name: str,
    since: datetime,
    until: datetime,
) -> TimeSeries:
    """is_anomaly=True 라벨 GasData 시계열을 반환한다 (평가용)."""
    if gas_name not in _GAS_NAMES:
        raise ValueError(f"unknown gas_name: {gas_name} (allowed: {_GAS_NAMES})")
    qs = GasData.objects.filter(
        gas_sensor_id=sensor_id,
        measured_at__gte=since,
        measured_at__lt=until,
        is_anomaly=True,
        **{f"{gas_name}__isnull": False},
    )
    arrays = _gas_to_arrays(qs, gas_name)
    return TimeSeries(
        sensor_identifier=f"gas:sensor_{sensor_id}:{gas_name}",
        measured_at=arrays[0],
        values=arrays[1],
        is_anomaly=arrays[2],
        anomaly_type=arrays[3],
    )


# 이성현 추가 — 다변량 학습용: 여러 가스 TimeSeries 를 리스트로 반환
def extract_normal_gas_multi_series(
    sensor_id: int,
    gas_names: list[str],
    since: datetime,
    until: datetime,
) -> list[TimeSeries]:
    """gas_names 각각에 대해 extract_normal_gas_series 를 호출해 리스트로 반환."""
    return [
        extract_normal_gas_series(sensor_id, gas_name, since, until)
        for gas_name in gas_names
    ]
