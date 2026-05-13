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
    - SENSOR_FAULT       → GasSensor 또는 PowerDevice (시스템 분류, 정책 화면 비노출)

    SENSOR_FAULT는 USER_FACING_ALARM_TYPES에서 제외 — 사용자가 정책으로
    설정하는 알람이 아니라 센서 자체의 통신/오류 상태.
    """

    # 기존 4종 (키/값 변경 없음)
    GAS_THRESHOLD = "gas_threshold", "가스 경보"
    POWER_OVERLOAD = "power_overload", "전력 이상"
    GEOFENCE_INTRUSION = "geofence_intrusion", "위험구역 진입"
    SENSOR_FAULT = "sensor_fault", "센서 이상"

    # 신규 6종 (CJY 화면 요구)
    PPE_VIOLATION = "ppe_violation", "PPE 미착용"
    VR_TRAINING_NOT_DONE = "vr_training_not_done", "VR 교육 미이수"
    SAFETY_CHECK_PENDING = "safety_check_pending", "작업 안전 체크리스트 미완료"
    INSPECTION_SCHEDULED = "inspection_scheduled", "점검 예정"
    BATCH_FAILED = "batch_failed", "배치 실패"
    STORAGE_OVERDUE = "storage_overdue", "보관 주기 실패"

    # T1 IF §2 — IsolationForest 추론 결과 기반 알람.
    # threshold 룰과 결합한 combined_risk 매트릭스로 발화 (PREDICT_WARN/WARNING/DANGER).
    # source FK는 GAS_THRESHOLD/POWER_OVERLOAD 와 동일하게 sensor 모델 사용.
    ANOMALY = "anomaly", "이상 패턴 감지"


# 정책 화면 노출 9종 (SENSOR_FAULT 제외) — AlertPolicy.event_type 선택지
USER_FACING_ALARM_TYPES = [
    AlarmType.GAS_THRESHOLD,
    AlarmType.POWER_OVERLOAD,
    AlarmType.GEOFENCE_INTRUSION,
    AlarmType.PPE_VIOLATION,
    AlarmType.VR_TRAINING_NOT_DONE,
    AlarmType.SAFETY_CHECK_PENDING,
    AlarmType.INSPECTION_SCHEDULED,
    AlarmType.BATCH_FAILED,
    AlarmType.STORAGE_OVERDUE,
    AlarmType.ANOMALY,
]


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
    가스 종류 — 9종 유해가스 (센서 정의서 2026-04-01 기준)

    사용 모델: AlarmRecord.gas_type, Event.gas_type, facilities.Threshold

    [PR-E 변경 — LEL dead code 제거]
    이전: 9종 + LEL = 10종. 그러나 센서 정의서에 LEL 측정값 미포함, threshold/모델 컬럼
    부재로 dead code 상태 → 메모리 `sensor_spec_truth_source.md` 결정 따라 제거.

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


# 로그인 화면 문의처 — 운영 연락처로 변경 필요
CONTACT_INFO = "담당 관리자에게 문의하세요."
