/* ──────────────────────────────────────────────────────────
   monitoring_workers.js — 실시간 작업자 현황
   데이터 소스:
     1. GET /dashboard/api/workers-list/  → 초기 작업자 목록 (이름·부서)
     2. GET /api/geofences/              → 지오펜스 영역·위험도
     3. WS  /ws/sensors/                  → worker_positions 실시간 수신
        (AppConfig.WS_BASE 사용, shared/ws-client.js의 WSClient 경유)
   ────────────────────────────────────────────────────────── */

'use strict';

const API_WORKERS   = '/dashboard/api/workers-list/';
const API_GEOFENCES = '/api/geofences/';
const STALE_SEC     = 10;  // 이 초 이상 위치 미수신 → 연결 끊김 처리

let _allRows        = [];   // 테이블 행 원본 배열
let _workerMap      = {};   // { worker_id: workerData } 빠른 조회
let _geofences      = [];   // 지오펜스 목록
let _activeFilters  = new Set();
let _selectedWorker = null;

/* ══════════════════════════════════════════════════════════
   유틸
══════════════════════════════════════════════════════════ */
function statusLabel(status) {
  return { danger: '위험', caution: '주의', normal: '정상' }[status] ?? '--';
}

function fmtDatetime(isoStr) {
  if (!isoStr) return '--';
  const d   = new Date(isoStr);
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} `
       + `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val ?? '—';
}

/* ── 지오펜스 판정 (Ray Casting) ── */
function _pointInPolygon(x, y, polygon) {
  if (!Array.isArray(polygon) || polygon.length < 3) return false;
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const [xi, yi] = polygon[i];
    const [xj, yj] = polygon[j];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) {
      inside = !inside;
    }
  }
  return inside;
}

function _findGeofence(x, y) {
  for (const g of _geofences) {
    if (_pointInPolygon(x, y, g.polygon)) return g;
  }
  return null;
}

// 위치 수신 시각 기준 연결 여부 판정
function _isConnected(updatedAt) {
  if (!updatedAt) return false;
  return (Date.now() - new Date(updatedAt).getTime()) < STALE_SEC * 1000;
}

// geofence risk_level → CSS 클래스 (warning → caution)
function _riskToCss(riskLevel) {
  if (riskLevel === 'danger')  return 'danger';
  if (riskLevel === 'warning') return 'caution';
  return 'normal';
}

function _movementLabel(status) {
  return { moving: '이동 중', stationary: '정지', idle: '대기' }[status] ?? '-';
}

/* ══════════════════════════════════════════════════════════
   테이블 렌더링
══════════════════════════════════════════════════════════ */
function renderWorkerTable(workerList) {
  _allRows   = workerList;
  _workerMap = {};
  workerList.forEach(w => { _workerMap[w.id] = w; });

  const tbody    = document.getElementById('worker-table-body');
  const template = document.getElementById('worker-row-template');
  tbody.innerHTML = '';

  workerList.forEach((w) => {
    const row = template.content.cloneNode(true).querySelector('tr');
    row.dataset.workerId = w.id;
    row.dataset.status   = w.status ?? 'normal';

    if (w.status === 'danger')  row.classList.add('danger');
    if (w.status === 'caution') row.classList.add('caution');
    if (!w.connected)           row.classList.add('offline');

    row.querySelector('.col-name').textContent      = w.name      ?? '--';
    row.querySelector('.col-dept').textContent      = w.dept      ?? '--';
    row.querySelector('.col-zone').textContent      = w.zone      ?? '--';
    row.querySelector('.col-last-seen').textContent = fmtDatetime(w.last_seen);

    const connIcon  = row.querySelector('.conn-icon');
    const connLabel = row.querySelector('.conn-label');
    connIcon.classList.add(w.connected ? 'connected' : 'disconnected');
    connLabel.textContent = w.connected ? '연결 정상' : '연결 끊김';

    const badge = row.querySelector('.status-badge');
    badge.classList.add(w.status ?? 'normal');
    badge.textContent = statusLabel(w.status);

    tbody.appendChild(row);
  });

  _updateBadgeCounts(workerList);
  _applyFilter();
  document.getElementById('select-all').checked = false;
  _syncNotifyBtn();
}

/* ── 특정 행만 갱신 (전체 리렌더 없이) ── */
function _updateRow(workerId, { status, zone, lastSeen, connected }) {
  const row = document.querySelector(`tr[data-worker-id="${workerId}"]`);
  if (!row) return;

  row.querySelector('.col-zone').textContent      = zone || '--';
  row.querySelector('.col-last-seen').textContent = fmtDatetime(lastSeen);

  const connIcon  = row.querySelector('.conn-icon');
  const connLabel = row.querySelector('.conn-label');
  connIcon.className    = `conn-icon ${connected ? 'connected' : 'disconnected'}`;
  connLabel.textContent = connected ? '연결 정상' : '연결 끊김';

  const badge = row.querySelector('.status-badge');
  badge.className   = `status-badge ${status}`;
  badge.textContent = statusLabel(status);

  row.classList.remove('danger', 'caution', 'offline');
  if (status === 'danger')  row.classList.add('danger');
  if (status === 'caution') row.classList.add('caution');
  if (!connected)           row.classList.add('offline');

  row.dataset.status = status;

  // 캐시 동기화
  const cached = _workerMap[workerId];
  if (cached) {
    Object.assign(cached, { status, zone, last_seen: lastSeen, connected });
  }
}

/* ══════════════════════════════════════════════════════════
   요약·배지·필터
══════════════════════════════════════════════════════════ */
function updateSummary(total, current) {
  setText('total-worker-count',   total);
  setText('current-worker-count', current);
}

function _updateBadgeCounts(workerList) {
  const counts = { danger: 0, caution: 0, normal: 0 };
  workerList.forEach((w) => { if (w.status in counts) counts[w.status]++; });
  setText('count-danger',  counts.danger);
  setText('count-caution', counts.caution);
  setText('count-normal',  counts.normal);
}

function _applyFilter() {
  document.querySelectorAll('#worker-table-body .worker-row').forEach((row) => {
    const show = _activeFilters.size === 0 || _activeFilters.has(row.dataset.status);
    row.classList.toggle('hidden', !show);
  });
}

/* ══════════════════════════════════════════════════════════
   체크박스
══════════════════════════════════════════════════════════ */
function _getSelectedIds() {
  return [...document.querySelectorAll('#worker-table-body .row-select:checked')]
    .map((cb) => cb.closest('tr').dataset.workerId);
}
function _syncNotifyBtn() {
  document.getElementById('btn-notify-selected').disabled = _getSelectedIds().length === 0;
}

/* ══════════════════════════════════════════════════════════
   디테일 패널
══════════════════════════════════════════════════════════ */
function openWorkerDetail(w) {
  _selectedWorker = w;
  const nameTag = `— ${w.name ?? '—'}`;
  setText('detail-map-name',     nameTag);
  setText('detail-profile-name', nameTag);
  setText('detail-risk-name',    nameTag);
  setText('dp-name',     w.name);
  setText('dp-id',       w.employee_id ?? '—');
  setText('dp-dept',     w.dept);
  setText('dp-position', w.position    ?? '—');
  setText('dp-email',    w.email       ?? '—');
  setText('dp-phone',    w.phone       ?? '—');

  _setRiskItem('risk-checklist', 'none');
  _setRiskItem('risk-vr',        'none');

  document.getElementById('worker-panel-wrap').classList.add('has-selection');
  document.querySelectorAll('#worker-table-body .worker-row').forEach((row) => {
    row.classList.toggle('selected', row.dataset.workerId === String(w.id));
  });
}

function closeWorkerDetail() {
  _selectedWorker = null;
  document.getElementById('worker-panel-wrap').classList.remove('has-selection');
  document.querySelectorAll('#worker-table-body .worker-row.selected')
    .forEach((r) => r.classList.remove('selected'));
}

// 아이콘은 HTML에 이미 이모지로 고정 — status(ok/warn/none)만 data 속성으로 갱신
function _setRiskItem(elemId, status) {
  const el = document.getElementById(elemId);
  if (!el) return;
  el.dataset.risk = status;
}

/* ══════════════════════════════════════════════════════════
   토스트 알림 (추후 API 연동 전 UI 피드백용)
══════════════════════════════════════════════════════════ */
function _showToast(msg, type = 'info') {
  const COLOR = { info: '#388bfd', success: '#2d9e75', warn: '#ef9f27', error: '#e24b4a' };
  const toast = document.createElement('div');
  toast.textContent = msg;
  Object.assign(toast.style, {
    position: 'fixed', bottom: '24px', right: '24px', zIndex: 9999,
    background: COLOR[type] || COLOR.info,
    color: '#fff', padding: '10px 18px', borderRadius: '6px',
    fontSize: '13px', fontWeight: '500', boxShadow: '0 4px 12px rgba(0,0,0,0.4)',
    opacity: '0', transition: 'opacity 0.2s',
  });
  document.body.appendChild(toast);
  requestAnimationFrame(() => { toast.style.opacity = '1'; });
  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 200);
  }, 3000);
}

/* ══════════════════════════════════════════════════════════
   알림 전송
══════════════════════════════════════════════════════════ */
async function sendNotification(target, workerIds = []) {
  const body = { target };
  if (target === 'selected') body.worker_ids = workerIds;
  // TODO: POST API_PUSH_NOTIFY 연동
  console.log('[알림 전송]', body);
  _showToast('추후 기능 연동 예정입니다.', 'info');
}

/* ══════════════════════════════════════════════════════════
   지오펜스 로드
══════════════════════════════════════════════════════════ */
async function _loadGeofences() {
  try {
    const res = await Auth.apiFetch(API_GEOFENCES);
    if (!res.ok) return;
    _geofences = await res.json();
    console.log(`[작업자 현황] 지오펜스 ${_geofences.length}개 로드`);
  } catch (e) {
    console.warn('[작업자 현황] 지오펜스 로드 실패:', e.message);
  }
}

/* ══════════════════════════════════════════════════════════
   위치 데이터 처리 (WS 수신 시마다 호출)
   worker_positions: { "worker_id": {x, y, worker_name, movement_status, updated_at} }
══════════════════════════════════════════════════════════ */
function _processPositions(workerPositions) {
  if (!workerPositions || typeof workerPositions !== 'object') return;

  const entries = Object.entries(workerPositions);
  if (entries.length === 0) return;

  let connectedCount = 0;
  let needsFullRender = false;

  entries.forEach(([wid, pos]) => {
    const workerId  = parseInt(wid);
    // status는 백엔드가 평가한 실시간 위험도(센서 측정값 기반) 사용.
    // 지오펜스의 정적 risk_level이 아니라 그 안 가스/전력 센서 임계치 초과 여부로 판정됨.
    const status    = _riskToCss(pos.risk_level || 'normal');
    const geofence  = _findGeofence(pos.x, pos.y);
    const zone      = pos.zone_name
                      || (geofence ? geofence.name : _movementLabel(pos.movement_status));
    const connected = _isConnected(pos.updated_at);
    if (connected) connectedCount++;

    if (!_workerMap[workerId]) {
      // 포지션에는 있지만 DB 목록에 없는 작업자 → 즉석 등록
      const newWorker = {
        id:        workerId,
        name:      pos.worker_name || `작업자 ${workerId}`,
        dept:      '-',
        zone,
        last_seen: pos.updated_at,
        connected,
        status,
      };
      _workerMap[workerId] = newWorker;
      _allRows.push(newWorker);
      needsFullRender = true;
    } else {
      _updateRow(workerId, { status, zone, lastSeen: pos.updated_at, connected });
    }
  });

  if (needsFullRender) {
    renderWorkerTable(_allRows);
  } else {
    _updateBadgeCounts(_allRows);
    _applyFilter();
  }

  updateSummary(_allRows.length, connectedCount);
}

/* ══════════════════════════════════════════════════════════
   WebSocket 연결 (재연결은 WSClient가 자동 처리)
══════════════════════════════════════════════════════════ */
function _connectWebSocket() {
  const ws = WSClient.connect('/ws/sensors/', { attachToken: true });
  if (typeof WsConnBanner !== 'undefined') WsConnBanner.attach(ws);  // P3 공용 배너
  ws.onOpen(() => console.log('[작업자 현황] WebSocket 연결됨'));
  ws.onClose(() => console.warn('[작업자 현황] 연결 끊김, WSClient 자동 재연결'));
  ws.onMessage((data) => {
    if (data.worker_positions) _processPositions(data.worker_positions);
  });
}

/* ══════════════════════════════════════════════════════════
   초기 작업자 목록 로드
══════════════════════════════════════════════════════════ */
async function loadWorkers() {
  try {
    const res = await Auth.apiFetch(API_WORKERS);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    const workerList = (data.workers || []).map(w => ({
      id:          w.id,
      name:        w.name,
      employee_id: w.employee_id ?? '-',
      dept:        w.department  ?? '-',
      position:    w.position    ?? '-',
      email:       w.email       ?? '-',
      phone:       w.phone       ?? '-',
      zone:        '-',
      last_seen:   null,
      connected:   false,
      status:      'normal',
    }));

    renderWorkerTable(workerList);
    updateSummary(workerList.length, 0);
    console.log(`[작업자 현황] 작업자 ${workerList.length}명 로드`);
  } catch (e) {
    console.warn('[작업자 현황] 목록 로드 실패, 위치 수신 대기:', e.message);
    updateSummary('--', '--');
  }
}

/* ══════════════════════════════════════════════════════════
   이벤트 바인딩
══════════════════════════════════════════════════════════ */
function _bindEvents() {
  document.getElementById('select-all').addEventListener('change', (e) => {
    document.querySelectorAll('#worker-table-body .row-select').forEach((cb) => {
      cb.checked = e.target.checked;
    });
    _syncNotifyBtn();
  });

  document.getElementById('worker-table-body').addEventListener('change', (e) => {
    if (!e.target.classList.contains('row-select')) return;
    _syncNotifyBtn();
  });

  document.getElementById('worker-table-body').addEventListener('click', (e) => {
    if (e.target.classList.contains('row-select')) return;
    const row = e.target.closest('tr.worker-row');
    if (!row) return;

    const workerId = row.dataset.workerId;
    if (_selectedWorker && String(_selectedWorker.id) === workerId) {
      closeWorkerDetail();
      return;
    }
    const workerData = _workerMap[workerId];
    if (workerData) openWorkerDetail(workerData);
  });

  document.querySelectorAll('.badge-filter').forEach((cb) => {
    cb.addEventListener('change', (e) => {
      const status = e.target.dataset.status;
      if (e.target.checked) _activeFilters.add(status);
      else                   _activeFilters.delete(status);
      _applyFilter();
    });
  });

  document.getElementById('btn-notify-selected').addEventListener('click', async () => {
    const ids = _getSelectedIds();
    if (ids.length === 0) return;
    if (!confirm('선택한 작업자에게 긴급 알림을 전송하시겠습니까?')) return;
    await sendNotification('selected', ids);
  });

  document.getElementById('btn-notify-all').addEventListener('click', async () => {
    if (!confirm('현장 전체 작업자에게 긴급 알림을 전송하시겠습니까?')) return;
    await sendNotification('all');
  });

  document.getElementById('btn-detail-notify').addEventListener('click', async () => {
    if (!_selectedWorker) return;
    await sendNotification('selected', [_selectedWorker.id]);
  });
}

/* ══════════════════════════════════════════════════════════
   초기화
══════════════════════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', async () => {
  _bindEvents();
  await Promise.all([loadWorkers(), _loadGeofences()]);
  _connectWebSocket();
});
