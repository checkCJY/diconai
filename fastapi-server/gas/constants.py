# gas/constants.py — 가스 관련 상수 단일 공급원
#
# [M-4] 가스 9종 필드 목록이 broadcast.py / gas_service.py 에 각각 흩어져 있던 것을
# 이 파일에 통합. 필드 추가·제거 시 이 파일 한 곳만 수정하면 된다.
#
# DRF 측 GAS_FIELDS (monitoring/services/gas_alarm.py) 는 별도 패키지이므로
# Python import 공유 불가 — 값이 바뀌면 양측 동시 수정 필요.

# 운영 중인 가스 측정 항목 (lel 제외 — raw_payload 에만 보관).
GAS_FIELDS: tuple[str, ...] = ("co", "h2s", "co2", "o2", "no2", "so2", "o3", "nh3", "voc")

# ARIMA 잔차 피처를 사용하는 가스 항목 (모델이 존재하는 경우에만 적재).
ARIMA_GAS_FIELDS: tuple[str, ...] = ("co", "h2s", "co2")
