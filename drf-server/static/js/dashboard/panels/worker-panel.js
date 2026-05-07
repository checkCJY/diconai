/* ==========================================================
   worker-panel.js — MN-04 작업자 현황 패널
   작업자 뷰: 본인 위치가 지오펜스에 진입/이탈 시 실시간 상태 갱신
   관리자 뷰: 전체 작업자 지오펜스 상태를 정상/주의/위험 인원으로 집계
   데이터 소스: MapPanel.updateWorkerPositions() → 'workerStatusComputed' CustomEvent
   ========================================================== */

'use strict';

(function initMN04() {
  const STATUS_CONFIG = {
    normal:  { cls: 'normal',  label: '정상' },
    warning: { cls: 'warning', label: '주의' },
    danger:  { cls: 'danger',  label: '위험' },
  };

  const viewWorker    = document.getElementById('mn04-view-worker');
  const viewAdmin     = document.getElementById('mn04-view-admin');
  const elStatusBlock = document.getElementById('mn04-worker-status-block');
  const elStatusText  = document.getElementById('mn04-status-text');
  const elWorkerErr   = document.getElementById('mn04-worker-error');
  const elTotal       = document.getElementById('mn04-kpi-total');
  const elNormal      = document.getElementById('mn04-kpi-normal');
  const elWarning     = document.getElementById('mn04-kpi-warning');
  const elDanger      = document.getElementById('mn04-kpi-danger');
  const elDangerBd    = document.getElementById('mn04-kpi-danger-bd');
  const elDangerBlock = document.getElementById('mn04-danger-block');
  const elRatioBar    = document.getElementById('mn04-ratio-bar');
  const elRatioNormal = document.getElementById('mn04-ratio-normal');
  const elRatioWarn   = document.getElementById('mn04-ratio-warning');
  const elRatioDanger = document.getElementById('mn04-ratio-danger');
  const elAdminErr    = document.getElementById('mn04-admin-error');

  function showErr(el, msg) { if (!el) return; el.textContent = msg; el.style.display = 'block'; }
  function clearErr(el)     { if (!el) return; el.textContent = '';  el.style.display = 'none'; }
  function setKpi(el, v)    { if (el) el.textContent = v; }

  // ── 작업자 뷰: 본인 상태 블록 갱신 ──────────────────────────────
  function renderWorkerStatus(statusEntry) {
    clearErr(elWorkerErr);
    const cfg = STATUS_CONFIG[statusEntry.status || 'normal'] || STATUS_CONFIG.normal;
    if (elStatusBlock) {
      elStatusBlock.classList.remove('normal', 'warning', 'danger');
      elStatusBlock.classList.add(cfg.cls);
    }
    if (elStatusText) elStatusText.textContent = cfg.label;
  }

  function renderWorkerWaiting() {
    if (elStatusText) elStatusText.textContent = '위치 수신 중...';
    if (elStatusBlock) elStatusBlock.classList.remove('normal', 'warning', 'danger');
    clearErr(elWorkerErr);
  }

  // ── 관리자 뷰: KPI 카드·비율 바 갱신 ────────────────────────────
  function renderAdminSummary({ total, normal, warning, danger }) {
    clearErr(elAdminErr);
    setKpi(elTotal, total);
    setKpi(elNormal, normal);
    setKpi(elWarning, warning);
    setKpi(elDanger, danger);
    setKpi(elDangerBd, danger);

    if (elDangerBlock) elDangerBlock.classList.toggle('active', danger > 0);

    if (!elRatioBar) return;
    if (total === 0) { elRatioBar.style.display = 'none'; return; }
    elRatioBar.style.display = 'flex';
    if (elRatioNormal) elRatioNormal.style.flex = normal;
    if (elRatioWarn)   elRatioWarn.style.flex   = warning;
    if (elRatioDanger) elRatioDanger.style.flex  = danger;
  }

  function renderAdminWaiting() {
    setKpi(elTotal, '--'); setKpi(elNormal, '--');
    setKpi(elWarning, '--'); setKpi(elDanger, '--'); setKpi(elDangerBd, '--');
    if (elDangerBlock) elDangerBlock.classList.remove('active');
    if (elRatioBar) elRatioBar.style.display = 'none';
  }

  document.getElementById('mn04-btn-detail')?.addEventListener('click', () => {
    window.location.href = '/dashboard/monitoring/workers/';
  });

  async function init() {
    const role    = Auth.getRole() || 'worker';
    const isAdmin = role === 'facility_admin' || role === 'super_admin';

    if (isAdmin) {
      if (viewWorker) viewWorker.style.display = 'none';
      if (viewAdmin)  viewAdmin.style.display  = 'flex';
      renderAdminWaiting();
    } else {
      if (viewAdmin)  viewAdmin.style.display  = 'none';
      if (viewWorker) viewWorker.style.display = 'flex';
      renderWorkerWaiting();
    }

    // 작업자 뷰: 본인 user_id 확인 (지오펜스 상태 맵에서 자신을 찾기 위해)
    let myWorkerId = null;
    if (!isAdmin) {
      try {
        const me = await Auth.getMe();
        if (me && me.id != null) myWorkerId = me.id;
      } catch { /* 실패 시 위치 데이터 수신 불가 상태 유지 */ }
    }

    // MapPanel.updateWorkerPositions() 호출 시 발행되는 이벤트 수신
    // statuses: { [worker_id]: { status: 'normal'|'warning'|'danger', geofence_name, worker_name } }
    document.addEventListener('workerStatusComputed', (e) => {
      const statuses = e.detail;

      if (isAdmin) {
        const values  = Object.values(statuses);
        const total   = values.length;
        const danger  = values.filter(s => s.status === 'danger').length;
        const warning = values.filter(s => s.status === 'warning').length;
        const normal  = total - danger - warning;
        renderAdminSummary({ total, normal, warning, danger });
      } else {
        if (myWorkerId === null) return;
        const myStatus = statuses[myWorkerId];
        if (myStatus) {
          renderWorkerStatus(myStatus);
        }
        // myStatus가 없으면 아직 위치 미수신 → 대기 상태 유지
      }
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
