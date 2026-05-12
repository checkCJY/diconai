/* admin/logs/log_utils.js — 로그 페이지 공통 유틸 */
'use strict';

const LogUtils = {
    // 날짜 범위 빠른 선택
    initDateQuick(onApply) {
        const applyRange = (from, to) => {
            document.getElementById('dateFrom').value = from;
            document.getElementById('dateTo').value = to;
            if (onApply) onApply();
        };

        const today = new Date();
        const fmt = d => d.toISOString().slice(0, 10);

        // 기본값: 최근 7일
        const weekAgo = new Date(today); weekAgo.setDate(today.getDate() - 6);
        applyRange(fmt(weekAgo), fmt(today));

        document.querySelectorAll('.date-quick-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.date-quick-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');

                const t = new Date();
                const range = btn.dataset.range;
                if (range === 'today') {
                    applyRange(fmt(t), fmt(t));
                } else if (range === 'yesterday') {
                    const y = new Date(t); y.setDate(t.getDate() - 1);
                    applyRange(fmt(y), fmt(y));
                } else if (range === 'week') {
                    const w = new Date(t); w.setDate(t.getDate() - 6);
                    applyRange(fmt(w), fmt(t));
                } else if (range === 'month') {
                    const m = new Date(t.getFullYear(), t.getMonth(), 1);
                    applyRange(fmt(m), fmt(t));
                }
            });
        });
    },

    // 페이지네이션 렌더링
    renderPagination(data, pageSize, currentPage, onPageChange) {
        const total = data.total || 0;
        const totalPages = Math.ceil(total / pageSize);
        const start = total ? (currentPage - 1) * pageSize + 1 : 0;
        const end = Math.min(currentPage * pageSize, total);

        document.getElementById('pageInfo').textContent = `${start} - ${end} / ${total}`;
        document.getElementById('totalCount').textContent = total;

        const pg = document.getElementById('pagination');
        pg.innerHTML = '';

        const mkBtn = (label, page, disabled, active) => {
            const btn = document.createElement('button');
            btn.textContent = label;
            btn.disabled = disabled;
            if (active) btn.classList.add('active');
            btn.addEventListener('click', () => onPageChange(page));
            pg.appendChild(btn);
        };

        mkBtn('<', currentPage - 1, currentPage <= 1, false);
        const s = Math.max(1, currentPage - 2);
        const e = Math.min(totalPages, s + 4);
        for (let i = s; i <= e; i++) mkBtn(i, i, false, i === currentPage);
        mkBtn('>', currentPage + 1, currentPage >= totalPages, false);
    },

    // CSV 내보내기
    exportCSV(headers, rows, filename) {
        const bom = '﻿';
        const lines = [headers.join(','), ...rows.map(r => r.map(c => `"${String(c).replace(/"/g,'""')}"`).join(','))];
        const blob = new Blob([bom + lines.join('\n')], { type: 'text/csv;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
    },

    // 날짜 포맷
    fmtDate(iso) {
        if (!iso) return '-';
        return iso.replace('T', ' ').slice(0, 19);
    },

    esc(str) {
        return String(str || '-').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }
};
