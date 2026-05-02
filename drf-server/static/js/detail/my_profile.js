/* ==========================================================
   my_profile.js — 내 정보 확인 페이지
   의존: auth.js (Auth), layout.js (initHeaderAndSNB)
   ========================================================== */

'use strict';

function setField(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value || '-';
}

function formatPhone(value) {
  if (!value) return '-';
  const d = value.replace(/\D/g, '');
  if (d.startsWith('02')) {
    return d.length === 9
      ? d.replace(/^(\d{2})(\d{3})(\d{4})$/, '$1-$2-$3')
      : d.replace(/^(\d{2})(\d{4})(\d{4})$/, '$1-$2-$3');
  }
  return d.length === 10
    ? d.replace(/^(\d{3})(\d{3})(\d{4})$/, '$1-$2-$3')
    : d.replace(/^(\d{3})(\d{4})(\d{4})$/, '$1-$2-$3');
}

async function loadProfile() {
  const res = await Auth.apiFetch('/api/auth/profile/');
  if (res.status === 401) { Auth.redirectLogin(); return; }
  if (!res.ok) return;

  const data = await res.json();
  setField('profileName',       data.name);
  setField('profileEmail',      data.email);
  setField('profileUsername',   data.username);
  setField('profilePhone',      formatPhone(data.phone));
  setField('profileFacility',   data.facility);
  setField('profileDepartment', data.department);
  setField('profilePosition',   data.position);
}


// ──────────────────────────────────────────────────────────
// 비밀번호 변경 모달
// ──────────────────────────────────────────────────────────
const PWD_MSG = {
  current: {
    required: '현재 사용 중인 비밀번호를 입력해 주세요.',
    wrong:    '현재 비밀번호가 일치하지 않습니다. 다시 확인해 주세요.',
    hint:     '본인 확인을 위해 현재 사용 중인 비밀번호를 입력해 주세요.',
  },
  new: {
    required: '새로운 비밀번호를 입력해 주세요.',
    format:   '8~16자의 영문, 숫자, 특수문자를 조합하여 입력해 주세요.',
    same:     '현재 사용 중인 비밀번호는 신규 비밀번호로 사용할 수 없습니다.',
    hint:     '영문, 숫자, 특수문자 조합으로 8~16자 이내로 입력해 주세요.',
  },
  confirm: {
    required: '비밀번호 확인을 위해 한 번 더 입력해 주세요.',
    mismatch: '입력하신 신규 비밀번호와 일치하지 않습니다.',
    hint:     '위에서 입력한 신규 비밀번호를 다시 한번 입력해 주세요.',
  },
};

const PasswordModal = {
  modal:        null,
  successModal: null,

  inputs: {},
  clears: {},
  hints:  {},

  init() {
    this.modal        = document.getElementById('pwdModal');
    this.successModal = document.getElementById('pwdSuccessModal');

    this.inputs  = {
      current: document.getElementById('inputCurrent'),
      new:     document.getElementById('inputNew'),
      confirm: document.getElementById('inputConfirm'),
    };
    this.clears = {
      current: document.getElementById('clearCurrent'),
      new:     document.getElementById('clearNew'),
      confirm: document.getElementById('clearConfirm'),
    };
    this.hints = {
      current: document.getElementById('hintCurrent'),
      new:     document.getElementById('hintNew'),
      confirm: document.getElementById('hintConfirm'),
    };

    document.getElementById('btnPassword')   ?.addEventListener('click', () => this.open());
    document.getElementById('btnPwdCancel')  ?.addEventListener('click', () => this.close());
    document.getElementById('btnPwdSubmit')  ?.addEventListener('click', () => this.submit());
    document.getElementById('btnPwdSuccessOk')?.addEventListener('click', () => this.closeSuccess());

    this._bindField('current');
    this._bindField('new');
    this._bindField('confirm');
  },

  _bindField(key) {
    const input = this.inputs[key];
    const clear = this.clears[key];

    input.addEventListener('input', () => {
      clear.classList.toggle('visible', input.value.length > 0);
      this._clearError(key);
      if (key === 'new' && input.value)    this._validateNew(false);
      if (key === 'confirm' && input.value) this._validateConfirm(false);
    });

    input.addEventListener('blur', () => {
      if (key === 'current') this._validateCurrent();
      if (key === 'new')     this._validateNew(true);
      if (key === 'confirm') this._validateConfirm(true);
    });

    clear.addEventListener('click', () => {
      input.value = '';
      clear.classList.remove('visible');
      this._clearError(key);
      input.focus();
    });
  },

  _showError(key, msg) {
    this.inputs[key].classList.add('error');
    this.hints[key].textContent = msg;
    this.hints[key].classList.add('error');
  },

  _clearError(key) {
    this.inputs[key].classList.remove('error');
    this.hints[key].textContent = PWD_MSG[key].hint;
    this.hints[key].classList.remove('error');
  },

  _validateCurrent() {
    const val = this.inputs.current.value;
    if (!val) { this._showError('current', PWD_MSG.current.required); return false; }
    return true;
  },

  _validateNew(strict) {
    const val = this.inputs.new.value;
    if (!val) {
      if (strict) this._showError('new', PWD_MSG.new.required);
      return false;
    }
    const tooShort = val.length < 8 || val.length > 16;
    const types = [/[a-zA-Z]/, /[0-9]/, /[^a-zA-Z0-9]/].filter(r => r.test(val)).length;
    if (tooShort || types < 2) { this._showError('new', PWD_MSG.new.format); return false; }
    this._clearError('new');
    return true;
  },

  _validateConfirm(strict) {
    const val     = this.inputs.confirm.value;
    const newVal  = this.inputs.new.value;
    if (!val) {
      if (strict) this._showError('confirm', PWD_MSG.confirm.required);
      return false;
    }
    if (val !== newVal) { this._showError('confirm', PWD_MSG.confirm.mismatch); return false; }
    this._clearError('confirm');
    return true;
  },

  open() {
    ['current', 'new', 'confirm'].forEach(k => {
      this.inputs[k].value = '';
      this.clears[k].classList.remove('visible');
      this._clearError(k);
    });
    this.modal.style.display = 'flex';
    this.inputs.current.focus();
  },

  close() {
    this.modal.style.display = 'none';
  },

  closeSuccess() {
    this.successModal.style.display = 'none';
  },

  async submit() {
    const okCurrent = this._validateCurrent();
    const okNew     = this._validateNew(true);
    const okConfirm = this._validateConfirm(true);
    if (!okCurrent || !okNew || !okConfirm) return;

    const btn = document.getElementById('btnPwdSubmit');
    btn.disabled = true;

    try {
      const res = await Auth.apiFetch('/api/auth/password/change/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          current_password:     this.inputs.current.value,
          new_password:         this.inputs.new.value,
          new_password_confirm: this.inputs.confirm.value,
        }),
      });

      if (res.status === 401) { Auth.redirectLogin(); return; }

      const data = await res.json();

      if (!res.ok) {
        if (data.current_password) this._showError('current', data.current_password[0] || PWD_MSG.current.wrong);
        if (data.new_password)     this._showError('new',     data.new_password[0]);
        if (data.new_password_confirm) this._showError('confirm', data.new_password_confirm[0]);
        return;
      }

      this.close();
      this.successModal.style.display = 'flex';
    } finally {
      btn.disabled = false;
    }
  },
};


document.addEventListener('DOMContentLoaded', async () => {
  await loadProfile();
  PasswordModal.init();
});
