# websocket/state.py — 프로세스 공유 상태
# 모든 라우터가 이 모듈을 import해 직접 읽고 씀.
# HTTP /internal/* 엔드포인트 없이 상태를 공유한다.
from fastapi import WebSocket

# 연결된 브라우저 WebSocket 클라이언트 목록
sensor_clients: list[WebSocket] = []

# 작업자 최신 위치 { worker_id: { x, y, facility_id, updated_at } }
worker_positions: dict[int, dict] = {}

# 가스 알람 이벤트 큐 — gas_service가 push, broadcast가 소비 후 비움
active_alarms: list[dict] = []

# 최신 가스 측정 스냅샷 — gas_service가 갱신, broadcast가 페이로드에 spread
latest_gas_snapshot: dict = {}

# 가스 스냅샷 최종 갱신 시각 — broadcast의 stale 판단에 사용
gas_latest: dict = {"updated_at": None}

# 전력 최신값 — power_service가 갱신, broadcast가 equipment[] 조립에 사용
power_latest: dict = {
    "onoff": {},
    "current": {},
    "voltage": {},
    "watt": {},
    "updated_at": None,
}
