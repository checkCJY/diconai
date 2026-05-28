/* admin/notices/notice_form.js — 공지사항 등록/수정 폼 페이지
 *
 * API:
 *   POST  /api/admin/notices/           등록
 *   PATCH /api/admin/notices/{id}/      수정
 *   POST  /api/admin/notices/{id}/attachments/          파일 업로드
 *   DELETE /api/admin/notices/{id}/attachments/{att_id}/ 파일 삭제
 */
'use strict';

const NoticeForm = {
    isActive: true,           // 노출 여부
    newFiles: [],             // 새로 선택한 File 객체 배열
    existingAttachments: [],  // 수정 모드: 기존 첨부파일 목록
    removedAttIds: [],        // 수정 모드: 삭제할 기존 첨부파일 id

    async init() {
        this._bindToggle();
        this._bindFileUpload();
        this._bindSubmit();
        this._bindCancel();
        this._loadAdminName();

        if (NOTICE_FORM_MODE === 'edit' && NOTICE_ID) {
            await this._loadExisting();
        }
    },

    // ── 노출 여부 토글 ─────────────────────────────────────

    _bindToggle() {
        document.getElementById('toggleVisible').addEventListener('click', () => this._setActive(true));
        document.getElementById('toggleHidden').addEventListener('click', () => this._setActive(false));
    },

    _setActive(val) {
        this.isActive = val;
        document.getElementById('toggleVisible').classList.toggle('active', val);
        document.getElementById('toggleHidden').classList.toggle('active', !val);
    },

    // ── 파일 업로드 ────────────────────────────────────────

    _bindFileUpload() {
        const dropZone  = document.getElementById('dropZone');
        const fileInput = document.getElementById('fileInput');
        const btnSelect = document.getElementById('btnFileSelect');

        btnSelect.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', (e) => this._addFiles(e.target.files));

        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover');
        });
        dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            this._addFiles(e.dataTransfer.files);
        });
    },

    _addFiles(fileList) {
        Array.from(fileList).forEach(f => {
            if (f.size > 10 * 1024 * 1024) {
                this._showToast(`${f.name}: 파일 크기가 10MB를 초과합니다.`, true);
                return;
            }
            this.newFiles.push(f);
        });
        this._renderNewFiles();
    },

    _renderNewFiles() {
        const list = document.getElementById('newFileList');
        list.innerHTML = this.newFiles.map((f, i) => `
            <div class="selected-file-item">
                <span class="selected-file-name">${this._esc(f.name)}</span>
                <span class="selected-file-size">${this._formatSize(f.size)}</span>
                <button type="button" class="btn-remove-file" data-idx="${i}">삭제</button>
            </div>`).join('');

        list.querySelectorAll('.btn-remove-file').forEach(btn => {
            btn.addEventListener('click', (e) => {
                this.newFiles.splice(parseInt(e.target.dataset.idx), 1);
                this._renderNewFiles();
            });
        });
    },

    // ── 기존 데이터 로드 (수정 모드) ──────────────────────

    async _loadExisting() {
        const token = localStorage.getItem('access_token');
        const res = await fetch(`/api/admin/notices/${NOTICE_ID}/`, {
            headers: { Authorization: `Bearer ${token}` }
        });
        if (!res.ok) return;

        const n = await res.json();
        document.getElementById('inputTitle').value = n.title || '';
        document.getElementById('inputCategory').value = n.category || '';
        document.getElementById('inputContent').value = n.content || '';
        this._setActive(n.is_active !== false);

        // 등록 정보
        document.getElementById('regAuthor').textContent = n.author_name || '-';
        document.getElementById('regCreatedAt').textContent = n.created_at ? n.created_at.slice(0, 10) : '-';
        document.getElementById('regUpdatedAt').textContent = n.updated_at ? n.updated_at.slice(0, 10) : '-';

        // 기존 첨부파일
        this.existingAttachments = n.attachments || [];
        if (this.existingAttachments.length > 0) {
            document.getElementById('existingFilesWrap').style.display = 'block';
            this._renderExistingFiles();
        }
    },

    _renderExistingFiles() {
        const list = document.getElementById('existingFileList');
        list.innerHTML = this.existingAttachments
            .filter(a => !this.removedAttIds.includes(a.id))
            .map(a => `
                <div class="selected-file-item">
                    <span class="selected-file-name">${this._esc(a.filename)}</span>
                    <span class="selected-file-size">${this._formatSize(a.size)}</span>
                    <button type="button" class="btn-remove-file" data-att-id="${a.id}">삭제</button>
                </div>`).join('');

        list.querySelectorAll('.btn-remove-file').forEach(btn => {
            btn.addEventListener('click', (e) => {
                this.removedAttIds.push(parseInt(e.target.dataset.attId));
                this._renderExistingFiles();
            });
        });
    },

    // ── 관리자 이름 로드 ───────────────────────────────────

    _loadAdminName() {
        const name = document.getElementById('adminName');
        if (name) {
            document.getElementById('regAuthor').textContent = name.textContent || '-';
        }
    },

    // ── 폼 제출 ────────────────────────────────────────────

    _bindSubmit() {
        document.getElementById('btnSubmit').addEventListener('click', () => {
            const title = document.getElementById('inputTitle').value.trim();
            const category = document.getElementById('inputCategory').value;

            if (!title) { this._showToast('공지 제목을 입력해 주세요.', true); return; }
            if (!category) { this._showToast('공지 구분을 선택해 주세요.', true); return; }

            const isEdit = NOTICE_FORM_MODE === 'edit';
            document.getElementById('confirmTitle').textContent =
                isEdit ? '공지사항을 수정하시겠습니까?' : '공지사항을 등록하시겠습니까?';
            document.getElementById('confirmMsg').textContent =
                isEdit
                    ? '해당 공지사항을 수정하시겠습니까?'
                    : '해당 공지사항을 등록하시겠습니까?';
            document.getElementById('confirmModal').style.display = 'flex';
        });

        document.getElementById('btnConfirmCancel').addEventListener('click', () => {
            document.getElementById('confirmModal').style.display = 'none';
        });

        document.getElementById('btnConfirmOk').addEventListener('click', () => {
            document.getElementById('confirmModal').style.display = 'none';
            this._submit();
        });
    },

    async _submit() {
        const token = localStorage.getItem('access_token');
        const title   = document.getElementById('inputTitle').value.trim();
        const category = document.getElementById('inputCategory').value;
        const content  = document.getElementById('inputContent').value;
        const isEdit   = NOTICE_FORM_MODE === 'edit';

        const body = { title, category, content, is_active: this.isActive };

        // 등록 또는 수정
        const url    = isEdit ? `/api/admin/notices/${NOTICE_ID}/` : '/api/admin/notices/';
        const method = isEdit ? 'PATCH' : 'POST';

        const res = await fetch(url, {
            method,
            headers: {
                Authorization: `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(body)
        });

        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            this._showToast(`저장 실패: ${JSON.stringify(err)}`, true);
            return;
        }

        const saved = await res.json();
        const noticeId = saved.id || NOTICE_ID;

        // 기존 첨부파일 삭제 (수정 모드)
        for (const attId of this.removedAttIds) {
            await fetch(`/api/admin/notices/${noticeId}/attachments/${attId}/`, {
                method: 'DELETE',
                headers: { Authorization: `Bearer ${token}` }
            });
        }

        // 새 파일 업로드
        for (const file of this.newFiles) {
            const fd = new FormData();
            fd.append('file', file);
            await fetch(`/api/admin/notices/${noticeId}/attachments/`, {
                method: 'POST',
                headers: { Authorization: `Bearer ${token}` },
                body: fd
            });
        }

        this._showToast(isEdit ? '수정되었습니다.' : '등록되었습니다.');
        setTimeout(() => { location.href = `/admin-panel/notices/${noticeId}/`; }, 800);
    },

    _bindCancel() {
        document.getElementById('btnCancel').addEventListener('click', () => {
            if (confirm('작성을 취소하시겠습니까?')) {
                location.href = NOTICE_FORM_MODE === 'edit'
                    ? `/admin-panel/notices/${NOTICE_ID}/`
                    : '/admin-panel/notices/';
            }
        });
    },

    _showToast(message, isError = false) {
        const toast = document.createElement('div');
        toast.style.cssText = `position:fixed;bottom:32px;left:50%;transform:translateX(-50%);
          background:${isError ? '#be123c' : '#1e293b'};color:#fff;
          padding:10px 20px;border-radius:6px;font-size:13px;z-index:10001;
          box-shadow:0 4px 12px rgba(0,0,0,0.2);`;
        toast.textContent = message;
        document.body.appendChild(toast);
        setTimeout(() => toast.remove(), 2500);
    },

    _formatSize(bytes) {
        if (!bytes) return '-';
        if (bytes >= 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + 'MB';
        return (bytes / 1024).toFixed(0) + 'KB';
    },

    _esc(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }
};

document.addEventListener('DOMContentLoaded', () => NoticeForm.init());
