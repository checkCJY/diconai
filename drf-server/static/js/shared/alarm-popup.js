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
  queue:    [],
  isOpen:   false,
  _inited:  false,
  MAX_QUEUE: 5,   // 큐 최대 크기 — 초과분은 버려 DOM 폭주 방지

  show(data) {
    if (this.queue.length >= this.MAX_QUEUE) return;
    this.queue.push(data);
    if (!this.isOpen) this._process();
  },

  // ── 큐에서 데이터를 꺼내 팝업 DOM을 채우고 10초 후 자동으로 닫는다. ─
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

  // confirm/close 클릭 시 남은 큐를 비우고 팝업을 닫는다.
  close() {
    clearTimeout(this._autoCloseTimer);
    this.queue  = [];
    this.isOpen = false;
    const popup = document.getElementById('alarm-popup');
    if (popup) popup.style.display = 'none';
  },

  init() {
    if (this._inited) return;   // 중복 리스너 방지
    this._inited = true;
    document.getElementById('alarm-popup-close')  ?.addEventListener('click', () => this.close());
    document.getElementById('alarm-popup-confirm') ?.addEventListener('click', () => this.close());
  },
};
