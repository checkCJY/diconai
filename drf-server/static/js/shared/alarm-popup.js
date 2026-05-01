/* ==========================================================
   alarm-popup.js — CM-07 실시간 알림 팝업 + 정상화 토스트
   의존: templates/alarm_popup.html (팝업 · 토스트 DOM)
   ========================================================== */

'use strict';

// ── 위험/주의 레벨별 중앙 팝업 설정 ────────────────────────
const _POPUP_CFG = {
  danger: {
    borderColor: 'var(--danger)',
    iconClass:   '',
    typeLabel:   '긴급 알림',
    actionText:  '즉시 대피하세요!',
    actionClass: 'alarm-popup-action',
    badgeClass:  'brisk danger',
    badgeText:   '위험',
  },
  warning: {
    borderColor: 'var(--caution)',
    iconClass:   'caution',
    typeLabel:   '주의 알림',
    actionText:  '주의하세요!',
    actionClass: 'alarm-popup-action caution-text',
    badgeClass:  'brisk caution',
    badgeText:   '주의',
  },
};

// ──────────────────────────────────────────────────────────
// AlarmPopup — 위험/주의 전용 중앙 차단형 팝업
// ──────────────────────────────────────────────────────────
const AlarmPopup = {
  queue:       [],
  isOpen:      false,
  _inited:     false,
  _currentId:  null,
  MAX_QUEUE: 5,

  show(data) {
    const level = data.alarm_level;
    if (level !== 'danger' && level !== 'warning') return;

    if (this.queue.length >= this.MAX_QUEUE) return;
    this.queue.push(data);
    if (!this.isOpen) this._process();
  },

  _process() {
    if (this.queue.length === 0) { this.isOpen = false; return; }
    this.isOpen = true;
    const data  = this.queue.shift();
    const cfg   = _POPUP_CFG[data.alarm_level] || _POPUP_CFG.danger;
    this._currentId = data.event_id || data.id || null;

    const popup = document.getElementById('alarm-popup');
    if (!popup) { this.isOpen = false; return; }

    popup.style.borderLeftColor = cfg.borderColor;

    const timeEl = document.getElementById('alarm-popup-time');
    if (timeEl) {
      const ts = data.timestamp || data.created_at;
      timeEl.textContent = ts
        ? new Date(ts).toLocaleString('ko-KR', { hour12: false })
        : '--';
    }

    const iconEl = document.getElementById('alarm-popup-icon');
    if (iconEl) iconEl.className = `alarm-popup-icon ${cfg.iconClass}`.trim();

    const typeEl = document.getElementById('alarm-popup-type-label');
    if (typeEl) typeEl.textContent = cfg.typeLabel;

    const actionEl = document.getElementById('alarm-popup-action');
    if (actionEl) {
      actionEl.textContent = cfg.actionText;
      actionEl.className   = cfg.actionClass;
    }

    const levelEl = document.getElementById('alarm-popup-level');
    if (levelEl) {
      levelEl.textContent = cfg.badgeText;
      levelEl.className   = cfg.badgeClass;
    }

    const msgEl = document.getElementById('alarm-popup-message');
    if (msgEl) {
      const sensor = data.sensor_name || data.source_label || '';
      const msg    = data.message     || data.summary      || '';
      msgEl.textContent = sensor ? `${sensor} — ${msg}` : msg;
    }

    popup.style.display = 'block';
    this._autoCloseTimer = setTimeout(() => this.close(), 10000);
  },

  close() {
    clearTimeout(this._autoCloseTimer);
    this._currentId = null;
    const popup = document.getElementById('alarm-popup');
    if (popup) popup.style.display = 'none';
    this.isOpen = false;
    this._process();
  },

  _goDetail() {
    const id = this._currentId;
    // 큐는 유지한 채 현재 팝업만 닫고 상세 페이지로 이동
    clearTimeout(this._autoCloseTimer);
    this._currentId = null;
    this.isOpen = false;
    this.queue = [];
    const popup = document.getElementById('alarm-popup');
    if (popup) popup.style.display = 'none';
    window.location.href = id
      ? `/dashboard/monitoring/events/${id}/`
      : '/dashboard/monitoring/events/';
  },

  init() {
    if (this._inited) return;
    this._inited = true;
    document.getElementById('alarm-popup-close') ?.addEventListener('click', () => this.close());
    document.getElementById('alarm-popup-confirm')?.addEventListener('click', () => this.close());
    document.getElementById('alarm-popup-detail') ?.addEventListener('click', () => this._goDetail());
  },
};

document.addEventListener('DOMContentLoaded', () => {
  AlarmPopup.init();
  AlarmToast.init();
});

// ──────────────────────────────────────────────────────────
// AlarmToast — 정상화 전용 우하단 비차단형 토스트
// ──────────────────────────────────────────────────────────
const AlarmToast = {
  _timer:  null,
  _inited: false,

  show(data) {
    const toast = document.getElementById('alarm-toast');
    if (!toast) return;

    clearTimeout(this._timer);

    const sensor = data.sensor_name || data.source_label || '';
    const msg    = data.message     || data.summary      || '';
    const msgEl  = document.getElementById('alarm-toast-message');
    if (msgEl) msgEl.textContent = sensor ? `${sensor} — ${msg}` : msg;

    toast.style.display = 'none';
    requestAnimationFrame(() => {
      toast.style.display = 'flex';
      this._timer = setTimeout(() => this.close(), 5000);
    });
  },

  close() {
    clearTimeout(this._timer);
    const toast = document.getElementById('alarm-toast');
    if (toast) toast.style.display = 'none';
  },

  init() {
    if (this._inited) return;
    this._inited = true;
    document.getElementById('alarm-toast-close')?.addEventListener('click', () => this.close());
  },
};
