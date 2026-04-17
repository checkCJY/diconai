/* ==========================================================
   worker-panel.js — MN-04 작업자 현황 패널
   출처: dashboard.js initMN04 IIFE (CJY.js)
   user_type: 'admin' → D View(KPI 카드), 그 외 → B View(상태 바)
   ========================================================== */

'use strict';

// ──────────────────────────────────────────────────────────
// MN-04 — 작업자 현황 패널
// ──────────────────────────────────────────────────────────
(function initMN04() {
  const POLL_MS            = 30_000;
  const API_MY_STATUS      = '/api/alarms/my-status/';
  const API_WORKER_SUMMARY = '/api/alarms/worker-summary/';

  const STATUS_CONFIG = {
    normal:  { left: '16%', color: '#2d9e75', label: '정상' },
    warning: { left: '50%', color: '#ef9f27', label: '경고' },
    danger:  { left: '84%', color: '#e24b4a', label: '위험' },
  };

  const viewWorker = document.getElementById('mn04-view-worker');
  const viewAdmin  = document.getElementById('mn04-view-admin');
  const elMarker      = document.getElementById('mn04-marker');
  const elStatusText  = document.getElementById('mn04-status-text');
  const elWorkerErr   = document.getElementById('mn04-worker-error');
  const elTotal       = document.getElementById('mn04-kpi-total');
  const elNormal      = document.getElementById('mn04-kpi-normal');
  const elWarning     = document.getElementById('mn04-kpi-warning');
  const elDanger      = document.getElementById('mn04-kpi-danger');
  const elRatioBar    = document.getElementById('mn04-ratio-bar');
  const elRatioNormal = document.getElementById('mn04-ratio-normal');
  const elRatioWarn   = document.getElementById('mn04-ratio-warning');
  const elRatioDanger = document.getElementById('mn04-ratio-danger');
  const elAdminErr    = document.getElementById('mn04-admin-error');

  function showErr(el, msg) { if (!el) return; el.textContent = msg; el.style.display = 'block'; }
  function clearErr(el)     { if (!el) return; el.textContent = '';  el.style.display = 'none'; }
  function setKpi(el, v)    { if (el) el.textContent = v; }

  function renderWorkerStatus(data) {
    clearErr(elWorkerErr);
    const cfg = STATUS_CONFIG[data.status || 'normal'] || STATUS_CONFIG.normal;
    if (elMarker)     { elMarker.style.left = cfg.left; elMarker.style.color = cfg.color; elMarker.style.display = 'block'; }
    if (elStatusText) { elStatusText.textContent = cfg.label; elStatusText.style.color = cfg.color; }
  }
  function renderWorkerError(msg) {
    if (elMarker) elMarker.style.display = 'none';
    if (elStatusText) elStatusText.textContent = '-';
    showErr(elWorkerErr, msg);
  }

  function renderAdminSummary(data) {
    clearErr(elAdminErr);
    const total = data.total_count ?? 0, normal = data.normal_count ?? 0,
          warning = data.warning_count ?? 0, danger = data.danger_count ?? 0;
    setKpi(elTotal, total); setKpi(elNormal, normal);
    setKpi(elWarning, warning); setKpi(elDanger, danger);
    if (!elRatioBar) return;
    if (total === 0) { elRatioBar.style.display = 'none'; return; }
    elRatioBar.style.display = 'flex';
    if (elRatioNormal) elRatioNormal.style.flex = normal;
    if (elRatioWarn)   elRatioWarn.style.flex   = warning;
    if (elRatioDanger) elRatioDanger.style.flex = danger;
  }
  function renderAdminError(msg) {
    setKpi(elTotal, '-'); setKpi(elNormal, '-'); setKpi(elWarning, '-'); setKpi(elDanger, '-');
    if (elRatioBar) elRatioBar.style.display = 'none';
    showErr(elAdminErr, msg);
  }

  async function fetchWorkerStatus() {
    try {
      const res = await fetch(API_MY_STATUS, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      renderWorkerStatus((await res.json()).data);
    } catch { renderWorkerError('데이터를 불러오지 못했습니다.'); }
  }

  async function fetchWorkerSummary() {
    try {
      const res = await fetch(API_WORKER_SUMMARY, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
      if (res.status === 403) { renderAdminError('접근 권한이 없습니다.'); return; }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      renderAdminSummary((await res.json()).data);
    } catch { renderAdminError('데이터를 불러오지 못했습니다.'); }
  }

  document.getElementById('mn04-btn-detail')?.addEventListener('click', () => { window.location.href = '/snb-09/'; });

  function init() {
    const isAdmin = (localStorage.getItem('user_type') || 'worker') === 'admin';
    if (isAdmin) {
      if (viewWorker) viewWorker.style.display = 'none';
      if (viewAdmin)  viewAdmin.style.display  = 'flex';
      fetchWorkerSummary();
      setInterval(fetchWorkerSummary, POLL_MS);
    } else {
      if (viewAdmin)  viewAdmin.style.display  = 'none';
      if (viewWorker) viewWorker.style.display = 'flex';
      fetchWorkerStatus();
      setInterval(fetchWorkerStatus, POLL_MS);
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
