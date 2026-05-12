/* admin/logs/integration_log.js — 연동 로그 (IntegrationLog) */
'use strict';

const IntegrationLog = {
    page: 1, pageSize: 10,
    TYPE_LABEL:  { collect: '수집', transmit: '전송', sync: '연동' },
    TYPE_BADGE:  { collect: 'badge-info', transmit: 'badge-batch', sync: 'badge-service' },
    RESULT_BADGE: { success: 'badge-success', failure: 'badge-failure', delay: 'badge-delay' },
    RESULT_LABEL: { success: '성공', failure: '실패', delay: '지연' },

    async init() {
        LogUtils.initDateQuick(() => { this.page=1; this.fetch(); });
        document.getElementById('btnSearch').addEventListener('click', () => { this.page=1; this.fetch(); });
        document.getElementById('filterKeyword').addEventListener('keydown', e => { if (e.key==='Enter') { this.page=1; this.fetch(); }});
        document.getElementById('btnReset').addEventListener('click', () => this._reset());
        document.getElementById('btnExport').addEventListener('click', () => this._export());
        document.getElementById('sortSelect').addEventListener('change', () => { this.page=1; this.fetch(); });
        await this.fetch();
    },

    _reset() {
        document.getElementById('filterType').value = '';
        document.getElementById('filterTarget').value = '';
        document.getElementById('filterKeyword').value = '';
        document.querySelector('[data-range="week"]').click();
    },

    _params() {
        const p = new URLSearchParams({ page: this.page, page_size: this.pageSize });
        const type   = document.getElementById('filterType').value;
        const target = document.getElementById('filterTarget').value.trim();
        const kw     = document.getElementById('filterKeyword').value.trim();
        const df     = document.getElementById('dateFrom').value;
        const dt     = document.getElementById('dateTo').value;
        if (type)   p.set('integration_type', type);
        if (target) p.set('keyword', target);
        else if (kw) p.set('keyword', kw);
        if (df) p.set('date_from', df);
        if (dt) p.set('date_to', dt);
        return p;
    },

    async fetch() {
        const token = localStorage.getItem('access_token');
        try {
            const res = await fetch(`/api/admin/integration-logs/?${this._params()}`, {
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
                `<tr><td colspan="5" class="empty-state">로딩 실패: ${e.message}</td></tr>`;
        }
    },

    _render(rows) {
        const tb = document.getElementById('logTableBody');
        if (!rows.length) { tb.innerHTML = '<tr><td colspan="5" class="empty-state">조회된 로그가 없습니다.</td></tr>'; return; }
        tb.innerHTML = rows.map(r => {
            const typeBadge  = this.TYPE_BADGE[r.integration_type] || 'badge-gray';
            const typeLabel  = this.TYPE_LABEL[r.integration_type] || r.integration_type_display;
            const resBadge   = this.RESULT_BADGE[r.result] || 'badge-gray';
            const resLabel   = this.RESULT_LABEL[r.result] || r.result_display;
            return `<tr>
                <td>${LogUtils.fmtDate(r.created_at)}</td>
                <td><span class="badge ${typeBadge}">${typeLabel}</span></td>
                <td>${LogUtils.esc(r.target_system)}</td>
                <td><span class="badge ${resBadge}">${resLabel}</span></td>
                <td class="log-msg" title="${LogUtils.esc(r.description)}">${LogUtils.esc(r.description)}</td>
            </tr>`;
        }).join('');
    },

    async _export() {
        const token = localStorage.getItem('access_token');
        const p = this._params(); p.set('page_size', '10000');
        const res = await fetch(`/api/admin/integration-logs/?${p}`, { headers: { Authorization: `Bearer ${token}` } });
        const data = await res.json();
        const rows = (data.results || []).map(r => [
            LogUtils.fmtDate(r.created_at), this.TYPE_LABEL[r.integration_type]||'',
            r.target_system||'', this.RESULT_LABEL[r.result]||'', r.description||''
        ]);
        LogUtils.exportCSV(['발생시간','연동구분','연동대상','결과','발생내용'], rows, '연동로그.csv');
    }
};

document.addEventListener('DOMContentLoaded', () => IntegrationLog.init());
