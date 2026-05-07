'use strict';

// ── 상태 ─────────────────────────────────────────────────
let _page = 1;
const _pageSize = 20;
let _total = 0;
let _selected = new Set();
let _deleteTargetId = null;
let _isEditMode = false;

// ── 헬퍼 ─────────────────────────────────────────────────
function _formatDate(iso) {
  if (!iso) return '-';
  return iso.slice(0, 10);
}

function _esc(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function _buildQuery() {
  const params = new URLSearchParams();
  const q = document.getElementById('searchInput').value.trim();
  if (q) params.set('q', q);
  const fac = document.getElementById('filterFacility').value;
  if (fac) params.set('facility', fac);
  const ia = document.getElementById('filterActive').value;
  if (ia) params.set('is_active', ia);
  params.set('order', document.getElementById('filterOrder').value);
  params.set('page', _page);
  params.set('page_size', _pageSize);
  return params.toString();
}

// ── 데이터 로드 ───────────────────────────────────────────
async function _loadEquipments() {
  const qs = _buildQuery();
  try {
    const res = await Auth.apiFetch(`/api/equipments/?${qs}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    _total = data.total;
    _renderTable(data.results);
    _renderPagination();
  } catch (err) {
    console.error('[Equipment] 목록 로드 실패:', err);
    document.getElementById('facilityTbody').innerHTML =
      '<tr class="fac-empty-row"><td colspan="11">데이터 로드에 실패했습니다.</td></tr>';
  }
}

async function _loadFacilityOptions() {
  try {
    const res = await Auth.apiFetch('/api/facilities/select/');
    if (!res.ok) return;
    const facilities = await res.json();
    [document.getElementById('filterFacility'), document.getElementById('formFacility')].forEach(sel => {
      const isFilter = sel.id === 'filterFacility';
      facilities.forEach(f => {
        const opt = document.createElement('option');
        opt.value = f.id;
        opt.textContent = `${f.facility_code} ${f.name}`;
        sel.appendChild(opt);
      });
    });
  } catch (_) {}
}

async function _loadPowerDeviceOptions(currentEquipmentId = null) {
  const sel = document.getElementById('formPowerDevice');
  // 기존 옵션 초기화 (첫 번째 "선택 안 함" 유지)
  while (sel.options.length > 1) sel.remove(1);

  try {
    const url = currentEquipmentId
      ? `/api/facilities/devices/select/?equipment_id=${currentEquipmentId}`
      : '/api/facilities/devices/select/';
    const res = await Auth.apiFetch(url);
    if (!res.ok) return;
    const devices = await res.json();
    devices.forEach(d => {
      const opt = document.createElement('option');
      opt.value = d.id;
      opt.textContent = d.is_active
        ? `${d.device_id}  ${d.device_name}`
        : `${d.device_id}  ${d.device_name}  (비활성)`;
      sel.appendChild(opt);
    });
  } catch (_) {}
}

// ── 렌더링 ───────────────────────────────────────────────
function _renderTable(equipments) {
  const tbody = document.getElementById('facilityTbody');
  if (!equipments.length) {
    tbody.innerHTML = '<tr class="fac-empty-row"><td colspan="11">검색 결과가 없습니다.</td></tr>';
    return;
  }

  tbody.innerHTML = equipments.map(e => {
    const badge = e.is_active
      ? '<span class="fac-badge fac-badge-active">사용</span>'
      : '<span class="fac-badge fac-badge-inactive">미사용</span>';
    const deviceTag = e.device_id
      ? `<span class="fac-power-tag fac-power-tag-id">${_esc(e.device_id)}</span> ${_esc(e.device_name || '')}`
      : '-';
    const checked = _selected.has(e.id) ? 'checked' : '';
    return `
      <tr data-id="${e.id}">
        <td class="col-chk"><input type="checkbox" class="row-chk" data-id="${e.id}" ${checked}></td>
        <td>${_esc(e.equipment_code)}</td>
        <td>${_esc(e.facility_code)}</td>
        <td>${_esc(e.name)}</td>
        <td>${_esc(e.facility_address || '-')}</td>
        <td>${deviceTag}</td>
        <td>${_esc(e.manager_name || '-')}</td>
        <td class="fac-notes-cell">${_esc(e.notes || '-')}</td>
        <td>${badge}</td>
        <td>${_formatDate(e.created_at)}</td>
        <td>
          <div class="fac-action-wrap">
            <button class="fac-action-btn" onclick="_openEdit(${e.id})">수정</button>
            ${e.is_active ? `<button class="fac-action-btn danger" onclick="_openDelete(${e.id})">비활성화</button>` : ''}
          </div>
        </td>
      </tr>`;
  }).join('');

  tbody.querySelectorAll('.row-chk').forEach(chk => {
    chk.addEventListener('change', ev => {
      const id = Number(ev.target.dataset.id);
      if (ev.target.checked) _selected.add(id);
      else _selected.delete(id);
      _syncBulkBtn();
      _syncChkAll();
    });
  });
}

function _renderPagination() {
  const totalPages = Math.ceil(_total / _pageSize) || 1;
  const pag = document.getElementById('pagination');
  let html = `<button class="fac-page-btn" onclick="_goPage(${_page - 1})" ${_page <= 1 ? 'disabled' : ''}>&#8249;</button>`;
  const start = Math.max(1, _page - 2);
  const end = Math.min(totalPages, _page + 2);
  if (start > 1) html += `<button class="fac-page-btn" onclick="_goPage(1)">1</button>`;
  if (start > 2) html += `<span class="fac-page-info">…</span>`;
  for (let p = start; p <= end; p++) {
    html += `<button class="fac-page-btn ${p === _page ? 'active' : ''}" onclick="_goPage(${p})">${p}</button>`;
  }
  if (end < totalPages - 1) html += `<span class="fac-page-info">…</span>`;
  if (end < totalPages) html += `<button class="fac-page-btn" onclick="_goPage(${totalPages})">${totalPages}</button>`;
  html += `<button class="fac-page-btn" onclick="_goPage(${_page + 1})" ${_page >= totalPages ? 'disabled' : ''}>&#8250;</button>`;
  html += `<span class="fac-page-info">총 ${_total}건</span>`;
  pag.innerHTML = html;
}

function _goPage(p) {
  const totalPages = Math.ceil(_total / _pageSize) || 1;
  _page = Math.max(1, Math.min(p, totalPages));
  _loadEquipments();
}

function _syncBulkBtn() {
  document.getElementById('btnBulkDelete').disabled = _selected.size === 0;
}

function _syncChkAll() {
  const allChks = document.querySelectorAll('.row-chk');
  const chkAll = document.getElementById('chkAll');
  if (!allChks.length) { chkAll.checked = false; chkAll.indeterminate = false; return; }
  const cnt = [...allChks].filter(c => c.checked).length;
  chkAll.checked = cnt === allChks.length;
  chkAll.indeterminate = cnt > 0 && cnt < allChks.length;
}

// ── 등록/수정 모달 ────────────────────────────────────────
function _clearForm() {
  document.getElementById('formEquipmentId').value = '';
  document.getElementById('formEquipmentCode').value = '';
  document.getElementById('formFacility').value = '';
  document.getElementById('formName').value = '';
  document.getElementById('formNotes').value = '';
  document.getElementById('formIsActive').checked = true;
  document.getElementById('errFacility').textContent = '';
  document.getElementById('errName').textContent = '';
  document.getElementById('errGlobal').textContent = '';
}

function _openCreate() {
  _isEditMode = false;
  _clearForm();
  document.getElementById('formModalTitle').textContent = '설비 등록';
  document.getElementById('formModalDesc').textContent = '신규 설비 정보를 입력하고 연결 전력 시스템을 선택하세요.';
  document.getElementById('formEquipmentCode').placeholder = '자동 생성';
  document.getElementById('btnFormSubmit').textContent = '등록';
  _loadPowerDeviceOptions();
  _showModal('formModal');
}

async function _openEdit(id) {
  try {
    const res = await Auth.apiFetch(`/api/equipments/${id}/`);
    if (!res.ok) { alert('설비 정보를 불러오지 못했습니다.'); return; }
    const e = await res.json();
    _isEditMode = true;
    _clearForm();
    document.getElementById('formModalTitle').textContent = '설비 수정';
    document.getElementById('formModalDesc').textContent = '설비 정보를 수정합니다.';
    document.getElementById('formEquipmentId').value = e.id;
    document.getElementById('formEquipmentCode').value = e.equipment_code;
    document.getElementById('formFacility').value = e.facility;
    document.getElementById('formName').value = e.name;
    document.getElementById('formNotes').value = e.notes || '';
    document.getElementById('formIsActive').checked = e.is_active;
    document.getElementById('btnFormSubmit').textContent = '저장';

    // 미연결 장치 + 현재 연결 장치 로드 후 선택
    await _loadPowerDeviceOptions(e.id);
    if (e.power_device_id) {
      document.getElementById('formPowerDevice').value = e.power_device_id;
    }
    _showModal('formModal');
  } catch (err) {
    alert('설비 정보 로드에 실패했습니다.');
  }
}

async function _submitForm() {
  const facilityId = document.getElementById('formFacility').value;
  const name = document.getElementById('formName').value.trim();

  let valid = true;
  if (!facilityId) {
    document.getElementById('errFacility').textContent = '공장을 선택하세요.';
    valid = false;
  } else {
    document.getElementById('errFacility').textContent = '';
  }
  if (!name) {
    document.getElementById('errName').textContent = '설비명은 필수입니다.';
    valid = false;
  } else {
    document.getElementById('errName').textContent = '';
  }
  if (!valid) return;

  document.getElementById('errGlobal').textContent = '';

  const powerDeviceVal = document.getElementById('formPowerDevice').value;
  const payload = {
    facility: Number(facilityId),
    name,
    notes: document.getElementById('formNotes').value.trim(),
    is_active: document.getElementById('formIsActive').checked,
    power_device: powerDeviceVal ? Number(powerDeviceVal) : null,
  };

  const eqId = document.getElementById('formEquipmentId').value;
  const url = eqId ? `/api/equipments/${eqId}/` : '/api/equipments/';
  const method = eqId ? 'PUT' : 'POST';

  try {
    const res = await Auth.apiFetch(url, { method, body: JSON.stringify(payload) });
    if (res.ok) {
      _hideModal('formModal');
      _page = eqId ? _page : 1;
      _loadEquipments();
      const msg = _isEditMode ? '수정되었습니다.' : '등록되었습니다.';
      document.getElementById('successModalText').textContent = msg;
      _showModal('successModal');
    } else {
      const err = await res.json();
      const msg = Object.values(err).flat().join(' ');
      document.getElementById('errGlobal').textContent = msg || '저장에 실패했습니다.';
    }
  } catch (_) {
    document.getElementById('errGlobal').textContent = '네트워크 오류가 발생했습니다.';
  }
}

// ── 비활성화 모달 ─────────────────────────────────────────
function _openDelete(id) {
  _deleteTargetId = id;
  document.getElementById('deleteModalText').textContent = '해당 설비를 비활성화하시겠습니까?';
  _showModal('deleteModal');
}

async function _confirmDelete() {
  if (!_deleteTargetId) return;
  try {
    const res = await Auth.apiFetch(`/api/equipments/${_deleteTargetId}/`, {
      method: 'DELETE',
    });
    if (res.ok || res.status === 204) {
      _hideModal('deleteModal');
      _selected.delete(_deleteTargetId);
      _deleteTargetId = null;
      _loadEquipments();
    } else {
      alert('비활성화에 실패했습니다.');
    }
  } catch (_) {
    alert('네트워크 오류가 발생했습니다.');
  }
}

async function _bulkDelete() {
  if (!_selected.size) return;
  const ids = [..._selected];
  if (!confirm(`선택한 ${ids.length}개 설비를 비활성화하시겠습니까?`)) return;
  try {
    const res = await Auth.apiFetch('/api/equipments/bulk-delete/', {
      method: 'POST', body: JSON.stringify({ ids }),
    });
    if (res.ok) {
      _selected.clear();
      _syncBulkBtn();
      _loadEquipments();
    } else {
      alert('일부 항목 비활성화에 실패했습니다.');
    }
  } catch (_) {
    alert('네트워크 오류가 발생했습니다.');
  }
}

// ── 모달 헬퍼 ─────────────────────────────────────────────
function _showModal(id) { document.getElementById(id).style.display = 'flex'; }
function _hideModal(id) { document.getElementById(id).style.display = 'none'; }

// ── 이벤트 바인딩 ─────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  if (!await AdminAccess.check()) return;
  _loadFacilityOptions();
  _loadEquipments();

  document.getElementById('btnCreate').addEventListener('click', _openCreate);
  document.getElementById('btnSearch').addEventListener('click', () => { _page = 1; _loadEquipments(); });
  document.getElementById('searchInput').addEventListener('keydown', e => {
    if (e.key === 'Enter') { _page = 1; _loadEquipments(); }
  });
  document.getElementById('filterFacility').addEventListener('change', () => { _page = 1; _loadEquipments(); });
  document.getElementById('filterActive').addEventListener('change', () => { _page = 1; _loadEquipments(); });
  document.getElementById('filterOrder').addEventListener('change', () => { _page = 1; _loadEquipments(); });

  document.getElementById('chkAll').addEventListener('change', e => {
    document.querySelectorAll('.row-chk').forEach(chk => {
      chk.checked = e.target.checked;
      const id = Number(chk.dataset.id);
      if (e.target.checked) _selected.add(id);
      else _selected.delete(id);
    });
    _syncBulkBtn();
  });

  document.getElementById('btnBulkDelete').addEventListener('click', _bulkDelete);
  document.getElementById('btnFormCancel').addEventListener('click', () => _hideModal('formModal'));
  document.getElementById('btnFormSubmit').addEventListener('click', _submitForm);
  document.getElementById('btnDeleteCancel').addEventListener('click', () => _hideModal('deleteModal'));
  document.getElementById('btnDeleteConfirm').addEventListener('click', _confirmDelete);
  document.getElementById('btnSuccessClose').addEventListener('click', () => _hideModal('successModal'));

  ['formModal', 'deleteModal', 'successModal'].forEach(id => {
    document.getElementById(id).addEventListener('click', e => {
      if (e.target === e.currentTarget) _hideModal(id);
    });
  });
});
