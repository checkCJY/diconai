/* admin/alerts/policies.js — 알림 정책 관리 페이지
 *
 * API: GET/POST  /api/admin/alerts/policies/
 *       GET/PATCH/DELETE /api/admin/alerts/policies/<id>/
 *
 * 모달 (등록/수정 + 권고 조치 탭) 은 2c 단계에서 별도 모듈로 추가 예정.
 */
'use strict';

const AlertPolicyAdmin = {
  page: 1,
  pageSize: 10,
  total: 0,
  filters: { name: '', event_type: '', is_active: '' },
  sort: 'updated_desc',
  selected: new Set(),

  CHANNEL_LABEL: {
    popup: '관제 실시간 알림',
    push: '앱',
    sms: 'SMS',
    email: '이메일',
  },
  USER_TYPE_LABEL: {
    super_admin: '슈퍼관리자',
    facility_admin: '관리자',
    worker: '작업자',
    viewer: '열람자',
  },

  async init() {
    this._bindEvents();
    await this.fetchList();
  },

  _bindEvents() {
    document.getElementById('btnSearch').addEventListener('click', () => {
      this._readFilters();
      this.page = 1;
      this.fetchList();
    });

    document.getElementById('btnReset').addEventListener('click', () => {
      document.getElementById('filterName').value = '';
      document.getElementById('filterEventType').value = '';
      document.getElementById('filterActive').value = '';
      this.filters = { name: '', event_type: '', is_active: '' };
      this.page = 1;
      this.fetchList();
    });

    document.getElementById('sortSelect').addEventListener('change', (e) => {
      this.sort = e.target.value;
      this.page = 1;
      this.fetchList();
    });

    document.getElementById('checkAll').addEventListener('change', (e) => {
      document.querySelectorAll('.row-check').forEach(cb => {
        cb.checked = e.target.checked;
        const id = parseInt(cb.dataset.id);
        e.target.checked ? this.selected.add(id) : this.selected.delete(id);
      });
      this._updateBulkButtons();
    });

    document.getElementById('btnDelete').addEventListener('click', () => this._deleteSelected());
    document.getElementById('btnAddPolicy').addEventListener('click', () => this._openCreateModal());

    PolicyModal.init(() => this.fetchList());
  },

  _readFilters() {
    this.filters = {
      name: document.getElementById('filterName').value.trim(),
      event_type: document.getElementById('filterEventType').value,
      is_active: document.getElementById('filterActive').value,
    };
  },

  async fetchList() {
    try {
      const params = new URLSearchParams({
        page: this.page,
        page_size: this.pageSize,
        sort: this.sort,
      });
      if (this.filters.name) params.append('name', this.filters.name);
      if (this.filters.event_type) params.append('event_type', this.filters.event_type);
      if (this.filters.is_active) params.append('is_active', this.filters.is_active);

      const res = await Auth.apiFetch(`/api/admin/alerts/policies/?${params}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const data = await res.json();
      this.total = data.total;
      this._renderTable(data.results);
      this._renderPagination();
      document.getElementById('totalCount').textContent = this.total;
    } catch (e) {
      console.error('[AlertPolicyAdmin] 목록 로드 실패:', e);
      document.getElementById('policiesTableBody').innerHTML =
        `<tr><td colspan="7" class="empty-state">데이터를 불러오지 못했습니다.</td></tr>`;
    }
  },

  _renderTable(items) {
    const tbody = document.getElementById('policiesTableBody');
    if (!items.length) {
      tbody.innerHTML = `<tr><td colspan="7" class="empty-state">검색 결과가 없습니다.</td></tr>`;
      return;
    }

    tbody.innerHTML = items.map(p => `
      <tr data-id="${p.id}">
        <td><input type="checkbox" class="row-check" data-id="${p.id}" ${this.selected.has(p.id) ? 'checked' : ''}></td>
        <td>${this._escape(p.name)}</td>
        <td>${this._escape(p.event_type_display || p.event_type)}</td>
        <td>${this._formatChannels(p.channels)}</td>
        <td>${this._formatRecipients(p.target_user_types)}</td>
        <td><span class="ap-badge ${p.is_active ? 'ap-badge-green' : 'ap-badge-gray'}">${p.is_active ? '사용' : '미사용'}</span></td>
        <td>${this._escape(p.condition_summary) || '<span class="ap-muted">조건 미설정</span>'}</td>
      </tr>
    `).join('');

    tbody.querySelectorAll('.row-check').forEach(cb => {
      cb.addEventListener('change', (e) => {
        e.stopPropagation();
        const id = parseInt(e.target.dataset.id);
        e.target.checked ? this.selected.add(id) : this.selected.delete(id);
        this._updateBulkButtons();
      });
      // 체크박스 클릭이 행 클릭으로 전파되지 않도록.
      cb.addEventListener('click', (e) => e.stopPropagation());
    });

    // 행 클릭 → 수정 모달.
    tbody.querySelectorAll('tr[data-id]').forEach(tr => {
      tr.addEventListener('click', () => {
        const id = parseInt(tr.dataset.id);
        this._openEditModal(id);
      });
    });
  },

  async _openCreateModal() {
    PolicyModal.open('create');
  },

  async _openEditModal(id) {
    try {
      const res = await Auth.apiFetch(`/api/admin/alerts/policies/${id}/`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const policy = await res.json();
      PolicyModal.open('edit', policy);
    } catch (e) {
      console.error('[AlertPolicyAdmin] 정책 상세 로드 실패:', e);
      alert('정책 정보를 불러올 수 없습니다.');
    }
  },

  _renderPagination() {
    const totalPages = Math.ceil(this.total / this.pageSize) || 1;
    const el = document.getElementById('pagination');
    const prevDisabled = this.page === 1 ? 'disabled' : '';
    const nextDisabled = this.page === totalPages ? 'disabled' : '';

    const startPage = Math.max(1, this.page - 2);
    const endPage = Math.min(totalPages, startPage + 4);
    const pageButtons = Array.from(
      { length: endPage - startPage + 1 },
      (_, i) => startPage + i
    ).map(p => `
      <button class="${p === this.page ? 'active' : ''}" onclick="AlertPolicyAdmin._goPage(${p})">${p}</button>
    `).join('');

    el.innerHTML = `
      <button onclick="AlertPolicyAdmin._goPage(${this.page - 1})" ${prevDisabled}>&lt;</button>
      ${pageButtons}
      <button onclick="AlertPolicyAdmin._goPage(${this.page + 1})" ${nextDisabled}>&gt;</button>
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

  _updateBulkButtons() {
    document.getElementById('btnDelete').disabled = this.selected.size === 0;
  },

  async _deleteSelected() {
    if (!confirm(`선택한 ${this.selected.size}개의 정책을 삭제하시겠습니까?`)) return;

    const ids = [...this.selected];
    const results = await Promise.allSettled(
      ids.map(id =>
        Auth.apiFetch(`/api/admin/alerts/policies/${id}/`, { method: 'DELETE' })
      )
    );
    const failed = results.filter(r => r.status === 'rejected' || !r.value.ok).length;
    if (failed > 0) alert(`${failed}건 삭제 실패`);

    this.selected.clear();
    this._updateBulkButtons();
    document.getElementById('checkAll').checked = false;
    await this.fetchList();
  },

  // 출력 전 escape — 정책명·요약이 운영자 편집 대상이라 XSS 방어.
  _escape(s) {
    if (s == null) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  },

  _formatChannels(channels) {
    if (!Array.isArray(channels) || channels.length === 0) return '-';
    return channels.map(c => this.CHANNEL_LABEL[c] || c).join(', ');
  },

  _formatRecipients(types) {
    if (!Array.isArray(types) || types.length === 0) return '-';
    return types.map(t => this.USER_TYPE_LABEL[t] || t).join(', ');
  },
};

document.addEventListener('DOMContentLoaded', () => AlertPolicyAdmin.init());
