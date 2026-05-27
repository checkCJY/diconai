/* ==========================================================
   app.js — 앱 진입점 (initApp)
   출처: dashboard.js initApp
   의존: auth.js, layout.js, charts.js, map-panel.js,
         websocket.js, alarm-popup.js
   ※ 반드시 모든 모듈 파일이 로드된 후 마지막에 로드되어야 함
   ========================================================== */

'use strict';

// ──────────────────────────────────────────────────────────
// 앱 초기화
// ──────────────────────────────────────────────────────────
async function initApp() {
  await initHeaderAndSNB();

  initCharts();
  // SoT 임계치 fetch — 가스 + 전력. WS 보다 먼저 끝나야 _switchPowerChart 가
  // 채널별 임계치를 올바르게 lookup. 실패 시 fallback 으로 동작.
  await loadDashboardThresholds();
  await MapPanel.init();
  initWebSocket();
  AlarmPopup.init();
  AlarmToast.init();
  EventPanel.init();
  loadMySafetyStatus();
}

// ──────────────────────────────────────────────────────────
// 나의 안전확인 완료 여부 조회 및 상태 텍스트 갱신
// ──────────────────────────────────────────────────────────
async function loadMySafetyStatus() {
  try {
    const res = await Auth.apiFetch('/dashboard/api/safety-status/');
    if (!res.ok) {
      console.warn('[loadMySafetyStatus] http error:', res.status);
      return;
    }
    const data = await res.json();

    const checklistEl = document.getElementById('safety-checklist-status');
    const vrEl        = document.getElementById('safety-vr-status');

    if (checklistEl) {
      checklistEl.textContent = data.checklist_done ? '완료' : '미완료';
      checklistEl.className   = data.checklist_done ? 'done' : 'todo';
    }
    if (vrEl) {
      vrEl.textContent = data.vr_done ? '완료' : '미완료';
      vrEl.className   = data.vr_done ? 'done' : 'todo';
    }
  } catch (e) {
    console.warn('[loadMySafetyStatus] fetch failed:', e);
  }
}

initApp().catch(err => {
  console.error('[app] initialization failed:', err);
});
