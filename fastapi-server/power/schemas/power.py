"""
FastAPI 전력 수신 페이로드 스키마.

DRF 모델과의 대응 관계:
  PowerOnOffPayload       ← monitoring/models/power_event.py  PowerEvent
  PowerMeasurementPayload ← monitoring/models/power_data.py   PowerData
  (device_id 공통)        ← facilities/models/devices.py      PowerDevice.device_id

[필드 갭 정리]
더미 → 모델 변환 시 FastAPI 라우터에서 처리해야 할 항목:
  - slave01~slave72 키  → PowerEvent.snapshot 키 "1"~"16" (1-based 정수 문자열)
  - ON/OFF 값 0/255     → bool (255=True, 0=False)
  - slave01~slave72 키  → PowerData.channel 정수 (1~16)
  - risk_level 없음     → FastAPI에서 임계치 기준으로 계산
  - trigger 없음        → PowerEvent.Trigger.UNKNOWN 기본값 사용
  - changed_channels 없음 → 직전 스냅샷과 비교해 FastAPI에서 계산

[시계열 주의사항]
  - timestamp는 항상 timezone-aware(UTC)로 전송해야 합니다.
    라우터에서 fallback이 필요하면 datetime.now(timezone.utc) 사용.
    datetime.now() (naive) 사용 금지 — PostgreSQL USE_TZ=True 환경에서 시계열 오염.
  - value == -1 채널(통신 불능)도 DB에 저장됩니다.
    통계·집계 쿼리에서는 반드시 WHERE value != -1 조건을 추가해야 합니다.

모델 변경 시 이 파일도 함께 수정해야 합니다.
"""

from pydantic import BaseModel, Field


# 채널 슬레이브 키 목록 — power_dummy_sender.py POWER_CHANNELS 와 동일
SLAVE_KEYS: list[str] = [
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

# slave 키 → 채널 번호(1-based) 매핑
SLAVE_TO_CHANNEL: dict[str, int] = {key: idx + 1 for idx, key in enumerate(SLAVE_KEYS)}


# ON/OFF 상태 페이로드 — POST /api/power/onoff → PowerEvent 대응
#
# 필드 대응:
#   device_id        → PowerDevice.device_id
#   timestamp        → PowerEvent.measured_at (장치 측정 시각, UTC 필수)
#   slave01~slave72  → PowerEvent.snapshot  {"1": bool, ..., "16": bool}
#                      값 변환: 255 → True, 0 → False
#
# 모델에 있으나 페이로드에 없는 필드:
#   PowerEvent.trigger          → 기본값 "unknown" 사용
#   PowerEvent.changed_channels → 직전 스냅샷과 비교해 FastAPI에서 계산
#   PowerEvent.created_at       → auto_now_add (수신 시각, 자동)
class PowerOnOffPayload(BaseModel):
    """
    16채널 ON/OFF 상태 스냅샷 페이로드.

    프로토콜 규정값: 255 = ON, 0 = OFF
    """

    device_id: str = Field(max_length=50)

    # 16채널 ON/OFF (프로토콜 규정: 255=ON, 0=OFF)
    slave01: int = Field(ge=0, le=255)
    slave02: int = Field(ge=0, le=255)
    slave11: int = Field(ge=0, le=255)
    slave12: int = Field(ge=0, le=255)
    slave21: int = Field(ge=0, le=255)
    slave22: int = Field(ge=0, le=255)
    slave31: int = Field(ge=0, le=255)
    slave32: int = Field(ge=0, le=255)
    slave41: int = Field(ge=0, le=255)
    slave42: int = Field(ge=0, le=255)
    slave51: int = Field(ge=0, le=255)
    slave52: int = Field(ge=0, le=255)
    slave61: int = Field(ge=0, le=255)
    slave62: int = Field(ge=0, le=255)
    slave71: int = Field(ge=0, le=255)
    slave72: int = Field(ge=0, le=255)

    def to_snapshot(self) -> dict[str, bool]:
        """
        PowerEvent.snapshot 형식으로 변환.

        {"1": bool, ..., "16": bool} — 키: 1-based 채널 번호 문자열, 값: ON/OFF bool
        """
        return {
            str(SLAVE_TO_CHANNEL[key]): getattr(self, key) == 255 for key in SLAVE_KEYS
        }


# 전력 측정값 공통 베이스 — PowerData 대응
#
# 필드 대응:
#   device_id        → PowerDevice.device_id
#   slave01~slave72  → PowerData.channel(1~16) + PowerData.value
#                      정규화: 16행으로 분리 저장 (long-format)
#
# 모델에 있으나 페이로드에 없는 필드:
#   PowerData.data_type  → 각 서브클래스에서 고정값으로 결정
#   PowerData.risk_level → FastAPI에서 임계치 기준으로 계산
class _PowerMeasurementBase(BaseModel):
    """16채널 측정값 페이로드 공통 베이스."""

    device_id: str = Field(max_length=50)

    # -1: 해당 포트 통신 불능 (프로토콜 규정) — DB에 그대로 저장됨
    # 집계 쿼리에서 WHERE value != -1 조건 필수
    slave01: float = Field(ge=-1)
    slave02: float = Field(ge=-1)
    slave11: float = Field(ge=-1)
    slave12: float = Field(ge=-1)
    slave21: float = Field(ge=-1)
    slave22: float = Field(ge=-1)
    slave31: float = Field(ge=-1)
    slave32: float = Field(ge=-1)
    slave41: float = Field(ge=-1)
    slave42: float = Field(ge=-1)
    slave51: float = Field(ge=-1)
    slave52: float = Field(ge=-1)
    slave61: float = Field(ge=-1)
    slave62: float = Field(ge=-1)
    slave71: float = Field(ge=-1)
    slave72: float = Field(ge=-1)

    # IF 학습 라벨링 — 더미 시뮬레이터에서만 채워서 전송. 운영 장비는 미전송.
    # 키: 채널 번호(1~16) 문자열, 값: AnomalyType code (overload/voltage_drop/...)
    # 채널 키가 anomaly_labels 에 있으면 PowerData.is_anomaly=True 로 저장된다.
    anomaly_labels: dict[str, str] | None = None

    def to_channel_values(self) -> dict[int, float | None]:
        """채널 번호(1~16) → 측정값 매핑으로 변환. 통신 불능(-1)은 None으로 변환."""
        return {
            SLAVE_TO_CHANNEL[key]: None
            if getattr(self, key) == -1
            else getattr(self, key)
            for key in SLAVE_KEYS
        }

    def to_anomaly_map(self) -> dict[int, str]:
        """anomaly_labels 를 채널 번호 키로 변환."""
        if not self.anomaly_labels:
            return {}
        return {int(k): v for k, v in self.anomaly_labels.items()}


# 전류 페이로드 — POST /api/power/current → PowerData(data_type="current"), 단위 A
class PowerCurrentPayload(_PowerMeasurementBase):
    """16채널 전류(A) 측정값 페이로드."""

    pass


# 전압 페이로드 — POST /api/power/voltage → PowerData(data_type="voltage"), 단위 V
class PowerVoltagePayload(_PowerMeasurementBase):
    """16채널 전압(V) 측정값 페이로드."""

    pass


# 전력 페이로드 — POST /api/power/watt → PowerData(data_type="watt"), 단위 W
class PowerWattPayload(_PowerMeasurementBase):
    """16채널 전력(W) 측정값 페이로드."""

    pass


# 응답 스키마 (OpenAPI 자동 문서화용)
class PowerIngestResponse(BaseModel):
    """전력 측정값 수신 확인 응답.

    `updated`는 어떤 측정 타입이 갱신되었는지 나타낸다 — onoff/current/voltage/watt.
    """

    status: str
    updated: str
