// shared/worker-ws.js — 작업자 개인 알림 전용 WebSocket 연결
//
// 로그인한 작업자가 /ws/worker/{userId}/ 에 연결해
// 지오펜스 진입 알람을 실시간으로 수신한다.
// 의존: auth.js (Auth), alarm-popup.js (AlarmPopup)
(function () {
  const WS_BASE = 'ws://127.0.0.1:8001/ws/worker/';
  const RECONNECT_DELAY = 3000;
  let _userId = null;
  let _reconnectTimer = null;

  function connect() {
    if (!_userId) return;
    const ws = new WebSocket(WS_BASE + _userId + '/');

    ws.onmessage = function (event) {
      let data;
      try { data = JSON.parse(event.data); } catch { return; }
      if (data.type !== 'worker_alert') return;

      const alarmData = {
        alarm_level:  data.risk_level,
        is_new_event: data.is_new_event,
        message:      data.summary,
        sensor_name:  data.source_label,
        timestamp:    new Date().toISOString(),
        event_id:     data.event_id,
      };
      if (typeof AlarmPopup !== 'undefined') AlarmPopup.show(alarmData);
    };

    ws.onclose = function () {
      _reconnectTimer = setTimeout(connect, RECONNECT_DELAY);
    };
  }

  document.addEventListener('DOMContentLoaded', async function () {
    const user = await Auth.getMe();
    if (!user || !user.id) return;
    _userId = user.id;
    connect();
  });
})();
