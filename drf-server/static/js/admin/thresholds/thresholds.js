'use strict';

/* ── 상태 ── */
let selectedGroupId   = null; // 현재 선택된 그룹 ID
let selectedGroupData = null; // 현재 선택된 그룹 전체 데이터
let allThresholds     = [];   // 현재 그룹의 전체 임계치 목록 (서버에서 받은 원본)
let filteredItems     = [];   // 검색·정렬 적용 후 목록

const PAGE_SIZE = 10;
let currentPage = 1;

/* ── 날짜 포맷 ── */
function fmt(iso) {
  if (!iso) return '-';
  if (typeof TimeFormat !== 'undefined') return TimeFormat.abs(iso);
  return new Date(iso).toLocaleString('ko-KR');
}

/* ── null 허용 숫자 파싱 (빈 문자열 → null) ── */
function parseNum(val) {
  const s = String(val).trim();
  if (!s) return null;
  const n = parseFloat(s);
  return isNaN(n) ? null : n;
}

/* ── 반영범위 코드 → 한글 ── */
const SCOPE_LABELS = { realtime: '실시간 관제', ai: 'AI 예측', alert: '알림' };

function scopeToText(scope) {
  if (!scope || !scope.length) return '-';
  return scope.map(s => SCOPE_LABELS[s] || s).join(' / ');
}

/* ════════════════════════════════
   그룹 목록
   ════════════════════════════════ */
async function loadGroups() {
  const q = document.getElementById('groupSearch').value.trim();
  const params = q ? `?q=${encodeURIComponent(q)}` : '';

  const ul = document.getElementById('groupList');
  ul.innerHTML = '<li class="group-empty">불러오는 중...</li>';

  try {
    const res = await Auth.apiFetch(`/api/admin/threshold-groups/${params}`);
    if (!res.ok) throw new Error();
    const data = await res.json();
    renderGroupList(data);
  } catch {
    ul.innerHTML = '<li class="group-empty">불러올 수 없습니다.</li>';
  }
}

function renderGroupList(groups) {
  const ul = document.getElementById('groupList');

  if (!groups.length) {
    ul.innerHTML = '<li class="group-empty">등록된 그룹이 없습니다.</li>';
    return;
  }

  ul.replaceChildren(
    ...groups.map(g => {
      const li = document.createElement('li');
      li.className = 'group-item' + (g.id === selectedGroupId ? ' active' : '');
      li.dataset.id = g.id;
      li.innerHTML = `
        <span class="group-name">${g.name}</span>
        <span class="group-code">${g.code}</span>
      `;
      li.addEventListener('click', () => selectGroup(g));
      return li;
    })
  );
}

function selectGroup(group) {
  selectedGroupId   = group.id;
  selectedGroupData = group;

  // 선택 표시
  document.querySelectorAll('.group-item').forEach(li => {
    li.classList.toggle('active', parseInt(li.dataset.id) === group.id);
  });

  // 그룹 수정 버튼 활성화
  document.getElementById('btnEditGroup').disabled = false;

  // 우측 패널 표시
  document.getElementById('rightEmpty').style.display   = 'none';
  document.getElementById('rightContent').style.display = '';

  // 그룹 정보 카드 채우기
  document.getElementById('infoSelectedBadge').textContent = `선택 분류: ${group.code}`;
  document.getElementById('infoName').textContent    = group.name;
  document.getElementById('infoCode').textContent    = group.code;
  document.getElementById('infoScope').textContent   = scopeToText(group.apply_scope);
  document.getElementById('infoUpdated').textContent = fmt(group.updated_at);
  document.getElementById('infoCount').textContent   = `${group.threshold_count ?? 0}건`;

  // 툴바 그룹명 배지
  document.getElementById('toolbarGroupBadge').textContent = group.name;

  // 임계치 목록 로드
  loadThresholds(group.id);
}

/* ════════════════════════════════
   임계치 목록
   ════════════════════════════════ */
async function loadThresholds(groupId) {
  const tbody = document.getElementById('thresholdTableBody');
  tbody.innerHTML = '<tr><td colspan="9" class="empty-state">불러오는 중...</td></tr>';

  // 선택 상태 초기화
  clearSelection();

  try {
    const res = await Auth.apiFetch(`/api/admin/threshold-groups/${groupId}/thresholds/`);
    if (!res.ok) throw new Error();
    const data = await res.json();

    allThresholds = data;
    currentPage   = 1;
    applyFilterAndSort();
  } catch {
    tbody.innerHTML = '<tr><td colspan="9" class="empty-state">불러올 수 없습니다.</td></tr>';
  }
}

/* 검색어 + 정렬 적용 후 렌더 */
function applyFilterAndSort() {
  const q    = document.getElementById('thresholdSearch').value.trim().toLowerCase();
  const sort = document.getElementById('sortSelect').value;

  // 1. 필터
  let items = q
    ? allThresholds.filter(t =>
        t.measurement_item.toLowerCase().includes(q) ||
        t.unit.toLowerCase().includes(q)
      )
    : [...allThresholds];

  // 2. 정렬
  items.sort((a, b) => {
    switch (sort) {
      case 'item_asc':    return a.measurement_item.localeCompare(b.measurement_item);
      case 'item_desc':   return b.measurement_item.localeCompare(a.measurement_item);
      case 'active_first': return (b.is_active ? 1 : 0) - (a.is_active ? 1 : 0);
      case 'updated_desc': return new Date(b.updated_at) - new Date(a.updated_at);
      case 'updated_asc':  return new Date(a.updated_at) - new Date(b.updated_at);
      default: return 0;
    }
  });

  filteredItems = items;
  document.getElementById('thresholdCount').textContent = items.length;
  renderPage(currentPage);
}

/* 페이지 렌더 */
function renderPage(page) {
  currentPage = page;
  const total     = filteredItems.length;
  const totalPages = Math.ceil(total / PAGE_SIZE);
  const start     = (page - 1) * PAGE_SIZE;
  const end       = Math.min(start + PAGE_SIZE, total);
  const pageItems = filteredItems.slice(start, end);

  renderThresholdTable(pageItems);
  renderPagination(page, totalPages, total, start, end);
}

function renderThresholdTable(items) {
  const tbody = document.getElementById('thresholdTableBody');

  document.getElementById('checkAll').checked = false;
  clearSelection();

  if (!items.length) {
    tbody.innerHTML = '<tr><td colspan="9" class="empty-state">등록된 임계치가 없습니다.</td></tr>';
    document.getElementById('paginationBar').style.display = 'none';
    return;
  }

  const scopeText = scopeToText(selectedGroupData?.apply_scope);

  tbody.replaceChildren(
    ...items.map(t => {
      const tr = document.createElement('tr');

      const warnStr   = formatRange(t.warning_min, t.warning_max);
      const dangerStr = formatRange(t.danger_min,  t.danger_max);

      tr.innerHTML = `
        <td class="col-check">
          <input type="checkbox" class="row-check" data-id="${t.id}">
        </td>
        <td><span class="mono">${t.measurement_item}</span></td>
        <td>${t.unit}</td>
        <td>${t.condition_type_display ?? t.condition_type}</td>
        <td>${warnStr}</td>
        <td>${dangerStr}</td>
        <td><span class="badge ${t.is_active ? 'badge-success' : 'badge-gray'}">${t.is_active ? '사용' : '미사용'}</span></td>
        <td>${scopeText}</td>
        <td>${fmt(t.updated_at)}</td>
      `;

      // 행 클릭 → 수정 모달 열기 (체크박스 직접 클릭은 제외)
      tr.addEventListener('click', e => {
        if (e.target.type === 'checkbox') return;
        const full = allThresholds.find(x => x.id === t.id);
        if (full) openThresholdModal(full);
      });

      tr.querySelector('.row-check').addEventListener('change', onRowCheckChange);

      return tr;
    })
  );
}

/* 소수점 불필요 자리 제거: 25.0000 → 25, 0.0600 → 0.06 */
function fmtNum(val) {
  if (val == null) return null;
  return parseFloat(val);  // trailing zero 제거
}

/* min~max → "25 ~ 50" 형태, 둘 다 null이면 "-" */
function formatRange(min, max) {
  const a = fmtNum(min), b = fmtNum(max);
  if (a == null && b == null) return '-';
  if (a == null) return `~ ${b}`;
  if (b == null) return `${a} ~`;
  return `${a} ~ ${b}`;
}

/* ── 페이지네이션 렌더 ── */
function renderPagination(page, totalPages, total, start, end) {
  const bar  = document.getElementById('paginationBar');
  const range = document.getElementById('pageRange');
  const btns  = document.getElementById('pageButtons');

  if (totalPages <= 1) {
    bar.style.display = 'none';
    return;
  }

  bar.style.display = '';
  range.textContent = `${start + 1} - ${end} / ${total}`;

  // 페이지 버튼 생성 (최대 5개 표시)
  const pageGroup = Math.floor((page - 1) / 5);
  const startPg   = pageGroup * 5 + 1;
  const endPg     = Math.min(startPg + 4, totalPages);

  const fragment = document.createDocumentFragment();

  // 이전 버튼
  const prev = document.createElement('button');
  prev.className = 'page-btn';
  prev.textContent = '<';
  prev.disabled = page === 1;
  prev.addEventListener('click', () => renderPage(page - 1));
  fragment.appendChild(prev);

  // 번호 버튼
  for (let p = startPg; p <= endPg; p++) {
    const btn = document.createElement('button');
    btn.className = 'page-btn' + (p === page ? ' active' : '');
    btn.textContent = p;
    const _p = p;
    btn.addEventListener('click', () => renderPage(_p));
    fragment.appendChild(btn);
  }

  // 다음 버튼
  const next = document.createElement('button');
  next.className = 'page-btn';
  next.textContent = '>';
  next.disabled = page === totalPages;
  next.addEventListener('click', () => renderPage(page + 1));
  fragment.appendChild(next);

  btns.replaceChildren(fragment);
}

/* ── 체크박스 선택 관련 ── */
function getCheckedIds() {
  return Array.from(document.querySelectorAll('.row-check:checked'))
    .map(cb => parseInt(cb.dataset.id));
}

function clearSelection() {
  document.querySelectorAll('.row-check').forEach(cb => { cb.checked = false; });
  document.getElementById('selectedBadge').style.display = 'none';
  document.getElementById('btnDeleteThreshold').disabled = true;
  if (document.getElementById('checkAll')) {
    document.getElementById('checkAll').checked = false;
  }
}

function onRowCheckChange() {
  const ids = getCheckedIds();
  const badge = document.getElementById('selectedBadge');
  const deleteBtn = document.getElementById('btnDeleteThreshold');

  if (ids.length > 0) {
    badge.textContent = `${ids.length}건 선택`;
    badge.style.display = '';
    deleteBtn.disabled = false;
  } else {
    badge.style.display = 'none';
    deleteBtn.disabled = true;
  }

  // 전체선택 체크박스 동기화
  const all = document.querySelectorAll('.row-check');
  document.getElementById('checkAll').checked = all.length > 0 && ids.length === all.length;
}

/* ── 임계치 삭제 (선택 항목 모두 삭제) ── */
async function deleteSelectedThresholds() {
  const ids = getCheckedIds();
  if (!ids.length) return;
  if (!confirm(`${ids.length}건을 삭제하시겠습니까?`)) return;

  try {
    // 병렬 DELETE 요청
    const results = await Promise.all(
      ids.map(id => Auth.apiFetch(`/api/admin/thresholds/${id}/`, { method: 'DELETE' }))
    );
    const failed = results.filter(r => !r.ok).length;
    if (failed > 0) {
      alert(`${failed}건 삭제에 실패했습니다.`);
    }
    loadThresholds(selectedGroupId);
  } catch {
    alert('삭제에 실패했습니다.');
  }
}

/* ════════════════════════════════
   그룹 모달 (등록 / 수정)
   ════════════════════════════════ */
function openGroupModal(mode, group = null) {
  document.getElementById('groupModalId').value     = group?.id ?? '';
  document.getElementById('groupModalCode').value   = group?.code ?? '';
  document.getElementById('groupModalName').value   = group?.name ?? '';
  document.getElementById('groupModalActive').value = group ? String(group.is_active) : 'true';
  document.getElementById('groupModalDesc').value   = group?.description ?? '';

  // 반영범위 체크박스 세팅
  const scope = group?.apply_scope ?? [];
  document.querySelectorAll('input[name="groupScope"]').forEach(cb => {
    cb.checked = scope.includes(cb.value);
  });

  // 수정 시 코드 읽기 전용
  document.getElementById('groupModalCode').readOnly = mode === 'edit';
  document.getElementById('groupModalCode').classList.toggle('readonly', mode === 'edit');

  document.getElementById('groupModalTitle').textContent   = mode === 'create' ? '기준 분류 등록' : '기준 분류 수정';
  document.getElementById('btnGroupModalSave').textContent = mode === 'create' ? '등록' : '수정';

  document.getElementById('groupModalOverlay').style.display = 'flex';
}

function closeGroupModal() {
  document.getElementById('groupModalOverlay').style.display = 'none';
}

async function saveGroup() {
  const id     = document.getElementById('groupModalId').value;
  const isEdit = !!id;

  const apply_scope = Array.from(document.querySelectorAll('input[name="groupScope"]:checked'))
    .map(cb => cb.value);

  const payload = {
    code:        document.getElementById('groupModalCode').value.trim(),
    name:        document.getElementById('groupModalName').value.trim(),
    is_active:   document.getElementById('groupModalActive').value === 'true',
    description: document.getElementById('groupModalDesc').value.trim(),
    apply_scope,
  };

  if (!payload.name) { alert('분류명을 입력해주세요.'); return; }
  if (!isEdit && !payload.code) { alert('분류코드를 입력해주세요.'); return; }

  const url    = isEdit ? `/api/admin/threshold-groups/${id}/` : '/api/admin/threshold-groups/';
  const method = isEdit ? 'PATCH' : 'POST';

  try {
    const res = await Auth.apiFetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json();
      alert(Object.values(err).flat().join('\n'));
      return;
    }
    const updated = await res.json();
    closeGroupModal();
    await loadGroups();
    // 수정 후 선택 상태 유지
    if (isEdit && selectedGroupId === parseInt(id)) {
      selectGroup(updated);
    }
  } catch {
    alert('저장에 실패했습니다.');
  }
}

/* ════════════════════════════════
   임계치 모달 (등록 / 수정)
   ════════════════════════════════ */
function openThresholdModal(threshold = null) {
  const isEdit = !!threshold;

  document.getElementById('thresholdModalId').value        = threshold?.id ?? '';
  document.getElementById('thresholdModalGroup').value     = selectedGroupData?.name ?? '';
  document.getElementById('thresholdModalItem').value      = threshold?.measurement_item ?? '';
  document.getElementById('thresholdModalUnit').value      = threshold?.unit ?? 'ppm';
  document.getElementById('thresholdModalCondition').value = threshold?.condition_type ?? 'gt';
  document.getElementById('thresholdModalWarnMin').value   = threshold?.warning_min ?? '';
  document.getElementById('thresholdModalWarnMax').value   = threshold?.warning_max ?? '';
  document.getElementById('thresholdModalDangerMin').value = threshold?.danger_min ?? '';
  document.getElementById('thresholdModalDangerMax').value = threshold?.danger_max ?? '';
  document.getElementById('thresholdModalChartMax').value  = threshold?.chart_max ?? '';
  document.getElementById('thresholdModalActive').value    = threshold ? String(threshold.is_active) : 'true';
  document.getElementById('thresholdModalDesc').value      = threshold?.description ?? '';

  // 수정 시 측정항목 읽기 전용 (UNIQUE 제약)
  document.getElementById('thresholdModalItem').readOnly = isEdit;
  document.getElementById('thresholdModalItem').classList.toggle('readonly', isEdit);

  document.getElementById('thresholdModalTitle').textContent   = isEdit ? '임계치 기준 수정' : '임계치 기준 등록';
  document.getElementById('btnThresholdModalSave').textContent = isEdit ? '수정' : '등록';

  document.getElementById('thresholdModalOverlay').style.display = 'flex';
}

function closeThresholdModal() {
  document.getElementById('thresholdModalOverlay').style.display = 'none';
}

async function saveThreshold() {
  const id     = document.getElementById('thresholdModalId').value;
  const isEdit = !!id;
  const item   = document.getElementById('thresholdModalItem').value.trim();

  if (!item) { alert('측정항목을 입력해주세요.'); return; }

  const payload = {
    measurement_item: item,
    unit:            document.getElementById('thresholdModalUnit').value.trim() || 'ppm',
    condition_type:  document.getElementById('thresholdModalCondition').value,
    warning_min:     parseNum(document.getElementById('thresholdModalWarnMin').value),
    warning_max:     parseNum(document.getElementById('thresholdModalWarnMax').value),
    danger_min:      parseNum(document.getElementById('thresholdModalDangerMin').value),
    danger_max:      parseNum(document.getElementById('thresholdModalDangerMax').value),
    chart_max:       parseNum(document.getElementById('thresholdModalChartMax').value),
    is_active:       document.getElementById('thresholdModalActive').value === 'true',
    description:     document.getElementById('thresholdModalDesc').value.trim(),
  };

  const url    = isEdit ? `/api/admin/thresholds/${id}/` : `/api/admin/threshold-groups/${selectedGroupId}/thresholds/`;
  const method = isEdit ? 'PATCH' : 'POST';

  try {
    const res = await Auth.apiFetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json();
      alert(Object.values(err).flat().join('\n'));
      return;
    }
    closeThresholdModal();
    loadThresholds(selectedGroupId);
  } catch {
    alert('저장에 실패했습니다.');
  }
}

/* ════════════════════════════════
   이벤트 리스너
   ════════════════════════════════ */
document.addEventListener('DOMContentLoaded', () => {
  loadGroups();

  // 그룹 검색
  document.getElementById('btnGroupSearch').addEventListener('click', loadGroups);
  document.getElementById('groupSearch').addEventListener('keydown', e => {
    if (e.key === 'Enter') loadGroups();
  });

  // 그룹 등록 (페이지 상단 버튼)
  document.getElementById('btnAddGroup').addEventListener('click', () => openGroupModal('create'));
  // 그룹 수정 (왼쪽 패널 하단 버튼)
  document.getElementById('btnEditGroup').addEventListener('click', () => openGroupModal('edit', selectedGroupData));

  // 그룹 모달
  document.getElementById('btnGroupModalClose').addEventListener('click',  closeGroupModal);
  document.getElementById('btnGroupModalCancel').addEventListener('click', closeGroupModal);
  document.getElementById('btnGroupModalSave').addEventListener('click',   saveGroup);
  document.getElementById('groupModalOverlay').addEventListener('click', e => {
    if (e.target === e.currentTarget) closeGroupModal();
  });

  // 임계치 검색
  document.getElementById('btnThresholdSearch').addEventListener('click', () => {
    currentPage = 1;
    applyFilterAndSort();
  });
  document.getElementById('thresholdSearch').addEventListener('keydown', e => {
    if (e.key === 'Enter') { currentPage = 1; applyFilterAndSort(); }
  });
  // 초기화
  document.getElementById('btnResetSearch').addEventListener('click', () => {
    document.getElementById('thresholdSearch').value = '';
    currentPage = 1;
    applyFilterAndSort();
  });
  // 정렬 변경
  document.getElementById('sortSelect').addEventListener('change', () => {
    currentPage = 1;
    applyFilterAndSort();
  });

  // 전체선택 체크박스
  document.getElementById('checkAll').addEventListener('change', e => {
    document.querySelectorAll('.row-check').forEach(cb => { cb.checked = e.target.checked; });
    onRowCheckChange();
  });

  // 임계치 삭제 (툴바 삭제 버튼)
  document.getElementById('btnDeleteThreshold').addEventListener('click', deleteSelectedThresholds);
  // 임계치 등록 (툴바 등록 버튼)
  document.getElementById('btnAddThreshold').addEventListener('click', () => openThresholdModal());

  // 임계치 모달
  document.getElementById('btnThresholdModalClose').addEventListener('click',  closeThresholdModal);
  document.getElementById('btnThresholdModalCancel').addEventListener('click', closeThresholdModal);
  document.getElementById('btnThresholdModalSave').addEventListener('click',   saveThreshold);
  document.getElementById('thresholdModalOverlay').addEventListener('click', e => {
    if (e.target === e.currentTarget) closeThresholdModal();
  });
});
