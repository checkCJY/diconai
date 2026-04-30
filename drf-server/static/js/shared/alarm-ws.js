// shared/alarm-ws.js — 비대시보드 페이지용 알람 전용 WebSocket 연결
//
// 대시보드(websocket.js)와 달리 가스·전력 DOM 갱신 없이
// alarms[] 배열만 처리해 팝업·토스트를 표시한다.
(function () {
  const WS_URL = 'ws://127.0.0.1:8001/ws/sensors/';
  const RECONNECT_DELAY = 3000;

  function connect() {
    const ws = new WebSocket(WS_URL);

    ws.onmessage = function (event) {
      let data;
      try { data = JSON.parse(event.data); } catch { return; }

      if (!Array.isArray(data.alarms) || data.alarms.length === 0) return;

      data.alarms.forEach(function (alarm) {
        const alarmData = {
          alarm_level:  alarm.risk_level,
          is_new_event: alarm.is_new_event,
          message:      alarm.summary,
          sensor_name:  alarm.source_label,
          timestamp:    new Date().toISOString(),
          gas_type:     alarm.gas_type,
          event_id:     alarm.event_id,
        };
        if (alarm.is_new_event) {
          AlarmPopup.show(alarmData);
          document.dispatchEvent(new CustomEvent('newAlarmEvent', { detail: alarmData }));
        }
        if (alarm.risk_level === 'normal' && typeof AlarmToast !== 'undefined') {
          AlarmToast.show(alarmData);
        }
      });
    };

    ws.onclose = function () {
      setTimeout(connect, RECONNECT_DELAY);
    };
  }

  document.addEventListener('DOMContentLoaded', connect);
})();
