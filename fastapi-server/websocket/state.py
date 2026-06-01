# websocket/state.py — 프로세스 공유 상태 (WebSocket 연결 목록만 유지)
#
# 이성현 수정 — 계층 1 Redis 이관으로 broadcast 스냅샷 변수 5개 제거:
#   worker_positions, latest_gas_snapshot, gas_latest, power_latest, scenario_mode
#   → 이관 위치: websocket/snap_store.py (Redis 키)
#
# 현재 이 파일에는 WebSocket 연결 목록만 남는다.
# 연결 목록은 프로세스 메모리에 두는 것이 맞다 — 각 pod의 연결만 관리하면 되기 때문.
# (broadcast 데이터는 Redis 공유, 연결 목록은 각 pod 독립 관리)

from fastapi import WebSocket

# 연결된 브라우저 WebSocket 클라이언트 목록 (broadcast용)
sensor_clients: list[WebSocket] = []

# 작업자 개인 알림용 WebSocket { user_id: WebSocket }
worker_clients: dict[int, WebSocket] = {}
