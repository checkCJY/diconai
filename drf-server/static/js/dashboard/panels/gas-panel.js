/* ==========================================================
   gas-panel.js — 유해가스 현황 패널 초기화 (패널 12/13)

   역할:
     - DOMContentLoaded 시 패널 초기 상태(KPI 박스) 설정
     - 실데이터는 WebSocket 수신 후 websocket.js 가 교체
     - 테이블 초기 스켈레톤은 HTML에 정의됨

   의존: dashboard.css (.skeleton, .skel-text, .skel-sm)
   ========================================================== */

'use strict';

document.addEventListener('DOMContentLoaded', () => {
  // KPI 박스: WebSocket 연결 전 "연결 중" 표시
  const gasWorstName = document.getElementById('gasWorstName');
  const gasWorstRisk = document.getElementById('gasWorstRisk');
  if (gasWorstName) gasWorstName.textContent = '연결 중...';
  if (gasWorstRisk) gasWorstRisk.textContent = '-';
});
