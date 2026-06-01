"""
FastAPI 수신 페이로드 Pydantic 스키마.

에어위드 HTTP 프로토콜 v1.0.1 기준 + 확장 필드 정의.
"""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from core.gas_thresholds import calculate_gas_status


class SensorLocation(BaseModel):
    """지오펜스 연산용 픽셀 좌표 (설비 도면 기준)."""

    x: float
    y: float


# 기기 정보 (부팅 시 1회) → POST /api/sensors/info
class DeviceInfoPayload(BaseModel):
    """
    기기 부팅 시 1회 전송하는 식별 정보.

    프로토콜 원본 필드: device_id, device_name, software_version
    확장 필드: location (지오펜스 좌표)

    Note: device_name은 프로토콜상 mac address와 동일하게 전송됨.
          불필요 시 팀 확인 후 제거 가능.
    """

    device_id: str
    device_name: str
    software_version: str
    location: SensorLocation


# 기기 환경 데이터 (1초마다) → POST /api/sensors/gas
class GasDataPayload(BaseModel):
    """
    가스 센서 실시간 측정값.

    프로토콜 원본 필드: device_id, o2, co, co2, h2s, lel
    확장 필드: no2, so2, o3, nh3, voc, location, status, timestamp

    단위
    - o2  : % (정상 범위 18.0 ~ 23.5)
    - lel : % (폭발하한계, 임계치 미정의 — 수집만 함)
    - 나머지 : ppm

    status는 수신 값을 무시하고 서버에서 가스값 기준으로 재계산한다.
    """

    timestamp: datetime
    device_id: str
    device_name: str
    location: SensorLocation

    # 가스 9종 + LEL
    o2: float = Field(ge=0, le=100)
    co: float = Field(ge=0)
    co2: float = Field(ge=0)
    h2s: float = Field(ge=0)
    lel: float = Field(
        ge=0, le=100, description="폭발하한계 (%) — 임계치 미정의, 수집만 함"
    )
    no2: float = Field(ge=0)
    so2: float = Field(ge=0)
    o3: float = Field(ge=0)
    nh3: float = Field(ge=0)
    voc: float = Field(ge=0)

    # 센서 전송값을 초기값으로 받지만 model_validator에서 서버 재계산으로 덮어씀
    status: Literal["normal", "warning", "danger"] = "normal"

    # IF 학습 라벨 — 더미 시뮬레이터에서만 채워서 전송. 운영 센서는 미전송.
    # 값: GasData.AnomalyType code (gas_dummy SCENARIOS 와 1:1).
    # 이 필드가 채워져 있으면 GasData.is_anomaly=True 로 저장된다.
    # Literal 화이트리스트 — 임의 문자열 차단 (DRF 단계 422 회피, fastapi 단에서 cut).
    anomaly_type: Literal["co_leak", "h2s_leak", "fire", "chemical_spill"] | None = None

    @field_validator("timestamp")
    @classmethod
    def ensure_timezone_aware(cls, v: datetime) -> datetime:
        """naive datetime은 UTC로 간주해 timezone-aware로 변환한다."""
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v

    @model_validator(mode="after")
    def recalculate_status(self) -> "GasDataPayload":
        """수신된 가스값으로 status를 서버에서 직접 재계산한다."""
        gas_values = {
            "o2": self.o2,
            "co": self.co,
            "co2": self.co2,
            "h2s": self.h2s,
            "lel": self.lel,
            "no2": self.no2,
            "so2": self.so2,
            "o3": self.o3,
            "nh3": self.nh3,
            "voc": self.voc,
        }
        self.status = calculate_gas_status(gas_values)
        return self


# 응답 스키마 (OpenAPI 자동 문서화용)
class DeviceInfoResponse(BaseModel):
    """기기 식별 정보 수신 확인 응답."""

    received: bool
    device_id: str


class GasDataResponse(BaseModel):
    """가스 측정값 수신 확인 응답.

    status는 서버에서 9가지 가스 임계치를 재평가해 결정.
    추가로 가스별 위험도(`*_risk`: 'normal'/'warning'/'danger')가 동적으로 포함된다.
    """

    model_config = {"extra": "allow"}

    received: bool
    device_id: str
    status: Literal["normal", "warning", "danger"]
