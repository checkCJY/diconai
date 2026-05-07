/* admin/geofence/geofence.js — 위험구역 관리 페이지 */
'use strict';

const GeofenceAdmin = {
  currentPolygon: [],
  page: 1,
  pageSize: 20,
  total: 0,
  filters: { name: '', risk: '' },
  selected: new Set(),

  RISK_LABEL: { danger: '위험', warning: '주의', normal: '정상' },
  RISK_BADGE: { danger: 'badge-danger', warning: 'badge-warning', normal: 'badge-normal' },

  async init() {
    this._bindEvents();
    await this._loadUser();
    await this.fetchList();
  },

  async _loadUser() {
    try {
      const res = await Auth.apiFetch('/api/auth/me/');
      const user = await res.json();
      document.getElementById('adminName').textContent = user.username || '';
      document.getElementById('adminRole').textContent = user.user_type || '';
    } catch (e) {
      console.error('[GeofenceAdmin] 유저 로드 실패:', e);
    }
  },

  _bindEvents() {
    document.getElementById('btnSearch').addEventListener('click', () => {
      this.filters.name = document.getElementById('filterName').value.trim();
      this.filters.risk = document.getElementById('filterRisk').value;
      this.page = 1;
      this.fetchList();
    });
    document.getElementById('btnReset').addEventListener('click', () => {
      document.getElementById('filterName').value = '';
      document.getElementById('filterRisk').value = '';
      this.filters = { name: '', risk: '' };
      this.page = 1;
      this.fetchList();
    });
    document.getElementById('btnAddCoord').addEventListener('click', () => {
      this._addCoordRow();
    });
    document.getElementById('checkAll').addEventListener('change', (e) => {
      document.querySelectorAll('.row-check').forEach(cb => {
        cb.checked = e.target.checked;
        const id = parseInt(cb.dataset.id);
        e.target.checked ? this.selected.add(id) : this.selected.delete(id);
      });
      this._updateDeleteBtn();
    });
    document.getElementById('btnDelete').addEventListener('click', () => this._deleteSelected());
    document.getElementById('btnAdd').addEventListener('click', () => this._openModal());
    document.getElementById('btnModalClose').addEventListener('click', () => this._closeModal());
    document.getElementById('btnModalCancel').addEventListener('click', () => this._closeModal());
    document.getElementById('btnModalSave').addEventListener('click', () => this._save());
    document.getElementById('btnLogout').addEventListener('click', () => {
      Auth.logout();
      location.href = '/accounts/login/';
    });
    document.getElementById('btnHome').addEventListener('click', () => {
      location.href = '/dashboard/';
    });
  },

  async fetchList() {
    try {
      const params = new URLSearchParams();
      if (this.filters.name) params.append('name', this.filters.name);
      if (this.filters.risk) params.append('risk_level', this.filters.risk);
      const res = await Auth.apiFetch(`/api/admin/geofences/?${params}`);
      const data = await res.json();
      this.total = data.total;
      this._renderTable(data.results);
      this._renderPagination();
      document.getElementById('totalCount').textContent = this.total;
    } catch (e) {
      console.error('[GeofenceAdmin] 목록 로드 실패:', e);
    }
  },

  _renderTable(items) {
    const tbody = document.getElementById('geofenceTableBody');
    if (!items.length) {
      tbody.innerHTML = `<tr><td colspan="8" class="empty-state">등록된 위험구역이 없습니다.</td></tr>`;
      return;
    }
    tbody.innerHTML = items.map(g => `
      <tr>
        <td><input type="checkbox" class="row-check" data-id="${g.id}" ${this.selected.has(g.id) ? 'checked' : ''}></td>
        <td>${g.id}</td>
        <td>${g.name}</td>
        <td>${g.facility_name || '-'}</td>
        <td><span class="badge ${this.RISK_BADGE[g.risk_level]}">${this.RISK_LABEL[g.risk_level]}</span></td>
        <td>${g.worker_count || 0}명</td>
        <td>${g.created_at ? g.created_at.slice(0, 10) : '-'}</td>
        <td><button class="btn-sm" onclick="GeofenceAdmin._openModal(${g.id})">수정</button></td>
      </tr>
    `).join('');
    document.querySelectorAll('.row-check').forEach(cb => {
      cb.addEventListener('change', (e) => {
        const id = parseInt(e.target.dataset.id);
        e.target.checked ? this.selected.add(id) : this.selected.delete(id);
        this._updateDeleteBtn();
      });
    });
  },

  _renderPagination() {
    const total = Math.ceil(this.total / this.pageSize);
    const el = document.getElementById('pagination');
    el.innerHTML = `
      <button onclick="GeofenceAdmin._goPage(${this.page - 1})" ${this.page === 1 ? 'disabled' : ''}>&lt;</button>
      ${Array.from({length: total}, (_, i) => `
        <button class="${i + 1 === this.page ? 'active' : ''}" onclick="GeofenceAdmin._goPage(${i + 1})">${i + 1}</button>
      `).join('')}
      <button onclick="GeofenceAdmin._goPage(${this.page + 1})" ${this.page === total ? 'disabled' : ''}>&gt;</button>
    `;
    const start = (this.page - 1) * this.pageSize + 1;
    const end = Math.min(this.page * this.pageSize, this.total);
    document.getElementById('pageInfo').textContent = `${start} - ${end} / ${this.total}`;
  },

  _goPage(page) {
    const total = Math.ceil(this.total / this.pageSize);
    if (page < 1 || page > total) return;
    this.page = page;
    this.fetchList();
  },

  _updateDeleteBtn() {
    document.getElementById('btnDelete').disabled = this.selected.size === 0;
  },

  async _deleteSelected() {
    if (!confirm(`선택한 ${this.selected.size}개의 위험구역을 삭제하시겠습니까?`)) return;
    try {
      await Promise.all([...this.selected].map(id =>
        Auth.apiFetch(`/api/admin/geofences/${id}/`, { method: 'DELETE' })
      ));
      this.selected.clear();
      this._updateDeleteBtn();
      await this.fetchList();
    } catch (e) {
      alert('삭제에 실패했습니다.');
    }
  },

  async _openModal(id = null) {
    document.getElementById('modalId').value = id || '';
    document.getElementById('modalTitle').textContent = id ? '위험구역 수정' : '위험구역 등록';
    document.getElementById('modalName').value = '';
    document.getElementById('modalRisk').value = 'danger';
    document.getElementById('modalDesc').value = '';

    if (id) {
      try {
        const res = await Auth.apiFetch(`/api/admin/geofences/${id}/`);
        const data = await res.json();
        document.getElementById('modalName').value = data.name;
        document.getElementById('modalRisk').value = data.risk_level;
        document.getElementById('modalDesc').value = data.description || '';
        this.currentPolygon = data.polygon || [];
        this._setCoords(this.currentPolygon);
      } catch (e) {
        alert('데이터 로드에 실패했습니다.');
        return;
      }
    } else {
      this.currentPolygon = [];
      this._setCoords([]);
    }
    document.getElementById('geofenceModal').style.display = 'flex';
  },

  _closeModal() {
    document.getElementById('geofenceModal').style.display = 'none';
  },

  _addCoordRow(x = '', y = '') {
    const row = document.createElement('div');
    row.className = 'coord-row';
    row.innerHTML = `
      <span class="coord-index"></span>
      <input type="number" placeholder="x" class="coord-x" value="${x}">
      <input type="number" placeholder="y" class="coord-y" value="${y}">
      <button class="btn-danger-sm" onclick="GeofenceAdmin._removeCoord(this)">✕</button>
    `;
    document.getElementById('coordList').appendChild(row);
    this._updateCoordIndex();
  },

  _removeCoord(btn) {
    const rows = document.querySelectorAll('.coord-row');
    if (rows.length <= 3) { alert('최소 3개의 좌표가 필요합니다.'); return; }
    btn.closest('.coord-row').remove();
    this._updateCoordIndex();
  },

  _updateCoordIndex() {
    document.querySelectorAll('.coord-row').forEach((row, i) => {
      row.querySelector('.coord-index').textContent = `${i + 1}.`;
    });
  },

  _getCoords() {
    const rows = document.querySelectorAll('.coord-row');
    const coords = [];
    rows.forEach(row => {
      const x = parseFloat(row.querySelector('.coord-x').value);
      const y = parseFloat(row.querySelector('.coord-y').value);
      if (!isNaN(x) && !isNaN(y)) coords.push([x, y]);
    });
    return coords;
  },

  _setCoords(polygon) {
    const list = document.getElementById('coordList');
    list.innerHTML = '';
    if (!polygon || polygon.length === 0) {
      for (let i = 0; i < 3; i++) this._addCoordRow();
    } else {
      polygon.forEach(([x, y]) => this._addCoordRow(x, y));
    }
  },

  async _save() {
    const id     = document.getElementById('modalId').value;
    const name   = document.getElementById('modalName').value.trim();
    const risk   = document.getElementById('modalRisk').value;
    const desc   = document.getElementById('modalDesc').value.trim();
    const coords = this._getCoords();

    if (!name) { alert('구역명을 입력해주세요.'); return; }
    if (coords.length < 3) { alert('최소 3개의 좌표를 입력해주세요.'); return; }

    const method = id ? 'PUT' : 'POST';
    const url = id ? `/api/admin/geofences/${id}/` : `/api/admin/geofences/`;

    try {
      const res = await Auth.apiFetch(url, {
        method,
        body: JSON.stringify({
          name,
          risk_level: risk,
          description: desc,
          facility: 1,
          polygon: coords,
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      this._closeModal();
      await this.fetchList();
    } catch (e) {
      alert('저장에 실패했습니다.');
    }
  },
};

document.addEventListener('DOMContentLoaded', async () => {
  if (!await AdminAccess.check()) return;
  GeofenceAdmin.init();
});
