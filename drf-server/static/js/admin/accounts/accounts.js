/* admin/accounts/accounts.js — 사용자 관리 페이지
 *
 * 역할: /admin-panel/accounts-management/ 페이지의 동작 전담.
 * - 사용자 목록 fetch (필터·정렬·페이지네이션 포함)
 * - 행 선택 → 일괄 삭제 / 계정 잠금 / 잠금 해제
 * - 수정 버튼 → 수정 모달 (추후 구현 예정)
 *
 * API 엔드포인트:
 *   GET    /api/admin/accounts/           목록 조회
 *   POST   /api/admin/accounts/           신규 등록
 *   PATCH  /api/admin/accounts/<id>/      정보 수정
 *   DELETE /api/admin/accounts/<id>/      비활성화
 *   POST   /api/admin/accounts/<id>/lock/ 잠금 / 잠금 해제
 *
 * facility 처리 비대칭 (의도된 동작):
 *   - 등록 모달: 빈 값이면 키 자체를 생략 → serializer의 allow_null로 NULL 처리
 *   - 수정 모달: 빈 값을 null로 명시 전송 → PATCH partial에서 기존 facility 비우기
 *   각 _submit*Form 내부 주석 참조.
 */
'use strict';

const AccountsAdmin = {
  page: 1,
  pageSize: 10,
  total: 0,
  filters: { name: '', department: '', position: '', user_type: '', status: '' },
  sort: 'name_asc',
  selected: new Set(),   // 선택된 사용자 id 집합

  USER_TYPE_LABEL: {
    super_admin: '슈퍼관리자',
    facility_admin: '관리자',
    worker: '일반사용자',
    viewer: '열람자',
  },
  USER_TYPE_BADGE: {
    super_admin: 'badge-red',
    facility_admin: 'badge-purple',
    worker: 'badge-gray',
    viewer: 'badge-blue',
  },
  STATUS_LABEL: { active: '사용', locked: '잠금', inactive: '비활성' },
  STATUS_BADGE: { active: 'badge-green', locked: 'badge-orange', inactive: 'badge-gray' },

  // ── 접근 권한 없음 팝업 ───────────────────────────────────

  _showAccessDenied() {
    const existing = document.getElementById('accessDeniedModal');
    if (existing) { existing.style.display = 'flex'; return; }

    const el = document.createElement('div');
    el.id = 'accessDeniedModal';
    el.className = 'modal-overlay';
    el.innerHTML = `
      <div class="modal-container" style="width:400px; text-align:center;">
        <div class="modal-body" style="padding:32px 24px; gap:12px;">
          <div style="font-size:36px;">🔒</div>
          <h3 style="font-size:16px; color:#c9d1d9; margin:0;">접근 권한이 없습니다</h3>
          <p style="font-size:13px; color:#6e7681; margin:0;">
            이 페이지는 슈퍼관리자만 접근할 수 있습니다.
          </p>
          <button class="btn-primary" id="btnAccessDeniedConfirm"
            style="margin-top:8px; width:100%;">대시보드로 이동</button>
        </div>
      </div>`;
    document.body.appendChild(el);
    document.getElementById('btnAccessDeniedConfirm').addEventListener('click', () => {
      window.location.href = '/dashboard/';
    });
  },

  // ── 초기화 ────────────────────────────────────────────────

  async init() {
    this._bindEvents();
    this._bindCreateModal();
    this._bindEditModal();
    await this.fetchList();
  },

  // ── 이벤트 바인딩 ─────────────────────────────────────────

  _bindEvents() {
    document.getElementById('btnSearch').addEventListener('click', () => {
      this._readFilters();
      this.page = 1;
      this.fetchList();
    });

    document.getElementById('btnReset').addEventListener('click', () => {
      document.getElementById('filterName').value = '';
      document.getElementById('filterDepartment').value = '';
      document.getElementById('filterPosition').value = '';
      document.getElementById('filterUserType').value = '';
      document.getElementById('filterStatus').value = '';
      this.filters = { name: '', department: '', position: '', user_type: '', status: '' };
      this.page = 1;
      this.fetchList();
    });

    document.getElementById('sortSelect').addEventListener('change', (e) => {
      this.sort = e.target.value;
      this.page = 1;
      this.fetchList();
    });

    // 전체 선택 체크박스
    document.getElementById('checkAll').addEventListener('change', (e) => {
      document.querySelectorAll('.row-check').forEach(cb => {
        cb.checked = e.target.checked;
        const id = parseInt(cb.dataset.id);
        e.target.checked ? this.selected.add(id) : this.selected.delete(id);
      });
      this._updateBulkButtons();
    });

    document.getElementById('btnDelete').addEventListener('click', () => this._deleteSelected());
    document.getElementById('btnLock').addEventListener('click', () => this._lockSelected('lock'));
    document.getElementById('btnUnlock').addEventListener('click', () => this._lockSelected('unlock'));
    document.getElementById('btnAddUser').addEventListener('click', () => this._openCreateModal());
  },

  // ── 필터값 읽기 ───────────────────────────────────────────

  _readFilters() {
    this.filters = {
      name: document.getElementById('filterName').value.trim(),
      department: document.getElementById('filterDepartment').value,
      position: document.getElementById('filterPosition').value,
      user_type: document.getElementById('filterUserType').value,
      status: document.getElementById('filterStatus').value,
    };
  },

  // ── 목록 fetch ────────────────────────────────────────────

  async fetchList() {
    try {
      const params = new URLSearchParams({ page: this.page, page_size: this.pageSize, sort: this.sort });
      if (this.filters.name)       params.append('name', this.filters.name);
      if (this.filters.department) params.append('department', this.filters.department);
      if (this.filters.position)   params.append('position', this.filters.position);
      if (this.filters.user_type)  params.append('user_type', this.filters.user_type);
      if (this.filters.status)     params.append('status', this.filters.status);

      const res = await Auth.apiFetch(`/api/admin/accounts/?${params}`);

      if (res.status === 403) { this._showAccessDenied(); return; }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const data = await res.json();
      this.total = data.total;
      this._renderTable(data.results);
      this._renderPagination();
      document.getElementById('totalCount').textContent = this.total;
    } catch (e) {
      console.error('[AccountsAdmin] 목록 로드 실패:', e);
      document.getElementById('accountsTableBody').innerHTML =
        `<tr><td colspan="12" class="empty-state">데이터를 불러오지 못했습니다.</td></tr>`;
    }
  },

  // ── 전화번호 포맷 ─────────────────────────────────────────

  _formatPhone(phone) {
    if (!phone) return '-';
    const digits = phone.replace(/\D/g, '');
    if (digits.length === 11) return digits.replace(/(\d{3})(\d{4})(\d{4})/, '$1-$2-$3');
    if (digits.length === 10) return digits.replace(/(\d{3})(\d{3})(\d{4})/, '$1-$2-$3');
    return phone;
  },

  // ── 테이블 렌더링 ─────────────────────────────────────────

  _renderTable(items) {
    const tbody = document.getElementById('accountsTableBody');
    if (!items.length) {
      tbody.innerHTML = `<tr><td colspan="12" class="empty-state">검색 결과가 없습니다.</td></tr>`;
      return;
    }

    tbody.innerHTML = items.map(u => `
      <tr>
        <td><input type="checkbox" class="row-check" data-id="${u.id}" ${this.selected.has(u.id) ? 'checked' : ''}></td>
        <td>${u.name || '-'}</td>
        <td>${u.department || '-'}</td>
        <td>${u.facility_name || '-'}</td>
        <td>${u.position || '-'}</td>
        <td>${u.username}</td>
        <td><span class="badge ${this.USER_TYPE_BADGE[u.user_type] || 'badge-gray'}">${this.USER_TYPE_LABEL[u.user_type] || u.user_type}</span></td>
        <td><span class="badge ${this.STATUS_BADGE[u.status] || 'badge-gray'}">${this.STATUS_LABEL[u.status] || u.status}</span></td>
        <td>${this._formatPhone(u.phone)}</td>
        <td>${u.last_login_at || '-'}</td>
        <td>${u.date_joined ? u.date_joined.slice(0, 10) : '-'}</td>
        <td><button class="btn-sm" onclick="AccountsAdmin._openEditModal(${u.id})">수정</button></td>
      </tr>
    `).join('');

    // 행 체크박스 이벤트 등록
    tbody.querySelectorAll('.row-check').forEach(cb => {
      cb.addEventListener('change', (e) => {
        const id = parseInt(e.target.dataset.id);
        e.target.checked ? this.selected.add(id) : this.selected.delete(id);
        this._updateBulkButtons();
      });
    });
  },

  // ── 페이지네이션 렌더링 ────────────────────────────────────

  _renderPagination() {
    const totalPages = Math.ceil(this.total / this.pageSize) || 1;
    const el = document.getElementById('pagination');

    const prevDisabled = this.page === 1 ? 'disabled' : '';
    const nextDisabled = this.page === totalPages ? 'disabled' : '';

    // 최대 5개 페이지 버튼 표시
    const startPage = Math.max(1, this.page - 2);
    const endPage = Math.min(totalPages, startPage + 4);

    const pageButtons = Array.from(
      { length: endPage - startPage + 1 },
      (_, i) => startPage + i
    ).map(p => `
      <button class="${p === this.page ? 'active' : ''}" onclick="AccountsAdmin._goPage(${p})">${p}</button>
    `).join('');

    el.innerHTML = `
      <button onclick="AccountsAdmin._goPage(${this.page - 1})" ${prevDisabled}>&lt;</button>
      ${pageButtons}
      <button onclick="AccountsAdmin._goPage(${this.page + 1})" ${nextDisabled}>&gt;</button>
    `;

    const start = (this.page - 1) * this.pageSize + 1;
    const end = Math.min(this.page * this.pageSize, this.total);
    document.getElementById('pageInfo').textContent =
      this.total > 0 ? `${start} - ${end} / ${this.total}` : '0 - 0 / 0';
  },

  _goPage(page) {
    const totalPages = Math.ceil(this.total / this.pageSize) || 1;
    if (page < 1 || page > totalPages) return;
    this.page = page;
    this.fetchList();
  },

  // ── 일괄 작업 버튼 활성화 ─────────────────────────────────

  _updateBulkButtons() {
    const hasSelected = this.selected.size > 0;
    document.getElementById('btnDelete').disabled = !hasSelected;
    document.getElementById('btnLock').disabled = !hasSelected;
    document.getElementById('btnUnlock').disabled = !hasSelected;
  },

  // ── 일괄 삭제 (비활성화) ──────────────────────────────────

  async _deleteSelected() {
    if (!confirm(`선택한 ${this.selected.size}명의 사용자를 비활성화하시겠습니까?`)) return;
    try {
      await Promise.all([...this.selected].map(id =>
        Auth.apiFetch(`/api/admin/accounts/${id}/`, { method: 'DELETE' })
      ));
      this.selected.clear();
      this._updateBulkButtons();
      await this.fetchList();
    } catch (e) {
      alert('비활성화에 실패했습니다.');
    }
  },

  // ── 일괄 잠금 / 잠금 해제 ────────────────────────────────

  async _lockSelected(action) {
    const label = action === 'lock' ? '잠금' : '잠금 해제';
    if (!confirm(`선택한 ${this.selected.size}명의 계정을 ${label} 처리하시겠습니까?`)) return;
    try {
      await Promise.all([...this.selected].map(id =>
        Auth.apiFetch(`/api/admin/accounts/${id}/${action}/`, { method: 'POST' })
      ));
      this.selected.clear();
      this._updateBulkButtons();
      await this.fetchList();
    } catch (e) {
      alert(`계정 ${label}에 실패했습니다.`);
    }
  },

  // ── 사용자 등록 모달 ──────────────────────────────────────

  _openCreateModal() {
    this._resetCreateForm();
    document.getElementById('createUserModal').style.display = 'flex';
  },

  _closeCreateModal() {
    document.getElementById('createUserModal').style.display = 'none';
  },

  _bindCreateModal() {
    document.getElementById('btnCreateClose').addEventListener('click', () => this._closeCreateModal());
    document.getElementById('btnCreateCancel').addEventListener('click', () => this._closeCreateModal());
    document.getElementById('btnCreateSubmit').addEventListener('click', () => this._submitCreateForm());
  },

  _resetCreateForm() {
    ['createName', 'createUsername', 'createPassword', 'createPasswordConfirm', 'createEmail', 'createPhone'].forEach(id => {
      document.getElementById(id).value = '';
    });
    ['createDepartment', 'createFacility', 'createUserType', 'createPosition', 'createStatus'].forEach(id => {
      document.getElementById(id).value = '';
    });
    document.querySelectorAll('#createUserModal .field-error').forEach(el => {
      el.textContent = '';
      el.classList.remove('visible');
    });
    document.querySelectorAll('#createUserModal .is-error').forEach(el => {
      el.classList.remove('is-error');
    });
  },

  _validateCreateForm() {
    let valid = true;

    const setError = (fieldId, errId, msg) => {
      const field = document.getElementById(fieldId);
      const err = document.getElementById(errId);
      if (msg) {
        field.classList.add('is-error');
        err.textContent = msg;
        err.classList.add('visible');
        valid = false;
      } else {
        field.classList.remove('is-error');
        err.textContent = '';
        err.classList.remove('visible');
      }
    };

    // 사용자명
    const nameTrimmed = document.getElementById('createName').value.trim();
    if (!nameTrimmed) {
      setError('createName', 'errName', '사용자명을 입력해 주세요.');
    } else if (nameTrimmed.length < 2) {
      setError('createName', 'errName', '사용자명을 2자 이상 입력해 주세요.');
    } else if (nameTrimmed.length > 20) {
      setError('createName', 'errName', '사용자명은 20자 이하로 입력해 주세요.');
    } else if (!/^[가-힣a-zA-Z0-9]+$/.test(nameTrimmed)) {
      setError('createName', 'errName', '사용자명은 한글, 영문, 숫자만 입력할 수 있습니다.');
    } else {
      setError('createName', 'errName', null);
    }

    // 아이디
    const username = document.getElementById('createUsername').value;
    if (!username) {
      setError('createUsername', 'errUsername', '아이디를 입력해 주세요.');
    } else if (/\s/.test(username)) {
      setError('createUsername', 'errUsername', '아이디에는 공백을 입력할 수 없습니다.');
    } else if (!/^[a-zA-Z0-9]+$/.test(username)) {
      setError('createUsername', 'errUsername', '아이디는 영문 또는 숫자만 입력할 수 있습니다.');
    } else if (username.length < 4) {
      setError('createUsername', 'errUsername', '아이디를 4자 이상 입력해 주세요.');
    } else if (username.length > 20) {
      setError('createUsername', 'errUsername', '아이디는 20자 이하로 입력해 주세요.');
    } else {
      setError('createUsername', 'errUsername', null);
    }

    // 비밀번호
    const password = document.getElementById('createPassword').value;
    if (!password) {
      setError('createPassword', 'errPassword', '비밀번호를 입력해 주세요.');
    } else if (/\s/.test(password)) {
      setError('createPassword', 'errPassword', '비밀번호에는 공백을 입력할 수 없습니다.');
    } else if (password.length < 8) {
      setError('createPassword', 'errPassword', '비밀번호는 8자 이상 입력해 주세요.');
    } else if (password.length > 20) {
      setError('createPassword', 'errPassword', '비밀번호는 20자 이하로 입력해 주세요.');
    } else {
      const hasAlpha = /[a-zA-Z]/.test(password);
      const hasDigit = /[0-9]/.test(password);
      const hasSpecial = /[^a-zA-Z0-9]/.test(password);
      if ([hasAlpha, hasDigit, hasSpecial].filter(Boolean).length < 2) {
        setError('createPassword', 'errPassword', '비밀번호는 영문, 숫자, 특수문자 중 2가지 이상을 포함해 주세요.');
      } else {
        setError('createPassword', 'errPassword', null);
      }
    }

    // 비밀번호 확인
    const passwordConfirm = document.getElementById('createPasswordConfirm').value;
    if (!passwordConfirm) {
      setError('createPasswordConfirm', 'errPasswordConfirm', '비밀번호 확인을 입력해 주세요.');
    } else if (passwordConfirm !== password) {
      setError('createPasswordConfirm', 'errPasswordConfirm', '비밀번호가 일치하지 않습니다.');
    } else {
      setError('createPasswordConfirm', 'errPasswordConfirm', null);
    }

    // 소속
    const department = document.getElementById('createDepartment').value;
    if (!department) {
      setError('createDepartment', 'errDepartment', '소속을 선택해 주세요.');
    } else {
      setError('createDepartment', 'errDepartment', null);
    }

    // 권한
    const userType = document.getElementById('createUserType').value;
    if (!userType) {
      setError('createUserType', 'errUserType', '권한을 선택해 주세요.');
    } else {
      setError('createUserType', 'errUserType', null);
    }

    // 계정 상태
    const accountStatus = document.getElementById('createStatus').value;
    if (!accountStatus) {
      setError('createStatus', 'errStatus', '계정 상태를 선택해 주세요.');
    } else {
      setError('createStatus', 'errStatus', null);
    }

    // 이메일 (입력 시에만 형식 검증)
    const email = document.getElementById('createEmail').value.trim();
    if (email) {
      if (email.length > 100) {
        setError('createEmail', 'errEmail', '이메일은 100자 이하로 입력해 주세요.');
      } else if (!/^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/.test(email)) {
        setError('createEmail', 'errEmail', '이메일 형식이 올바르지 않습니다.');
      } else {
        setError('createEmail', 'errEmail', null);
      }
    } else {
      setError('createEmail', 'errEmail', null);
    }

    // 연락처 (입력 시에만 형식 검증)
    const phone = document.getElementById('createPhone').value.trim();
    if (phone) {
      if (/[^0-9\-]/.test(phone)) {
        setError('createPhone', 'errPhone', '연락처는 숫자만 입력할 수 있습니다.');
      } else {
        const digits = phone.replace(/-/g, '');
        if (digits.length !== 10 && digits.length !== 11) {
          setError('createPhone', 'errPhone', '연락처를 정확히 입력해 주세요.');
        } else if (!/^0\d{1,2}-?\d{3,4}-?\d{4}$/.test(phone)) {
          setError('createPhone', 'errPhone', '연락처 형식이 올바르지 않습니다.');
        } else {
          setError('createPhone', 'errPhone', null);
        }
      }
    } else {
      setError('createPhone', 'errPhone', null);
    }

    return valid;
  },

  async _submitCreateForm() {
    if (!this._validateCreateForm()) return;

    const payload = {
      name: document.getElementById('createName').value.trim(),
      username: document.getElementById('createUsername').value,
      password: document.getElementById('createPassword').value,
      department_id: parseInt(document.getElementById('createDepartment').value),
      user_type: document.getElementById('createUserType').value,
      status: document.getElementById('createStatus').value,
    };

    // facility는 선택 항목. 등록 시 빈 값이면 키 자체를 생략해 serializer의 allow_null=True가 NULL로 처리.
    const facility = document.getElementById('createFacility').value;
    if (facility) payload.facility_id = parseInt(facility);

    const position = document.getElementById('createPosition').value;
    if (position) payload.position = parseInt(position);

    const email = document.getElementById('createEmail').value.trim();
    if (email) payload.email = email;

    const phone = document.getElementById('createPhone').value.trim();
    if (phone) payload.phone = phone.replace(/-/g, '');

    const submitBtn = document.getElementById('btnCreateSubmit');
    submitBtn.disabled = true;

    try {
      const res = await Auth.apiFetch('/api/admin/accounts/', {
        method: 'POST',
        body: JSON.stringify(payload),
      });

      if (res.status === 201) {
        this._closeCreateModal();
        await this.fetchList();
        return;
      }

      if (res.status === 403) { this._showAccessDenied(); return; }

      if (res.status === 400) {
        const errors = await res.json();
        const errUsername = document.getElementById('errUsername');
        const errUsernameField = document.getElementById('createUsername');
        if (errors.username) {
          errUsernameField.classList.add('is-error');
          errUsername.textContent = Array.isArray(errors.username) ? errors.username[0] : errors.username;
          errUsername.classList.add('visible');
        }
        if (errors.password) {
          const errPw = document.getElementById('errPassword');
          const errPwField = document.getElementById('createPassword');
          errPwField.classList.add('is-error');
          errPw.textContent = Array.isArray(errors.password) ? errors.password[0] : errors.password;
          errPw.classList.add('visible');
        }
        return;
      }

      throw new Error(`HTTP ${res.status}`);
    } catch (e) {
      console.error('[AccountsAdmin] 사용자 등록 실패:', e);
      alert('사용자 등록에 실패했습니다. 다시 시도해 주세요.');
    } finally {
      submitBtn.disabled = false;
    }
  },

  // ── 사용자 수정 모달 ──────────────────────────────────────

  async _openEditModal(id) {
    this._resetEditForm();
    document.getElementById('editUserModal').style.display = 'flex';
    document.getElementById('btnEditSubmit').disabled = true;

    try {
      const res = await Auth.apiFetch(`/api/admin/accounts/${id}/`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const user = await res.json();
      document.getElementById('editUserId').value = user.id;
      document.getElementById('editName').value = user.name || '';
      document.getElementById('editUsername').value = user.username || '';
      document.getElementById('editEmail').value = user.email || '';
      document.getElementById('editPhone').value = user.phone ? this._formatPhone(user.phone) : '';
      document.getElementById('editDepartment').value = user.department_id || '';
      document.getElementById('editFacility').value = user.facility_id || '';
      document.getElementById('editPosition').value = user.position_id || '';
      document.getElementById('editStatus').value = user.status || '';
      document.getElementById('btnEditSubmit').disabled = false;
    } catch (e) {
      console.error('[AccountsAdmin] 사용자 정보 로드 실패:', e);
      alert('사용자 정보를 불러오지 못했습니다.');
      this._closeEditModal();
    }
  },

  _closeEditModal() {
    document.getElementById('editUserModal').style.display = 'none';
  },

  _bindEditModal() {
    document.getElementById('btnEditClose').addEventListener('click', () => this._closeEditModal());
    document.getElementById('btnEditCancel').addEventListener('click', () => this._closeEditModal());
    document.getElementById('btnEditSubmit').addEventListener('click', () => this._submitEditForm());
    document.getElementById('btnPasswordReset').addEventListener('click', () => this._resetPassword());
  },

  _resetEditForm() {
    ['editName', 'editUsername', 'editEmail', 'editPhone'].forEach(id => {
      document.getElementById(id).value = '';
    });
    ['editDepartment', 'editFacility', 'editPosition', 'editStatus'].forEach(id => {
      document.getElementById(id).value = '';
    });
    document.getElementById('editUserId').value = '';
    document.querySelectorAll('#editUserModal .field-error').forEach(el => {
      el.textContent = '';
      el.classList.remove('visible');
    });
    document.querySelectorAll('#editUserModal .is-error').forEach(el => {
      el.classList.remove('is-error');
    });
    const resetBtn = document.getElementById('btnPasswordReset');
    resetBtn.textContent = '비밀번호 초기화';
    resetBtn.disabled = false;
  },

  _validateEditForm() {
    let valid = true;

    const setError = (fieldId, errId, msg) => {
      const field = document.getElementById(fieldId);
      const err = document.getElementById(errId);
      if (msg) {
        field.classList.add('is-error');
        err.textContent = msg;
        err.classList.add('visible');
        valid = false;
      } else {
        field.classList.remove('is-error');
        err.textContent = '';
        err.classList.remove('visible');
      }
    };

    // 사용자명
    const nameTrimmed = document.getElementById('editName').value.trim();
    if (!nameTrimmed) {
      setError('editName', 'editErrName', '사용자명을 입력해 주세요.');
    } else if (nameTrimmed.length < 2) {
      setError('editName', 'editErrName', '사용자명을 2자 이상 입력해 주세요.');
    } else if (nameTrimmed.length > 20) {
      setError('editName', 'editErrName', '사용자명은 20자 이하로 입력해 주세요.');
    } else if (!/^[가-힣a-zA-Z0-9]+$/.test(nameTrimmed)) {
      setError('editName', 'editErrName', '사용자명은 한글, 영문, 숫자만 입력할 수 있습니다.');
    } else {
      setError('editName', 'editErrName', null);
    }

    // 소속
    if (!document.getElementById('editDepartment').value) {
      setError('editDepartment', 'editErrDepartment', '소속을 선택해 주세요.');
    } else {
      setError('editDepartment', 'editErrDepartment', null);
    }

    // 계정 상태
    if (!document.getElementById('editStatus').value) {
      setError('editStatus', 'editErrStatus', '계정 상태를 선택해 주세요.');
    } else {
      setError('editStatus', 'editErrStatus', null);
    }

    // 이메일 (입력 시에만 형식 검증)
    const email = document.getElementById('editEmail').value.trim();
    if (email) {
      if (email.length > 100) {
        setError('editEmail', 'editErrEmail', '이메일은 100자 이하로 입력해 주세요.');
      } else if (!/^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/.test(email)) {
        setError('editEmail', 'editErrEmail', '이메일 형식이 올바르지 않습니다.');
      } else {
        setError('editEmail', 'editErrEmail', null);
      }
    } else {
      setError('editEmail', 'editErrEmail', null);
    }

    // 연락처 (입력 시에만 형식 검증)
    const phone = document.getElementById('editPhone').value.trim();
    if (phone) {
      if (/[^0-9\-]/.test(phone)) {
        setError('editPhone', 'editErrPhone', '연락처는 숫자만 입력할 수 있습니다.');
      } else {
        const digits = phone.replace(/-/g, '');
        if (digits.length !== 10 && digits.length !== 11) {
          setError('editPhone', 'editErrPhone', '연락처를 정확히 입력해 주세요.');
        } else if (!/^0\d{1,2}-?\d{3,4}-?\d{4}$/.test(phone)) {
          setError('editPhone', 'editErrPhone', '연락처 형식이 올바르지 않습니다.');
        } else {
          setError('editPhone', 'editErrPhone', null);
        }
      }
    } else {
      setError('editPhone', 'editErrPhone', null);
    }

    return valid;
  },

  async _submitEditForm() {
    if (!this._validateEditForm()) return;

    const id = document.getElementById('editUserId').value;
    const payload = {
      name: document.getElementById('editName').value.trim(),
      department_id: parseInt(document.getElementById('editDepartment').value),
      status: document.getElementById('editStatus').value,
    };

    // 수정 시에는 빈 값을 명시적 null로 보내야 기존 facility를 비울 수 있다 (PATCH partial 특성).
    // 등록 폼의 "키 생략" 처리와 비대칭한 이유 — 기존 값 제거 의도를 살리기 위함.
    const facility = document.getElementById('editFacility').value;
    payload.facility_id = facility ? parseInt(facility) : null;

    const position = document.getElementById('editPosition').value;
    if (position) payload.position = parseInt(position);

    const email = document.getElementById('editEmail').value.trim();
    if (email) payload.email = email;

    const phone = document.getElementById('editPhone').value.trim();
    if (phone) payload.phone = phone.replace(/-/g, '');

    const submitBtn = document.getElementById('btnEditSubmit');
    submitBtn.disabled = true;

    try {
      const res = await Auth.apiFetch(`/api/admin/accounts/${id}/`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        this._closeEditModal();
        await this.fetchList();
        return;
      }

      if (res.status === 403) { this._showAccessDenied(); return; }

      if (res.status === 400) {
        const errors = await res.json();
        if (errors.name) {
          const el = document.getElementById('editErrName');
          document.getElementById('editName').classList.add('is-error');
          el.textContent = Array.isArray(errors.name) ? errors.name[0] : errors.name;
          el.classList.add('visible');
        }
        return;
      }

      throw new Error(`HTTP ${res.status}`);
    } catch (e) {
      console.error('[AccountsAdmin] 사용자 수정 실패:', e);
      alert('사용자 정보 수정에 실패했습니다. 다시 시도해 주세요.');
    } finally {
      submitBtn.disabled = false;
    }
  },

  async _resetPassword() {
    const id = document.getElementById('editUserId').value;
    if (!confirm('비밀번호를 초기화하시겠습니까?\n초기화 비밀번호: 테스트123!')) return;

    const resetBtn = document.getElementById('btnPasswordReset');
    resetBtn.disabled = true;

    try {
      const res = await Auth.apiFetch(`/api/admin/accounts/${id}/`, {
        method: 'PATCH',
        body: JSON.stringify({ password: 'xptmxm123!' }),
      });

      if (res.ok) {
        resetBtn.textContent = '초기화 완료';
        setTimeout(() => {
          resetBtn.textContent = '비밀번호 초기화';
          resetBtn.disabled = false;
        }, 2000);
      } else if (res.status === 403) {
        this._showAccessDenied();
      } else {
        alert('비밀번호 초기화에 실패했습니다.');
        resetBtn.disabled = false;
      }
    } catch (e) {
      console.error('[AccountsAdmin] 비밀번호 초기화 실패:', e);
      alert('비밀번호 초기화에 실패했습니다.');
      resetBtn.disabled = false;
    }
  },
};

document.addEventListener('DOMContentLoaded', () => AccountsAdmin.init());
