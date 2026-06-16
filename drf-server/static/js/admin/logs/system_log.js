/* admin/logs/system_log.js — 시스템 로그 (AppLog) */
'use strict';

const SystemLog = {
    page: 1, pageSize: 10,
    CAT_BADGE: { error: 'badge-error', batch: 'badge-batch', service: 'badge-service' },
    CAT_LABEL: { error: '오류', batch: '배치', service: '서비스' },

    async init() {
        LogUtils.initDateQuick(() => { this.page = 1; this.fetch(); });
        document.getElementById('btnSearch').addEventListener('click', () => { this.page = 1; this.fetch(); });
        document.getElementById('filterKeyword').addEventListener('keydown', e => { if (e.key==='Enter') { this.page=1; this.fetch(); }});
        document.getElementById('btnReset').addEventListener('click', () => this._reset());
        document.getElementById('btnExport').addEventListener('click', () => this._export());
        document.getElementById('sortSelect').addEventListener('change', () => { this.page=1; this.fetch(); });
        await this.fetch();
    },

    _reset() {
        document.getElementById('filterCategory').value = '';
        document.getElementById('filterKeyword').value = '';
        document.querySelectorAll('.date-quick-btn').forEach(b => b.classList.remove('active'));
        document.querySelector('[data-range="week"]').classList.add('active');
        document.querySelector('[data-range="week"]').click();
    },

    _params() {
        const p = new URLSearchParams({ page: this.page, page_size: this.pageSize });
        const cat = document.getElementById('filterCategory').value;
        const kw  = document.getElementById('filterKeyword').value.trim();
        const df  = document.getElementById('dateFrom').value;
        const dt  = document.getElementById('dateTo').value;
        if (cat) p.set('log_category', cat);
        if (kw)  p.set('keyword', kw);
        if (df)  p.set('date_from', df);
        if (dt)  p.set('date_to', dt);
        return p;
    },

    async fetch() {
        const token = localStorage.getItem('access_token');
        try {
            const res = await fetch(`/api/admin/system-logs/?${this._params()}`, {
                headers: { Authorization: `Bearer ${token}` }
            });
            if (res.status === 401) { location.href = '/accounts/login/'; return; }
            const data = await res.json();
            let rows = data.results || [];
            if (document.getElementById('sortSelect').value === 'oldest') rows.reverse();
            this._render(rows);
            LogUtils.renderPagination(data, this.pageSize, this.page, p => { this.page=p; this.fetch(); });
        } catch(e) {
            document.getElementById('logTableBody').innerHTML =
                `<tr><td colspan="4" class="empty-state">로딩 실패: ${e.message}</td></tr>`;
        }
    },

    _render(rows) {
        const tb = document.getElementById('logTableBody');
        if (!rows.length) { tb.innerHTML = '<tr><td colspan="4" class="empty-state">조회된 로그가 없습니다.</td></tr>'; return; }
        tb.innerHTML = rows.map(r => {
            const cat = r.log_category || '';
            const badge = this.CAT_BADGE[cat] || 'badge-gray';
            const label = this.CAT_LABEL[cat] || cat;
            return `<tr>
                <td>${LogUtils.fmtDate(r.created_at)}</td>
                <td><span class="badge ${badge}">${label}</span></td>
                <td>${LogUtils.esc(r.service_module)}</td>
                <td class="log-msg" title="${LogUtils.esc(r.message)}">${LogUtils.esc(r.message)}</td>
            </tr>`;
        }).join('');
    },

    async _export() {
        const token = localStorage.getItem('access_token');
        const p = this._params();
        p.set('page_size', '10000');
        const res = await fetch(`/api/admin/system-logs/?${p}`, { headers: { Authorization: `Bearer ${token}` } });
        const data = await res.json();
        const rows = (data.results || []).map(r => [
            LogUtils.fmtDate(r.created_at),
            this.CAT_LABEL[r.log_category] || r.log_category,
            r.service_module || '',
            r.message || ''
        ]);
        LogUtils.exportCSV(['발생시간','로그구분','서비스/모듈','발생내용'], rows, '시스템로그.csv');
    }
};

document.addEventListener('DOMContentLoaded', () => SystemLog.init());
