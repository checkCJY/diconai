// shared/alarm-ws.js — 비대시보드 페이지용 알람 전용 WebSocket 연결
//
// 대시보드(websocket.js)와 달리 가스·전력 DOM 갱신 없이
// alarms[] 배열만 처리해 팝업·토스트를 표시한다.
//
// shared/ws-client.js의 WSClient를 사용해 동일 엔드포인트 중복 연결을 방지한다.
// (대시보드와 같은 페이지에 로드되면 WSClient 캐시로 한 연결만 유지됨)
(function () {
  document.addEventListener('DOMContentLoaded', function () {
    const ws = WSClient.connect('/ws/sensors/', { attachToken: true });

    ws.onMessage(function (data) {
      if (!Array.isArray(data.alarms) || data.alarms.length === 0) return;

      data.alarms.forEach(function (alarm) {
        const alarmData = AlarmMapper.fromSensorsAlarm(alarm);
        // event_resolved_at 박힌 RESOLVED 신호도 AlarmPopup.show 로 흘려보내
        // _handleResolved 분기가 같은 event_id 팝업 close + 토스트 처리.
        if (alarm.is_new_event || alarm.event_resolved_at) {
          AlarmPopup.show(alarmData);
        }
        document.dispatchEvent(new CustomEvent('newAlarmEvent', { detail: alarmData }));
        if (alarm.risk_level === 'normal' && typeof AlarmToast !== 'undefined') {
          AlarmToast.show(alarmData);
        }
      });
    });
  });
})();
