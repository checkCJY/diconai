/* ==========================================================
   map_detail.js — 실시간 모니터링 상세 페이지 초기화
   의존: layout.js, auth.js, map-panel.js, alarm-popup.js, websocket.js
   ========================================================== */
'use strict';

async function initApp() {
  await initHeaderAndSNB();
  await MapPanel.init();
  AlarmPopup.init();
  initWebSocket();

  _initLayerToggles();
  _initFocusBtn();
  _initLegendToggle();
  _initTimeline();
}

/* ── 레이어 ON/OFF 토글 ── */
function _initLayerToggles() {
  document.querySelectorAll('.rt-toggle[data-layer-key]').forEach(btn => {
    btn.addEventListener('click', () => {
      const key = btn.dataset.layerKey;
      const layer = MapPanel.layers[key];
      if (!layer) return;

      if (btn.classList.contains('on')) {
        MapPanel.map.removeLayer(layer);
        btn.classList.replace('on', 'off');
        btn.textContent = 'OFF';
      } else {
        MapPanel.map.addLayer(layer);
        btn.classList.replace('off', 'on');
        btn.textContent = 'ON';
      }
    });
  });
}

/* ── 전체 맞춤 버튼 ── */
function _initFocusBtn() {
  const btn = document.getElementById('btn-focus-all');
  if (btn) btn.addEventListener('click', () => MapPanel.recenter());
}

/* ── 범례 패널 토글 ── */
function _initLegendToggle() {
  const btn    = document.getElementById('btn-toggle-legend');
  const panel  = document.getElementById('rt-legend-panel');
  if (!btn || !panel) return;

  btn.addEventListener('click', () => {
    const hidden = panel.style.display === 'none';
    panel.style.display = hidden ? '' : 'none';
    btn.style.background = hidden ? 'var(--accent)' : '';
    btn.style.color      = hidden ? '#fff' : '';
    btn.style.borderColor= hidden ? 'var(--accent)' : '';
  });
}

/* ── AI 타임라인 드래그 ── */
function _initTimeline() {
  const track = document.querySelector('.rt-timeline-track');
  const fill  = document.getElementById('rt-timeline-fill');
  const thumb = document.getElementById('rt-timeline-thumb');
  const badge = document.getElementById('rt-timeline-badge');
  if (!track) return;

  let dragging = false;

  function updateAt(clientX) {
    const rect = track.getBoundingClientRect();
    let pct = (clientX - rect.left) / rect.width;
    pct = Math.max(0, Math.min(1, pct));
    const minutes = Math.round(pct * 20);
    fill.style.width  = (pct * 100) + '%';
    thumb.style.left  = (pct * 100) + '%';
    badge.textContent = minutes === 0 ? '현재 시점' : `현재 +${minutes}분`;
  }

  track.addEventListener('mousedown', e => { dragging = true; updateAt(e.clientX); });
  document.addEventListener('mousemove', e => { if (dragging) updateAt(e.clientX); });
  document.addEventListener('mouseup', () => { dragging = false; });
}

initApp();
