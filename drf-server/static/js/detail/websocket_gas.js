/* ──────────────────────────────────────────────────────────
   websocket_gas.js  —  실시간/AI 예측 유해가스 현황
   WebSocket 연결 → gas_monitoring.js 렌더 함수 연동

   수신 페이로드 (ws://127.0.0.1:8002/ws/sensors/):
     co, h2s, co2, o2, no2, so2, o3, nh3, voc  — 측정값
     co_risk, h2s_risk, ...                      — 위험도
   ────────────────────────────────────────────────────────── */

'use strict';

const GAS_WS_URL = 'ws://127.0.0.1:8001/ws/sensors/';

function initGasWebSocket() {
  function connect() {
    let ws;
    try {
      ws = new WebSocket(GAS_WS_URL);
    } catch {
      updateGasPage({}, false);
      return;
    }

    ws.onmessage = (e) => {
      let data;
      try { data = JSON.parse(e.data); } catch { return; }

      // gas snapshot 필드가 없으면(더미 틱) 스킵하지 않고 있는 값만 넘김
      updateGasPage(data, true);
    };

    ws.onerror = () => updateGasPage({}, false);

    ws.onclose = () => {
      updateGasPage({}, false);
      setTimeout(connect, 3000);
    };
  }

  connect();
}

document.addEventListener('DOMContentLoaded', () => {
  initGasWebSocket();
});
