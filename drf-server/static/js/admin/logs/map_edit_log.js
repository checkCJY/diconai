/* admin/logs/map_edit_log.js — 지도 편집 로그 (SystemLog MAP_) */
'use strict';

const MapEditLog = {
    page: 1, pageSize: 10,
    ACTION_LABEL: {
        map_geofence_create: '위험구역 생성',
        map_sensor_move: '센서 이동',
        map_facility_update: '설비 수정',
        map_position_node_register: '위치 노드 등록',
        map_object_delete: '객체 삭제',
    },
    RESULT_BADGE:  { success: 'badge-success', failure: 'badge-failure' },
    RESULT_LABEL:  { success: '성공', failure: '실패' },

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
        document.getElementById('filterActionType').value = '';
        document.getElementById('filterTarget').value = '';
        document.getElementById('filterKeyword').value = '';
        document.querySelector('[data-range="week"]').click();
    },

    _params() {
        const p = new URLSearchParams({ page: this.page, page_size: this.pageSize });
        const action = document.getElementById('filterActionType').value;
        const target = document.getElementById('filterTarget').value.trim();
        const kw     = document.getElementById('filterKeyword').value.trim();
        const df     = document.getElementById('dateFrom').value;
        const dt     = document.getElementById('dateTo').value;
        if (action) p.set('action_type', action);
        if (target) p.set('keyword', target);
        else if (kw) p.set('keyword', kw);
        if (df) p.set('date_from', df);
        if (dt) p.set('date_to', dt);
        return p;
    },

    async fetch() {
        const token = localStorage.getItem('access_token');
        try {
            const res = await fetch(`/api/admin/map-edit-logs/?${this._params()}`, {
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
            const actionLabel = this.ACTION_LABEL[r.action_type] || r.action_type_display;
            const resBadge    = this.RESULT_BADGE[r.result] || 'badge-gray';
            const resLabel    = this.RESULT_LABEL[r.result] || r.result_display || '-';
            return `<tr>
                <td>${LogUtils.fmtDate(r.created_at)}</td>
                <td><span class="badge badge-info">${LogUtils.esc(actionLabel)}</span></td>
                <td>${LogUtils.esc(r.target_name || r.target_model)}</td>
                <td><span class="badge ${resBadge}">${resLabel}</span></td>
                <td class="log-msg" title="${LogUtils.esc(r.description)}">${LogUtils.esc(r.description)}</td>
            </tr>`;
        }).join('');
    },

    async _export() {
        const token = localStorage.getItem('access_token');
        const p = this._params(); p.set('page_size', '10000');
        const res = await fetch(`/api/admin/map-edit-logs/?${p}`, { headers: { Authorization: `Bearer ${token}` } });
        const data = await res.json();
        const rows = (data.results || []).map(r => [
            LogUtils.fmtDate(r.created_at), this.ACTION_LABEL[r.action_type]||'',
            r.target_name||'', this.RESULT_LABEL[r.result]||'', r.description||''
        ]);
        LogUtils.exportCSV(['발생시간','작업구분','편집대상','작업결과','작업내용'], rows, '지도편집로그.csv');
    }
};

document.addEventListener('DOMContentLoaded', () => MapEditLog.init());
