'use strict';

/* ── 날짜 포맷 헬퍼 ── */
function fmtDatetime(iso) {
  if (!iso) return '-';
  if (typeof TimeFormat !== 'undefined') return TimeFormat.abs(iso);
  return new Date(iso).toLocaleString('ko-KR');
}

/* ── 목록 로드 ── */
async function loadList() {
  const code     = document.getElementById('filterCode').value;
  const isActive = document.getElementById('filterActive').value;
  const color    = document.getElementById('filterColor').value;

  const params = new URLSearchParams();
  if (code)     params.set('code', code);
  if (isActive) params.set('is_active', isActive);
  if (color)    params.set('display_color', color);

  const tbody = document.getElementById('riskTableBody');
  tbody.innerHTML = '<tr><td colspan="7" class="empty-state">불러오는 중...</td></tr>';

  try {
    const res = await Auth.apiFetch(`/api/admin/risk-standards/?${params}`);
    if (!res.ok) throw new Error();
    const data = await res.json();

    document.getElementById('totalCount').textContent = data.length ?? 0;
    renderTable(data);
  } catch {
    tbody.innerHTML = '<tr><td colspan="7" class="empty-state">데이터를 불러올 수 없습니다.</td></tr>';
  }
}

/* ── 테이블 렌더 ── */
function renderTable(items) {
  const tbody = document.getElementById('riskTableBody');

  if (!items.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="empty-state">조회된 항목이 없습니다.</td></tr>';
    return;
  }

  tbody.replaceChildren(
    ...items.map(item => {
      const tr = document.createElement('tr');
      tr.style.cursor = 'pointer';

      // 색상 미리보기 칩
      const colorChip = `<span class="color-chip" style="background:${item.display_color}"></span>${item.display_color}`;

      tr.innerHTML = `
        <td>${item.name}</td>
        <td><span class="code-badge">${item.code}</span></td>
        <td><span class="badge ${item.is_active ? 'badge-success' : 'badge-gray'}">${item.is_active ? '사용' : '미사용'}</span></td>
        <td class="color-cell">${colorChip}</td>
        <td>${item.alert_intensity_display}</td>
        <td>${item.event_priority}</td>
        <td>${fmtDatetime(item.updated_at)}</td>
      `;

      // 행 클릭 → 수정 모달
      tr.addEventListener('click', () => openEditModal(item));
      return tr;
    })
  );
}

/* ── 수정 모달 열기 ── */
function openEditModal(item) {
  document.getElementById('editId').value          = item.id;
  document.getElementById('editCode').value        = item.code;
  document.getElementById('editName').value        = item.name;
  document.getElementById('editColor').value       = item.display_color;
  document.getElementById('editIntensity').value   = item.alert_intensity;
  document.getElementById('editPriority').value    = item.event_priority;
  document.getElementById('editActive').value      = item.is_active ? 'true' : 'false';
  document.getElementById('editDescription').value = item.description ?? '';

  document.getElementById('editOverlay').style.display = 'flex';
}

function closeEditModal() {
  document.getElementById('editOverlay').style.display = 'none';
}

/* ── 저장 ── */
async function saveEdit() {
  const id = document.getElementById('editId').value;
  const name = document.getElementById('editName').value.trim();

  if (!name) {
    alert('단계명을 입력해주세요.');
    return;
  }

  const payload = {
    name,
    display_color:    document.getElementById('editColor').value.trim(),
    alert_intensity:  document.getElementById('editIntensity').value,
    event_priority:   parseInt(document.getElementById('editPriority').value, 10),
    is_active:        document.getElementById('editActive').value === 'true',
    description:      document.getElementById('editDescription').value.trim(),
  };

  try {
    const res = await Auth.apiFetch(`/api/admin/risk-standards/${id}/`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const err = await res.json();
      alert(err.detail ?? '저장에 실패했습니다.');
      return;
    }

    closeEditModal();
    loadList(); // 저장 후 목록 새로고침
  } catch {
    alert('저장에 실패했습니다.');
  }
}

/* ── 이벤트 리스너 ── */
document.addEventListener('DOMContentLoaded', () => {
  loadList();

  document.getElementById('btnSearch').addEventListener('click', loadList);

  document.getElementById('btnReset').addEventListener('click', () => {
    document.getElementById('filterCode').value   = '';
    document.getElementById('filterActive').value = '';
    document.getElementById('filterColor').value  = '';
    loadList();
  });

  document.getElementById('btnEditClose').addEventListener('click',  closeEditModal);
  document.getElementById('btnEditCancel').addEventListener('click', closeEditModal);
  document.getElementById('btnEditSave').addEventListener('click',   saveEdit);

  // 오버레이 클릭으로 모달 닫기
  document.getElementById('editOverlay').addEventListener('click', (e) => {
    if (e.target === e.currentTarget) closeEditModal();
  });
});
