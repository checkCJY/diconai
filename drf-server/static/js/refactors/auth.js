/* ==========================================================
   auth.js — JWT 토큰 관리
   출처: dashboard.js Auth 모듈
   ========================================================== */

'use strict';

// ──────────────────────────────────────────────────────────
// AUTH 모듈 — JWT 토큰 관리
// ──────────────────────────────────────────────────────────
const Auth = {
  getAccessToken() { return localStorage.getItem('access_token'); },
  getRole()        { return localStorage.getItem('role'); },
  getUsername()    { return localStorage.getItem('username'); },

  clear() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('username');
    localStorage.removeItem('role');
  },

  async apiFetch(url, opts = {}) {
    const token   = this.getAccessToken();
    const headers = Object.assign({ 'Content-Type': 'application/json' }, opts.headers || {});
    if (token) headers['Authorization'] = `Bearer ${token}`;
    return fetch(url, { ...opts, headers });
  },

  async getMe() {
    try {
      const res = await this.apiFetch('/accounts/api/auth/me/');
      if (res.status === 401) { this.redirectLogin(); return null; }
      if (!res.ok)            { return null; }
      return await res.json();
    } catch {
      return null;
    }
  },

  redirectLogin() {
    this.clear();
    window.location.href = '/accounts/login/';
  },
};
