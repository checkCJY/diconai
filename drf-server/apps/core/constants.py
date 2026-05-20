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
    # source FK 는 POWER_OVERLOAD 와 동일하게 PowerDevice 사용.
    # 도메인별 분리: gas_anomaly_ai 는 가스 트랙에서 별도 enum 추가 예정 (현재 미정의 anti-pattern).
    POWER_ANOMALY_AI = "power_anomaly_ai", "전력 AI 이상 감지"
    # 이성현 추가 — 가스 AI 이상탐지 알람 타입
    GAS_ANOMALY_AI = "gas_anomaly_ai", "가스 AI 이상 감지"


# AI 알람 algorithm_source 코드 → 운영자 친화 한국어 라벨 매핑.
# get_short_message / push_payload 양쪽 표시 통일 (단일 진실 공급원).
# 본 dict 에 없는 algorithm_source 는 fallback 으로 코드값 그대로 표시.
ALGORITHM_SOURCE_LABEL: dict[str, str] = {
    "isolation_forest": "IF",
    "arima": "ARIMA",
    "combined": "IF+ARIMA",
    "night_abnormal": "야간 가동",
    # §F — 5축 정책 엔진 도입 (plan power-zscore-changepoint-apply §F).
    # STEP 5 키워드 직접 노출 — fastapi 측 _ALGORITHM_SOURCE_LABEL 와 단일 동기화.
    "zscore": "Z-score",
    "change_point": "급변",
}


# T1+T6 (2026-05-19) — algorithm_source 코드 → 운영자 친화 워딩.
# 칩·아이콘 없이 텍스트만으로 알고리즘 본질 구분 가능하도록 각 알고리즘 동작을 반영.
# - IF (Isolation Forest) = 분포 outlier → "이상 수치 탐지"
# - ARIMA = 시계열 예측 잔차 → "이상 패턴 탐지"
# - Z-score = sliding window 통계 → "통계 이상 수치"
# - Change Point = 변화점 검출 → "패턴 변화 탐지"
# - combined = IF+ARIMA 동시 발화 (최고 신뢰도) → "이상 수치·패턴 동시 탐지"
# - night_abnormal = 운영 시간 외 baseline 초과 → "야간 이상 가동"
# 룰 기반 (power_overload) = "정적 임계치 초과" — ML 의 동적 탐지와 구분.
# fastapi-server/power/services/power_service.py 와 단일 동기화.
ALGORITHM_SOURCE_PHRASE: dict[str, str] = {
    "isolation_forest": "이상 수치 탐지",
    "arima": "이상 패턴 탐지",
    "combined": "이상 수치·패턴 동시 탐지",
    "zscore": "통계 이상 수치",
    "change_point": "패턴 변화 탐지",
    "night_abnormal": "야간 이상 가동",
}


# T4 — AlarmRecord.source + push_payload.source 단일 진실 공급원.
# algorithm_source (AI 안 알고리즘 출처: IF/ARIMA/...) 와 직교 차원.
# "검출 주체가 AI 냐 정적룰이냐" 1차원만 표현.
#
# STATIC_LEGACY 는 T4 도입 전 데이터 backfill 전용 — 신규 알람에 사용 금지.
# decide_alarm 매트릭스 (D2) 는 STATIC_LEGACY 를 결과로 반환하지 않는다.
class AlarmSource(models.TextChoices):
    AI = "ai", "AI"
    STATIC_COVER_MISS = "static_cover_miss", "정적 보완 (AI 미탐 의심)"
    STATIC_COVER_INFERENCE_FAIL = (
        "static_cover_inference_fail",
        "정적 보완 (AI 추론 실패)",
    )
    STATIC_COVER_WARMUP = "static_cover_warmup", "정적 보완 (AI 워밍업)"
    STATIC_NO_AI_AVAILABLE = "static_no_ai_available", "정적 (AI 비활성 채널)"
    STATIC_LEGACY = "static_legacy", "정적 (T4 전 데이터)"


# source 별 운영자 친화 reason 문구 — push_payload.reason 필드 + 모달 사유 텍스트.
# None 인 source 는 reason 표시 생략 (일반 알람과 동일 톤).
# fastapi-server 측 동일 dict 와 단일 동기 — 키 변경 시 양쪽 갱신 필수.
ALARM_SOURCE_REASON: dict[str, str | None] = {
    "ai": None,
    "static_cover_miss": "AI 미탐 의심 — 정적 임계치 초과",
    "static_cover_inference_fail": "AI 추론 실패 보완",
    "static_cover_warmup": "AI 윈도우 빌드 중 — 정적룰 보완",
    "static_no_ai_available": None,
    "static_legacy": None,
}


# source 별 토스트·모달 배지 라벨 (프론트 분기용).
# 빈 문자열인 source 는 배지 미표시 — D4 alarm-popup.js 가 truthy 체크로 분기.
ALARM_SOURCE_BADGE: dict[str, str] = {
    "ai": "",
    "static_cover_miss": "AI 미탐 의심",
    "static_cover_inference_fail": "AI 추론 실패 보완",
    "static_cover_warmup": "AI 준비 중 보완",
    "static_no_ai_available": "",
    "static_legacy": "",
}


# source 별 CSS 시각 톤 키 — 프론트 alarm-popup / event-panel 분기 (D4).
# - "risk"  : 기존 risk_level 분기 (danger=빨강 / warning=노랑) 그대로
# - "cover" : 노랑 + .cover-badge (보조 알람 — 운영자 인지 톤 1단계 약화)
ALARM_SOURCE_TONE: dict[str, str] = {
    "ai": "risk",
    "static_cover_miss": "cover",
    "static_cover_inference_fail": "cover",
    "static_cover_warmup": "cover",
    "static_no_ai_available": "risk",
    "static_legacy": "risk",
}


# AI 추론 위험도 → 룰 측 RiskLevel 매핑.
# AI 모델은 4단계(normal/caution/predict_warn/danger), 룰은 3단계(normal/warning/danger).
# Step 3 AI mute 가드에서 "AI 발화 레벨 이상의 룰 fire 를 60s suppress" 로직의 단일
# 진실 공급원. 곳곳에 암묵 매핑이 박히면 회귀 — predict_warn 이 warning 인지 danger
# 인지 의견 갈리는 순간 dedup 키 충돌·격상 bypass 깨짐.
# W4 — 동일 dict 가 2회 정의되어 있던 것을 단일로 정리 (ARIMA un-downgrade plan §8).
AI_TO_RULE_LEVEL: dict[str, str] = {
    "normal": RiskLevel.NORMAL.value,
    "caution": RiskLevel.WARNING.value,
    "predict_warn": RiskLevel.WARNING.value,
    "danger": RiskLevel.DANGER.value,
}


# 정책 화면 노출 9종 (SENSOR_FAULT 제외) — AlertPolicy.event_type 선택지
USER_FACING_ALARM_TYPES = [
    AlarmType.GAS_THRESHOLD,
    AlarmType.POWER_OVERLOAD,
    AlarmType.GEOFENCE_INTRUSION,
    AlarmType.PPE_VIOLATION,
    AlarmType.VR_TRAINING_NOT_DONE,
    AlarmType.SAFETY_CHECK_PENDING,
    AlarmType.INSPECTION_SCHEDULED,
    AlarmType.GAS_ANOMALY_AI,  # 이성현 추가
    AlarmType.BATCH_FAILED,
    AlarmType.STORAGE_OVERDUE,
    AlarmType.POWER_ANOMALY_AI,
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
