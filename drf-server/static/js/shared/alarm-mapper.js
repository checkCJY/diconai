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
      // [Step 3-4] 백엔드가 AlarmRecord.get_short_message() 결과를 message 필드로
      // 보냄 (API serializer 와 동일 텍스트). 구버전 payload 호환을 위해 summary
      // (긴 운영자 안내문) fallback 유지 — alarm-popup.js:183/284 도 같은 패턴.
      message:        src.message || src.summary,
      sensor_name:    src.source_label,
      // 서버 발신 시각 우선(03 R3) — 누락 시 도착 시각으로 fallback
      timestamp:      src.created_at || new Date().toISOString(),
      event_id:       src.event_id,
      // 임계값 컨텍스트 (P2 추가) — 메시지 아래 줄에 "기준 X 초과 (측정 Y)" 표시
      measured_value: src.measured_value,
      threshold_value: src.threshold_value,
      alarm_type:     src.alarm_type,
      // 2026-05-15 알람 재설계: RESOLVED 신호 (update_status PATCH 시 박힘).
      // AlarmPopup._handleResolved 가 이 필드를 받으면 같은 event_id 팝업 close + 토스트.
      event_resolved_at: src.event_resolved_at || null,
      // T3 (2026-05-19) — 다중 관리자 환경에서 EventAck 한 사용자명 list.
      // 토스트·모달 본문에 "(N 확인 중)" 시그널 표시. dedup 과 분리 유지 (안전망).
      event_ack_users: Array.isArray(src.event_ack_users) ? src.event_ack_users : [],
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
