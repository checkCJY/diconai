/**
 * common_codes.js — 공통 코드 관리 페이지 클라이언트 로직
 *
 * [데이터 흐름]
 * 1. 페이지 로드 → loadGroups() → 왼쪽 패널 CodeGroup 목록 렌더
 * 2. 그룹 클릭 → selectGroup(id) → 오른쪽 그룹 정보 + 코드 목록 로드
 * 3. 코드 등록/수정/삭제/미사용전환 → API → 화면 갱신
 *
 * [API 경로 (/api/admin/ 하위)]
 * GET/POST   code-groups/                  그룹 목록·생성
 * PATCH/DEL  code-groups/<id>/             그룹 수정·삭제
 * GET/POST   code-groups/<id>/codes/       코드 목록·생성
 * PATCH/DEL  codes/<id>/                   코드 수정·삭제
 * POST       codes/bulk-deactivate/        코드 일괄 미사용
 */

const BASE = '/api/admin';
const PAGE_SIZE = 10;

/* ── 상태 ── */
let groups = [];            // 전체 그룹 목록
let selectedGroup = null;  // 현재 선택된 그룹
let allCodes = [];          // 현재 그룹의 전체 코드 목록
let filteredCodes = [];     // 검색·정렬 적용 후 목록
let currentPage = 1;
// 사용여부 토글 상태 — true=사용, false=미사용
let codeActiveValue = true;

/* ── 유틸 ── */

function fmtDate(iso) {
  if (!iso) return '-';
  const d = new Date(iso);
  const p = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

function activeBadge(isActive) {
  return isActive
    ? '<span class="badge badge-success">사용</span>'
    : '<span class="badge badge-gray">미사용</span>';
}

/* ── 그룹 목록 ── */

async function loadGroups(query = '') {
  const url = query
    ? `${BASE}/code-groups/?q=${encodeURIComponent(query)}`
    : `${BASE}/code-groups/`;
  try {
    const res = await Auth.apiFetch(url);
    groups = await res.json();
    renderGroupList();
  } catch (e) {
    console.error('그룹 로드 실패', e);
  }
}

function renderGroupList() {
  const ul = document.getElementById('groupList');
  if (!groups.length) {
    ul.innerHTML = '<li class="group-empty">등록된 그룹이 없습니다.</li>';
    return;
  }
  ul.innerHTML = groups.map(g => `
    <li class="group-item${selectedGroup?.id === g.id ? ' active' : ''}"
        data-id="${g.id}" onclick="selectGroup(${g.id})">
      <div>
        <div class="group-name">${g.name}</div>
        <div class="group-code">${g.code}</div>
      </div>
    </li>
  `).join('');
}

/* ── 그룹 선택 ── */

async function selectGroup(id) {
  selectedGroup = groups.find(g => g.id === id) || null;
  if (!selectedGroup) return;

  renderGroupList();
  document.getElementById('btnEditGroup').disabled = false;

  document.getElementById('rightEmpty').style.display = 'none';
  document.getElementById('rightContent').style.display = 'block';
  document.getElementById('infoSelectedBadge').textContent = `선택 그룹: ${selectedGroup.code}`;
  document.getElementById('infoName').textContent = selectedGroup.name;
  document.getElementById('infoCode').textContent = selectedGroup.code;
  document.getElementById('infoScope').textContent = selectedGroup.scope || '-';
  document.getElementById('infoUpdated').textContent = fmtDate(selectedGroup.updated_at);
  document.getElementById('infoCount').textContent = `${selectedGroup.code_count}건`;
  document.getElementById('toolbarGroupBadge').textContent = selectedGroup.name;

  await loadCodes(id);
}

/* ── 코드 목록 ── */

async function loadCodes(groupId) {
  try {
    const res = await Auth.apiFetch(`${BASE}/code-groups/${groupId}/codes/`);
    allCodes = await res.json();
    currentPage = 1;
    applyFilterAndSort();
  } catch (e) {
    console.error('코드 로드 실패', e);
  }
}

function applyFilterAndSort() {
  const q = document.getElementById('codeSearch').value.trim().toLowerCase();
  const sort = document.getElementById('sortSelect').value;

  let result = allCodes.filter(c => {
    if (!q) return true;
    return c.code.toLowerCase().includes(q) || c.name.toLowerCase().includes(q);
  });

  result.sort((a, b) => {
    if (sort === 'sort_asc')    return a.code.localeCompare(b.code);
    if (sort === 'sort_desc')   return b.code.localeCompare(a.code);
    if (sort === 'name_asc')    return a.name.localeCompare(b.name);
    if (sort === 'name_desc')   return b.name.localeCompare(a.name);
    if (sort === 'order_asc')   return a.sort_order - b.sort_order;
    if (sort === 'order_desc')  return b.sort_order - a.sort_order;
    if (sort === 'active_first') {
      if (a.is_active === b.is_active) return 0;
      return a.is_active ? -1 : 1;
    }
    if (sort === 'updated_desc') return new Date(b.updated_at) - new Date(a.updated_at);
    return 0;
  });

  filteredCodes = result;
  document.getElementById('codeCount').textContent = filteredCodes.length;
  renderPage();
  renderPagination();
  document.getElementById('checkAll').checked = false;
  updateSelectionUI();
}

function renderPage() {
  const tbody = document.getElementById('codeTableBody');
  const start = (currentPage - 1) * PAGE_SIZE;
  const items = filteredCodes.slice(start, start + PAGE_SIZE);

  if (!items.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="empty-state">코드가 없습니다.</td></tr>`;
    document.getElementById('paginationBar').style.display = 'none';
    return;
  }

  tbody.innerHTML = items.map(c => `
    <tr data-id="${c.id}">
      <td><input type="checkbox" class="row-check" value="${c.id}"></td>
      <td class="mono">${c.code}</td>
      <td>${c.name}</td>
      <td>${c.description || '-'}</td>
      <td>${c.sort_order}</td>
      <td>${activeBadge(c.is_active)}</td>
      <td>${fmtDate(c.updated_at)}</td>
    </tr>
  `).join('');

  tbody.querySelectorAll('.row-check').forEach(cb => {
    cb.addEventListener('change', updateSelectionUI);
  });

  document.getElementById('paginationBar').style.display =
    filteredCodes.length > PAGE_SIZE ? 'flex' : 'none';
}

function renderPagination() {
  const total = filteredCodes.length;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const start = (currentPage - 1) * PAGE_SIZE + 1;
  const end = Math.min(currentPage * PAGE_SIZE, total);
  document.getElementById('pageRange').textContent = `${start} - ${end} / ${total}`;

  const btns = document.getElementById('pageButtons');
  let html = `<button class="page-btn" onclick="goPage(${currentPage-1})" ${currentPage<=1?'disabled':''}>&lt;</button>`;
  for (let i = 1; i <= totalPages; i++) {
    html += `<button class="page-btn${i===currentPage?' active':''}" onclick="goPage(${i})">${i}</button>`;
  }
  html += `<button class="page-btn" onclick="goPage(${currentPage+1})" ${currentPage>=totalPages?'disabled':''}>&gt;</button>`;
  btns.innerHTML = html;
}

function goPage(page) {
  const totalPages = Math.ceil(filteredCodes.length / PAGE_SIZE);
  if (page < 1 || page > totalPages) return;
  currentPage = page;
  renderPage();
  renderPagination();
  document.getElementById('checkAll').checked = false;
  updateSelectionUI();
}

function getSelectedIds() {
  return [...document.querySelectorAll('.row-check:checked')].map(cb => parseInt(cb.value));
}

/**
 * 선택 상태에 따라 배지·버튼 활성/비활성 처리
 * - 0건: 삭제·미사용·수정 비활성
 * - 1건: 삭제·미사용·수정 모두 활성
 * - 2건+: 삭제·미사용 활성, 수정 비활성 (단일 수정만 허용)
 */
function updateSelectionUI() {
  const ids = getSelectedIds();
  const n = ids.length;

  // 툴바 배지
  const badge = document.getElementById('selectedBadge');
  if (n > 0) {
    badge.textContent = `${n}건 선택`;
    badge.style.display = 'inline-flex';
  } else {
    badge.style.display = 'none';
  }

  // 하단 배지
  const bottomBadge = document.getElementById('bottomCountBadge');
  if (n > 0) {
    bottomBadge.textContent = `${n}건`;
    bottomBadge.style.display = 'inline-block';
  } else {
    bottomBadge.style.display = 'none';
  }

  // 버튼 활성화 제어
  document.getElementById('btnDeleteCode').disabled = n === 0;
  document.getElementById('btnDeactivateCode').disabled = n === 0;
  document.getElementById('btnEditCodeBottom').disabled = n !== 1; // 수정은 1건만
}

/* ── 그룹 모달 ── */

function openAddGroupModal() {
  document.getElementById('groupModalTitle').textContent = '코드 그룹 등록';
  document.getElementById('btnGroupModalSave').textContent = '등록';
  document.getElementById('groupModalId').value = '';
  document.getElementById('groupModalName').value = '';
  document.getElementById('groupModalCode').value = '';
  document.getElementById('groupModalCode').readOnly = false;
  document.getElementById('groupModalCode').classList.remove('readonly');
  document.getElementById('groupModalScope').value = '';
  // 등록 시 최근수정일은 현재 시각으로 표시 (서버에서 자동 생성)
  document.getElementById('groupModalUpdated').value = fmtDate(new Date().toISOString());
  document.getElementById('groupModalDesc').value = '';
  document.getElementById('groupDescCount').textContent = '0';
  document.getElementById('groupModalEditor').value = ADMIN_CURRENT_USER;
  document.getElementById('groupModalCodeCount').value = '-건';
  document.getElementById('groupModalOverlay').style.display = 'flex';
}

function openEditGroupModal() {
  if (!selectedGroup) return;
  document.getElementById('groupModalTitle').textContent = '코드 그룹 수정';
  document.getElementById('btnGroupModalSave').textContent = '수정';
  document.getElementById('groupModalId').value = selectedGroup.id;
  document.getElementById('groupModalName').value = selectedGroup.name;
  // 수정 시 그룹코드 읽기전용 (Figma Screen 5)
  document.getElementById('groupModalCode').value = selectedGroup.code;
  document.getElementById('groupModalCode').readOnly = true;
  document.getElementById('groupModalCode').classList.add('readonly');
  document.getElementById('groupModalScope').value = selectedGroup.scope || '';
  document.getElementById('groupModalUpdated').value = fmtDate(selectedGroup.updated_at);
  document.getElementById('groupModalDesc').value = selectedGroup.description || '';
  document.getElementById('groupDescCount').textContent = (selectedGroup.description || '').length;
  document.getElementById('groupModalEditor').value = ADMIN_CURRENT_USER;
  document.getElementById('groupModalCodeCount').value = `${selectedGroup.code_count}건`;
  document.getElementById('groupModalOverlay').style.display = 'flex';
}

function closeGroupModal() {
  document.getElementById('groupModalOverlay').style.display = 'none';
}

async function saveGroup() {
  const id = document.getElementById('groupModalId').value;
  const isEdit = !!id;

  const payload = {
    name:        document.getElementById('groupModalName').value.trim(),
    code:        document.getElementById('groupModalCode').value.trim(),
    scope:       document.getElementById('groupModalScope').value.trim(),
    description: document.getElementById('groupModalDesc').value.trim(),
    is_active:   true,
  };

  if (!payload.name)  { alert('그룹명을 입력하세요.'); return; }
  if (!isEdit && !payload.code)  { alert('그룹 코드를 입력하세요.'); return; }
  if (!payload.scope) { alert('관리 범위를 입력하세요.'); return; }

  const url = isEdit ? `${BASE}/code-groups/${id}/` : `${BASE}/code-groups/`;
  const method = isEdit ? 'PATCH' : 'POST';
  if (isEdit) delete payload.code; // 수정 시 코드 필드 전송 안 함

  try {
    const res = await Auth.apiFetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) { const err = await res.json(); alert(JSON.stringify(err)); return; }

    closeGroupModal();
    await loadGroups(document.getElementById('groupSearch').value.trim());

    if (isEdit) {
      // 수정 후 선택 그룹 정보 갱신
      selectedGroup = groups.find(g => g.id === parseInt(id)) || selectedGroup;
      if (selectedGroup) {
        document.getElementById('infoName').textContent = selectedGroup.name;
        document.getElementById('infoScope').textContent = selectedGroup.scope || '-';
        document.getElementById('infoUpdated').textContent = fmtDate(selectedGroup.updated_at);
        renderGroupList();
      }
    }
  } catch (e) {
    alert('저장에 실패했습니다.');
    console.error(e);
  }
}

/* ── 코드 모달 ── */

/** 사용여부 토글 상태 반영 */
function setActiveToggle(isActive) {
  codeActiveValue = isActive;
  document.getElementById('codeActiveTrue').classList.toggle('toggle-active', isActive);
  document.getElementById('codeActiveFalse').classList.toggle('toggle-active', !isActive);
}

function openAddCodeModal() {
  if (!selectedGroup) return;
  document.getElementById('codeModalTitle').textContent = '공통 코드 등록';
  document.getElementById('btnCodeModalSave').textContent = '등록';
  document.getElementById('codeModalId').value = '';
  document.getElementById('codeModalGroup').value = `${selectedGroup.name} (${selectedGroup.code})`;
  document.getElementById('codeModalEditor').value = ADMIN_CURRENT_USER;
  document.getElementById('codeModalCode').value = '';
  document.getElementById('codeModalCode').readOnly = false;
  document.getElementById('codeModalCode').classList.remove('readonly');
  document.getElementById('codeModalName').value = '';
  document.getElementById('codeModalDesc').value = '';
  document.getElementById('codeDescCount').textContent = '0';
  document.getElementById('codeModalSort').value = '0';
  setActiveToggle(true);
  document.getElementById('codeModalOverlay').style.display = 'flex';
}

function openEditCodeModal(id) {
  const code = allCodes.find(c => c.id === id);
  if (!code) return;

  document.getElementById('codeModalTitle').textContent = '공통 코드 수정';
  document.getElementById('btnCodeModalSave').textContent = '수정';
  document.getElementById('codeModalId').value = code.id;
  document.getElementById('codeModalGroup').value = `${selectedGroup.name} (${selectedGroup.code})`;
  document.getElementById('codeModalEditor').value = ADMIN_CURRENT_USER;
  // 수정 시 코드값 읽기전용 (Figma Screen 3)
  document.getElementById('codeModalCode').value = code.code;
  document.getElementById('codeModalCode').readOnly = true;
  document.getElementById('codeModalCode').classList.add('readonly');
  document.getElementById('codeModalName').value = code.name;
  document.getElementById('codeModalDesc').value = code.description || '';
  document.getElementById('codeDescCount').textContent = (code.description || '').length;
  document.getElementById('codeModalSort').value = code.sort_order;
  setActiveToggle(code.is_active);
  document.getElementById('codeModalOverlay').style.display = 'flex';
}

function closeCodeModal() {
  document.getElementById('codeModalOverlay').style.display = 'none';
}

async function saveCode() {
  const id = document.getElementById('codeModalId').value;
  const isEdit = !!id;

  const payload = {
    code:        document.getElementById('codeModalCode').value.trim(),
    name:        document.getElementById('codeModalName').value.trim(),
    description: document.getElementById('codeModalDesc').value.trim(),
    sort_order:  parseInt(document.getElementById('codeModalSort').value) || 0,
    is_active:   codeActiveValue,
  };

  if (!isEdit && !payload.code) { alert('코드를 입력하세요.'); return; }
  if (!payload.name)            { alert('코드명을 입력하세요.'); return; }
  if (!payload.description)     { alert('설명을 입력하세요.'); return; }

  const url = isEdit
    ? `${BASE}/codes/${id}/`
    : `${BASE}/code-groups/${selectedGroup.id}/codes/`;
  const method = isEdit ? 'PATCH' : 'POST';
  if (isEdit) delete payload.code;

  try {
    const res = await Auth.apiFetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) { const err = await res.json(); alert(JSON.stringify(err)); return; }

    closeCodeModal();
    await loadCodes(selectedGroup.id);
    await refreshGroupInfo();
  } catch (e) {
    alert('저장에 실패했습니다.');
    console.error(e);
  }
}

/* ── 코드 삭제 ── */

async function deleteSelectedCodes() {
  const ids = getSelectedIds();
  if (!ids.length) return;
  if (!confirm(`선택한 ${ids.length}건을 삭제하시겠습니까?`)) return;

  const results = await Promise.allSettled(
    ids.map(id => Auth.apiFetch(`${BASE}/codes/${id}/`, { method: 'DELETE' }))
  );
  const failed = results.filter(r => r.status === 'rejected' || (r.value && !r.value.ok));
  if (failed.length) alert(`${failed.length}건 삭제에 실패했습니다.`);

  await loadCodes(selectedGroup.id);
  await refreshGroupInfo();
}

/* ── 코드 일괄 미사용 전환 ── */

async function deactivateSelectedCodes() {
  const ids = getSelectedIds();
  if (!ids.length) return;
  if (!confirm(`선택한 ${ids.length}건을 미사용으로 전환하시겠습니까?`)) return;

  try {
    const res = await Auth.apiFetch(`${BASE}/codes/bulk-deactivate/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids }),
    });
    if (!res.ok) { alert('미사용 전환에 실패했습니다.'); return; }

    await loadCodes(selectedGroup.id);
    await refreshGroupInfo();
  } catch (e) {
    alert('미사용 전환에 실패했습니다.');
    console.error(e);
  }
}

/* ── 하단 수정 버튼 ── */

function editSelectedCode() {
  const ids = getSelectedIds();
  if (ids.length !== 1) return;
  openEditCodeModal(ids[0]);
}

/* ── 그룹 정보 카드 갱신 ── */

async function refreshGroupInfo() {
  if (!selectedGroup) return;
  try {
    const res = await Auth.apiFetch(`${BASE}/code-groups/`);
    groups = await res.json();
    const refreshed = groups.find(g => g.id === selectedGroup.id);
    if (refreshed) {
      selectedGroup = refreshed;
      document.getElementById('infoCount').textContent = `${selectedGroup.code_count}건`;
      document.getElementById('infoUpdated').textContent = fmtDate(selectedGroup.updated_at);
      renderGroupList();
    }
  } catch (e) {
    console.error('그룹 정보 갱신 실패', e);
  }
}

/* ── 이벤트 바인딩 ── */

document.addEventListener('DOMContentLoaded', () => {

  loadGroups();

  // 상단 코드 그룹 등록 버튼
  document.getElementById('btnAddGroup').addEventListener('click', openAddGroupModal);

  // 그룹 검색
  document.getElementById('groupSearch').addEventListener('keydown', e => {
    if (e.key === 'Enter') loadGroups(e.target.value.trim());
  });
  document.getElementById('btnGroupSearch').addEventListener('click', () => {
    loadGroups(document.getElementById('groupSearch').value.trim());
  });

  // 그룹 수정 버튼 (왼쪽 패널 하단)
  document.getElementById('btnEditGroup').addEventListener('click', openEditGroupModal);

  // 그룹 모달
  document.getElementById('btnGroupModalClose').addEventListener('click', closeGroupModal);
  document.getElementById('btnGroupModalCancel').addEventListener('click', closeGroupModal);
  document.getElementById('btnGroupModalSave').addEventListener('click', saveGroup);

  // 그룹 설명 글자 수 카운트
  document.getElementById('groupModalDesc').addEventListener('input', function() {
    document.getElementById('groupDescCount').textContent = this.value.length;
  });

  // 코드 등록 버튼 (툴바 상단 + 하단 액션바)
  document.getElementById('btnAddCodeTop').addEventListener('click', openAddCodeModal);
  document.getElementById('btnAddCodeBottom').addEventListener('click', openAddCodeModal);

  // 코드 삭제 버튼 (툴바)
  document.getElementById('btnDeleteCode').addEventListener('click', deleteSelectedCodes);

  // 미사용 전환 버튼 (하단 액션바)
  document.getElementById('btnDeactivateCode').addEventListener('click', deactivateSelectedCodes);

  // 수정 버튼 (하단 액션바 — 1건 선택 시 활성)
  document.getElementById('btnEditCodeBottom').addEventListener('click', editSelectedCode);

  // 코드 모달
  document.getElementById('btnCodeModalClose').addEventListener('click', closeCodeModal);
  document.getElementById('btnCodeModalCancel').addEventListener('click', closeCodeModal);
  document.getElementById('btnCodeModalSave').addEventListener('click', saveCode);

  // 사용여부 토글 버튼
  document.getElementById('codeActiveTrue').addEventListener('click', () => setActiveToggle(true));
  document.getElementById('codeActiveFalse').addEventListener('click', () => setActiveToggle(false));

  // 코드 설명 글자 수 카운트
  document.getElementById('codeModalDesc').addEventListener('input', function() {
    document.getElementById('codeDescCount').textContent = this.value.length;
  });

  // 코드 검색
  document.getElementById('codeSearch').addEventListener('keydown', e => {
    if (e.key === 'Enter') applyFilterAndSort();
  });
  document.getElementById('btnCodeSearch').addEventListener('click', applyFilterAndSort);
  document.getElementById('btnResetSearch').addEventListener('click', () => {
    document.getElementById('codeSearch').value = '';
    applyFilterAndSort();
  });

  // 정렬 변경
  document.getElementById('sortSelect').addEventListener('change', applyFilterAndSort);

  // 전체 선택 체크박스
  document.getElementById('checkAll').addEventListener('change', e => {
    document.querySelectorAll('.row-check').forEach(cb => cb.checked = e.target.checked);
    updateSelectionUI();
  });

  // 모달 외부 클릭 닫기
  document.getElementById('groupModalOverlay').addEventListener('click', e => {
    if (e.target === e.currentTarget) closeGroupModal();
  });
  document.getElementById('codeModalOverlay').addEventListener('click', e => {
    if (e.target === e.currentTarget) closeCodeModal();
  });
});
