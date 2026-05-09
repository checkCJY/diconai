// shared/worker-ws.js — 작업자 개인 알림 전용 WebSocket 연결
//
// 로그인한 작업자가 /ws/worker/{userId}/ 에 연결해
// 지오펜스 진입 알람을 실시간으로 수신한다.
// 의존: auth.js (Auth), ws-client.js (WSClient), alarm-popup.js (AlarmPopup)
(function () {
  document.addEventListener('DOMContentLoaded', async function () {
    const user = await Auth.getMe();
    if (!user || !user.id) return;

    const ws = WSClient.connect('/ws/worker/' + user.id + '/', { attachToken: true });

    ws.onMessage(function (data) {
      if (data.type !== 'worker_alert') return;

      const alarmData = {
        alarm_level:  data.risk_level,
        is_new_event: data.is_new_event,
        message:      data.summary,
        sensor_name:  data.source_label,
        timestamp:    new Date().toISOString(),
        event_id:     data.event_id,
      };
      if (typeof AlarmPopup !== 'undefined') {
        AlarmPopup.show(alarmData);
        document.dispatchEvent(new CustomEvent('newAlarmEvent', { detail: alarmData }));
      }
    });
  });
})();
