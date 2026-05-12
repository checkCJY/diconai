/* ==========================================================
   ws-conn-banner.js — WebSocket 연결 상태 배너 자동 후킹 (Phase 2 P3)
   ==========================================================
   사용:
     const ws = WSClient.connect('/ws/sensors/', { attachToken: true });
     WsConnBanner.attach(ws);  // #ws-conn-banner 요소가 있으면 자동 후킹

   상태 라벨:
     - 초기: '연결 시도 중...'        (스피너 표시)
     - close: '연결 끊김 — 재연결 중...' (스피너 표시)
     - max_reconnect_attempts: '연결 실패 — 페이지 새로고침이 필요합니다' (스피너 숨김)
     - open: 배너 자체를 숨김
   ========================================================== */

'use strict';

const WsConnBanner = (function () {
  function attach(ws, opts = {}) {
    const bannerId = opts.bannerId || 'ws-conn-banner';
    const banner = document.getElementById(bannerId);
    if (!banner) return;  // 페이지에 배너 없으면 silent skip

    const txt = banner.querySelector('.ws-conn-text');
    const spinner = banner.querySelector('.conn-spinner');

    function show(text, spinning = true) {
      if (txt) txt.textContent = text;
      if (spinner) spinner.style.display = spinning ? '' : 'none';
      banner.style.display = '';
    }
    function hide() {
      banner.style.display = 'none';
    }

    // 초기 상태 — 첫 onOpen 전까지 표시
    show('연결 시도 중...');

    ws.onOpen(() => hide());
    ws.onClose(() => show('연결 끊김 — 재연결 중...'));
    ws.onError((err) => {
      // ws-client.js의 max_reconnect_attempts 시그널만 별도 처리 (포기 상태)
      if (err && err.message === 'max_reconnect_attempts') {
        show('연결 실패 — 페이지 새로고침이 필요합니다', false);
      }
    });
  }

  return { attach };
})();
