/* admin/notices/notices_list.js — 공지사항 목록 페이지
 *
 * API:
 *   GET    /api/admin/notices/       목록 조회
 *   DELETE /api/admin/notices/{id}/  소프트 삭제
 */
'use strict';

const NoticesList = {
    page: 1,
    pageSize: 10,
    total: 0,
    filters: { keyword: '', category: '', is_active: '' },
    sort: 'recent',
    selected: new Set(),

    CATEGORY_LABEL: { general: '일반 공지', urgent: '긴급 공지', maintenance: '점검 안내' },
    CATEGORY_BADGE: { general: 'badge-general', urgent: 'badge-urgent', maintenance: 'badge-maintenance' },

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

        document.getElementById('filterTitle').addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                this._readFilters();
                this.page = 1;
                this.fetchList();
            }
        });

        document.getElementById('btnReset').addEventListener('click', () => {
            document.getElementById('filterTitle').value = '';
            document.getElementById('filterCategory').value = '';
            document.getElementById('filterActive').value = '';
            this.filters = { keyword: '', category: '', is_active: '' };
            this.page = 1;
            this.fetchList();
        });

        document.getElementById('sortSelect').addEventListener('change', () => {
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

        document.getElementById('btnDelete').addEventListener('click', () => this._confirmDelete());
        document.getElementById('btnCreateNotice').addEventListener('click', () => {
            location.href = '/admin-panel/notices/create/';
        });

        // 삭제 모달
        document.getElementById('btnDeleteCancel').addEventListener('click', () => {
            document.getElementById('deleteModal').style.display = 'none';
        });
        document.getElementById('btnDeleteConfirm').addEventListener('click', () => this._deleteSelected());
    },

    _readFilters() {
        this.filters.keyword  = document.getElementById('filterTitle').value.trim();
        this.filters.category = document.getElementById('filterCategory').value;
        this.filters.is_active = document.getElementById('filterActive').value;
    },

    _buildParams() {
        const params = new URLSearchParams({ page: this.page, page_size: this.pageSize });
        if (this.filters.keyword)   params.set('keyword', this.filters.keyword);
        if (this.filters.category)  params.set('category', this.filters.category);
        // is_active 필터는 서버가 아직 지원하지 않으므로 클라이언트 필터링
        return params;
    },

    async fetchList() {
        const token = localStorage.getItem('access_token');
        const params = this._buildParams();

        try {
            const res = await fetch(`/api/admin/notices/?${params}`, {
                headers: { Authorization: `Bearer ${token}` }
            });

            if (res.status === 401) { location.href = '/accounts/login/'; return; }
            if (!res.ok) throw new Error(`서버 오류: ${res.status}`);

            const data = await res.json();
            let results = data.results || [];

            // is_active 클라이언트 필터 (선택사항)
            if (this.filters.is_active === 'true')  results = results.filter(n => n.is_active);
            if (this.filters.is_active === 'false') results = results.filter(n => !n.is_active);

            // 정렬
            const sort = document.getElementById('sortSelect').value;
            if (sort === 'pinned') results.sort((a, b) => b.is_pinned - a.is_pinned);

            this.total = data.total || results.length;
            this._renderTable(results);
            this._renderPagination(data);
            this._updateTotal(data.total);
        } catch (e) {
            document.getElementById('noticesTableBody').innerHTML =
                `<tr><td colspan="6" class="empty-state">데이터 로딩 실패: ${e.message}</td></tr>`;
        }
    },

    _renderTable(items) {
        const tbody = document.getElementById('noticesTableBody');
        this.selected.clear();
        this._updateBulkButtons();

        if (!items.length) {
            tbody.innerHTML = '<tr><td colspan="6" class="empty-state">등록된 공지사항이 없습니다.</td></tr>';
            return;
        }

        tbody.innerHTML = items.map(n => {
            const catLabel = this.CATEGORY_LABEL[n.category] || n.category;
            const catBadge = this.CATEGORY_BADGE[n.category] || '';
            const activeBadge = n.is_active
                ? '<span class="badge badge-visible">노출</span>'
                : '<span class="badge badge-hidden">숨김</span>';
            const pinIcon = n.is_pinned ? '<span class="pin-icon" title="상단 고정">📌</span>' : '';
            const updatedAt = n.updated_at ? n.updated_at.slice(0, 10) : '-';

            return `<tr>
                <td><input type="checkbox" class="row-check" data-id="${n.id}"></td>
                <td>
                    <div class="notice-title-cell">
                        <a class="notice-title-link" href="/admin-panel/notices/${n.id}/">${this._esc(n.title)}</a>
                        ${pinIcon}
                    </div>
                </td>
                <td><span class="badge ${catBadge}">${catLabel}</span></td>
                <td>${activeBadge}</td>
                <td>${this._esc(n.author_name || '-')}</td>
                <td>${updatedAt}</td>
            </tr>`;
        }).join('');

        // 체크박스 이벤트 바인딩
        tbody.querySelectorAll('.row-check').forEach(cb => {
            cb.addEventListener('change', (e) => {
                const id = parseInt(e.target.dataset.id);
                e.target.checked ? this.selected.add(id) : this.selected.delete(id);
                this._updateBulkButtons();
            });
        });
    },

    _renderPagination(data) {
        const total = data.total || 0;
        const pageSize = this.pageSize;
        const totalPages = Math.ceil(total / pageSize);
        const start = total ? (this.page - 1) * pageSize + 1 : 0;
        const end = Math.min(this.page * pageSize, total);

        document.getElementById('pageInfo').textContent = `${start} - ${end} / ${total}`;

        const pg = document.getElementById('pagination');
        pg.innerHTML = '';

        const mkBtn = (label, page, disabled = false, active = false) => {
            const btn = document.createElement('button');
            btn.textContent = label;
            btn.disabled = disabled;
            if (active) btn.classList.add('active');
            btn.addEventListener('click', () => { this.page = page; this.fetchList(); });
            pg.appendChild(btn);
        };

        mkBtn('<', this.page - 1, this.page <= 1);

        // 최대 5페이지 버튼
        const startPage = Math.max(1, this.page - 2);
        const endPage   = Math.min(totalPages, startPage + 4);
        for (let i = startPage; i <= endPage; i++) {
            mkBtn(i, i, false, i === this.page);
        }

        mkBtn('>', this.page + 1, this.page >= totalPages);
    },

    _updateTotal(total) {
        document.getElementById('totalCount').textContent = total || 0;
    },

    _updateBulkButtons() {
        const count = this.selected.size;
        const btn = document.getElementById('btnDelete');
        btn.disabled = count === 0;

        const sel = document.getElementById('selectedCount');
        sel.textContent = count > 0 ? `${count}건 선택` : '';
    },

    _confirmDelete() {
        const count = this.selected.size;
        document.getElementById('deleteModalMsg').textContent =
            `선택한 공지사항 ${count}건을 삭제하시겠습니까?`;
        document.getElementById('deleteModal').style.display = 'flex';
    },

    async _deleteSelected() {
        document.getElementById('deleteModal').style.display = 'none';
        const token = localStorage.getItem('access_token');
        const ids = [...this.selected];

        await Promise.all(ids.map(id =>
            fetch(`/api/admin/notices/${id}/`, {
                method: 'DELETE',
                headers: { Authorization: `Bearer ${token}` }
            })
        ));

        this.selected.clear();
        this.page = 1;
        await this.fetchList();
    },

    _esc(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }
};

document.addEventListener('DOMContentLoaded', () => NoticesList.init());
