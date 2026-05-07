/* ==========================================================
   scenario-panel.js — 시연 시나리오 컨트롤 (영상 녹화 전용)
   FastAPI(/internal/scenario/mode)에 GET/POST로 모드 동기화.
   ========================================================== */

'use strict';

const ScenarioPanel = {
  // FastAPI HTTP base URL은 WS_BASE에서 derive
  _baseUrl() {
    const ws = (window.AppConfig && window.AppConfig.WS_BASE) || 'ws://127.0.0.1:8001';
    return ws.replace(/^ws/, 'http');
  },

  async _fetchMode() {
    try {
      const res = await fetch(this._baseUrl() + '/internal/scenario/mode');
      if (!res.ok) return null;
      const data = await res.json();
      return data.mode;
    } catch (_) {
      return null;
    }
  },

  async _setMode(mode) {
    try {
      const res = await fetch(this._baseUrl() + '/internal/scenario/mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode }),
      });
      if (!res.ok) return null;
      const data = await res.json();
      return data.mode;
    } catch (_) {
      return null;
    }
  },

  _render(mode) {
    const status = document.getElementById('scenario-status');
    if (status) {
      const labels = { mixed: '혼합', normal: '정상', warning: '주의', danger: '위험' };
      if (mode && labels[mode]) {
        status.textContent = labels[mode];
        status.dataset.mode = mode;
      } else {
        status.textContent = '연결 실패';
        status.dataset.mode = 'error';
      }
    }
    document.querySelectorAll('.scenario-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.mode === mode);
    });
  },

  async init() {
    const buttons = document.querySelectorAll('.scenario-btn');
    if (buttons.length === 0) return;

    buttons.forEach(btn => {
      btn.addEventListener('click', async () => {
        const mode = btn.dataset.mode;
        const updated = await this._setMode(mode);
        this._render(updated || mode);
      });
    });

    const current = await this._fetchMode();
    this._render(current);
  },
};

document.addEventListener('DOMContentLoaded', () => ScenarioPanel.init());
