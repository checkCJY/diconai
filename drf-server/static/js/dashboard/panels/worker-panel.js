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
  const POLL_MS            = 2_000;
  const API_MY_STATUS      = '/alerts/api/my-status/';
  const API_WORKER_SUMMARY = '/alerts/api/worker-summary/';

  const STATUS_CONFIG = {
    normal:  { cls: 'normal',  label: '정상' },
    warning: { cls: 'warning', label: '주의' },
    danger:  { cls: 'danger',  label: '위험' },
  };

  const viewWorker = document.getElementById('mn04-view-worker');
  const viewAdmin  = document.getElementById('mn04-view-admin');
  const elStatusBlock = document.getElementById('mn04-worker-status-block');
  const elStatusText  = document.getElementById('mn04-status-text');
  const elWorkerErr   = document.getElementById('mn04-worker-error');
  const elTotal        = document.getElementById('mn04-kpi-total');
  const elNormal       = document.getElementById('mn04-kpi-normal');
  const elWarning      = document.getElementById('mn04-kpi-warning');
  const elDanger       = document.getElementById('mn04-kpi-danger');
  const elDangerBd     = document.getElementById('mn04-kpi-danger-bd');   // 우측 상세의 위험 수치
  const elDangerBlock  = document.getElementById('mn04-danger-block');    // 좌측 강조 블록
  const elRatioBar     = document.getElementById('mn04-ratio-bar');
  const elRatioNormal  = document.getElementById('mn04-ratio-normal');
  const elRatioWarn    = document.getElementById('mn04-ratio-warning');
  const elRatioDanger  = document.getElementById('mn04-ratio-danger');
  const elAdminErr     = document.getElementById('mn04-admin-error');

  function showErr(el, msg) { if (!el) return; el.textContent = msg; el.style.display = 'block'; }
  function clearErr(el)     { if (!el) return; el.textContent = '';  el.style.display = 'none'; }
  function setKpi(el, v)    { if (el) el.textContent = v; }

  // ── 나의 상태 API 응답으로 상태 바 마커 위치와 텍스트를 갱신한다. ──────
  function renderWorkerStatus(data) {
    clearErr(elWorkerErr);
    const cfg = STATUS_CONFIG[data.status || 'normal'] || STATUS_CONFIG.normal;
    if (elStatusBlock) {
      elStatusBlock.classList.remove('normal', 'warning', 'danger');
      elStatusBlock.classList.add(cfg.cls);
    }
    if (elStatusText) elStatusText.textContent = cfg.label;
  }
  function renderWorkerError(msg) {
    if (elStatusBlock) elStatusBlock.classList.remove('normal', 'warning', 'danger');
    if (elStatusText) elStatusText.textContent = '-';
    showErr(elWorkerErr, msg);
  }

  // ── 작업자 요약 API 응답으로 총원·정상·경고·위험 KPI 카드와 비율 바를 갱신한다. ─
  function renderAdminSummary(data) {
    clearErr(elAdminErr);
    const total = data.total_count ?? 0, normal = data.normal_count ?? 0,
          warning = data.warning_count ?? 0, danger = data.danger_count ?? 0;
    setKpi(elTotal, total); setKpi(elNormal, normal);
    setKpi(elWarning, warning); setKpi(elDanger, danger);
    setKpi(elDangerBd, danger);

    // 위험 인원 강조: danger > 0 이면 active 클래스로 pulse 애니메이션 + 빨간 테두리
    if (elDangerBlock) elDangerBlock.classList.toggle('active', danger > 0);

    if (!elRatioBar) return;
    if (total === 0) { elRatioBar.style.display = 'none'; return; }
    elRatioBar.style.display = 'flex';
    if (elRatioNormal) elRatioNormal.style.flex = normal;
    if (elRatioWarn)   elRatioWarn.style.flex   = warning;
    if (elRatioDanger) elRatioDanger.style.flex  = danger;
  }
  function renderAdminError(msg) {
    setKpi(elTotal, '-'); setKpi(elNormal, '-'); setKpi(elWarning, '-');
    setKpi(elDanger, '-'); setKpi(elDangerBd, '-');
    if (elDangerBlock) elDangerBlock.classList.remove('active');
    if (elRatioBar) elRatioBar.style.display = 'none';
    showErr(elAdminErr, msg);
  }

  async function fetchWorkerStatus() {
    try {
      // Auth.apiFetch: Authorization: Bearer <JWT> 헤더 자동 포함 (auth.js)
      const res = await Auth.apiFetch(API_MY_STATUS, { headers: { Accept: 'application/json' } });
      if (res.status === 401) { Auth.redirectLogin(); return; }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      renderWorkerStatus((await res.json()).data);
    } catch { renderWorkerError('데이터를 불러오지 못했습니다.'); }
  }

  async function fetchWorkerSummary() {
    try {
      // Auth.apiFetch: Authorization: Bearer <JWT> 헤더 자동 포함 (auth.js)
      const res = await Auth.apiFetch(API_WORKER_SUMMARY, { headers: { Accept: 'application/json' } });
      if (res.status === 401) { Auth.redirectLogin(); return; }
      if (res.status === 403) { renderAdminError('접근 권한이 없습니다.'); return; }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      renderAdminSummary((await res.json()).data);
    } catch { renderAdminError('데이터를 불러오지 못했습니다.'); }
  }

  document.getElementById('mn04-btn-detail')?.addEventListener('click', () => { window.location.href = '/dashboard/monitoring/workers/'; });


  // ── role에 따라 작업자 뷰 또는 관리자 뷰를 표시하고 30초 폴링을 시작한다. ─
  function init() {
    const role = localStorage.getItem('role') || 'worker';
    const isAdmin = role === 'facility_admin' || role === 'super_admin';
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
