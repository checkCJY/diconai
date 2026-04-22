"""
FastAPI 수신 페이로드 스키마.

DRF 모델과의 대응 관계:
  DeviceInfoPayload  ← facilities/models/devices.py  DeviceBase + GasSensor
  GasDataPayload     ← monitoring/models/gas_data.py  GasData
  RiskLevel          ← core/constants.py              RiskLevel (값 동일)

모델 변경 시 이 파일도 함께 수정해야 합니다.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ============================================================
# 공통 열거형 — core/constants.py RiskLevel 대응
# ============================================================


class RiskLevel(str, Enum):
    """
    위험도 — core/constants.py RiskLevel과 값 동일.

    GasData.max_risk_level / dummy_sender의 status 필드에 사용.
    """

    NORMAL = "normal"
    WARNING = "warning"
    DANGER = "danger"


# ============================================================
# 공통 서브모델
# ============================================================


class Location(BaseModel):
    """
    도면 픽셀 좌표 — DeviceBase.x / DeviceBase.y 대응.

    DB 저장 시 x, y 개별 컬럼으로 분리됩니다.
    """

    x: float
    y: float


# ============================================================
# 기기 정보 페이로드 — POST /api/sensors/info
# DeviceBase + GasSensor 대응
# ============================================================


class DeviceInfoPayload(BaseModel):
    """
    부팅 시 1회 수신하는 기기 등록 페이로드.

    필드 대응:
      device_id        → DeviceBase.device_id        CharField(max_length=50, unique=True)
      device_name      → DeviceBase.device_name       CharField(max_length=100)
      software_version → 프로토콜 전용 (DB 미저장)
      location.x/y     → DeviceBase.x / DeviceBase.y  FloatField
    """

    device_id: str = Field(max_length=50)
    device_name: str = Field(max_length=100)
    software_version: str  # 프로토콜 전용 필드 (GasSensor 모델에 없음)
    location: Location


# ============================================================
# 가스 환경 데이터 페이로드 — POST /api/sensors/gas
# GasData 대응
# ============================================================


class GasDataPayload(BaseModel):
    """
    1초마다 수신하는 가스 센서 측정값 페이로드.

    필드 대응:
      timestamp    → GasData.measured_at          DateTimeField
      device_id    → GasData.gas_sensor(FK).device_id
      device_name  → GasData.gas_sensor(FK).device_name
      location.x/y → GasData.gas_sensor(FK).x / .y
      co ~ voc     → GasData.co ~ voc             FloatField(null=True) → Optional[float]
      lel          → GasTypeChoices.LEL 정의됨, GasData 컬럼 없음 (raw_payload 보관용)
      status       → GasData.max_risk_level        RiskLevel.choices
    """

    timestamp: datetime
    device_id: str = Field(max_length=50)
    device_name: str = Field(max_length=100)
    location: Location

    # 가스 9종 — GasData 개별 컬럼과 1:1 대응 (null=True → Optional)
    co: Optional[float] = None  # 일산화탄소 (ppm)
    h2s: Optional[float] = None  # 황화수소 (ppm)
    co2: Optional[float] = None  # 이산화탄소 (ppm)
    o2: Optional[float] = None  # 산소 (%)
    no2: Optional[float] = None  # 이산화질소 (ppm)
    so2: Optional[float] = None  # 이산화황 (ppm)
    o3: Optional[float] = None  # 오존 (ppm)
    nh3: Optional[float] = None  # 암모니아 (ppm)
    voc: Optional[float] = None  # 휘발성유기화합물 (ppm)

    # LEL — GasTypeChoices.LEL로 정의되어 있으나 GasData 컬럼 없음
    # raw_payload 보관 목적으로 수신만 허용
    lel: Optional[float] = None  # 폭발하한계 (%)

    # 전체 위험도 — GasData.max_risk_level 대응
    status: RiskLevel = RiskLevel.NORMAL
