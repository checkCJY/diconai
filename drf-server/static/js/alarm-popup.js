/* ==========================================================
   alarm-popup.js — CM-07 실시간 알림 팝업
   출처: dashboard.js AlarmPopup 모듈
   의존: templates/alarm_popup.html (팝업 DOM)
   ========================================================== */

'use strict';

// ──────────────────────────────────────────────────────────
// CM-07 — 실시간 알림 팝업
// WebSocket 수신 시 level === '위험' 이면 팝업 큐에 추가
// ──────────────────────────────────────────────────────────
const AlarmPopup = {
  queue:  [],
  isOpen: false,

  show(data) {
    this.queue.push(data);
    if (!this.isOpen) this._process();
  },

  _process() {
    if (this.queue.length === 0) { this.isOpen = false; return; }
    this.isOpen    = true;
    const data     = this.queue.shift();
    const isDanger = data.alarm_level === 'danger';
    const popup    = document.getElementById('alarm-popup');
    if (!popup) { this.isOpen = false; return; }

    const levelEl   = document.getElementById('alarm-popup-level');
    const msgEl     = document.getElementById('alarm-popup-message');
    const metaEl    = document.getElementById('alarm-popup-meta');

    levelEl.textContent  = isDanger ? '🔴 위험' : '🟡 주의';
    levelEl.style.color  = isDanger ? 'var(--danger)' : 'var(--caution)';
    popup.style.borderLeftColor = isDanger ? 'var(--danger)' : 'var(--caution)';
    msgEl.textContent    = data.message || '위험 이벤트가 발생했습니다.';

    const parts = [];
    if (data.sensor_name) parts.push(data.sensor_name);
    if (data.worker_name) parts.push(data.worker_name);
    if (data.timestamp)   parts.push(new Date(data.timestamp).toLocaleTimeString());
    metaEl.textContent = parts.join(' | ');

    popup.style.display = 'block';
    this._autoCloseTimer = setTimeout(() => this.close(), 10000);
  },

  close() {
    clearTimeout(this._autoCloseTimer);
    const popup = document.getElementById('alarm-popup');
    if (popup) popup.style.display = 'none';
    setTimeout(() => this._process(), 500);
  },

  init() {
    document.getElementById('alarm-popup-close')  ?.addEventListener('click', () => this.close());
    document.getElementById('alarm-popup-confirm') ?.addEventListener('click', () => this.close());
  },
};
