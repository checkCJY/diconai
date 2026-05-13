# apps/ml/services/dataset_service.py
"""
ML 학습/평가 데이터셋 추출.

PowerData (3축 long-format) 에서 (device, channel, data_type) 단위 시계열을 뽑아
학습/평가용 numpy array 로 변환한다. 가스 데이터는 동일 패턴으로 후속 확장.

설계 선택:
- pandas 의존성을 피하기 위해 numpy + dataclass 만 사용 (feature_service 의 계산도 numpy)
- 채널·축별 분리 시계열 — 멀티변수 IF 가 필요하면 호출자가 column-merge
- value=None 또는 -1 (통신 불능) 은 제외 (학습 노이즈)

가스 도메인 추가 절차 (가스 트랙 인원용):
1. GasData 모델에 `is_anomaly`/`anomaly_type` 필드 추가 + 마이그
   (참조: 전력 Phase 3 — drf-server/apps/monitoring/migrations/0006_powerdata_is_anomaly_anomaly_type.py)
2. 본 파일에 `extract_normal_gas_series()`, `extract_labeled_gas_series()` 함수 추가
   - 시그니처: `(gas_type: str, since, until) -> TimeSeries`
   - sensor_identifier 패턴: `"gas:{gas_type}"` 예: "gas:co"
   - `_build_identifier()` 헬퍼는 그대로 재사용 가능
3. ml 앱 자체는 도메인 무관 — train_anomaly_model 커맨드가 `--sensor-type gas` 옵션으로 호출
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np

from apps.monitoring.models import PowerData


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
