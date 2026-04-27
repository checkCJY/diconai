/* admin/accounts/accounts.js — 사용자 관리 페이지
 *
 * 역할: /admin-panel/accounts-management/ 페이지의 동작 전담.
 * - 사용자 목록 fetch (필터·정렬·페이지네이션 포함)
 * - 행 선택 → 일괄 삭제 / 계정 잠금 / 잠금 해제
 * - 수정 버튼 → 수정 모달 (추후 구현 예정)
 *
 * API 엔드포인트:
 *   GET    /api/admin/accounts/           목록 조회
 *   POST   /api/admin/accounts/           신규 등록
 *   PATCH  /api/admin/accounts/<id>/      정보 수정
 *   DELETE /api/admin/accounts/<id>/      비활성화
 *   POST   /api/admin/accounts/<id>/lock/ 잠금 / 잠금 해제
 */
'use strict';

const AccountsAdmin = {
  page: 1,
  pageSize: 10,
  total: 0,
  filters: { name: '', department: '', position: '', user_type: '', status: '' },
  sort: 'name_asc',
  selected: new Set(),   // 선택된 사용자 id 집합

  USER_TYPE_LABEL: {
    super_admin: '슈퍼관리자',
    facility_admin: '관리자',
    worker: '일반사용자',
    viewer: '열람자',
  },
  USER_TYPE_BADGE: {
    super_admin: 'badge-red',
    facility_admin: 'badge-purple',
    worker: 'badge-gray',
    viewer: 'badge-blue',
  },
  STATUS_LABEL: { active: '사용', locked: '잠금', inactive: '비활성' },
  STATUS_BADGE: { active: 'badge-green', locked: 'badge-orange', inactive: 'badge-gray' },

  // ── 초기화 ────────────────────────────────────────────────

  async init() {
    this._bindEvents();
    await this.fetchList();
  },

  // ── 이벤트 바인딩 ─────────────────────────────────────────

  _bindEvents() {
    document.getElementById('btnSearch').addEventListener('click', () => {
      this._readFilters();
      this.page = 1;
      this.fetchList();
    });

    document.getElementById('btnReset').addEventListener('click', () => {
      document.getElementById('filterName').value = '';
      document.getElementById('filterDepartment').value = '';
      document.getElementById('filterPosition').value = '';
      document.getElementById('filterUserType').value = '';
      document.getElementById('filterStatus').value = '';
      this.filters = { name: '', department: '', position: '', user_type: '', status: '' };
      this.page = 1;
      this.fetchList();
    });

    document.getElementById('sortSelect').addEventListener('change', (e) => {
      this.sort = e.target.value;
      this.page = 1;
      this.fetchList();
    });

    // 전체 선택 체크박스
    document.getElementById('checkAll').addEventListener('change', (e) => {
      document.querySelectorAll('.row-check').forEach(cb => {
        cb.checked = e.target.checked;
        const id = parseInt(cb.dataset.id);
        e.target.checked ? this.selected.add(id) : this.selected.delete(id);
      });
      this._updateBulkButtons();
    });

    document.getElementById('btnDelete').addEventListener('click', () => this._deleteSelected());
    document.getElementById('btnLock').addEventListener('click', () => this._lockSelected('lock'));
    document.getElementById('btnUnlock').addEventListener('click', () => this._lockSelected('unlock'));
    document.getElementById('btnAddUser').addEventListener('click', () => this._openCreateModal());
  },

  // ── 필터값 읽기 ───────────────────────────────────────────

  _readFilters() {
    this.filters = {
      name: document.getElementById('filterName').value.trim(),
      department: document.getElementById('filterDepartment').value,
      position: document.getElementById('filterPosition').value,
      user_type: document.getElementById('filterUserType').value,
      status: document.getElementById('filterStatus').value,
    };
  },

  // ── 목록 fetch ────────────────────────────────────────────

  async fetchList() {
    try {
      const token = Auth.getAccessToken();
      const params = new URLSearchParams({ page: this.page, page_size: this.pageSize, sort: this.sort });
      if (this.filters.name)       params.append('name', this.filters.name);
      if (this.filters.department) params.append('department', this.filters.department);
      if (this.filters.position)   params.append('position', this.filters.position);
      if (this.filters.user_type)  params.append('user_type', this.filters.user_type);
      if (this.filters.status)     params.append('status', this.filters.status);

      const res = await fetch(`/api/admin/accounts/?${params}`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const data = await res.json();
      this.total = data.total;
      this._renderTable(data.results);
      this._renderPagination();
      document.getElementById('totalCount').textContent = this.total;
    } catch (e) {
      console.error('[AccountsAdmin] 목록 로드 실패:', e);
      document.getElementById('accountsTableBody').innerHTML =
        `<tr><td colspan="11" class="empty-state">데이터를 불러오지 못했습니다.</td></tr>`;
    }
  },

  // ── 전화번호 포맷 ─────────────────────────────────────────

  _formatPhone(phone) {
    if (!phone) return '-';
    const digits = phone.replace(/\D/g, '');
    if (digits.length === 11) return digits.replace(/(\d{3})(\d{4})(\d{4})/, '$1-$2-$3');
    if (digits.length === 10) return digits.replace(/(\d{3})(\d{3})(\d{4})/, '$1-$2-$3');
    return phone;
  },

  // ── 테이블 렌더링 ─────────────────────────────────────────

  _renderTable(items) {
    const tbody = document.getElementById('accountsTableBody');
    if (!items.length) {
      tbody.innerHTML = `<tr><td colspan="11" class="empty-state">검색 결과가 없습니다.</td></tr>`;
      return;
    }

    tbody.innerHTML = items.map(u => `
      <tr>
        <td><input type="checkbox" class="row-check" data-id="${u.id}" ${this.selected.has(u.id) ? 'checked' : ''}></td>
        <td>${u.name || '-'}</td>
        <td>${u.department || '-'}</td>
        <td>${u.position || '-'}</td>
        <td>${u.username}</td>
        <td><span class="badge ${this.USER_TYPE_BADGE[u.user_type] || 'badge-gray'}">${this.USER_TYPE_LABEL[u.user_type] || u.user_type}</span></td>
        <td><span class="badge ${this.STATUS_BADGE[u.status] || 'badge-gray'}">${this.STATUS_LABEL[u.status] || u.status}</span></td>
        <td>${this._formatPhone(u.phone)}</td>
        <td>${u.last_login_at || '-'}</td>
        <td>${u.date_joined ? u.date_joined.slice(0, 10) : '-'}</td>
        <td><button class="btn-sm" onclick="AccountsAdmin._openEditModal(${u.id})">수정</button></td>
      </tr>
    `).join('');

    // 행 체크박스 이벤트 등록
    tbody.querySelectorAll('.row-check').forEach(cb => {
      cb.addEventListener('change', (e) => {
        const id = parseInt(e.target.dataset.id);
        e.target.checked ? this.selected.add(id) : this.selected.delete(id);
        this._updateBulkButtons();
      });
    });
  },

  // ── 페이지네이션 렌더링 ────────────────────────────────────

  _renderPagination() {
    const totalPages = Math.ceil(this.total / this.pageSize) || 1;
    const el = document.getElementById('pagination');

    const prevDisabled = this.page === 1 ? 'disabled' : '';
    const nextDisabled = this.page === totalPages ? 'disabled' : '';

    // 최대 5개 페이지 버튼 표시
    const startPage = Math.max(1, this.page - 2);
    const endPage = Math.min(totalPages, startPage + 4);

    const pageButtons = Array.from(
      { length: endPage - startPage + 1 },
      (_, i) => startPage + i
    ).map(p => `
      <button class="${p === this.page ? 'active' : ''}" onclick="AccountsAdmin._goPage(${p})">${p}</button>
    `).join('');

    el.innerHTML = `
      <button onclick="AccountsAdmin._goPage(${this.page - 1})" ${prevDisabled}>&lt;</button>
      ${pageButtons}
      <button onclick="AccountsAdmin._goPage(${this.page + 1})" ${nextDisabled}>&gt;</button>
    `;

    const start = (this.page - 1) * this.pageSize + 1;
    const end = Math.min(this.page * this.pageSize, this.total);
    document.getElementById('pageInfo').textContent =
      this.total > 0 ? `${start} - ${end} / ${this.total}` : '0 - 0 / 0';
  },

  _goPage(page) {
    const totalPages = Math.ceil(this.total / this.pageSize) || 1;
    if (page < 1 || page > totalPages) return;
    this.page = page;
    this.fetchList();
  },

  // ── 일괄 작업 버튼 활성화 ─────────────────────────────────

  _updateBulkButtons() {
    const hasSelected = this.selected.size > 0;
    document.getElementById('btnDelete').disabled = !hasSelected;
    document.getElementById('btnLock').disabled = !hasSelected;
    document.getElementById('btnUnlock').disabled = !hasSelected;
  },

  // ── 일괄 삭제 (비활성화) ──────────────────────────────────

  async _deleteSelected() {
    if (!confirm(`선택한 ${this.selected.size}명의 사용자를 비활성화하시겠습니까?`)) return;
    const token = Auth.getAccessToken();
    try {
      await Promise.all([...this.selected].map(id =>
        fetch(`/api/admin/accounts/${id}/`, {
          method: 'DELETE',
          headers: { 'Authorization': `Bearer ${token}` },
        })
      ));
      this.selected.clear();
      this._updateBulkButtons();
      await this.fetchList();
    } catch (e) {
      alert('비활성화에 실패했습니다.');
    }
  },

  // ── 일괄 잠금 / 잠금 해제 ────────────────────────────────

  async _lockSelected(action) {
    const label = action === 'lock' ? '잠금' : '잠금 해제';
    if (!confirm(`선택한 ${this.selected.size}명의 계정을 ${label} 처리하시겠습니까?`)) return;
    const token = Auth.getAccessToken();
    try {
      await Promise.all([...this.selected].map(id =>
        fetch(`/api/admin/accounts/${id}/${action}/`, {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}` },
        })
      ));
      this.selected.clear();
      this._updateBulkButtons();
      await this.fetchList();
    } catch (e) {
      alert(`계정 ${label}에 실패했습니다.`);
    }
  },

  // ── 모달 (등록 / 수정) ── 추후 구현 ─────────────────────

  _openCreateModal() {
    alert('사용자 등록 모달 — 추후 구현 예정');
  },

  _openEditModal(id) {
    alert(`사용자 수정 모달 (id: ${id}) — 추후 구현 예정`);
  },
};

document.addEventListener('DOMContentLoaded', () => AccountsAdmin.init());
