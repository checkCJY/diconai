/* ==========================================================
   level-mapper.js — RiskLevel ↔ CSS 클래스 / 한글 라벨 변환 단일화
   ==========================================================
   백엔드 enum: 'danger' / 'warning' / 'normal'
   CSS 클래스 : 'danger' / 'caution' / 'safe'
   한글 라벨   : '위험'  / '주의'    / '정상'

   기존 dashboard/websocket.js, detail/monitoring_workers.js 등에 분산되어
   있던 로컬 매핑을 대체. 새 호출자는 LevelMapper.toCssClass / .toLabel 사용.

   ※ CSS 클래스를 백엔드와 통일하는 옵션 A는 10+ CSS 파일 영향이 커
     별도 sprint로 분리. 본 모듈은 "변환층" 단일화에 한함 (옵션 B).
   ========================================================== */

'use strict';

const LevelMapper = (function () {
  const TO_CSS   = { danger: 'danger', warning: 'caution', normal: 'safe' };
  const TO_LABEL = { danger: '위험',   warning: '주의',    normal: '정상' };
  // text 변종 — '-text' 접미사 패턴이 dashboard.css에 정의됨 (danger-text/caution-text).
  // normal은 색상 강조 없음 → 빈 문자열.
  const TO_TEXT  = { danger: 'danger-text', warning: 'caution-text', normal: '' };

  // 서버가 일부 경로에서 CSS 표기('safe')를 보내는 케이스 보정 — 도메인 enum으로 정규화.
  const NORMALIZE = { safe: 'normal', caution: 'warning' };

  function _normalize(level) {
    if (!level) return 'normal';
    return NORMALIZE[level] || level;
  }

  return {
    toCssClass(level) {
      return TO_CSS[_normalize(level)] || 'safe';
    },
    toLabel(level) {
      return TO_LABEL[_normalize(level)] || '-';
    },
    // 텍스트 강조 클래스 — '<level>-text' 패턴. normal은 빈 문자열.
    toTextClass(level) {
      return TO_TEXT[_normalize(level)] ?? '';
    },
    normalize: _normalize,
  };
})();
