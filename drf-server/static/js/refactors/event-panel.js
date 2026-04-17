/* ==========================================================
   event-panel.js — MN-03 이벤트 현황 패널
   출처: alarm_panel.html 인라인 스크립트
   의존: auth.js (Auth.apiFetch)
   ========================================================== */

'use strict';

// ──────────────────────────────────────────────────────────
// MN-03 — 이벤트 현황 패널 (API 동적 로드)
// ──────────────────────────────────────────────────────────
const EventPanel = {

  // ── 이벤트 항목 1개 추가 ────────────────────────────────
  addItem(data) {
    const listEl  = document.getElementById('event-list');
    const emptyEl = document.getElementById('event-empty');
    if (!listEl) return;
    if (emptyEl) emptyEl.remove();

    const isDanger   = data.alarm_level === 'danger';
    const colorClass = isDanger ? 'danger-text' : 'caution-text';
    const dotClass   = isDanger ? 'danger'       : 'caution';
    const label      = data.sensor_name || data.worker_name || '알 수 없음';
    const time       = data.created_at
      ? new Date(data.created_at).toLocaleTimeString()
      : (data.timestamp ? new Date(data.timestamp).toLocaleTimeString() : '');
    const isResolved = data.status === 'resolved';

    const item = document.createElement('div');
    item.className    = 'event-item';
    item.style.opacity = isResolved ? '0.5' : '1';
    item.innerHTML = `
      <div class="event-head">
        <span><span class="dot ${dotClass}"></span>${label}</span>
        <span class="sub">${time}</span>
      </div>
      <div class="${colorClass} event-desc">${data.message || data.alarm_type || ''}</div>
    `;
    listEl.insertBefore(item, listEl.firstChild);
  },

  // ── 24시간 요약 카운트 갱신 ─────────────────────────────
  async loadSummary() {
    try {
      const res  = await Auth.apiFetch('/alarms/api/summary/');
      if (!res.ok) return;
      const data = await res.json();
      const dangerEl  = document.getElementById('summary-danger');
      const warningEl = document.getElementById('summary-warning');
      if (dangerEl)  dangerEl.textContent  = data.last_24h_danger  || 0;
      if (warningEl) warningEl.textContent = data.last_24h_warning || 0;
    } catch {
      // 실패 시 카운트 유지
    }
  },

  // ── 최근 이벤트 목록 로드 ────────────────────────────────
  async loadEventList() {
    try {
      const res  = await Auth.apiFetch('/alarms/api/?ordering=-created_at&limit=10');
      if (!res.ok) return;
      const data = await res.json();
      const list = Array.isArray(data) ? data : (data.results || []);
      list.forEach(item => this.addItem(item));
      await this.loadSummary();
    } catch {
      // 실패 시 empty 상태 유지
    }
  },

  init() {
    this.loadEventList();
  },
};
