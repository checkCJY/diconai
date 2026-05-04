'use strict';

// ── 상태 ─────────────────────────────────────────────────
let _page = 1;
const _pageSize = 10;
let _total = 0;
let _selected = new Set();
let _currentSensor = null;   // 상세 보기 중인 센서 객체
let _deleteTargetIds = [];
let _createConnOk = false;
let _editConnOk = false;

// ── 헬퍼 ─────────────────────────────────────────────────
function _esc(str) {
  if (!str) return '';
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function _fmt(iso) {
  if (!iso) return '-';
  return String(iso).slice(0, 16).replace('T', ' ');
}
function _fmtDate(d) {
  if (!d) return '-';
  return String(d).slice(0, 10);
}
function _showModal(id) { document.getElementById(id).style.display = 'flex'; }
function _hideModal(id) { document.getElementById(id).style.display = 'none'; }
function _showSuccess(msg) {
  document.getElementById('successModalText').textContent = msg;
  _showModal('successModal');
}

// ── 쿼리 빌드 ─────────────────────────────────────────────
function _buildQuery() {
  const p = new URLSearchParams();
  const sid = document.getElementById('filterSensorId').value;
  if (sid) p.set('q', sid);
  const ia = document.getElementById('filterActive').value;
  if (ia) p.set('is_active', ia);
  const conn = document.getElementById('filterConnection').value;
  if (conn) p.set('connection', conn);
  p.set('order', document.getElementById('filterOrder').value);
  p.set('page', _page);
  p.set('page_size', _pageSize);
  return p.toString();
}

// ── 데이터 로드 ───────────────────────────────────────────
async function _loadSensors() {
  try {
    const res = await Auth.apiFetch(`/api/gas-sensors/?${_buildQuery()}`);
    if (!res.ok) throw new Error();
    const data = await res.json();
    _total = data.total;
    _renderTable(data.results);
    _renderPagination();
    document.getElementById('totalCount').textContent = _total;
    _populateSensorIdFilter(data.results);
  } catch {
    document.getElementById('sensorTbody').innerHTML =
      '<tr class="gs-empty-row"><td colspan="9">데이터 로드에 실패했습니다.</td></tr>';
  }
}

function _populateSensorIdFilter(sensors) {
  const sel = document.getElementById('filterSensorId');
  const current = sel.value;
  while (sel.options.length > 1) sel.remove(1);
  sensors.forEach(s => {
    const opt = document.createElement('option');
    opt.value = s.sensor_id;
    opt.textContent = s.sensor_id;
    sel.appendChild(opt);
  });
  sel.value = current;
}

async function _loadDepartmentOptions(selId, selectedId = '') {
  const sel = document.getElementById(selId);
  while (sel.options.length > 1) sel.remove(1);
  try {
    const res = await Auth.apiFetch('/api/departments/select/');
    if (!res.ok) return;
    const depts = await res.json();
    depts.forEach(d => {
      const opt = document.createElement('option');
      opt.value = d.id;
      opt.textContent = d.name;
      sel.appendChild(opt);
    });
    if (selectedId) sel.value = String(selectedId);
  } catch {}
}

async function _loadManagerOptions(selId, deptId = '', selectedId = '') {
  const sel = document.getElementById(selId);
  while (sel.options.length > 1) sel.remove(1);
  try {
    const url = deptId
      ? `/api/managers/select/?department_id=${deptId}`
      : '/api/managers/select/';
    const res = await Auth.apiFetch(url);
    if (!res.ok) return;
    const mgrs = await res.json();
    mgrs.forEach(m => {
      const opt = document.createElement('option');
      opt.value = m.id;
      opt.textContent = m.name;
      sel.appendChild(opt);
    });
    if (selectedId) sel.value = String(selectedId);
  } catch {}
}

// ── 테이블 렌더링 ─────────────────────────────────────────
function _renderTable(sensors) {
  const tbody = document.getElementById('sensorTbody');
  if (!sensors.length) {
    tbody.innerHTML = '<tr class="gs-empty-row"><td colspan="10">검색 결과가 없습니다.</td></tr>';
    return;
  }

  let hasAbnormal = false;
  tbody.innerHTML = sensors.map(s => {
    const isAbnormal = s.connection_status === 'disconnected';
    if (isAbnormal) hasAbnormal = true;

    const inspBadge = s.inspection_status === 'done'
      ? '<span class="gs-badge gs-badge-done">점검 완료</span>'
      : '<span class="gs-badge gs-badge-needed">점검 필요</span>';

    const activeBadge = s.is_active
      ? '<span class="gs-badge gs-badge-active">사용</span>'
      : '<span class="gs-badge gs-badge-inactive">미사용</span>';

    // 연결 상태: 미사용(inactive) / 연결끊김(disconnected) / 정상(normal) 3가지
    let connBadge;
    if (s.connection_status === 'inactive') {
      connBadge = '<span class="gs-conn-dash">-</span>';
    } else if (s.connection_status === 'disconnected') {
      connBadge = '<span class="gs-conn-dot disconnected"></span> 연결 끊김';
    } else {
      connBadge = '<span class="gs-conn-dot normal"></span> 정상';
    }

    const checked = _selected.has(s.id) ? 'checked' : '';
    const rowClass = isAbnormal ? 'gs-row-abnormal' : '';

    return `
      <tr data-id="${s.id}" class="${rowClass}">
        <td class="col-chk col-center"><input type="checkbox" class="row-chk" data-id="${s.id}" ${checked}></td>
        <td class="col-center">${inspBadge}</td>
        <td><a href="#" class="gs-sensor-link" data-id="${s.id}">${_esc(s.sensor_id)}</a></td>
        <td>${_esc(s.device_name || '-')}</td>
        <td class="col-center">${activeBadge}</td>
        <td class="col-center">${connBadge}</td>
        <td>${_fmt(s.last_reading)}</td>
        <td>${_fmtDate(s.latest_inspection_date)}</td>
        <td>${_esc(s.manager_name || '-')}</td>
        <td class="col-center">
          <div class="gs-action-wrap" style="justify-content:center;">
            <button class="gs-action-btn" onclick="_openDetail(${s.id})">수정</button>
            ${s.is_active ? `<button class="gs-action-btn danger" onclick="_openBulkDelete([${s.id}])">비활성화</button>` : ''}
          </div>
        </td>
      </tr>`;
  }).join('');

  document.getElementById('abnormalNote').style.display = hasAbnormal ? '' : 'none';

  tbody.querySelectorAll('.row-chk').forEach(chk => {
    chk.addEventListener('change', ev => {
      const id = Number(ev.target.dataset.id);
      if (ev.target.checked) _selected.add(id); else _selected.delete(id);
      _syncBulkBtn(); _syncChkAll();
    });
  });
  tbody.querySelectorAll('.gs-sensor-link').forEach(a => {
    a.addEventListener('click', ev => { ev.preventDefault(); _openDetail(Number(a.dataset.id)); });
  });
}

// ── 페이지네이션 ──────────────────────────────────────────
function _renderPagination() {
  const totalPages = Math.ceil(_total / _pageSize) || 1;
  const pag = document.getElementById('pagination');
  let html = `<button class="gs-page-btn" onclick="_goPage(${_page-1})" ${_page<=1?'disabled':''}>&#8249;</button>`;
  const start = Math.max(1, _page - 2), end = Math.min(totalPages, _page + 2);
  if (start > 1) html += `<button class="gs-page-btn" onclick="_goPage(1)">1</button>`;
  if (start > 2) html += `<span class="gs-page-info">…</span>`;
  for (let p = start; p <= end; p++) {
    html += `<button class="gs-page-btn ${p===_page?'active':''}" onclick="_goPage(${p})">${p}</button>`;
  }
  if (end < totalPages - 1) html += `<span class="gs-page-info">…</span>`;
  if (end < totalPages) html += `<button class="gs-page-btn" onclick="_goPage(${totalPages})">${totalPages}</button>`;
  html += `<button class="gs-page-btn" onclick="_goPage(${_page+1})" ${_page>=totalPages?'disabled':''}>&#8250;</button>`;
  html += `<span class="gs-page-info">총 ${_total}건</span>`;
  pag.innerHTML = html;
}
function _goPage(p) {
  const total = Math.ceil(_total / _pageSize) || 1;
  _page = Math.max(1, Math.min(p, total));
  _loadSensors();
}

function _syncBulkBtn() {
  document.getElementById('btnBulkDelete').disabled = _selected.size === 0;
}
function _syncChkAll() {
  const all = document.querySelectorAll('.row-chk');
  const chkAll = document.getElementById('chkAll');
  if (!all.length) { chkAll.checked = false; chkAll.indeterminate = false; return; }
  const cnt = [...all].filter(c => c.checked).length;
  chkAll.checked = cnt === all.length;
  chkAll.indeterminate = cnt > 0 && cnt < all.length;
}

// ── 장비 등록 모달 ────────────────────────────────────────
function _openCreate() {
  _createConnOk = false;
  document.getElementById('createDeviceType').value = '';
  document.getElementById('createDeviceCode').value = '';
  document.getElementById('createDeviceName').value = '';
  document.getElementById('createDeviceId').value = '';
  document.getElementById('createIp').value = '';
  document.getElementById('createPort').value = '';
  document.getElementById('createNotes').value = '';
  document.getElementById('createConnStatus').style.display = 'none';
  document.getElementById('createConnCheckedAt').value = '';
  document.querySelectorAll('input[name="createIsActive"]')[0].checked = true;
  ['errCreateDeviceType','errCreateDeviceName','errCreateDeviceId','errCreateDepartment','errCreateManager','errCreateConn','errCreateGlobal']
    .forEach(id => { document.getElementById(id).textContent = ''; });
  _loadDepartmentOptions('createDepartment');
  _loadManagerOptions('createManager');
  _showModal('createModal');
}

async function _onCreateTypeChange() {
  const type = document.getElementById('createDeviceType').value;
  if (!type) { document.getElementById('createDeviceCode').value = ''; return; }
  document.getElementById('errCreateDeviceType').textContent = '';
  try {
    const res = await Auth.apiFetch('/api/gas-sensors/next-code/');
    const data = await res.json();
    document.getElementById('createDeviceCode').value = data.code;
    document.getElementById('createDeviceName').value = `GAS-${data.code}`;
  } catch {
    document.getElementById('createDeviceCode').value = '';
  }
}

async function _checkConnection(ipId, portId, statusId, connCheckedId, isCreate) {
  const ip = document.getElementById(ipId).value.trim();
  const port = document.getElementById(portId).value.trim();
  const errId = isCreate ? 'errCreateConn' : null;

  if (!ip) { if (errId) document.getElementById(errId).textContent = 'IP 주소를 입력해 주세요.'; return; }
  if (!port) { if (errId) document.getElementById(errId).textContent = '포트 번호를 입력해 주세요.'; return; }
  if (errId) document.getElementById(errId).textContent = '';

  try {
    const res = await Auth.apiFetch('/api/gas-sensors/check-connection/', { method: 'POST', body: JSON.stringify({ ip_address: ip, port: Number(port) }),
    });
    const data = await res.json();
    const el = document.getElementById(statusId);
    el.style.display = '';
    if (data.ok) {
      el.className = 'gs-conn-status success';
      el.textContent = '연결 성공';
      if (isCreate) _createConnOk = true; else _editConnOk = true;
    } else {
      el.className = 'gs-conn-status fail';
      el.textContent = data.detail || '연결 실패';
      if (isCreate) _createConnOk = false; else _editConnOk = false;
    }
    const checkedAt = data.checked_at ? new Date(data.checked_at).toLocaleString('ko-KR') : '';
    document.getElementById(connCheckedId).value = checkedAt;
  } catch {
    if (errId) document.getElementById(errId).textContent = '연결 확인 중 오류가 발생했습니다.';
  }
}

async function _submitCreate() {
  const deviceType = document.getElementById('createDeviceType').value;
  const deviceName = document.getElementById('createDeviceName').value.trim();
  const deviceId = document.getElementById('createDeviceId').value.trim();
  const deptId = document.getElementById('createDepartment').value;
  const managerId = document.getElementById('createManager').value;

  let valid = true;
  if (!deviceType) { document.getElementById('errCreateDeviceType').textContent = '장비 유형을 선택해주세요.'; valid = false; }
  if (!deviceName) { document.getElementById('errCreateDeviceName').textContent = '장비명을 입력해주세요.'; valid = false; }
  else if (deviceName.length > 50) { document.getElementById('errCreateDeviceName').textContent = '장비명은 50자 이내로 입력해 주세요.'; valid = false; }
  if (!deviceId) { document.getElementById('errCreateDeviceId').textContent = '장비 ID를 입력해주세요.'; valid = false; }
  if (!deptId) { document.getElementById('errCreateDepartment').textContent = '관리 부서를 선택해 주세요.'; valid = false; }
  if (!managerId) { document.getElementById('errCreateManager').textContent = '관리 담당자를 선택해 주세요.'; valid = false; }
  if (!valid) return;

  const isActive = document.querySelector('input[name="createIsActive"]:checked').value === 'true';
  const payload = {
    facility: 1,  // 기본값 (추후 공장 선택 드롭다운 연동)
    device_code: document.getElementById('createDeviceCode').value,
    device_name: deviceName,
    device_id: deviceId,
    department: deptId ? Number(deptId) : null,
    manager: managerId ? Number(managerId) : null,
    ip_address: document.getElementById('createIp').value.trim(),
    port: document.getElementById('createPort').value ? Number(document.getElementById('createPort').value) : null,
    is_active: isActive,
    notes: document.getElementById('createNotes').value.trim(),
  };

  try {
    const res = await Auth.apiFetch('/api/gas-sensors/', { method: 'POST', body: JSON.stringify(payload) });
    if (res.ok) {
      _hideModal('createModal');
      _page = 1;
      _loadSensors();
      _showSuccess('등록되었습니다.');
    } else {
      const err = await res.json();
      const msg = Object.values(err).flat().join(' ');
      document.getElementById('errCreateGlobal').textContent = msg || '등록에 실패했습니다.';
    }
  } catch {
    document.getElementById('errCreateGlobal').textContent = '네트워크 오류가 발생했습니다.';
  }
}

// ── 센서 상세 모달 ────────────────────────────────────────
async function _openDetail(id) {
  try {
    const res = await Auth.apiFetch(`/api/gas-sensors/${id}/`);
    if (!res.ok) { alert('센서 정보를 불러오지 못했습니다.'); return; }
    _currentSensor = await res.json();
  } catch { alert('네트워크 오류가 발생했습니다.'); return; }

  const s = _currentSensor;
  document.getElementById('detailModalTitle').textContent = `유해가스 센서 ${s.sensor_id}`;
  document.getElementById('detailSensorId').value = s.id;

  // 기본 정보 채우기
  document.getElementById('editDeviceCode').value = s.device_code || '';
  document.getElementById('editDeviceName').value = s.device_name || '';
  document.getElementById('editDeviceId').value = s.device_id || '';
  document.getElementById('editIp').value = s.ip_address || '';
  document.getElementById('editPort').value = s.port || '';
  document.getElementById('editNotes').value = s.notes || '';
  document.querySelector(`input[name="editIsActive"][value="${s.is_active ? 'true' : 'false'}"]`).checked = true;
  document.getElementById('editConnOk').checked = !!s.connection_ok;
  document.getElementById('editConnCheckedAt').value = s.connection_checked_at
    ? new Date(s.connection_checked_at).toLocaleString('ko-KR') : '';
  document.getElementById('editConnStatus').style.display = 'none';
  _editConnOk = !!s.connection_ok;

  ['errEditDeviceName','errEditDeviceId','errEditDepartment','errEditManager','errEditGlobal']
    .forEach(id => { document.getElementById(id).textContent = ''; });

  // 부서/담당자 드롭다운 로드
  await _loadDepartmentOptions('editDepartment', s.department);
  await _loadManagerOptions('editManager', s.department, s.manager);

  // 기본 탭 활성화
  _switchTab('info');

  _showModal('detailModal');
}

function _switchTab(tab) {
  document.querySelectorAll('.gs-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
  document.getElementById('tabInfo').style.display = tab === 'info' ? '' : 'none';
  document.getElementById('tabInspection').style.display = tab === 'inspection' ? '' : 'none';
  if (tab === 'inspection' && _currentSensor) _loadInspectionTab();
}

async function _submitEdit() {
  const id = document.getElementById('detailSensorId').value;
  const deviceName = document.getElementById('editDeviceName').value.trim();
  const deviceId = document.getElementById('editDeviceId').value.trim();

  let valid = true;
  if (!deviceName) { document.getElementById('errEditDeviceName').textContent = '장비명을 입력해주세요.'; valid = false; }
  if (!deviceId) { document.getElementById('errEditDeviceId').textContent = '장비 ID를 입력해주세요.'; valid = false; }
  if (!valid) return;

  const isActive = document.querySelector('input[name="editIsActive"]:checked').value === 'true';
  const payload = {
    device_name: deviceName,
    device_id: deviceId,
    department: document.getElementById('editDepartment').value || null,
    manager: document.getElementById('editManager').value || null,
    ip_address: document.getElementById('editIp').value.trim(),
    port: document.getElementById('editPort').value ? Number(document.getElementById('editPort').value) : null,
    is_active: isActive,
    notes: document.getElementById('editNotes').value.trim(),
    connection_ok: document.getElementById('editConnOk').checked,
  };

  try {
    const res = await Auth.apiFetch(`/api/gas-sensors/${id}/`, { method: 'PUT', body: JSON.stringify(payload) });
    if (res.ok) {
      _hideModal('detailModal');
      _loadSensors();
      _showSuccess('수정되었습니다.');
    } else {
      const err = await res.json();
      const msg = Object.values(err).flat().join(' ');
      document.getElementById('errEditGlobal').textContent = msg || '저장에 실패했습니다.';
    }
  } catch {
    document.getElementById('errEditGlobal').textContent = '네트워크 오류가 발생했습니다.';
  }
}

// ── 점검 탭 ───────────────────────────────────────────────
async function _loadInspectionTab() {
  const s = _currentSensor;

  // 장비 요약 카드
  document.getElementById('inspSummary').innerHTML = `
    <div class="gs-insp-card">
      <span class="gs-insp-card-id">${_esc(s.sensor_id)}</span>
      유해가스 센서 &middot; MAC ${_esc(s.device_id)} &middot; 담당자 : ${_esc(s.manager_name || '-')}
      <button class="gs-action-btn" style="margin-left:auto;" onclick="_openInspCreate()">점검 등록</button>
    </div>`;

  // 점검 이력 로드
  try {
    const res = await Auth.apiFetch(`/api/gas-sensors/${s.id}/inspections/`);
    const inspections = await res.json();

    // 최근 점검 상태 카드
    const latest = inspections[0] || null;
    const nextDate = latest
      ? new Date(new Date(latest.inspection_date).getTime() + 30 * 86400000).toISOString().slice(0, 10)
      : '-';
    document.getElementById('inspStatusCards').innerHTML = `
      <div class="gs-status-card">
        <div class="gs-status-label">점검 여부</div>
        <div class="gs-status-val ${latest ? 'done' : 'needed'}">${latest ? '점검 완료' : '점검 필요'}</div>
      </div>
      <div class="gs-status-card">
        <div class="gs-status-label">최근 점검일</div>
        <div class="gs-status-val">${latest ? _fmtDate(latest.inspection_date) : '-'}</div>
      </div>
      <div class="gs-status-card">
        <div class="gs-status-label">다음 점검 예정일</div>
        <div class="gs-status-val">${nextDate}</div>
      </div>
      <div class="gs-status-card">
        <div class="gs-status-label">현재 상태</div>
        <div class="gs-status-val ${latest && latest.status === 'action_needed' && !latest.is_actioned ? 'needed' : 'done'}">
          ${latest && latest.status === 'action_needed' && !latest.is_actioned ? '조치 필요' : '조치 완료'}
        </div>
      </div>`;

    // 점검 이력 테이블
    const tbody = document.getElementById('inspTbody');
    if (!inspections.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="gs-empty-cell">점검 이력이 없습니다.</td></tr>';
      return;
    }
    tbody.innerHTML = inspections.map(insp => {
      const actionNeeded = insp.status === 'action_needed' && !insp.is_actioned;
      const actionBadge = actionNeeded
        ? `<span class="gs-badge gs-badge-needed">조치 필요</span>`
        : `<span class="gs-badge gs-badge-done">조치 완료</span>`;
      const actionBtn = actionNeeded
        ? `<button class="gs-action-btn" onclick="_openAction(${insp.id})">조치 등록</button>` : '';
      return `
        <tr>
          <td>${_esc(insp.inspection_type_display)}</td>
          <td>${actionBadge}</td>
          <td>${_fmtDate(insp.inspection_date)}</td>
          <td>${_esc(insp.inspector_name || '-')}</td>
          <td>${_esc(insp.action_user_name || '-')}</td>
          <td class="gs-notes-cell">${_esc(insp.notes)}${insp.action_notes ? ' / ' + _esc(insp.action_notes) : ''}</td>
          <td>${actionBtn}</td>
        </tr>`;
    }).join('');
  } catch {
    document.getElementById('inspTbody').innerHTML =
      '<tr><td colspan="7" class="gs-empty-cell">이력 로드에 실패했습니다.</td></tr>';
  }
}

// ── 점검 등록 ─────────────────────────────────────────────
function _openInspCreate() {
  if (!_currentSensor) return;
  const s = _currentSensor;
  document.getElementById('inspTargetCard').innerHTML = `
    <div class="gs-insp-card">
      <span class="gs-insp-card-id">${_esc(s.sensor_id)}</span>
      유해가스 센서 &middot; MAC ${_esc(s.device_id)} &middot; 담당자 : ${_esc(s.manager_name || '-')}
    </div>`;
  document.getElementById('inspType').value = '';
  document.getElementById('inspStatus').value = '';
  document.getElementById('inspNotes').value = '';
  document.getElementById('inspExpectedDate').value = '';
  document.getElementById('inspDate').value = new Date().toISOString().slice(0, 10);
  document.getElementById('inspector').value = s.manager_name || '-';
  document.getElementById('rowExpectedDate').style.display = 'none';
  ['errInspType','errInspStatus','errInspNotes','errInspExpectedDate']
    .forEach(id => { document.getElementById(id).textContent = ''; });
  _showModal('inspCreateModal');
}

async function _submitInspCreate() {
  const type = document.getElementById('inspType').value;
  const status = document.getElementById('inspStatus').value;
  const notes = document.getElementById('inspNotes').value.trim();
  const expected = document.getElementById('inspExpectedDate').value.trim();

  let valid = true;
  if (!type) { document.getElementById('errInspType').textContent = '점검 구분을 선택해 주세요.'; valid = false; }
  if (!status) { document.getElementById('errInspStatus').textContent = '점검 상태를 선택해 주세요.'; valid = false; }
  if (!notes) { document.getElementById('errInspNotes').textContent = '점검 의견을 입력해 주세요.'; valid = false; }
  if (status === 'action_needed' && !expected) {
    document.getElementById('errInspExpectedDate').textContent = '예상 조치일을 입력해 주세요.'; valid = false;
  }
  if (!valid) return;

  const payload = {
    sensor: _currentSensor.id,
    inspection_type: type,
    status,
    notes,
    expected_action_date: expected ? expected.replace(/\./g, '-') : null,
    inspection_date: document.getElementById('inspDate').value,
  };

  try {
    const res = await Auth.apiFetch(`/api/gas-sensors/${_currentSensor.id}/inspections/`, { method: 'POST', body: JSON.stringify(payload) });
    if (res.ok) {
      _hideModal('inspCreateModal');
      _loadInspectionTab();
      _showSuccess('저장되었습니다.');
    } else {
      const err = await res.json();
      const msg = Object.values(err).flat().join(' ');
      document.getElementById('errInspNotes').textContent = msg || '등록에 실패했습니다.';
    }
  } catch {
    document.getElementById('errInspNotes').textContent = '네트워크 오류가 발생했습니다.';
  }
}

// ── 조치 등록 ─────────────────────────────────────────────
async function _openAction(inspectionId) {
  try {
    const res = await Auth.apiFetch(`/api/gas-sensors/${_currentSensor.id}/inspections/`);
    const inspections = await res.json();
    const insp = inspections.find(i => i.id === inspectionId);
    if (!insp) return;

    document.getElementById('actionInspectionId').value = inspectionId;
    document.getElementById('actionTargetCard').innerHTML = `
      <div class="gs-insp-card">
        <span class="gs-insp-card-id">${_esc(_currentSensor.sensor_id)}</span>
        유해가스 센서 &middot; MAC ${_esc(_currentSensor.device_id)} &middot; 담당자 : ${_esc(_currentSensor.manager_name || '-')}
      </div>`;
    document.getElementById('actionInspType').value = insp.inspection_type_display;
    document.getElementById('actionInspDate').value = _fmtDate(insp.inspection_date);
    document.getElementById('actionInspector').value = insp.inspector_name || '-';
    document.getElementById('actionInspStatus').value = insp.status_display;
    document.getElementById('actionInspNotes').value = insp.notes;
    document.getElementById('actionDate').value = new Date().toISOString().slice(0, 10);
    document.getElementById('actionUser').value = _currentSensor.manager_name || '-';
    document.getElementById('actionNotes').value = '';
    document.getElementById('errActionNotes').textContent = '';
    _showModal('actionModal');
  } catch { alert('조치 정보를 불러오지 못했습니다.'); }
}

async function _submitAction() {
  const inspId = document.getElementById('actionInspectionId').value;
  const notes = document.getElementById('actionNotes').value.trim();
  if (!notes) { document.getElementById('errActionNotes').textContent = '조치 의견을 입력해 주세요.'; return; }

  try {
    const res = await Auth.apiFetch(`/api/gas-sensors/inspections/${inspId}/action/`, { method: 'POST', body: JSON.stringify({ action_notes: notes }),
    });
    if (res.ok) {
      _hideModal('actionModal');
      _loadInspectionTab();
      _showSuccess('저장되었습니다.');
    } else {
      const err = await res.json();
      document.getElementById('errActionNotes').textContent = err.detail || '조치 등록에 실패했습니다.';
    }
  } catch {
    document.getElementById('errActionNotes').textContent = '네트워크 오류가 발생했습니다.';
  }
}

// ── 비활성화 ──────────────────────────────────────────────
function _openBulkDelete(ids) {
  _deleteTargetIds = ids;
  document.getElementById('deleteModalText').textContent =
    `선택한 ${ids.length}개 장비를 비활성화하시겠습니까?`;
  _showModal('deleteModal');
}

async function _confirmDelete() {
  try {
    const res = await Auth.apiFetch('/api/gas-sensors/bulk-delete/', { method: 'POST', body: JSON.stringify({ ids: _deleteTargetIds }),
    });
    if (res.ok) {
      _hideModal('deleteModal');
      _selected.clear(); _syncBulkBtn();
      _loadSensors();
    } else { alert('비활성화에 실패했습니다.'); }
  } catch { alert('네트워크 오류가 발생했습니다.'); }
}

// ── 이벤트 바인딩 ─────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  if (!await AdminAccess.check()) return;
  _loadSensors();

  document.getElementById('btnCreate').addEventListener('click', _openCreate);
  document.getElementById('btnSearch').addEventListener('click', () => { _page = 1; _loadSensors(); });
  document.getElementById('btnReset').addEventListener('click', () => {
    document.getElementById('filterSensorId').value = '';
    document.getElementById('filterActive').value = '';
    document.getElementById('filterConnection').value = '';
    document.getElementById('filterOrder').value = 'sensor_id_asc';
    _page = 1; _loadSensors();
  });
  document.getElementById('filterOrder').addEventListener('change', () => { _page = 1; _loadSensors(); });

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
  document.getElementById('createDepartment').addEventListener('change', () => {
    _loadManagerOptions('createManager', document.getElementById('createDepartment').value);
  });
  document.getElementById('btnCreateConnCheck').addEventListener('click', () => {
    _checkConnection('createIp', 'createPort', 'createConnStatus', 'createConnCheckedAt', true);
  });
  document.getElementById('btnCreateCancel').addEventListener('click', () => _hideModal('createModal'));
  document.getElementById('btnCreateSubmit').addEventListener('click', _submitCreate);

  // 상세 모달 탭
  document.querySelectorAll('.gs-tab').forEach(tab => {
    tab.addEventListener('click', () => _switchTab(tab.dataset.tab));
  });
  document.getElementById('editDepartment').addEventListener('change', () => {
    _loadManagerOptions('editManager', document.getElementById('editDepartment').value);
  });
  document.getElementById('btnEditConnCheck').addEventListener('click', () => {
    _checkConnection('editIp', 'editPort', 'editConnStatus', 'editConnCheckedAt', false);
  });
  document.getElementById('btnDetailCancel').addEventListener('click', () => _hideModal('detailModal'));
  document.getElementById('btnInspCancel').addEventListener('click', () => _hideModal('detailModal'));
  document.getElementById('btnDetailSave').addEventListener('click', _submitEdit);

  // 점검 등록
  document.getElementById('inspStatus').addEventListener('change', () => {
    const show = document.getElementById('inspStatus').value === 'action_needed';
    document.getElementById('rowExpectedDate').style.display = show ? '' : 'none';
  });
  document.getElementById('btnInspCreateCancel').addEventListener('click', () => _hideModal('inspCreateModal'));
  document.getElementById('btnInspCreateSubmit').addEventListener('click', _submitInspCreate);

  // 조치 등록
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
