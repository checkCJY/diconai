(function () {
  // 이미 로그인 상태면 대시보드로 자동 이동. 토큰 만료/무효는 Auth.clear로 정리.
  if (Auth.getAccessToken()) {
    Auth.apiFetch('/api/auth/me/')
      .then(res => {
        if (res.ok) {
          window.location.href = '/dashboard/';
        } else {
          Auth.clear();
        }
      })
      .catch(() => {});
  }

  const MSG = {
    username: {
      required: '아이디를 입력해주세요.',
      format:   '아이디는 영문 또는 숫자만 입력할 수 있습니다.',
      length:   '아이디를 4~20자로 입력해주세요.',
    },
    password: {
      required:  '비밀번호를 입력해주세요.',
      minLength: '비밀번호를 8자 이상 입력해야 합니다.',
      pattern:   '비밀번호는 영문, 숫자, 특수문자 중 2가지 이상을 포함해야 합니다.',
    },
    server: {
      authFail:    '아이디 또는 비밀번호가 올바르지 않습니다.',
      networkFail: '서버에 연결할 수 없습니다.',
    },
  };

  const form          = document.getElementById('loginForm');
  const btn           = document.getElementById('loginBtn');
  const serverErrEl   = document.getElementById('serverError');
  const usernameInput = document.getElementById('username');
  const passwordInput = document.getElementById('password');
  const clearUsername = document.getElementById('clearUsername');
  const clearPassword = document.getElementById('clearPassword');
  const usernameError = document.getElementById('usernameError');
  const passwordError = document.getElementById('passwordError');

  function syncClear(input, clearBtn) {
    clearBtn.classList.toggle('visible', input.value.length > 0);
  }
  usernameInput.addEventListener('input', () => {
    syncClear(usernameInput, clearUsername);
    clearFieldError(usernameInput, usernameError);
  });
  passwordInput.addEventListener('input', () => {
    syncClear(passwordInput, clearPassword);
    clearFieldError(passwordInput, passwordError);
  });
  clearUsername.addEventListener('click', () => {
    usernameInput.value = '';
    clearUsername.classList.remove('visible');
    usernameInput.focus();
    clearFieldError(usernameInput, usernameError);
  });
  clearPassword.addEventListener('click', () => {
    passwordInput.value = '';
    clearPassword.classList.remove('visible');
    passwordInput.focus();
    clearFieldError(passwordInput, passwordError);
  });

  usernameInput.addEventListener('blur', () => {
    if (!usernameInput.value) return;
    const err = validateUsername(usernameInput.value.trim());
    if (err) showFieldError(usernameInput, usernameError, err);
  });
  passwordInput.addEventListener('blur', () => {
    if (!passwordInput.value) return;
    const err = validatePassword(passwordInput.value);
    if (err) showFieldError(passwordInput, passwordError, err);
  });

  function showFieldError(input, errorEl, msg) {
    input.classList.add('error');
    errorEl.textContent = msg;
    errorEl.classList.add('show');
  }
  function clearFieldError(input, errorEl) {
    input.classList.remove('error');
    errorEl.classList.remove('show');
  }

  function showServerError(msg) {
    serverErrEl.textContent = msg;
    serverErrEl.classList.add('show');
  }
  function clearServerError() {
    serverErrEl.classList.remove('show');
  }

  function validateUsername(val) {
    if (!val)                               return MSG.username.required;
    if (!/^[a-zA-Z0-9]+$/.test(val))       return MSG.username.format;
    if (val.length < 4 || val.length > 20) return MSG.username.length;
    return '';
  }
  function validatePassword(val) {
    if (!val)           return MSG.password.required;
    if (val.length < 8) return MSG.password.minLength;
    const types = [/[a-zA-Z]/, /[0-9]/, /[^a-zA-Z0-9]/].filter(r => r.test(val)).length;
    if (types < 2)      return MSG.password.pattern;
    return '';
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    clearServerError();

    const username = usernameInput.value.trim();
    const password = passwordInput.value;

    const uErr = validateUsername(username);
    const pErr = validatePassword(password);
    if (uErr) showFieldError(usernameInput, usernameError, uErr);
    if (pErr) showFieldError(passwordInput, passwordError, pErr);
    if (uErr || pErr) return;

    btn.disabled = true;
    btn.textContent = '로그인 중...';

    try {
      const url = (window.AppConfig && window.AppConfig.apiUrl)
        ? window.AppConfig.apiUrl('/api/auth/login/') : '/api/auth/login/';
      const res = await fetch(url, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ username, password }),
      });
      const data = await res.json();

      if (!res.ok) {
        showServerError(data.error || MSG.server.authFail);
        return;
      }

      Auth.setTokens({
        access:   data.access,
        refresh:  data.refresh,
        username: data.username,
        role:     data.role,
      });

      window.location.href = '/dashboard/';
    } catch {
      showServerError(MSG.server.networkFail);
    } finally {
      btn.disabled = false;
      btn.textContent = '로그인';
    }
  });
})();
