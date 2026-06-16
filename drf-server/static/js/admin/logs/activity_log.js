/* admin/logs/activity_log.js — 사용자 활동 로그 (SystemLog) */
'use strict';

const ActivityLog = {
    page: 1, pageSize: 10,
    ACTION_BADGE: {
        create: 'badge-create', created: 'badge-create',
        update: 'badge-update', updated: 'badge-update',
        delete: 'badge-delete', deleted: 'badge-delete',
    },

    async init() {
        LogUtils.initDateQuick(() => { this.page = 1; this.fetch(); });
        document.getElementById('btnSearch').addEventListener('click', () => { this.page=1; this.fetch(); });
        document.getElementById('filterKeyword').addEventListener('keydown', e => { if (e.key==='Enter') { this.page=1; this.fetch(); }});
        document.getElementById('btnReset').addEventListener('click', () => this._reset());
        document.getElementById('btnExport').addEventListener('click', () => this._export());
        document.getElementById('sortSelect').addEventListener('change', () => { this.page=1; this.fetch(); });
        await this.fetch();
    },

    _reset() {
        document.getElementById('filterActor').value = '';
        document.getElementById('filterActionType').value = '';
        document.getElementById('filterKeyword').value = '';
        document.querySelector('[data-range="week"]').click();
    },

    _params() {
        const p = new URLSearchParams({ page: this.page, page_size: this.pageSize });
        const actor  = document.getElementById('filterActor').value.trim();
        const action = document.getElementById('filterActionType').value;
        const kw     = document.getElementById('filterKeyword').value.trim();
        const df     = document.getElementById('dateFrom').value;
        const dt     = document.getElementById('dateTo').value;
        if (actor)  p.set('actor', actor);
        if (action) p.set('action_type', action);
        if (kw)     p.set('keyword', kw);
        if (df)     p.set('date_from', df);
        if (dt)     p.set('date_to', dt);
        return p;
    },

    _actionBadge(actionType) {
        for (const [key, cls] of Object.entries(this.ACTION_BADGE)) {
            if (actionType.includes(key)) return cls;
        }
        return 'badge-gray';
    },

    async fetch() {
        const token = localStorage.getItem('access_token');
        try {
            const res = await fetch(`/api/admin/activity-logs/?${this._params()}`, {
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
            const badge = this._actionBadge(r.action_type || '');
            const target = r.target_name ? `${r.target_model} · ${r.target_name}` : (r.target_model || '-');
            return `<tr>
                <td>${LogUtils.fmtDate(r.created_at)}</td>
                <td>${LogUtils.esc(r.actor_name)}</td>
                <td><span class="badge ${badge}">${LogUtils.esc(r.action_type_display)}</span></td>
                <td>${LogUtils.esc(target)}</td>
                <td class="log-msg" title="${LogUtils.esc(r.description)}">${LogUtils.esc(r.description)}</td>
            </tr>`;
        }).join('');
    },

    async _export() {
        const token = localStorage.getItem('access_token');
        const p = this._params(); p.set('page_size', '10000');
        const res = await fetch(`/api/admin/activity-logs/?${p}`, { headers: { Authorization: `Bearer ${token}` } });
        const data = await res.json();
        const rows = (data.results || []).map(r => [
            LogUtils.fmtDate(r.created_at), r.actor_name||'', r.action_type_display||'',
            r.target_name||'', r.description||''
        ]);
        LogUtils.exportCSV(['발생시간','사용자','작업유형','대상','활동내용'], rows, '사용자활동로그.csv');
    }
};

document.addEventListener('DOMContentLoaded', () => ActivityLog.init());
