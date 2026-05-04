'use strict';

/* =================================================================
   organizations.js — 조직 관리 페이지
   API 명세: docs/api_organizations.md
================================================================= */

const Org = {
  // ── 상태 ──────────────────────────────────────────────────
  selectedDeptId: null,       // 현재 선택된 부서 ID ('none' | int | null)
  memberPage: 1,
  memberPageSize: 10,
  memberTotal: 0,
  memberSelected: new Set(),  // 선택된 구성원 id 집합
  memberQ: '',

  STATUS_LABEL: { active: '사용', locked: '잠금', inactive: '비활성' },
  STATUS_BADGE:  { active: 'badge-green', locked: 'badge-orange', inactive: 'badge-gray' },

  // ── API 헬퍼 ──────────────────────────────────────────────

  async _api(method, url, body) {
    const opts = { method };
    if (body) opts.body = JSON.stringify(body);
    const res = await Auth.apiFetch(url, opts);
    if (res.status === 204) return null;
    return res.json();
  },

  // ── 초기화 ────────────────────────────────────────────────

  async init() {
    await this.loadTree();
    this._bindSearch();
    this._bindMemberSearch();
    this._bindCheckboxes();
    this._bindActionButtons();
  },

  // ═══════════════════════════════════════════════════════════
  // 1. 조직도 트리
  // ═══════════════════════════════════════════════════════════

  async loadTree() {
    const data = await this._api('GET', '/api/admin/organizations/tree/');
    this._renderTree(data);
  },

  _renderTree(data) {
    const container = document.getElementById('orgTree');
    container.innerHTML = '';

    data.companies.forEach(company => {
      const li = document.createElement('li');
      li.innerHTML = `
        <div class="tree-company">
          <div style="display:flex;align-items:center;gap:6px;">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="#64748b"><path d="M12 7V3H2v18h20V7H12zm-2 12H4v-2h6v2zm0-4H4v-2h6v2zm0-4H4V9h6v2zm0-4H4V5h6v2zm10 12h-8V9h8v10z"/></svg>
            <span>${company.name}</span>
          </div>
          <button class="btn btn-sm btn-outline btn-add-dept"
            style="font-size:11px;padding:2px 8px;margin-left:auto;">+ 추가</button>
        </div>`;

      const ul = document.createElement('ul');
      ul.className = 'tree-children';
      company.departments.forEach(dept => {
        ul.appendChild(this._makeDeptItem(dept));
      });
      li.appendChild(ul);
      container.appendChild(li);

      li.querySelector('.btn-add-dept').addEventListener('click', e => {
        e.stopPropagation();
        this._openAddDeptInline(ul, company.id);
      });
    });

    // 조직 없음
    const noDeptEl = document.getElementById('noDeptItem');
    if (noDeptEl) {
      const count = data.no_dept_count ?? 0;
      noDeptEl.dataset.count = count;
      noDeptEl.querySelector('.no-dept-count').textContent = count > 0 ? `(${count})` : '';
    }
  },

  _makeDeptItem(dept) {
    const li = document.createElement('li');
    li.className = 'tree-item';
    li.dataset.deptId = dept.id;
    li.innerHTML = `
      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M20 6h-2.18c.07-.44.18-.86.18-1a3 3 0 00-6 0c0 .14.11.56.18 1H10c-.28 0-.47.1-.6.28L7 10H4a1 1 0 000 2h3l.4 1H4a1 1 0 000 2h4l1.5 4h5l1.5-4h4a1 1 0 000-2h-3.4l.4-1h3a1 1 0 000-2h-3l-2.4-3.72A.994.994 0 0020 6z"/></svg>
      <span>${dept.name}</span>
      <div class="item-actions">
        <button class="item-action-btn btn-edit-dept" data-id="${dept.id}" title="수정">✎</button>
        <button class="item-action-btn btn-delete-dept" data-id="${dept.id}" title="삭제">✕</button>
      </div>`;

    // 하위 부서
    if (dept.children && dept.children.length) {
      const sub = document.createElement('ul');
      sub.className = 'tree-children';
      dept.children.forEach(child => sub.appendChild(this._makeDeptItem(child)));
      li.appendChild(sub);
    }

    li.addEventListener('click', e => {
      if (e.target.closest('.item-action-btn')) return;
      this._selectDept(dept.id, li);
    });
    li.querySelector('.btn-edit-dept')?.addEventListener('click', e => {
      e.stopPropagation();
      this._openEditDeptInline(li, dept);
    });
    li.querySelector('.btn-delete-dept')?.addEventListener('click', e => {
      e.stopPropagation();
      this._confirmDeleteDept(dept.id, dept.name);
    });

    return li;
  },

  _selectDept(deptId, liEl) {
    document.querySelectorAll('.tree-item').forEach(el => el.classList.remove('selected'));
    document.getElementById('noDeptItem')?.classList.remove('selected');
    liEl?.classList.add('selected');

    this.selectedDeptId = deptId;
    this.memberPage = 1;
    this.memberSelected.clear();
    this._updateActionButtons();
    this.loadDeptDetail(deptId);
    this.loadMembers();
  },

  _selectNoDept() {
    document.querySelectorAll('.tree-item').forEach(el => el.classList.remove('selected'));
    document.getElementById('noDeptItem')?.classList.add('selected');

    this.selectedDeptId = 'none';
    this.memberPage = 1;
    this.memberSelected.clear();
    this._updateActionButtons();
    this._clearDeptDetail();
    this.loadMembers();
  },

  // ── 부서명 검색 ───────────────────────────────────────────

  _bindSearch() {
    const input = document.getElementById('orgSearchInput');
    const btnClear = document.getElementById('btnClearOrgSearch');

    input.addEventListener('input', () => {
      const q = input.value.trim().toLowerCase();
      btnClear.style.display = q ? 'block' : 'none';
      document.querySelectorAll('.tree-item').forEach(li => {
        const name = li.querySelector('span')?.textContent.toLowerCase() ?? '';
        li.style.display = (!q || name.includes(q)) ? '' : 'none';
      });
    });
    btnClear.addEventListener('click', () => {
      input.value = '';
      btnClear.style.display = 'none';
      document.querySelectorAll('.tree-item').forEach(li => li.style.display = '');
    });

    document.getElementById('noDeptItem')?.addEventListener('click', () => this._selectNoDept());
  },

  // ── 부서 추가 인라인 ─────────────────────────────────────

  _openAddDeptInline(targetUl, companyId) {
    if (document.getElementById('inlineAddDept')) return;

    const li = document.createElement('li');
    li.id = 'inlineAddDept';
    li.className = 'tree-item';
    li.innerHTML = `
      <input type="text" id="newDeptNameInput" placeholder="부서명 입력 후 Enter"
        style="flex:1; padding:4px 8px; border:1px solid #3b82f6; border-radius:4px; font-size:13px; outline:none;">
      <button class="item-action-btn" id="btnCancelAddDept" title="취소">✕</button>`;
    targetUl.appendChild(li);

    const nameInput = document.getElementById('newDeptNameInput');
    nameInput.focus();
    nameInput.addEventListener('keydown', async e => {
      if (e.key === 'Enter') await this._submitAddDept(nameInput.value.trim(), companyId);
      if (e.key === 'Escape') li.remove();
    });
    document.getElementById('btnCancelAddDept').addEventListener('click', () => li.remove());
  },

  async _submitAddDept(name, companyId) {
    if (!name) return;
    const codeInput = prompt('부서 코드를 입력하세요:');
    if (!codeInput) return;

    const data = await this._api('POST', '/api/admin/departments/', { name, code: codeInput, company: companyId });
    document.getElementById('inlineAddDept')?.remove();
    if (data?.id) {
      this._showToast('부서가 추가되었습니다.');
      await this.loadTree();
    } else {
      this._showToast(data?.name?.[0] || data?.code?.[0] || '부서 추가 실패', true);
    }
  },

  // ── 부서 수정 인라인 ──────────────────────────────────────

  _openEditDeptInline(li, dept) {
    const span = li.querySelector('span');
    const original = span.textContent;
    span.innerHTML = `<input type="text" value="${original}"
      style="padding:2px 6px; border:1px solid #3b82f6; border-radius:3px; font-size:13px; outline:none; width:140px;">`;
    const input = span.querySelector('input');
    input.focus();
    input.select();

    input.addEventListener('keydown', async e => {
      if (e.key === 'Enter') {
        const newName = input.value.trim();
        if (!newName || newName === original) { span.textContent = original; return; }
        await this._submitEditDept(dept.id, newName, span, original);
      }
      if (e.key === 'Escape') span.textContent = original;
    });
    input.addEventListener('blur', () => {
      if (span.querySelector('input')) span.textContent = original;
    });
  },

  async _submitEditDept(id, name, span, original) {
    const data = await this._api('PATCH', `/api/admin/departments/${id}/`, { name });
    if (data?.id) {
      span.textContent = name;
      this._showToast('부서명이 수정되었습니다.');
      if (this.selectedDeptId === id) this.loadDeptDetail(id);
    } else {
      span.textContent = original;
      this._showToast('수정 실패', true);
    }
  },

  // ── 부서 삭제 확인 ────────────────────────────────────────

  _confirmDeleteDept(id, name) {
    this._showConfirm(
      `"${name}" 부서를 삭제하시겠습니까?`,
      async () => {
        await this._api('DELETE', `/api/admin/departments/${id}/`);
        this._showToast('부서가 삭제되었습니다.');
        if (this.selectedDeptId === id) {
          this.selectedDeptId = null;
          this._clearDeptDetail();
          this._clearMembers();
        }
        await this.loadTree();
      }
    );
  },

  // ═══════════════════════════════════════════════════════════
  // 2. 부서 정보 카드
  // ═══════════════════════════════════════════════════════════

  async loadDeptDetail(deptId) {
    const data = await this._api('GET', `/api/admin/departments/${deptId}/`);
    document.getElementById('deptName').textContent     = data.name ?? '-';
    document.getElementById('deptCode').textContent     = data.code ?? '-';
    document.getElementById('deptCreatedAt').textContent  = data.created_at ? data.created_at.slice(0, 10) : '-';
    document.getElementById('deptUpdatedAt').textContent  = data.updated_at ? data.updated_at.slice(0, 16).replace('T', ' ') : '-';
    document.getElementById('deptUpdatedBy').textContent  = data.updated_by_name ?? '-';
  },

  _clearDeptDetail() {
    ['deptName', 'deptCode', 'deptCreatedAt', 'deptUpdatedAt', 'deptUpdatedBy']
      .forEach(id => { document.getElementById(id).textContent = '-'; });
  },

  // ═══════════════════════════════════════════════════════════
  // 3. 구성원 목록
  // ═══════════════════════════════════════════════════════════

  async loadMembers() {
    if (!this.selectedDeptId) return;

    const params = new URLSearchParams({
      page: this.memberPage,
      page_size: this.memberPageSize,
      ...(this.memberQ && { q: this.memberQ }),
    });

    const data = await this._api(
      'GET', `/api/admin/departments/${this.selectedDeptId}/members/?${params}`
    );
    this.memberTotal = data.total;
    this._renderMemberTable(data.results);
    this._renderPagination(data.total, data.page, data.page_size);
    document.getElementById('selectedCount').textContent = '0';
    this.memberSelected.clear();
    this._updateActionButtons();
  },

  _renderMemberTable(members) {
    const tbody = document.getElementById('memberTableBody');
    if (!members.length) {
      tbody.innerHTML = `<tr><td colspan="5" style="color:#94a3b8; padding:32px 0;">구성원이 없습니다.</td></tr>`;
      return;
    }
    tbody.innerHTML = members.map(m => `
      <tr>
        <td><input type="checkbox" class="member-check" data-id="${m.id}"></td>
        <td>
          ${m.name}
          ${m.is_leader ? '<span class="badge badge-green" style="margin-left:4px;">조직장</span>' : ''}
        </td>
        <td>${m.username}</td>
        <td>${m.position ?? '-'}</td>
        <td><span class="badge ${this.STATUS_BADGE[m.status] ?? 'badge-gray'}">${this.STATUS_LABEL[m.status] ?? '-'}</span></td>
      </tr>`).join('');

    tbody.querySelectorAll('.member-check').forEach(cb => {
      cb.addEventListener('change', () => {
        const id = Number(cb.dataset.id);
        cb.checked ? this.memberSelected.add(id) : this.memberSelected.delete(id);
        document.getElementById('selectedCount').textContent = this.memberSelected.size;
        this._updateActionButtons();
      });
    });
  },

  _clearMembers() {
    document.getElementById('memberTableBody').innerHTML =
      `<tr><td colspan="5" style="color:#94a3b8; padding:32px 0;">부서를 선택하면 구성원 목록이 표시됩니다.</td></tr>`;
    document.getElementById('memberPagination').innerHTML = '';
    document.getElementById('selectedCount').textContent = '0';
  },

  _renderPagination(total, page, pageSize) {
    const totalPages = Math.ceil(total / pageSize);
    const nav = document.getElementById('memberPagination');
    nav.innerHTML = '';

    const addBtn = (label, targetPage, disabled = false) => {
      const btn = document.createElement('button');
      btn.textContent = label;
      if (targetPage === page) btn.classList.add('active');
      btn.disabled = disabled;
      btn.addEventListener('click', () => { this.memberPage = targetPage; this.loadMembers(); });
      nav.appendChild(btn);
    };

    addBtn('<', page - 1, page === 1);
    for (let p = 1; p <= totalPages; p++) addBtn(p, p);
    addBtn('>', page + 1, page === totalPages);
  },

  // ── 구성원 검색 ───────────────────────────────────────────

  _bindMemberSearch() {
    const input = document.getElementById('memberSearchInput');
    const btnClear = document.getElementById('btnClearMemberSearch');
    let debounceTimer = null;

    input.addEventListener('input', () => {
      this.memberQ = input.value.trim();
      btnClear.style.display = this.memberQ ? 'block' : 'none';
      this.memberPage = 1;
      if (!this.selectedDeptId) return;
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => this.loadMembers(), 300);
    });
    btnClear.addEventListener('click', () => {
      input.value = '';
      this.memberQ = '';
      this.memberPage = 1;
      btnClear.style.display = 'none';
      clearTimeout(debounceTimer);
      if (this.selectedDeptId) this.loadMembers();
    });
  },

  // ── 전체 선택 체크박스 ────────────────────────────────────

  _bindCheckboxes() {
    document.getElementById('checkAllMembers').addEventListener('change', e => {
      const checked = e.target.checked;
      document.querySelectorAll('.member-check').forEach(cb => {
        cb.checked = checked;
        const id = Number(cb.dataset.id);
        checked ? this.memberSelected.add(id) : this.memberSelected.delete(id);
      });
      document.getElementById('selectedCount').textContent = this.memberSelected.size;
      this._updateActionButtons();
    });
  },

  // ── 액션 버튼 활성화 ──────────────────────────────────────

  _updateActionButtons() {
    const count = this.memberSelected.size;
    const isNoDept = this.selectedDeptId === 'none';

    document.getElementById('btnMoveDept').disabled    = count === 0;
    document.getElementById('btnRemoveMember').disabled = count === 0;
    // 조직장 임명: 단일 선택 + 실제 부서(조직없음 제외)
    document.getElementById('btnAssignLeader').disabled = count !== 1 || isNoDept;
  },

  // ═══════════════════════════════════════════════════════════
  // 4. 액션 버튼
  // ═══════════════════════════════════════════════════════════

  _bindActionButtons() {
    document.getElementById('btnAddMember').addEventListener('click', () => this._openAddMemberPopup());
    document.getElementById('btnMoveDept').addEventListener('click', () => this._openMoveDeptPopup());
    document.getElementById('btnRemoveMember').addEventListener('click', () => this._openRemoveConfirm());
    document.getElementById('btnAssignLeader').addEventListener('click', () => this._openAssignLeaderConfirm());
  },

  // ═══════════════════════════════════════════════════════════
  // 5. 구성원 추가 팝업
  // ═══════════════════════════════════════════════════════════

  _openAddMemberPopup() {
    if (!this.selectedDeptId || this.selectedDeptId === 'none') {
      this._showToast('부서를 먼저 선택하세요.', true);
      return;
    }
    const popup = this._createPopupBase('구성원 추가', 'addMemberPopup');
    popup.innerHTML += `
      <div style="display:flex; gap:12px; height:400px;">
        <!-- 조직 트리 -->
        <div style="width:220px; flex-shrink:0; border:1px solid #e2e8f0; border-radius:6px; overflow-y:auto; padding:12px;">
          <div style="font-size:12px; font-weight:600; color:#64748b; margin-bottom:8px;">조직 선택</div>
          <div id="addPopupTree"></div>
        </div>
        <!-- 구성원 목록 -->
        <div style="flex:1; border:1px solid #e2e8f0; border-radius:6px; overflow-y:auto;">
          <div style="font-size:12px; font-weight:600; color:#64748b; padding:12px 12px 4px;">구성원 목록</div>
          <div id="addPopupMemberList" style="padding:0 12px 12px;"></div>
        </div>
        <!-- 선택된 구성원 -->
        <div style="width:200px; flex-shrink:0; border:1px solid #e2e8f0; border-radius:6px; padding:12px; display:flex; flex-direction:column; gap:8px;">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <span style="font-size:12px; font-weight:600; color:#64748b;">선택된 구성원</span>
            <button id="btnClearAddSelection" style="font-size:11px; color:#94a3b8; background:none; border:none; cursor:pointer;">모두 해제</button>
          </div>
          <div id="addPopupSelectedList" style="flex:1; overflow-y:auto;"></div>
        </div>
      </div>
      <div style="margin-top:12px;">
        <label style="display:flex; align-items:center; gap:6px; font-size:13px; cursor:pointer;">
          <input type="checkbox" id="keepPreviousAdd"> 이전 소속 부서 유지 (겸직)
        </label>
      </div>
      <div style="display:flex; justify-content:flex-end; gap:8px; margin-top:16px;">
        <button class="btn btn-outline popup-cancel">취소</button>
        <button class="btn btn-primary" id="btnConfirmAdd">확인</button>
      </div>`;

    this._bindPopupCancel(popup);

    const selectedUsers = new Map(); // id → {id, name, username}

    const renderSelected = () => {
      const list = document.getElementById('addPopupSelectedList');
      list.innerHTML = [...selectedUsers.values()].map(u => `
        <div style="display:flex; align-items:center; gap:6px; padding:4px 0; font-size:13px;">
          <button data-id="${u.id}" class="btn-remove-selected"
            style="background:none;border:none;color:#94a3b8;cursor:pointer;font-size:12px;">✕</button>
          <span>${u.name}</span>
        </div>`).join('');
      list.querySelectorAll('.btn-remove-selected').forEach(btn => {
        btn.addEventListener('click', () => {
          const id = Number(btn.dataset.id);
          selectedUsers.delete(id);
          // 체크박스 해제
          const cb = document.querySelector(`#addPopupMemberList input[data-id="${id}"]`);
          if (cb) cb.checked = false;
          renderSelected();
        });
      });
    };

    const loadAddPopupMembers = async deptId => {
      const url = `/api/admin/departments/${deptId}/members/?page_size=100`;
      const data = await this._api('GET', url);
      const list = document.getElementById('addPopupMemberList');
      // 이미 해당 부서 소속이면 선택 불가
      const currentDeptId = this.selectedDeptId;
      list.innerHTML = data.results.map(m => {
        const isCurrentDept = String(deptId) === String(currentDeptId);
        return `<div style="display:flex; align-items:center; gap:6px; padding:5px 0; font-size:13px;">
          <input type="checkbox" data-id="${m.id}" data-name="${m.name}" ${isCurrentDept ? 'disabled' : ''}>
          <span style="${isCurrentDept ? 'color:#94a3b8;' : ''}">${m.name} <span style="color:#94a3b8;">(${m.username})</span></span>
        </div>`;
      }).join('') || '<div style="color:#94a3b8; font-size:12px;">구성원 없음</div>';

      list.querySelectorAll('input[type=checkbox]:not(:disabled)').forEach(cb => {
        if (selectedUsers.has(Number(cb.dataset.id))) cb.checked = true;
        cb.addEventListener('change', () => {
          const id = Number(cb.dataset.id);
          if (cb.checked) {
            selectedUsers.set(id, { id, name: cb.dataset.name });
          } else {
            selectedUsers.delete(id);
          }
          renderSelected();
        });
      });
    };

    // 조직 트리 로드
    this._api('GET', '/api/admin/organizations/tree/').then(data => {
      const tree = document.getElementById('addPopupTree');
      data.companies.forEach(company => {
        const companyEl = document.createElement('div');
        companyEl.style.cssText = 'font-size:13px; font-weight:600; padding:4px 0; cursor:pointer;';
        companyEl.textContent = company.name;
        companyEl.addEventListener('click', async () => {
          // 회사 클릭 시 첫 번째 부서 구성원 표시
          if (company.departments[0]) await loadAddPopupMembers(company.departments[0].id);
        });
        tree.appendChild(companyEl);

        company.departments.forEach(dept => {
          const deptEl = document.createElement('div');
          deptEl.style.cssText = 'font-size:12px; padding:3px 0 3px 12px; cursor:pointer; color:#475569;';
          deptEl.textContent = dept.name;
          deptEl.addEventListener('click', () => loadAddPopupMembers(dept.id));
          tree.appendChild(deptEl);
        });
      });
    });

    document.getElementById('btnClearAddSelection').addEventListener('click', () => {
      selectedUsers.clear();
      document.querySelectorAll('#addPopupMemberList input[type=checkbox]').forEach(cb => cb.checked = false);
      renderSelected();
    });

    document.getElementById('btnConfirmAdd').addEventListener('click', async () => {
      if (!selectedUsers.size) { this._showToast('구성원을 선택하세요.', true); return; }
      this._showConfirm(`${selectedUsers.size}명을 추가하시겠습니까?`, async () => {
        popup.parentElement?.remove();
        const keepPrevious = document.getElementById('keepPreviousAdd')?.checked ?? false;
        const res = await this._api('POST', `/api/admin/departments/${this.selectedDeptId}/members/add/`, {
          user_ids: [...selectedUsers.keys()],
          keep_previous: keepPrevious,
        });
        if (res?.ok) {
          this._showToast('구성원이 추가되었습니다.');
          this.loadMembers();
        } else {
          this._showToast('추가 실패', true);
        }
      });
    });
  },

  // ═══════════════════════════════════════════════════════════
  // 6. 부서 이동 팝업
  // ═══════════════════════════════════════════════════════════

  _openMoveDeptPopup() {
    const popup = this._createPopupBase('부서 이동', 'moveDeptPopup');
    popup.innerHTML += `
      <div style="display:flex; gap:12px; height:360px;">
        <!-- 조직 트리 -->
        <div style="flex:1; border:1px solid #e2e8f0; border-radius:6px; overflow-y:auto; padding:12px;">
          <div style="font-size:12px; font-weight:600; color:#64748b; margin-bottom:8px;">이동할 부서 선택</div>
          <div id="movePopupTree"></div>
        </div>
        <!-- 선택 부서 -->
        <div style="width:200px; flex-shrink:0; border:1px solid #e2e8f0; border-radius:6px; padding:12px; display:flex; flex-direction:column; gap:8px;">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <span style="font-size:12px; font-weight:600; color:#64748b;">선택 부서</span>
            <button id="btnClearMoveSelection" style="font-size:11px; color:#94a3b8; background:none; border:none; cursor:pointer;">모두 해제</button>
          </div>
          <div id="movePopupSelectedList" style="flex:1; overflow-y:auto;"></div>
        </div>
      </div>
      <div style="margin-top:12px;">
        <label style="display:flex; align-items:center; gap:6px; font-size:13px; cursor:pointer;">
          <input type="checkbox" id="keepPreviousMove"> 이전 소속 부서 유지 (겸직)
        </label>
      </div>
      <div style="display:flex; justify-content:flex-end; gap:8px; margin-top:16px;">
        <button class="btn btn-outline popup-cancel">취소</button>
        <button class="btn btn-primary" id="btnConfirmMove" disabled>확인</button>
      </div>`;

    this._bindPopupCancel(popup);

    const selectedDepts = new Map();
    const deptElMap = new Map(); // dept.id → deptEl (하이라이트 토글용)

    const setDeptHighlight = (deptId, on) => {
      const el = deptElMap.get(deptId);
      if (!el) return;
      el.style.background = on ? '#eff6ff' : '';
      el.style.color     = on ? '#2563eb' : '#475569';
    };

    const renderSelectedDepts = () => {
      const list = document.getElementById('movePopupSelectedList');
      list.innerHTML = [...selectedDepts.values()].map(d => `
        <div style="display:flex; align-items:center; gap:6px; padding:4px 0; font-size:13px;">
          <button data-id="${d.id}" class="btn-remove-dept-sel"
            style="background:none;border:none;color:#94a3b8;cursor:pointer;font-size:12px;">✕</button>
          <span>${d.name}</span>
        </div>`).join('');
      list.querySelectorAll('.btn-remove-dept-sel').forEach(btn => {
        btn.addEventListener('click', () => {
          const id = Number(btn.dataset.id);
          selectedDepts.delete(id);
          setDeptHighlight(id, false);
          renderSelectedDepts();
          document.getElementById('btnConfirmMove').disabled = selectedDepts.size === 0;
        });
      });
    };

    // 트리 로드
    this._api('GET', '/api/admin/organizations/tree/').then(data => {
      const tree = document.getElementById('movePopupTree');
      data.companies.forEach(company => {
        const compEl = document.createElement('div');
        compEl.style.cssText = 'font-size:13px; font-weight:600; padding:4px 0; color:#1e293b;';
        compEl.textContent = company.name;
        tree.appendChild(compEl);

        company.departments.forEach(dept => {
          const isCurrentDept = String(dept.id) === String(this.selectedDeptId);
          const deptEl = document.createElement('div');
          deptEl.style.cssText = `font-size:12px; padding:4px 0 4px 12px; border-radius:4px; cursor:${isCurrentDept ? 'not-allowed' : 'pointer'}; color:${isCurrentDept ? '#94a3b8' : '#475569'};`;
          deptEl.textContent = dept.name + (isCurrentDept ? ' (현재 부서)' : '');
          deptElMap.set(dept.id, deptEl);

          if (!isCurrentDept) {
            deptEl.addEventListener('click', () => {
              if (selectedDepts.has(dept.id)) {
                selectedDepts.delete(dept.id);
                setDeptHighlight(dept.id, false);
              } else {
                selectedDepts.set(dept.id, { id: dept.id, name: dept.name });
                setDeptHighlight(dept.id, true);
              }
              renderSelectedDepts();
              document.getElementById('btnConfirmMove').disabled = selectedDepts.size === 0;
            });
          }
          tree.appendChild(deptEl);
        });
      });
    });

    document.getElementById('btnClearMoveSelection').addEventListener('click', () => {
      [...selectedDepts.keys()].forEach(id => setDeptHighlight(id, false));
      selectedDepts.clear();
      renderSelectedDepts();
      document.getElementById('btnConfirmMove').disabled = true;
    });

    document.getElementById('btnConfirmMove').addEventListener('click', async () => {
      const targetId = [...selectedDepts.keys()][0];
      if (!targetId) return;
      const count = this.memberSelected.size;
      if (!count) { this._showToast('이동할 구성원을 선택하세요.', true); return; }
      this._showConfirm(`${count}명을 선택한 부서로 이동하시겠습니까?`, async () => {
        popup.parentElement?.remove();
        const keepPrevious = document.getElementById('keepPreviousMove')?.checked ?? false;
        const res = await this._api('POST', `/api/admin/departments/${this.selectedDeptId}/members/move/`, {
          user_ids: [...this.memberSelected],
          target_dept_id: targetId,
          keep_previous: keepPrevious,
        });
        if (res?.ok) {
          this._showToast('부서 이동이 완료되었습니다.');
          this.memberSelected.clear();
          this.loadMembers();
        } else {
          this._showToast('이동 실패', true);
        }
      });
    });
  },

  // ═══════════════════════════════════════════════════════════
  // 7. 소속 제외 확인 팝업
  // ═══════════════════════════════════════════════════════════

  _openRemoveConfirm() {
    const count = this.memberSelected.size;
    this._showConfirm(
      `선택한 ${count}명의 사용자를 소속에서 제외하시겠습니까?`,
      async () => {
        const res = await this._api('POST', `/api/admin/departments/${this.selectedDeptId}/members/remove/`, {
          user_ids: [...this.memberSelected],
        });
        if (res?.ok) {
          this._showToast('제외되었습니다.');
          this.memberSelected.clear();
          this.loadMembers();
          this.loadTree();
        } else {
          this._showToast('제외 실패', true);
        }
      }
    );
  },

  // ═══════════════════════════════════════════════════════════
  // 8. 조직장 임명 재확인 팝업
  // ═══════════════════════════════════════════════════════════

  _openAssignLeaderConfirm() {
    const userId = [...this.memberSelected][0];
    this._showConfirm(
      '선택한 구성원을 조직장으로 임명하시겠습니까?',
      async () => {
        const res = await this._api('POST', `/api/admin/departments/${this.selectedDeptId}/members/assign-leader/`, {
          user_id: userId,
        });
        if (res?.ok) {
          this._showToast(`${res.leader.name}님이 조직장으로 임명되었습니다.`);
          this.memberSelected.clear();
          this.loadMembers();
          this.loadDeptDetail(this.selectedDeptId);
        } else {
          this._showToast('임명 실패', true);
        }
      }
    );
  },

  // ═══════════════════════════════════════════════════════════
  // 공통 팝업 유틸
  // ═══════════════════════════════════════════════════════════

  _createPopupBase(title, id) {
    const overlay = document.createElement('div');
    overlay.id = id;
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:9999;display:flex;align-items:center;justify-content:center;';
    const box = document.createElement('div');
    box.style.cssText = 'background:#fff;border-radius:8px;padding:24px;min-width:560px;max-width:92vw;max-height:90vh;overflow-y:auto;box-shadow:0 8px 32px rgba(0,0,0,0.15);';
    box.innerHTML = `<h3 style="font-size:16px;font-weight:700;margin:0 0 16px;color:#1e293b;">${title}</h3>`;
    overlay.appendChild(box);
    document.body.appendChild(overlay);
    return box;
  },

  _bindPopupCancel(popupBox) {
    popupBox.parentElement?.querySelectorAll('.popup-cancel').forEach(btn => {
      btn.addEventListener('click', () => popupBox.parentElement?.remove());
    });
  },

  _showConfirm(message, onConfirm) {
    const overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:10000;display:flex;align-items:center;justify-content:center;';
    overlay.innerHTML = `
      <div style="background:#fff;border-radius:8px;padding:28px 24px;width:380px;text-align:center;box-shadow:0 8px 32px rgba(0,0,0,0.15);">
        <p style="font-size:14px;color:#1e293b;margin:0 0 20px;line-height:1.6;">${message}</p>
        <div style="display:flex;justify-content:center;gap:8px;">
          <button id="confirmCancel" class="btn btn-outline">취소</button>
          <button id="confirmOk" class="btn btn-primary">확인</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);
    overlay.querySelector('#confirmCancel').addEventListener('click', () => overlay.remove());
    overlay.querySelector('#confirmOk').addEventListener('click', async () => {
      overlay.remove();
      await onConfirm();
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
};

document.addEventListener('DOMContentLoaded', () => Org.init());
