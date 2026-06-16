"""
전력 임계치 기준 — FastAPI 측 표시용 fallback.
단위: W (와트), Phase A 기준

[단일 진실 공급원 정책 — Phase 4 회귀 점검 fix]
실제 알람 판정 + DB 저장은 DRF가 담당:
  - DRF 측 진실 공급원: facilities.Threshold(group_code="power_default", item="power_w")
  - alerts/tasks.py + monitoring/views/power_data.py + threshold_service.py 모두 DB 조회
  - 어드민에서 운영자가 caution/danger/chart_max 직접 수정 가능

본 파일의 POWER_THRESHOLDS는 power_service.build_equipment()의 채널별
risk_level 표시용 fallback. WebSocket 페이로드에만 포함되며 DB 저장 대상 아님.
DRF GasData.save() 패턴과 일관: fastapi 측 risk는 표시용, DRF가 단일 진실 공급원.

값은 core.config.Settings의 POWER_THRESHOLD_CAUTION / POWER_THRESHOLD_DANGER env로
주입. 운영 시 DRF Threshold DB와 env 동기화 의무 (양측 갱신).

[운영 진입 시 검토 사항]
- DRF API (`/monitoring/api/power/thresholds/`) 호출 캐시로 자동 동기화 옵션 검토
- 또는 펌웨어 합의 트랙과 묶어 진실 공급원 통합 정책 재결정
"""

from core.config import settings

POWER_THRESHOLDS: dict = {
    "caution": settings.POWER_THRESHOLD_CAUTION,
    "danger": settings.POWER_THRESHOLD_DANGER,
}

# 추론 측 sensor_fault_overflow 검출용 절대 상한.
# 현실적으로 도달 불가능한 값 (펌웨어/센서 오버플로우 99999 같은 일탈 신호) 을
# IF 학습/추론에서 배제하기 위해 사용. 채널 정격 최댓값(CHANNEL_RATED) 의
# 안전 마진 위로 설정. 본 임계치는 raw 데이터 저장에는 영향 없음.
# 추론 quality_guard 진입부에서만 참조 (power.services.quality_guard).
UPPER_BOUND_BY_TYPE: dict[str, float] = {
    "watt": 50000.0,
    "current": 200.0,
    "voltage": 600.0,
}
