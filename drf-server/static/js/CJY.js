/**
 * MN-04 작업자 현황 패널
 * - localStorage.user_type 기반으로 작업자(B View) / 관리자(D View) 분기
 * - 30초 폴링으로 데이터 자동 갱신
 * - 에러 시 수치 '-' 처리 및 오류 문구 노출
 */

(function () {
  'use strict';

  /* ── 상수 ── */
  const POLL_INTERVAL_MS = 30_000;
  const API_MY_STATUS      = '/api/alarms/my-status/';
  const API_WORKER_SUMMARY = '/api/alarms/worker-summary/';

  // 작업자 뷰: 상태별 마커 위치와 색상
  const STATUS_CONFIG = {
    normal:  { left: '16%', color: '#2d9e75', label: '정상' },
    warning: { left: '50%', color: '#ef9f27', label: '경고' },
    danger:  { left: '84%', color: '#e24b4a', label: '위험' },
  };

  /* ── DOM 참조 ── */
  const viewWorker = document.getElementById('mn04-view-worker');
  const viewAdmin  = document.getElementById('mn04-view-admin');

  // 작업자 뷰 요소
  const elMarker     = document.getElementById('mn04-marker');
  const elStatusText = document.getElementById('mn04-status-text');
  const elWorkerErr  = document.getElementById('mn04-worker-error');

  // 관리자 뷰 요소
  const elTotal   = document.getElementById('mn04-kpi-total');
  const elNormal  = document.getElementById('mn04-kpi-normal');
  const elWarning = document.getElementById('mn04-kpi-warning');
  const elDanger  = document.getElementById('mn04-kpi-danger');

  const elRatioBar     = document.getElementById('mn04-ratio-bar');
  const elRatioNormal  = document.getElementById('mn04-ratio-normal');
  const elRatioWarning = document.getElementById('mn04-ratio-warning');
  const elRatioDanger  = document.getElementById('mn04-ratio-danger');

  const elAdminErr = document.getElementById('mn04-admin-error');

  /* ── 유틸 ── */
  function getUserType() {
    return localStorage.getItem('user_type') || 'worker';
  }

  function showError(el, msg) {
    if (!el) return;
    el.textContent = msg;
    el.style.display = 'block';
  }

  function clearError(el) {
    if (!el) return;
    el.textContent = '';
    el.style.display = 'none';
  }

  /* ── 작업자 뷰 렌더 ── */
  function renderWorkerError(msg) {
    if (elMarker)     elMarker.style.display = 'none';
    if (elStatusText) elStatusText.textContent = '-';
    showError(elWorkerErr, msg);
  }

  function renderWorkerStatus(data) {
    clearError(elWorkerErr);
    const status = data.status || 'normal';
    const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.normal;

    if (elMarker) {
      elMarker.style.left    = cfg.left;
      elMarker.style.color   = cfg.color;
      elMarker.style.display = 'block';
    }
    if (elStatusText) {
      elStatusText.textContent = cfg.label;
      elStatusText.style.color = cfg.color;
    }
  }

  /* ── 관리자 뷰 렌더 ── */
  function setKpi(el, value) {
    if (el) el.textContent = value;
  }

  function renderAdminError(msg) {
    setKpi(elTotal,   '-');
    setKpi(elNormal,  '-');
    setKpi(elWarning, '-');
    setKpi(elDanger,  '-');
    if (elRatioBar) elRatioBar.style.display = 'none';
    showError(elAdminErr, msg);
  }

  function renderAdminSummary(data) {
    clearError(elAdminErr);

    const total   = data.total_count   ?? 0;
    const normal  = data.normal_count  ?? 0;
    const warning = data.warning_count ?? 0;
    const danger  = data.danger_count  ?? 0;

    setKpi(elTotal,   total);
    setKpi(elNormal,  normal);
    setKpi(elWarning, warning);
    setKpi(elDanger,  danger);

    // Zero State: 작업자 0명이면 비율 바 숨김
    if (!elRatioBar) return;

    if (total === 0) {
      elRatioBar.style.display = 'none';
      return;
    }

    elRatioBar.style.display = 'flex';
    // flex 비율로 바 너비 표현
    if (elRatioNormal)  elRatioNormal.style.flex  = normal;
    if (elRatioWarning) elRatioWarning.style.flex = warning;
    if (elRatioDanger)  elRatioDanger.style.flex  = danger;
  }

  /* ── API 호출 ── */
  async function fetchWorkerStatus() {
    try {
      const res = await fetch(API_MY_STATUS, {
        credentials: 'same-origin',
        headers: { 'Accept': 'application/json' },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      renderWorkerStatus(json.data);
    } catch (err) {
      renderWorkerError('데이터를 불러오지 못했습니다.');
    }
  }

  async function fetchWorkerSummary() {
    try {
      const res = await fetch(API_WORKER_SUMMARY, {
        credentials: 'same-origin',
        headers: { 'Accept': 'application/json' },
      });
      if (res.status === 403) {
        renderAdminError('접근 권한이 없습니다.');
        return;
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      renderAdminSummary(json.data);
    } catch (err) {
      renderAdminError('데이터를 불러오지 못했습니다.');
    }
  }

  /* ── 상세보기 버튼 ── */
  const btnDetail = document.getElementById('mn04-btn-detail');
  if (btnDetail) {
    btnDetail.addEventListener('click', () => {
      window.location.href = '/snb-09/';
    });
  }

  /* ── 초기화 및 폴링 시작 ── */
  function init() {
    const userType = getUserType();

    if (userType === 'admin') {
      if (viewWorker) viewWorker.style.display = 'none';
      if (viewAdmin)  viewAdmin.style.display  = 'flex';
      fetchWorkerSummary();
      setInterval(fetchWorkerSummary, POLL_INTERVAL_MS);
    } else {
      if (viewAdmin)  viewAdmin.style.display  = 'none';
      if (viewWorker) viewWorker.style.display = 'flex';
      fetchWorkerStatus();
      setInterval(fetchWorkerStatus, POLL_INTERVAL_MS);
    }
  }

  // DOM 준비 후 실행
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
