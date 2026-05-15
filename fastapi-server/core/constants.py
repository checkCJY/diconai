# core/constants.py — fastapi 측 도메인 상수
#
# DRF apps/core/constants.py 의 일부 enum/매핑을 fastapi 환경에 복제. fastapi 는
# Django ORM 비의존 (TextChoices 못 씀) 이라 plain dict/string 으로 정의한다.
# 두 쪽 정의가 어긋나면 알람 흐름 회귀 — 추가 시 양쪽 동시 갱신 필수.

# AI 추론 위험도 → 룰 측 위험도 매핑.
# AI 모델은 4단계 (normal/caution/predict_warn/danger), 룰은 3단계 (normal/warning/
# danger). Step 3 AI mute 마킹에서 "AI 발화 레벨을 룰 단위로 환산 후 키 생성" 의
# 단일 진실 공급원. drf-server/apps/core/constants.py 의 AI_TO_RULE_LEVEL 과 동일
# 값을 유지해야 한다 — fastapi 가 마킹한 Redis 키를 DRF 가 읽어야 하므로.
AI_TO_RULE_LEVEL: dict[str, str] = {
    "normal": "normal",
    "caution": "warning",
    "predict_warn": "warning",
    "danger": "danger",
}
