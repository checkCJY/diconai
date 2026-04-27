/* ──────────────────────────────────────────────────────────
   monitoring_workers.js — 실시간 작업자 현황
   담당: 테이블 렌더링, 필터 배지, 체크박스, 행 클릭 디테일, 알림 전송
   ────────────────────────────────────────────────────────── */

/* ── API 엔드포인트 ── */
// TODO: 실제 엔드포인트로 교체
const API_WORKERS     = '/api/workers/status/';
const API_PUSH_NOTIFY = '/api/notifications/push/';
// TODO: WebSocket 주소 확정 후 교체
// const WS_URL = `ws://${location.host}/ws/workers/`;

/* ── 상태 ── */
let _allRows = [];
let _activeFilters  = new Set();
let _selectedWorker = null;   // 현재 디테일 패널에 표시 중인 작업자 객체

/* ────────────────────────────────────────────────────────
   유틸
──────────────────────────────────────────────────────── */
function statusLabel(status) {
  return { danger: '위험', caution: '주의', normal: '정상' }[status] ?? '--';
}

function fmtDatetime(isoStr) {
  if (!isoStr) return '--';
  const d = new Date(isoStr);
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} `
       + `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val ?? '—';
}

/* ────────────────────────────────────────────────────────
   테이블 렌더링
   workerList 항목 스키마 (API 확정 전 임시):
   { id, name, dept, zone, last_seen(ISO), connected(bool),
     status('danger'|'caution'|'normal'),
     employee_id, position, email, phone }   ← 프로필용 추가 필드
   TODO: API /api/workers/status/ 응답 스키마 확정 후 필드명 수정
──────────────────────────────────────────────────────── */
function renderWorkerTable(workerList) {
  _allRows = workerList;

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

    row.querySelector('.col-name').textContent      = w.name  ?? '--';
    row.querySelector('.col-dept').textContent      = w.dept  ?? '--';
    row.querySelector('.col-zone').textContent      = w.zone  ?? '--';
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

/* ────────────────────────────────────────────────────────
   현장 투입 요약
   TODO: WebSocket 이벤트 또는 API 응답에서 값 수신 후 호출
──────────────────────────────────────────────────────── */
function updateSummary(total, current) {
  setText('total-worker-count',   total);
  setText('current-worker-count', current);
}

/* ────────────────────────────────────────────────────────
   배지 카운트 업데이트
──────────────────────────────────────────────────────── */
function _updateBadgeCounts(workerList) {
  const counts = { danger: 0, caution: 0, normal: 0 };
  workerList.forEach((w) => { if (w.status in counts) counts[w.status]++; });
  setText('count-danger',  counts.danger);
  setText('count-caution', counts.caution);
  setText('count-normal',  counts.normal);
}

/* ────────────────────────────────────────────────────────
   필터 적용
──────────────────────────────────────────────────────── */
function _applyFilter() {
  document.querySelectorAll('#worker-table-body .worker-row').forEach((row) => {
    const show = _activeFilters.size === 0 || _activeFilters.has(row.dataset.status);
    row.classList.toggle('hidden', !show);
  });
}

/* ────────────────────────────────────────────────────────
   체크박스 관리
──────────────────────────────────────────────────────── */
function _getSelectedIds() {
  return [...document.querySelectorAll('#worker-table-body .row-select:checked')]
    .map((cb) => cb.closest('tr').dataset.workerId);
}

function _syncNotifyBtn() {
  document.getElementById('btn-notify-selected').disabled = _getSelectedIds().length === 0;
}

/* ────────────────────────────────────────────────────────
   디테일 패널 — 열기
   TODO: 프로필(2)과 위험 현황(3)은 작업자 ID로 별도 API 호출 후 채워야 함
         - GET /api/workers/{id}/profile/  → 이름·ID·소속·직급·이메일·연락처
         - GET /api/workers/{id}/risk/     → PPE·체크리스트·VR 교육 상태
──────────────────────────────────────────────────────── */
function openWorkerDetail(w) {
  _selectedWorker = w;

  // 이름 태그 공통 업데이트
  const nameTag = `— ${w.name ?? '—'}`;
  setText('detail-map-name',     nameTag);
  setText('detail-profile-name', nameTag);
  setText('detail-risk-name',    nameTag);

  // 2. 프로필 채우기 (현재는 workerList 데이터 사용)
  // TODO: 상세 프로필은 GET /api/workers/{id}/profile/ 로 별도 요청 필요
  setText('dp-name',     w.name);
  setText('dp-id',       w.employee_id ?? '—');
  setText('dp-dept',     w.dept);
  setText('dp-position', w.position    ?? '—');
  setText('dp-email',    w.email       ?? '—');
  setText('dp-phone',    w.phone       ?? '—');

  // 3. 위험 현황 채우기
  // TODO: GET /api/workers/{id}/risk/ 연동 전까지 미확인 상태(none)로 표시
  _setRiskItem('risk-ppe',       'none', '?');
  _setRiskItem('risk-checklist', 'none', '?');
  _setRiskItem('risk-vr',        'none', '?');

  // 분할 레이아웃 활성화
  document.getElementById('worker-panel-wrap').classList.add('has-selection');

  // 선택 행 강조
  document.querySelectorAll('#worker-table-body .worker-row').forEach((row) => {
    row.classList.toggle('selected', row.dataset.workerId === String(w.id));
  });
}

// 디테일 패널 — 닫기 (같은 행 재클릭 시)
function closeWorkerDetail() {
  _selectedWorker = null;
  document.getElementById('worker-panel-wrap').classList.remove('has-selection');
  document.querySelectorAll('#worker-table-body .worker-row.selected')
    .forEach((r) => r.classList.remove('selected'));
}

// 위험 현황 아이콘 상태 적용
// status: 'ok' | 'warn' | 'none'
function _setRiskItem(elemId, status, iconText) {
  const el = document.getElementById(elemId);
  if (!el) return;
  el.dataset.risk = status;
  el.querySelector('.risk-item-icon').textContent = iconText;
}

/* ────────────────────────────────────────────────────────
   WebSocket 실시간 상태 업데이트 (외부 연동 진입점)
   TODO: WebSocket 연결 구현 후 이벤트 핸들러에서 호출
   이벤트 스키마: { type:'worker_status', worker_id, status, connected, last_seen }
──────────────────────────────────────────────────────── */
function onWorkerStatusEvent(event) {
  const row = document.querySelector(`tr[data-worker-id="${event.worker_id}"]`);
  if (!row) return;

  const badge = row.querySelector('.status-badge');
  badge.className   = `status-badge ${event.status}`;
  badge.textContent = statusLabel(event.status);

  row.classList.remove('danger', 'caution', 'offline');
  if (event.status === 'danger')  row.classList.add('danger');
  if (event.status === 'caution') row.classList.add('caution');
  if (!event.connected)           row.classList.add('offline');

  const connIcon  = row.querySelector('.conn-icon');
  const connLabel = row.querySelector('.conn-label');
  connIcon.className    = `conn-icon ${event.connected ? 'connected' : 'disconnected'}`;
  connLabel.textContent = event.connected ? '연결 정상' : '연결 끊김';
  row.querySelector('.col-last-seen').textContent = fmtDatetime(event.last_seen);

  row.dataset.status = event.status;

  // 캐시 동기화
  const cached = _allRows.find((w) => String(w.id) === String(event.worker_id));
  if (cached) {
    cached.status    = event.status;
    cached.connected = event.connected;
    cached.last_seen = event.last_seen;
  }

  _updateBadgeCounts(_allRows);
  _applyFilter();
}

/* ────────────────────────────────────────────────────────
   알림 전송
   TODO: CSRF 토큰 — getCsrfToken()은 shared/util.js 참고
   TODO: 응답 성공 시 토스트 메시지 노출
──────────────────────────────────────────────────────── */
async function sendNotification(target, workerIds = []) {
  const body = { target };
  if (target === 'selected') body.worker_ids = workerIds;

  // TODO: fetch 실제 호출 활성화
  // const res = await fetch(API_PUSH_NOTIFY, {
  //   method: 'POST',
  //   headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
  //   body: JSON.stringify(body),
  // });
  // if (!res.ok) throw new Error('알림 전송 실패');

  console.log('[알림 전송]', body);
}

/* ────────────────────────────────────────────────────────
   데이터 로드
   TODO: WebSocket 연동 완료 후 폴링 제거하고 WS 이벤트로 대체
──────────────────────────────────────────────────────── */
async function loadWorkers() {
  try {
    const res = await fetch(API_WORKERS, { headers: { 'X-CSRFToken': getCsrfToken() } });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    updateSummary(data.total, data.current);
    renderWorkerTable(data.workers);
  } catch (e) {
    // API 미구현 구간 — 더미 데이터로 UI 확인
    console.warn('[작업자 현황] API 미연동, 더미 데이터 사용:', e.message);
    updateSummary(100, 50);
    renderWorkerTable([
      { id: 'w1', name: '홍길동', dept: '공정관리팀', zone: '1공장',
        last_seen: '2025-01-15T12:00:00', connected: true,  status: 'danger',
        employee_id: 'EMP-001', position: '대리', email: 'hong@example.com', phone: '010-1234-5678' },
      { id: 'w2', name: '김철수', dept: '안전관리팀', zone: '2공장',
        last_seen: '2025-01-15T11:50:00', connected: true,  status: 'caution',
        employee_id: 'EMP-002', position: '과장', email: 'kim@example.com',  phone: '010-2345-6789' },
      { id: 'w3', name: '이영희', dept: '공정관리팀', zone: '1공장',
        last_seen: '2025-01-15T11:30:00', connected: false, status: 'normal',
        employee_id: 'EMP-003', position: '사원', email: 'lee@example.com',  phone: '010-3456-7890' },
      { id: 'w4', name: '박민준', dept: '설비팀',     zone: '3공장',
        last_seen: '2025-01-15T12:00:00', connected: true,  status: 'normal',
        employee_id: 'EMP-004', position: '대리', email: 'park@example.com', phone: '010-4567-8901' },
    ]);
  }
}

/* ────────────────────────────────────────────────────────
   이벤트 바인딩
──────────────────────────────────────────────────────── */
function _bindEvents() {
  // 전체 선택 체크박스
  document.getElementById('select-all').addEventListener('change', (e) => {
    document.querySelectorAll('#worker-table-body .row-select').forEach((cb) => {
      cb.checked = e.target.checked;
    });
    _syncNotifyBtn();
  });

  // 행 체크박스 변경 (이벤트 위임)
  document.getElementById('worker-table-body').addEventListener('change', (e) => {
    if (!e.target.classList.contains('row-select')) return;
    _syncNotifyBtn();
  });

  // 행 클릭 → 디테일 패널 열기/닫기
  document.getElementById('worker-table-body').addEventListener('click', (e) => {
    // 체크박스 클릭은 디테일 패널 제어에서 제외
    if (e.target.classList.contains('row-select')) return;

    const row = e.target.closest('tr.worker-row');
    if (!row) return;

    const workerId = row.dataset.workerId;
    if (_selectedWorker && String(_selectedWorker.id) === workerId) {
      closeWorkerDetail();
      return;
    }

    const workerData = _allRows.find((w) => String(w.id) === workerId);
    if (workerData) openWorkerDetail(workerData);
  });

  // 위험 단계별 필터 배지
  document.querySelectorAll('.badge-filter').forEach((cb) => {
    cb.addEventListener('change', (e) => {
      const status = e.target.dataset.status;
      if (e.target.checked) _activeFilters.add(status);
      else                   _activeFilters.delete(status);
      _applyFilter();
    });
  });

  // 선택 알림 전송
  document.getElementById('btn-notify-selected').addEventListener('click', async () => {
    const ids = _getSelectedIds();
    if (ids.length === 0) return;
    if (!confirm('선택한 작업자에게 긴급 알림을 전송하시겠습니까?')) return;
    await sendNotification('selected', ids);
  });

  // 전체 알림 전송
  // TODO: confirm 다이얼로그 → 커스텀 모달로 교체 권장
  document.getElementById('btn-notify-all').addEventListener('click', async () => {
    if (!confirm('현장 전체 작업자에게 긴급 알림을 전송하시겠습니까?')) return;
    await sendNotification('all');
  });

  // 디테일 패널 — 알림 전송 버튼 (1:1)
  document.getElementById('btn-detail-notify').addEventListener('click', async () => {
    if (!_selectedWorker) return;
    await sendNotification('selected', [_selectedWorker.id]);
  });
}

/* ────────────────────────────────────────────────────────
   초기화
──────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  _bindEvents();
  loadWorkers();
});
