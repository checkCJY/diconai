/* ==========================================================
   auth.js — JWT 토큰 관리 + API 호출 단일 진입점
   ==========================================================
   사용 원칙:
   1. 모든 인증 API 호출은 Auth.apiFetch(url, opts)를 사용한다.
      → AppConfig.API_BASE 자동 prefix + Authorization 자동 부착
      + 401 시 자동 refresh + 재시도 + 실패 시 로그인 리다이렉트.
   2. 토큰을 직접 localStorage.getItem/setItem 하지 않는다.
      → Auth.getAccessToken / Auth.setTokens / Auth.clear 사용.
   3. WebSocket 연결은 shared/ws-client.js의 WSClient를 사용한다.
   ========================================================== */

'use strict';

const Auth = {
  // ── 토큰 조회 ───────────────────────────────────────
  getAccessToken()  { return localStorage.getItem('access_token'); },
  getRefreshToken() { return localStorage.getItem('refresh_token'); },
  getRole()         { return localStorage.getItem('role'); },
  getUsername()     { return localStorage.getItem('username'); },

  // ── 토큰 저장·삭제 (login.js 등에서 사용) ─────────────
  setTokens({ access, refresh, username, role } = {}) {
    if (access)   localStorage.setItem('access_token',  access);
    if (refresh)  localStorage.setItem('refresh_token', refresh);
    if (username !== undefined) localStorage.setItem('username', username ?? '');
    if (role !== undefined)     localStorage.setItem('role',     role ?? '');
  },

  setRole(role) { localStorage.setItem('role', role ?? ''); },

  clear() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('username');
    localStorage.removeItem('role');
  },

  // ── URL 헬퍼 ─────────────────────────────────────────
  // AppConfig.apiUrl이 정의되어 있으면 그걸 사용, 아니면 path 그대로(same-origin).
  _resolveUrl(url) {
    if (window.AppConfig && typeof window.AppConfig.apiUrl === 'function') {
      return window.AppConfig.apiUrl(url);
    }
    return url;
  },

  // ── 토큰 갱신 ───────────────────────────────────────
  async _refresh() {
    const refreshToken = this.getRefreshToken();
    if (!refreshToken) return false;
    try {
      const res = await fetch(this._resolveUrl('/api/auth/token/refresh/'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh: refreshToken }),
      });
      if (!res.ok) return false;
      const data = await res.json();
      localStorage.setItem('access_token', data.access);
      return true;
    } catch {
      return false;
    }
  },

  // ── API 호출 단일 진입점 ─────────────────────────────
  // 401 발생 시 1회 refresh 시도 후 재호출. 그래도 401이면 로그인 리다이렉트.
  async apiFetch(url, opts = {}) {
    const finalUrl = this._resolveUrl(url);
    const token   = this.getAccessToken();
    const headers = Object.assign({ 'Content-Type': 'application/json' }, opts.headers || {});
    if (token) headers['Authorization'] = `Bearer ${token}`;

    let res = await fetch(finalUrl, { ...opts, headers });

    if (res.status === 401) {
      const refreshed = await this._refresh();
      if (refreshed) {
        headers['Authorization'] = `Bearer ${this.getAccessToken()}`;
        res = await fetch(finalUrl, { ...opts, headers });
      }
      if (res.status === 401) {
        this.redirectLogin();
        return res;
      }
    }

    return res;
  },

  async getMe() {
    try {
      const res = await this.apiFetch('/api/auth/me/');
      if (!res.ok) return null;
      return await res.json();
    } catch (e) {
      console.warn('[Auth.getMe]', e);
      return null;
    }
  },

  redirectLogin() {
    this.clear();
    window.location.href = '/accounts/login/';
  },
};
