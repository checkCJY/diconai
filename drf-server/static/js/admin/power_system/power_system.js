'use strict';

// ── 유틸 ──────────────────────────────────────────────────────
function _esc(s) {
  if (s == null) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function _fmt(dt) {
  if (!dt) return '-';
  return dt.replace('T',' ').substring(0, 19);
}
function _fmtDate(d) { return d || '-'; }

// ── 상태 ──────────────────────────────────────────────────────
let _page = 1;
const _pageSize = 10;
let _total = 0;
let _selected = new Set();
let _deleteTargetIds = [];
let _currentDevice = null;
let _currentInspectionId = null;
let _connCheckedAt = null;
let _connOk = null;

// ── API 호출 ──────────────────────────────────────────────────
function _buildQuery() {
  const p = new URLSearchParams();
  const q = document.getElementById('filterDeviceId').value;
  const active = document.getElementById('filterActive').value;
  const conn = document.getElementById('filterConnection').value;
  const order = document.getElementById('filterOrder').value;
  if (q) p.append('q', q);
  if (active) p.append('is_active', active);
  if (conn) p.append('connection', conn);
  if (order) p.append('order', order);
  p.append('page', _page);
  p.append('page_size', _pageSize);
  return p.toString();
}

async function _loadDevices() {
  try {
    const res = await Auth.apiFetch(`/api/power-devices/?${_buildQuery()}`);
    if (!res.ok) return;
    const data = await res.json();
    _total = data.total;
    _renderTable(data.results);
    _renderPagination(data.total, data.page, data.page_size);
    document.getElementById('totalCount').textContent = data.total;
  } catch (e) { console.error(e); }
}

async function _populateDeviceFilter() {
  const sel = document.getElementById('filterDeviceId');
  const cur = sel.value;
  while (sel.options.length > 1) sel.remove(1);
  try {
    const res = await Auth.apiFetch('/api/power-devices/codes/');
    if (!res.ok) return;
    const codes = await res.json();
    codes.forEach(code => {
      const opt = document.createElement('option');
      opt.value = code;
      opt.textContent = code;
      sel.appendChild(opt);
    });
  } catch {}
  sel.value = cur;
}

// ── 드롭다운 ──────────────────────────────────────────────────
async function _loadDepartmentOptions(selId, selectedId = '') {
  const sel = document.getElementById(selId);
  while (sel.options.length > 1) sel.remove(1);
  try {
    const res = await Auth.apiFetch('/api/departments/select/');
    if (!res.ok) return;
    const depts = await res.json();
    depts.forEach(d => {
      const opt = document.createElement('option');
      opt.value = d.id; opt.textContent = d.name;
      sel.appendChild(opt);
    });
    if (selectedId) sel.value = String(selectedId);
  } catch {}
}

async function _loadManagerOptions(selId, deptId = '', selectedId = '') {
  const sel = document.getElementById(selId);
  while (sel.options.length > 1) sel.remove(1);
  try {
    const url = deptId ? `/api/managers/select/?department_id=${deptId}` : '/api/managers/select/';
    const res = await Auth.apiFetch(url);
    if (!res.ok) return;
    const mgrs = await res.json();
    mgrs.forEach(m => {
      const opt = document.createElement('option');
      opt.value = m.id; opt.textContent = m.name;
      sel.appendChild(opt);
    });
    if (selectedId) sel.value = String(selectedId);
  } catch {}
}

// ── 테이블 렌더링 ─────────────────────────────────────────────
function _renderTable(devices) {
  const tbody = document.getElementById('deviceTbody');
  if (!devices.length) {
    tbody.innerHTML = '<tr class="ps-empty-row"><td colspan="10">검색 결과가 없습니다.</td></tr>';
    return;
  }

  let hasAbnormal = false;
  tbody.innerHTML = devices.map(d => {
    const isAbnormal = d.connection_status === 'disconnected';
    if (isAbnormal) hasAbnormal = true;

    const inspBadge = d.inspection_status === 'done'
      ? '<span class="ps-badge ps-badge-done">점검 완료</span>'
      : '<span class="ps-badge ps-badge-needed">점검 필요</span>';

    const activeBadge = d.is_active
      ? '<span class="ps-badge ps-badge-active">사용</span>'
      : '<span class="ps-badge ps-badge-inactive">미사용</span>';

    let connBadge;
    if (d.connection_status === 'inactive') {
      connBadge = '<span class="ps-conn-dash">-</span>';
    } else if (d.connection_status === 'disconnected') {
      connBadge = '<span class="ps-conn-dot disconnected"></span> 연결 끊김';
    } else {
      connBadge = '<span class="ps-conn-dot normal"></span> 정상';
    }

    const checked = _selected.has(d.id) ? 'checked' : '';
    const rowClass = isAbnormal ? 'ps-row-abnormal' : '';

    return `
      <tr data-id="${d.id}" class="${rowClass}">
        <td class="col-chk col-center"><input type="checkbox" class="row-chk" data-id="${d.id}" ${checked}></td>
        <td class="col-center">${inspBadge}</td>
        <td><a href="#" class="ps-device-link" data-id="${d.id}">${_esc(d.power_id)}</a></td>
        <td>${_esc(d.device_name || '-')}</td>
        <td class="col-center">${activeBadge}</td>
        <td class="col-center">${connBadge}</td>
        <td>${_fmt(d.last_reading)}</td>
        <td>${_fmtDate(d.latest_inspection_date)}</td>
        <td>${_esc(d.manager_name || '-')}</td>
        <td class="col-center">
          <div class="ps-action-wrap" style="justify-content:center;">
            <button class="ps-action-btn" onclick="_openDetail(${d.id})">수정</button>
            ${d.is_active ? `<button class="ps-action-btn danger" onclick="_openBulkDelete([${d.id}])">비활성화</button>` : ''}
          </div>
        </td>
      </tr>`;
  }).join('');

  document.getElementById('abnormalNote').style.display = hasAbnormal ? '' : 'none';

  document.querySelectorAll('.row-chk').forEach(chk => {
    chk.addEventListener('change', e => {
      const id = Number(e.target.dataset.id);
      if (e.target.checked) _selected.add(id); else _selected.delete(id);
      _syncBulkBtn();
    });
  });
  document.querySelectorAll('.ps-device-link').forEach(a => {
    a.addEventListener('click', e => { e.preventDefault(); _openDetail(Number(a.dataset.id)); });
  });
}

function _syncBulkBtn() {
  document.getElementById('btnBulkDelete').disabled = _selected.size === 0;
}

// ── 페이지네이션 ──────────────────────────────────────────────
function _renderPagination(total, page, pageSize) {
  const totalPages = Math.ceil(total / pageSize) || 1;
  const el = document.getElementById('pagination');
  let html = `<button class="ps-page-btn" ${page <= 1 ? 'disabled' : ''} onclick="_goPage(${page-1})">&lt;</button>`;
  const start = Math.max(1, page - 2), end = Math.min(totalPages, page + 2);
  for (let i = start; i <= end; i++) {
    html += `<button class="ps-page-btn${i === page ? ' active' : ''}" onclick="_goPage(${i})">${i}</button>`;
  }
  html += `<button class="ps-page-btn" ${page >= totalPages ? 'disabled' : ''} onclick="_goPage(${page+1})">&gt;</button>`;
  el.innerHTML = html;
}
function _goPage(p) { _page = p; _loadDevices(); }

// ── 모달 유틸 ─────────────────────────────────────────────────
function _showModal(id) { document.getElementById(id).style.display = 'flex'; }
function _hideModal(id) { document.getElementById(id).style.display = 'none'; }

// ── 장비 등록 ─────────────────────────────────────────────────
async function _openCreate() {
  ['errCreateDeviceType','errCreateDeviceName','errCreateDeviceId','errCreateDepartment',
   'errCreateManager','errCreateConn','errCreateGlobal'].forEach(id => {
    document.getElementById(id).textContent = '';
  });
  document.getElementById('createDeviceType').value = '';
  document.getElementById('createDeviceCode').value = '';
  document.getElementById('createDeviceName').value = '';
  document.getElementById('createDeviceId').value = '';
  document.getElementById('createIp').value = '';
  document.getElementById('createPort').value = '';
  document.getElementById('createConnStatus').style.display = 'none';
  document.querySelector('input[name="createActive"][value="true"]').checked = true;
  _connCheckedAt = null; _connOk = null;
  _loadDepartmentOptions('createDepartment');
  _loadManagerOptions('createManager');
  _showModal('createModal');
}

async function _onCreateTypeChange() {
  const type = document.getElementById('createDeviceType').value;
  if (!type) {
    document.getElementById('createDeviceCode').value = '';
    document.getElementById('createDeviceName').value = '';
    return;
  }
  document.getElementById('createDeviceName').value = '스마트 전력 시스템';
  try {
    const res = await Auth.apiFetch('/api/power-devices/next-code/');
    const data = await res.json();
    document.getElementById('createDeviceCode').value = data.code;
  } catch {}
}

async function _submitCreate() {
  let valid = true;
  ['errCreateDeviceType','errCreateDeviceName','errCreateDeviceId',
   'errCreateDepartment','errCreateManager','errCreateConn','errCreateGlobal'].forEach(id => {
    document.getElementById(id).textContent = '';
  });

  const deviceType = document.getElementById('createDeviceType').value;
  const deviceCode = document.getElementById('createDeviceCode').value.trim();
  const deviceName = document.getElementById('createDeviceName').value.trim();
  const deviceId = document.getElementById('createDeviceId').value.trim();
  const deptId = document.getElementById('createDepartment').value;
  const managerId = document.getElementById('createManager').value;
  const ip = document.getElementById('createIp').value.trim();
  const port = document.getElementById('createPort').value.trim();
  const isActive = document.querySelector('input[name="createActive"]:checked').value === 'true';

  if (!deviceType) { document.getElementById('errCreateDeviceType').textContent = '장비 유형을 선택해 주세요.'; valid = false; }
  if (!deviceName) { document.getElementById('errCreateDeviceName').textContent = '장비명을 입력해 주세요.'; valid = false; }
  if (!deviceId) { document.getElementById('errCreateDeviceId').textContent = '장비 ID를 입력해 주세요.'; valid = false; }
  if (!deptId) { document.getElementById('errCreateDepartment').textContent = '관리 부서를 선택해 주세요.'; valid = false; }
  if (!managerId) { document.getElementById('errCreateManager').textContent = '관리 담당자를 선택해 주세요.'; valid = false; }
  if (!valid) return;

  // facility는 기본 첫 번째 facility 사용
  let facilityId = 1;
  try {
    const fr = await Auth.apiFetch('/api/facilities/select/');
    if (fr.ok) { const flist = await fr.json(); if (flist.length) facilityId = flist[0].id; }
  } catch {}

  const payload = {
    device_code: deviceCode, device_id: deviceId, device_name: deviceName,
    department: deptId ? Number(deptId) : null,
    manager: managerId ? Number(managerId) : null,
    ip_address: ip, port: port ? Number(port) : null,
    is_active: isActive, facility: facilityId,
    x: 0, y: 0,
    connection_checked_at: _connCheckedAt,
    connection_ok: _connOk,
  };

  try {
    const res = await Auth.apiFetch('/api/power-devices/', { method: 'POST', body: JSON.stringify(payload) });
    if (!res.ok) {
      const err = await res.json();
      document.getElementById('errCreateGlobal').textContent = JSON.stringify(err);
      return;
    }
    _hideModal('createModal');
    document.getElementById('successMsg').textContent = '장비가 등록되었습니다.';
    _showModal('successModal');
    _page = 1; _loadDevices();
  } catch (e) {
    document.getElementById('errCreateGlobal').textContent = '등록 중 오류가 발생했습니다.';
  }
}

// ── 연결 확인 ─────────────────────────────────────────────────
async function _checkConn(ipId, portId, statusId) {
  const ip = document.getElementById(ipId).value.trim();
  const port = document.getElementById(portId).value.trim();
  const statusEl = document.getElementById(statusId);
  statusEl.style.display = 'none';
  try {
    const res = await Auth.apiFetch('/api/power-devices/check-connection/', { method: 'POST', body: JSON.stringify({ ip_address: ip, port: port ? Number(port) : null }),
    });
    const data = await res.json();
    _connCheckedAt = data.checked_at;
    _connOk = data.ok;
    statusEl.style.display = '';
    statusEl.className = `ps-conn-status ${data.ok ? 'success' : 'fail'}`;
    statusEl.textContent = data.ok ? '연결 성공' : (data.detail || '연결 실패');
  } catch {
    statusEl.style.display = '';
    statusEl.className = 'ps-conn-status fail';
    statusEl.textContent = '연결 확인 중 오류가 발생했습니다.';
  }
}

// ── 상세 / 수정 ───────────────────────────────────────────────
async function _openDetail(id) {
  try {
    const res = await Auth.apiFetch(`/api/power-devices/${id}/`);
    if (!res.ok) return;
    const d = await res.json();
    _currentDevice = d;

    document.getElementById('detailTitle').textContent = `스마트 전력 시스템 ${_esc(d.power_id)}`;
    document.getElementById('detailDesc').textContent =
      `해당 장비의 기본 정보와 점검 실행 및 이력을 확인합니다.`;

    document.getElementById('editDeviceType').value = '스마트 전력 시스템';
    document.getElementById('editDeviceCode').value = d.power_id;
    document.getElementById('editDeviceName').value = d.device_name || '';
    document.getElementById('editDeviceId').value = d.device_id || '';
    document.getElementById('editIp').value = d.ip_address || '';
    document.getElementById('editPort').value = d.port || '';
    document.getElementById('editConnStatus').style.display = 'none';
    document.querySelector(`input[name="editActive"][value="${d.is_active ? 'true' : 'false'}"]`).checked = true;
    ['errEditDeviceName','errEditDeviceId','errEditDepartment','errEditManager','errEditGlobal'].forEach(id => {
      document.getElementById(id).textContent = '';
    });

    await _loadDepartmentOptions('editDepartment', d.department);
    await _loadManagerOptions('editManager', d.department, d.manager);

    _switchTab('info');
    _showModal('detailModal');
  } catch (e) { console.error(e); }
}

async function _submitEdit() {
  let valid = true;
  ['errEditDeviceName','errEditDeviceId','errEditDepartment','errEditManager','errEditGlobal'].forEach(id => {
    document.getElementById(id).textContent = '';
  });

  const deviceName = document.getElementById('editDeviceName').value.trim();
  const deviceId = document.getElementById('editDeviceId').value.trim();
  const deptId = document.getElementById('editDepartment').value;
  const managerId = document.getElementById('editManager').value;
  const ip = document.getElementById('editIp').value.trim();
  const port = document.getElementById('editPort').value.trim();
  const isActive = document.querySelector('input[name="editActive"]:checked').value === 'true';

  if (!deviceName) { document.getElementById('errEditDeviceName').textContent = '장비명을 입력해 주세요.'; valid = false; }
  if (!deviceId) { document.getElementById('errEditDeviceId').textContent = '장비 ID를 입력해 주세요.'; valid = false; }
  if (!valid) return;

  const payload = {
    device_name: deviceName, device_id: deviceId,
    department: deptId ? Number(deptId) : null,
    manager: managerId ? Number(managerId) : null,
    ip_address: ip, port: port ? Number(port) : null,
    is_active: isActive,
    connection_checked_at: _connCheckedAt ?? _currentDevice.connection_checked_at,
    connection_ok: _connOk ?? _currentDevice.connection_ok,
  };

  try {
    const res = await Auth.apiFetch(`/api/power-devices/${_currentDevice.id}/`, { method: 'PUT', body: JSON.stringify(payload) });
    if (!res.ok) {
      const err = await res.json();
      document.getElementById('errEditGlobal').textContent = JSON.stringify(err);
      return;
    }
    _hideModal('detailModal');
    document.getElementById('successMsg').textContent = '수정되었습니다.';
    _showModal('successModal');
    _loadDevices();
  } catch {
    document.getElementById('errEditGlobal').textContent = '수정 중 오류가 발생했습니다.';
  }
}

// ── 점검 탭 ───────────────────────────────────────────────────
async function _loadInspections(deviceId) {
  const res = await Auth.apiFetch(`/api/power-devices/${deviceId}/inspections/`);
  if (!res.ok) return [];
  return await res.json();
}

async function _renderInspTab() {
  const d = _currentDevice;
  document.getElementById('inspDeviceCard').innerHTML =
    `<span class="ps-insp-card-id">${_esc(d.power_id)}</span>
     스마트 전력 시스템 &middot; MAC ${_esc(d.device_id)} &middot; 담당자 : ${_esc(d.manager_name || '-')}`;

  const inspections = await _loadInspections(d.id);
  const actionNeeded = inspections.filter(i => i.status === 'action_needed' && !i.is_actioned);
  const latest = inspections[0];

  document.getElementById('inspStatusVal').textContent = actionNeeded.length ? '점검 필요' : '점검 완료';
  document.getElementById('inspStatusVal').className = `ps-status-val ${actionNeeded.length ? 'needed' : 'done'}`;
  document.getElementById('inspLastDate').textContent = latest ? latest.inspection_date : '-';
  document.getElementById('inspActionCount').textContent = actionNeeded.length;

  const tbody = document.getElementById('inspTbody');
  if (!inspections.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="ps-empty-cell">점검 이력이 없습니다.</td></tr>';
    return;
  }
  tbody.innerHTML = inspections.map(i => {
    const typeLabel = i.inspection_type === 'regular' ? '정기' : '이상';
    const actionBadge = i.is_actioned
      ? '<span class="ps-badge ps-badge-done">조치 완료</span>'
      : (i.status === 'action_needed'
        ? `<span class="ps-badge ps-badge-needed">조치 필요</span>`
        : '-');
    const actionBtn = (i.status === 'action_needed' && !i.is_actioned)
      ? `<button class="ps-action-btn" onclick="_openAction(${i.id})">조치 등록</button>`
      : '';
    return `<tr>
      <td>${typeLabel}</td>
      <td>${actionBadge}</td>
      <td>${_fmtDate(i.inspection_date)}</td>
      <td>${_esc(i.inspector_name || '-')}</td>
      <td>${_esc(i.action_user_name || '-')}</td>
      <td class="ps-notes-cell">${_esc(i.notes || '-')}</td>
      <td>${actionBtn}</td>
    </tr>`;
  }).join('');
}

// ── 점검 등록 ─────────────────────────────────────────────────
function _openInspCreate() {
  const d = _currentDevice;
  document.getElementById('inspCreateCard').innerHTML =
    `<span class="ps-insp-card-id">${_esc(d.power_id)}</span>
     스마트 전력 시스템 &middot; MAC ${_esc(d.device_id)} &middot; 담당자 : ${_esc(d.manager_name || '-')}`;
  document.getElementById('inspType').value = 'regular';
  document.getElementById('inspDate').value = new Date().toISOString().split('T')[0];
  document.getElementById('inspector').value = d.manager_name || '-';
  document.getElementById('inspStatus').value = 'normal';
  document.getElementById('inspExpectedDateWrap').style.display = 'none';
  document.getElementById('inspExpectedDate').value = '';
  document.getElementById('inspNotes').value = '';
  document.getElementById('errInspNotes').textContent = '';
  document.getElementById('errInspGlobal').textContent = '';
  _hideModal('detailModal');
  _showModal('inspCreateModal');
}

async function _submitInspection() {
  document.getElementById('errInspNotes').textContent = '';
  document.getElementById('errInspGlobal').textContent = '';
  const notes = document.getElementById('inspNotes').value.trim();
  if (!notes) { document.getElementById('errInspNotes').textContent = '점검 의견을 입력해 주세요.'; return; }

  const payload = {
    device: _currentDevice.id,
    inspection_type: document.getElementById('inspType').value,
    inspection_date: document.getElementById('inspDate').value,
    status: document.getElementById('inspStatus').value,
    notes,
    expected_action_date: document.getElementById('inspExpectedDate').value || null,
  };

  try {
    const res = await Auth.apiFetch(`/api/power-devices/${_currentDevice.id}/inspections/`, { method: 'POST', body: JSON.stringify(payload) });
    if (!res.ok) {
      const err = await res.json();
      document.getElementById('errInspGlobal').textContent = JSON.stringify(err);
      return;
    }
    _hideModal('inspCreateModal');
    document.getElementById('successMsg').textContent = '점검이 등록되었습니다.';
    _showModal('successModal');
    _loadDevices();
    await _renderInspTab();
    _showModal('detailModal');
    _switchTab('insp');
  } catch {
    document.getElementById('errInspGlobal').textContent = '점검 등록 중 오류가 발생했습니다.';
  }
}

// ── 조치 등록 ─────────────────────────────────────────────────
function _openAction(inspectionId) {
  _currentInspectionId = inspectionId;
  const d = _currentDevice;
  document.getElementById('actionCard').innerHTML =
    `<span class="ps-insp-card-id">${_esc(d.power_id)}</span>
     스마트 전력 시스템 &middot; MAC ${_esc(d.device_id)} &middot; 담당자 : ${_esc(d.manager_name || '-')}`;
  document.getElementById('actionUser').value = d.manager_name || '-';
  document.getElementById('actionNotes').value = '';
  document.getElementById('errActionNotes').textContent = '';
  _showModal('actionModal');
}

async function _submitAction() {
  document.getElementById('errActionNotes').textContent = '';
  const notes = document.getElementById('actionNotes').value.trim();
  if (!notes) { document.getElementById('errActionNotes').textContent = '조치 내용을 입력해 주세요.'; return; }

  const payload = {
    action_notes: notes,
    action_user: _currentDevice.manager || null,
  };

  try {
    const res = await Auth.apiFetch(`/api/power-devices/inspections/${_currentInspectionId}/action/`, { method: 'POST', body: JSON.stringify(payload) });
    if (!res.ok) return;
    _hideModal('actionModal');
    document.getElementById('successMsg').textContent = '조치가 등록되었습니다.';
    _showModal('successModal');
    _loadDevices();
    await _renderInspTab();
    _showModal('detailModal');
    _switchTab('insp');
  } catch { console.error('조치 등록 실패'); }
}

// ── 탭 전환 ───────────────────────────────────────────────────
function _switchTab(tab) {
  document.querySelectorAll('.ps-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
  document.getElementById('tabInfo').style.display = tab === 'info' ? '' : 'none';
  document.getElementById('tabInsp').style.display = tab === 'insp' ? '' : 'none';
  if (tab === 'insp') _renderInspTab();
}

// ── 비활성화 ──────────────────────────────────────────────────
function _openBulkDelete(ids) {
  _deleteTargetIds = ids;
  document.getElementById('deleteMsg').textContent =
    ids.length === 1
      ? '선택한 장비를 비활성화 하시겠습니까?'
      : `선택한 ${ids.length}개 장비를 비활성화 하시겠습니까?`;
  _showModal('deleteModal');
}

async function _confirmDelete() {
  try {
    const res = await Auth.apiFetch('/api/power-devices/bulk-delete/', { method: 'POST', body: JSON.stringify({ ids: _deleteTargetIds }),
    });
    if (!res.ok) return;
    _hideModal('deleteModal');
    _selected.clear(); _syncBulkBtn();
    document.getElementById('successMsg').textContent = '비활성화되었습니다.';
    _showModal('successModal');
    _page = 1; _loadDevices();
  } catch { console.error('삭제 실패'); }
}

// ── 이벤트 바인딩 ─────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  if (!await AdminAccess.check()) return;
  _populateDeviceFilter();
  _loadDevices();

  document.getElementById('btnCreate').addEventListener('click', _openCreate);
  document.getElementById('btnSearch').addEventListener('click', () => { _page = 1; _loadDevices(); });
  document.getElementById('btnReset').addEventListener('click', () => {
    document.getElementById('filterDeviceId').value = '';
    document.getElementById('filterActive').value = '';
    document.getElementById('filterConnection').value = '';
    document.getElementById('filterOrder').value = 'device_id_asc';
    _page = 1; _loadDevices();
  });
  document.getElementById('filterOrder').addEventListener('change', () => { _page = 1; _loadDevices(); });

  document.getElementById('chkAll').addEventListener('change', e => {
    document.querySelectorAll('.row-chk').forEach(chk => {
      chk.checked = e.target.checked;
      const id = Number(chk.dataset.id);
      if (e.target.checked) _selected.add(id); else _selected.delete(id);
    });
    _syncBulkBtn();
  });

  document.getElementById('btnBulkDelete').addEventListener('click', () => {
    _openBulkDelete([..._selected]);
  });

  // 등록 모달
  document.getElementById('createDeviceType').addEventListener('change', _onCreateTypeChange);
  document.getElementById('btnCreateCancel').addEventListener('click', () => _hideModal('createModal'));
  document.getElementById('btnCreateSubmit').addEventListener('click', _submitCreate);
  document.getElementById('btnCreateConnCheck').addEventListener('click', () =>
    _checkConn('createIp', 'createPort', 'createConnStatus'));

  // 수정 모달
  document.getElementById('btnEditCancel').addEventListener('click', () => _hideModal('detailModal'));
  document.getElementById('btnEditSubmit').addEventListener('click', _submitEdit);
  document.getElementById('btnEditConnCheck').addEventListener('click', () =>
    _checkConn('editIp', 'editPort', 'editConnStatus'));
  document.querySelectorAll('.ps-tab').forEach(t => {
    t.addEventListener('click', () => _switchTab(t.dataset.tab));
  });
  document.getElementById('createDepartment').addEventListener('change', () => {
    _loadManagerOptions('createManager', document.getElementById('createDepartment').value);
  });
  document.getElementById('editDepartment').addEventListener('change', () => {
    _loadManagerOptions('editManager', document.getElementById('editDepartment').value);
  });

  // 점검 탭
  document.getElementById('btnInspCreate').addEventListener('click', _openInspCreate);
  document.getElementById('btnInspClose').addEventListener('click', () => _hideModal('detailModal'));
  document.getElementById('inspStatus').addEventListener('change', () => {
    const needed = document.getElementById('inspStatus').value === 'action_needed';
    document.getElementById('inspExpectedDateWrap').style.display = needed ? '' : 'none';
  });
  document.getElementById('btnInspCancel').addEventListener('click', () => {
    _hideModal('inspCreateModal');
    _showModal('detailModal');
    _switchTab('insp');
  });
  document.getElementById('btnInspSubmit').addEventListener('click', _submitInspection);

  // 조치 모달
  document.getElementById('btnActionCancel').addEventListener('click', () => _hideModal('actionModal'));
  document.getElementById('btnActionSubmit').addEventListener('click', _submitAction);

  // 삭제 확인
  document.getElementById('btnDeleteCancel').addEventListener('click', () => _hideModal('deleteModal'));
  document.getElementById('btnDeleteConfirm').addEventListener('click', _confirmDelete);

  // 성공 팝업
  document.getElementById('btnSuccessClose').addEventListener('click', () => _hideModal('successModal'));

  // 오버레이 클릭 닫기
  ['createModal','detailModal','inspCreateModal','actionModal','successModal','deleteModal'].forEach(id => {
    document.getElementById(id).addEventListener('click', e => {
      if (e.target === e.currentTarget) _hideModal(id);
    });
  });
});
