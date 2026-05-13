/* ==========================================================
   alarm-mapper.js — 서버 알람 페이로드 → 클라이언트 형식 변환 단일화
   ==========================================================
   alarm-ws.js / worker-ws.js / dashboard/websocket.js 3곳에 동일 매핑이
   분산되어 있던 것을 단일 모듈로 통합. 백엔드 키 변경 시 본 파일만 갱신하면 됨.

   서버 페이로드 키 출처: fastapi-server/internal/routers/alarm_router.py
   AlarmPayload (alarm_type/risk_level/source_label/summary/is_new_event/
                 event_id/gas_type/...).
   ========================================================== */

'use strict';

const AlarmMapper = (function () {
  function _common(src) {
    return {
      alarm_level:    src.risk_level,
      is_new_event:   src.is_new_event,
      message:        src.summary,
      sensor_name:    src.source_label,
      // 서버 발신 시각 우선(03 R3) — 누락 시 도착 시각으로 fallback
      timestamp:      src.created_at || new Date().toISOString(),
      event_id:       src.event_id,
      // 임계값 컨텍스트 (P2 추가) — 메시지 아래 줄에 "기준 X 초과 (측정 Y)" 표시
      measured_value: src.measured_value,
      threshold_value: src.threshold_value,
      alarm_type:     src.alarm_type,
    };
  }

  return {
    // /ws/sensors/ 채널의 alarms[] 항목용
    fromSensorsAlarm(serverAlarm) {
      return Object.assign(_common(serverAlarm), {
        gas_type: serverAlarm.gas_type,
      });
    },

    // /ws/worker/{id}/ 채널의 worker_alert 메시지용
    fromWorkerAlert(serverData) {
      return _common(serverData);
    },
  };
})();
