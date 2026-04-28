# core/constants.py
from django.db import models


class RiskLevel(models.TextChoices):
    """
    위험도 — 전 시스템 공통

    사용 모델: GasData, PowerData, GeoFence, AlarmRecord, Event, Notification
    프론트엔드: JSON 값 그대로 CSS 클래스로 매핑 가능
    """

    NORMAL = "normal", "정상"
    WARNING = "warning", "주의"
    DANGER = "danger", "위험"
    # 4차 추가 예정: CRITICAL = 'critical', '긴급'


class EventStatus(models.TextChoices):
    """
    이벤트 상태 — alerts 앱 전용

    상태 전환 흐름:
    active → acknowledged → in_progress → resolved
    """

    ACTIVE = "active", "발생"
    ACKNOWLEDGED = "acknowledged", "확인"
    IN_PROGRESS = "in_progress", "조치중"
    RESOLVED = "resolved", "완료"


class AlarmType(models.TextChoices):
    """
    알람 유형 — AlarmRecord, Event 공유

    각 유형별로 사용하는 source FK가 다름:
    - GAS_THRESHOLD      → GasSensor
    - POWER_OVERLOAD     → PowerDevice
    - GEOFENCE_INTRUSION → GeoFence + CustomUser (worker)
    - SENSOR_FAULT       → GasSensor 또는 PowerDevice
    """

    GAS_THRESHOLD = "gas_threshold", "가스 임계치 초과"
    POWER_OVERLOAD = "power_overload", "전력 과부하"
    GEOFENCE_INTRUSION = "geofence_intrusion", "위험구역 진입"
    SENSOR_FAULT = "sensor_fault", "센서 오류"


class UserType(models.TextChoices):
    """
    사용자 유형 — accounts.CustomUser 전용

    - SUPER_ADMIN    : 전체 공장 관리 (facility=NULL 허용)
    - FACILITY_ADMIN : 소속 공장 관리자
    - WORKER         : 내부 직원 (백오피스·현장)
    - VIEWER         : 열람 전용 — 외부 방문자 (견학객, 파견 점검자 등)
    """

    SUPER_ADMIN = "super_admin", "슈퍼관리자"
    FACILITY_ADMIN = "facility_admin", "관리자"
    WORKER = "worker", "일반사용자"
    VIEWER = "viewer", "열람자"


class SensorStatus(models.TextChoices):
    """
    센서 통신 상태 — PowerData.sensor_status 전용

    ACTIVE      : 정상 측정 중
    COMM_FAILURE: 통신 불능 (-1 수신, value=NULL 저장)
    """

    ACTIVE = "active", "정상"
    COMM_FAILURE = "comm_failure", "통신 불능"


class GasTypeChoices(models.TextChoices):
    """
    가스 종류 — 9종 유해가스 + LEL

    사용 모델: AlarmRecord.gas_type, Event.gas_type, (4차) LegalThreshold, FacilityThreshold

    법적 근거: 산업안전보건기준에 관한 규칙 제618조 (밀폐공간 공기 상태)
    """

    CO = "co", "CO (일산화탄소)"
    H2S = "h2s", "H2S (황화수소)"
    CO2 = "co2", "CO2 (이산화탄소)"
    O2 = "o2", "O2 (산소)"
    NO2 = "no2", "NO2 (이산화질소)"
    SO2 = "so2", "SO2 (이산화황)"
    O3 = "o3", "O3 (오존)"
    NH3 = "nh3", "NH3 (암모니아)"
    VOC = "voc", "VOC (휘발성유기화합물)"
    LEL = "lel", "LEL (폭발하한계)"


# 전력 임계치 (단위: W) — Phase A 기준
# caution: 정상→주의 경계, danger: 주의→위험 경계 (caution × 1.3), maxY: 차트 Y축 기본 최대값
POWER_THRESHOLDS: dict = {
    "caution": 2200,
    "danger": 2860,
    "maxY": 3500,
    "unit": "W",
}

# 로그인 화면 문의처 — 운영 연락처로 변경 필요
CONTACT_INFO = "담당 관리자에게 문의하세요."
