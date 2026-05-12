/* admin/notices/notice_detail.js — 공지사항 상세 페이지
 *
 * API:
 *   GET    /api/admin/notices/{id}/  상세 조회
 *   DELETE /api/admin/notices/{id}/  삭제
 */
'use strict';

const NoticeDetail = {
    notice: null,

    CATEGORY_LABEL: { general: '일반 공지', urgent: '긴급 공지', maintenance: '점검 안내' },
    CATEGORY_BADGE: { general: 'badge-general', urgent: 'badge-urgent', maintenance: 'badge-maintenance' },

    async init() {
        await this.fetchDetail();
        this._bindEvents();
    },

    async fetchDetail() {
        const token = localStorage.getItem('access_token');
        try {
            const res = await fetch(`/api/admin/notices/${NOTICE_ID}/`, {
                headers: { Authorization: `Bearer ${token}` }
            });
            if (res.status === 401) { location.href = '/accounts/login/'; return; }
            if (res.status === 404) { this._renderNotFound(); return; }
            if (!res.ok) throw new Error(`서버 오류: ${res.status}`);

            this.notice = await res.json();
            this._render(this.notice);
            await this._loadNavigation();
        } catch (e) {
            document.getElementById('noticeTitle').textContent = `로딩 실패: ${e.message}`;
        }
    },

    _render(n) {
        document.getElementById('noticeTitle').textContent = n.title;

        const catLabel = this.CATEGORY_LABEL[n.category] || n.category;
        const catBadge = this.CATEGORY_BADGE[n.category] || '';
        const badge = document.getElementById('noticeCategoryBadge');
        badge.textContent = catLabel;
        badge.className = `badge ${catBadge}`;

        if (n.is_pinned) {
            document.getElementById('noticePinnedBadge').innerHTML =
                '<span class="badge" style="background:#fef9c3;color:#854d0e;">📌 상단 고정</span>';
        }

        document.getElementById('noticeAuthor').textContent = n.author_name || '-';
        document.getElementById('noticeCreatedAt').textContent = this._formatDate(n.created_at);
        document.getElementById('noticeUpdatedAt').textContent = this._formatDate(n.updated_at);
        document.getElementById('noticeBody').textContent = n.content || '';

        // 첨부파일
        if (n.attachments && n.attachments.length > 0) {
            const section = document.getElementById('attachmentSection');
            section.style.display = 'block';
            document.getElementById('attachmentCount').textContent = `(${n.attachments.length}개)`;

            document.getElementById('attachmentList').innerHTML = n.attachments.map(a => {
                const ext = (a.filename || '').split('.').pop().toUpperCase();
                const size = this._formatSize(a.size);
                return `<div class="attachment-item">
                    <div class="attachment-info">
                        <span class="attachment-icon">${this._fileIcon(ext)}</span>
                        <div>
                            <div class="attachment-name">${this._esc(a.filename)}</div>
                            <div class="attachment-size">${ext} · ${size}</div>
                        </div>
                    </div>
                    <a class="btn-download" href="${a.file_url}" download="${this._esc(a.filename)}">다운로드</a>
                </div>`;
            }).join('');
        }
    },

    async _loadNavigation() {
        // 이전글/다음글: 목록에서 현재 id 기준으로 인접 항목 조회
        const token = localStorage.getItem('access_token');
        try {
            const res = await fetch(`/api/admin/notices/?page=1&page_size=200`, {
                headers: { Authorization: `Bearer ${token}` }
            });
            if (!res.ok) return;
            const data = await res.json();
            const items = (data.results || []).sort((a, b) =>
                new Date(b.published_at) - new Date(a.published_at)
            );
            const idx = items.findIndex(n => n.id === NOTICE_ID);

            const prevItem = idx > 0 ? items[idx - 1] : null;
            const nextItem = idx < items.length - 1 ? items[idx + 1] : null;

            const navPrev = document.getElementById('navPrev');
            const navNext = document.getElementById('navNext');

            if (prevItem) {
                navPrev.innerHTML = `
                    <span class="notice-nav-label">이전글</span>
                    <span class="notice-nav-title">${this._esc(prevItem.title)}</span>`;
                navPrev.style.cursor = 'pointer';
                navPrev.addEventListener('click', () => location.href = `/admin-panel/notices/${prevItem.id}/`);
            }
            if (nextItem) {
                navNext.innerHTML = `
                    <span class="notice-nav-label">다음글</span>
                    <span class="notice-nav-title">${this._esc(nextItem.title)}</span>`;
                navNext.style.cursor = 'pointer';
                navNext.addEventListener('click', () => location.href = `/admin-panel/notices/${nextItem.id}/`);
            }
        } catch (_) { /* 네비 실패는 무시 */ }
    },

    _bindEvents() {
        document.getElementById('btnEdit').addEventListener('click', () => {
            location.href = `/admin-panel/notices/${NOTICE_ID}/edit/`;
        });

        document.getElementById('btnDelete').addEventListener('click', () => {
            document.getElementById('deleteModal').style.display = 'flex';
        });

        document.getElementById('btnDeleteCancel').addEventListener('click', () => {
            document.getElementById('deleteModal').style.display = 'none';
        });

        document.getElementById('btnDeleteConfirm').addEventListener('click', () => this._delete());
    },

    async _delete() {
        const token = localStorage.getItem('access_token');
        document.getElementById('deleteModal').style.display = 'none';

        const res = await fetch(`/api/admin/notices/${NOTICE_ID}/`, {
            method: 'DELETE',
            headers: { Authorization: `Bearer ${token}` }
        });

        if (res.status === 204) {
            alert('삭제되었습니다.');
            location.href = '/admin-panel/notices/';
        } else {
            alert('삭제 실패. 다시 시도해주세요.');
        }
    },

    _renderNotFound() {
        document.getElementById('noticeTitle').textContent = '공지사항을 찾을 수 없습니다.';
    },

    _formatDate(iso) {
        if (!iso) return '-';
        return iso.slice(0, 10);
    },

    _formatSize(bytes) {
        if (!bytes) return '-';
        if (bytes >= 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + 'MB';
        return (bytes / 1024).toFixed(0) + 'KB';
    },

    _fileIcon(ext) {
        const icons = { PDF: '📄', JPG: '🖼', JPEG: '🖼', PNG: '🖼', XLSX: '📊', XLS: '📊', HWP: '📝' };
        return icons[ext] || '📎';
    },

    _esc(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }
};

document.addEventListener('DOMContentLoaded', () => NoticeDetail.init());
