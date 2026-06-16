/* ==========================================================
   time-format.js — 시각 표시 형식 단일화 (Phase 2 P5)
   ==========================================================
   페이지마다 toLocaleString / toLocaleTimeString 혼용으로 형식이
   불일치했던 것을 본 헬퍼로 일원화. 모든 시각은 KST 라벨 명시.

   API:
     TimeFormat.abs(input)   → "2026-05-12 14:30:45 KST"  (전체 시각 — 이력·상세 페이지)
     TimeFormat.short(input) → "14:30:45"                  (컴팩트 — 대시보드 당일 알람)
     TimeFormat.rel(input)   → "3분 전"                    (상대 — 모바일·요약 표시)

   입력: ISO 8601 문자열, Date 객체, 또는 epoch ms 모두 허용.
   null/undefined/invalid → '-' 반환 (UI 깨짐 방지).
   ========================================================== */

'use strict';

const TimeFormat = (function () {
  const TZ_LABEL = 'KST';

  function _parse(input) {
    if (input == null) return null;
    const d = input instanceof Date ? input : new Date(input);
    return Number.isFinite(d.getTime()) ? d : null;
  }

  function _pad(n) { return String(n).padStart(2, '0'); }

  return {
    // 전체 시각 + KST 라벨 — 정확한 시각이 필요한 곳
    abs(input) {
      const d = _parse(input);
      if (!d) return '-';
      const y = d.getFullYear();
      const M = _pad(d.getMonth() + 1);
      const D = _pad(d.getDate());
      const h = _pad(d.getHours());
      const m = _pad(d.getMinutes());
      const s = _pad(d.getSeconds());
      return `${y}-${M}-${D} ${h}:${m}:${s} ${TZ_LABEL}`;
    },

    // 시:분:초 — 당일 한정 컴팩트 표시 (대시보드 이벤트 패널)
    short(input) {
      const d = _parse(input);
      if (!d) return '-';
      return `${_pad(d.getHours())}:${_pad(d.getMinutes())}:${_pad(d.getSeconds())}`;
    },

    // 상대 시각 — 모바일/요약 표시
    rel(input) {
      const d = _parse(input);
      if (!d) return '-';
      const diff = Math.max(0, (Date.now() - d.getTime()) / 1000);
      if (diff < 60)    return '방금';
      if (diff < 3600)  return `${Math.floor(diff / 60)}분 전`;
      if (diff < 86400) return `${Math.floor(diff / 3600)}시간 전`;
      return `${Math.floor(diff / 86400)}일 전`;
    },
  };
})();
