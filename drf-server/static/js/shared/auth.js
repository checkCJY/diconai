/* ==========================================================
   auth.js — JWT 토큰 관리
   출처: dashboard.js Auth 모듈
   ========================================================== */

'use strict';

// ──────────────────────────────────────────────────────────
// AUTH 모듈 — JWT 토큰 관리
// ──────────────────────────────────────────────────────────
const Auth = {
  getAccessToken()  { return localStorage.getItem('access_token'); },
  getRefreshToken() { return localStorage.getItem('refresh_token'); },
  getRole()         { return localStorage.getItem('role'); },
  getUsername()     { return localStorage.getItem('username'); },

  clear() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('username');
    localStorage.removeItem('role');
  },

  async _refresh() {
    const refreshToken = this.getRefreshToken();
    if (!refreshToken) return false;
    try {
      const res = await fetch('/api/auth/token/refresh/', {
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

  async apiFetch(url, opts = {}) {
    const token   = this.getAccessToken();
    const headers = Object.assign({ 'Content-Type': 'application/json' }, opts.headers || {});
    if (token) headers['Authorization'] = `Bearer ${token}`;

    let res = await fetch(url, { ...opts, headers });

    if (res.status === 401) {
      const refreshed = await this._refresh();
      if (refreshed) {
        headers['Authorization'] = `Bearer ${this.getAccessToken()}`;
        res = await fetch(url, { ...opts, headers });
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
    } catch {
      return null;
    }
  },

  redirectLogin() {
    this.clear();
    window.location.href = '/accounts/login/';
  },
};
