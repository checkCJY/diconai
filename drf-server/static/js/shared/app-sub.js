'use strict';

// ──────────────────────────────────────────────────────────
// 서브 페이지 초기화 — 헤더 / SNB만 초기화 (차트·WebSocket 제외)
// 의존: layout.js (initHeaderAndSNB)
// ──────────────────────────────────────────────────────────
async function initApp() {
  await initHeaderAndSNB();
}

initApp().catch(err => {
  console.error('[app-sub] initialization failed:', err);
});
