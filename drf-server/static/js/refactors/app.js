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
  if (!Auth.getAccessToken()) { Auth.redirectLogin(); return; }

  const user = await Auth.getMe();
  if (!user) {
    Header.renderUser(Auth.getUsername() || '-');
    Menu.showError();
  } else {
    Header.renderUser(user.username);
    Header.showAdminBtn(user.role);
    Menu.render(user.menu_tree);
  }

  SNB.init();
  Header.init();
  Header.updateLastUpdated();

  initCharts();
  MapPanel.init();
  initWebSocket();
  AlarmPopup.init();
}

initApp();
