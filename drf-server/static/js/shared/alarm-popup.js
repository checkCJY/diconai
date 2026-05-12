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
    actionClass: 'alarm-popup-action',  // 색상은 사용 시점에 LevelMapper.toTextClass(level)로 결합
    badgeClass:  'brisk caution',
    badgeText:   '주의',
  },
};

// 위험도별 자동닫힘 (ms) — danger는 운영자 확인 시간 충분 확보 (P2-2).
const _AUTO_CLOSE_MS = { danger: 15000, warning: 10000 };
const _PULSE_COUNT_THRESHOLD = 10;  // 그룹 카운트 ≥ 이 값이면 펄스 애니메이션

// 위험도별 비프음 — Web Audio API로 합성 (외부 mp3 의존 없음).
// danger: 880Hz × 3펄스 / warning: 660Hz × 2펄스.
// 브라우저 자동재생 정책 — AudioContext는 user gesture 후에만 시작되므로
// 첫 클릭/키 입력 후부터 작동. 페이지 로드 직후 알람은 silent fallback.
const _SOUND_CFG = {
  danger:  { freq: 880, repeat: 3, interval: 0.22, duration: 0.18, volume: 0.32 },
  warning: { freq: 660, repeat: 2, interval: 0.28, duration: 0.20, volume: 0.22 },
};
let _audioCtx = null;
function _playAlarmSound(level) {
  const cfg = _SOUND_CFG[level];
  if (!cfg) return;
  const AC = window.AudioContext || window.webkitAudioContext;
  if (!AC) return;
  try {
    if (!_audioCtx) _audioCtx = new AC();
    if (_audioCtx.state === 'suspended') _audioCtx.resume();  // gesture 후 unlock
    const now = _audioCtx.currentTime;
    for (let i = 0; i < cfg.repeat; i++) {
      const t = now + i * cfg.interval;
      const osc = _audioCtx.createOscillator();
      const gain = _audioCtx.createGain();
      osc.type = 'sine';
      osc.frequency.value = cfg.freq;
      gain.gain.setValueAtTime(0, t);
      gain.gain.linearRampToValueAtTime(cfg.volume, t + 0.01);
      gain.gain.linearRampToValueAtTime(0, t + cfg.duration);
      osc.connect(gain).connect(_audioCtx.destination);
      osc.start(t);
      osc.stop(t + cfg.duration + 0.02);
    }
  } catch (e) {
    console.warn('[AlarmPopup] sound play failed:', e);
  }
}

// ──────────────────────────────────────────────────────────
// AlarmPopup — 위험/주의 전용 중앙 차단형 팝업
// ──────────────────────────────────────────────────────────
const AlarmPopup = {
  queue:        [],
  isOpen:       false,
  _inited:      false,
  _currentId:   null,
  droppedCount: 0,           // 큐 풀 시 누적 (운영 가시성 — 03 R2)
  MAX_QUEUE:    5,
  GROUP_WINDOW_MS: 5000,     // 같은 센서·동일 레벨 연속 알람 그룹핑 윈도우

  show(data) {
    const level = data.alarm_level;
    if (level !== 'danger' && level !== 'warning') return;

    // 옵션 B: 같은 센서·동일 레벨 5초 내 연속 알람은 마지막 큐 항목에 카운트만 누적
    const last = this.queue[this.queue.length - 1];
    if (last && last.sensor_name === data.sensor_name && last.alarm_level === data.alarm_level) {
      const lastTs = new Date(last.timestamp).getTime();
      if (Number.isFinite(lastTs) && (Date.now() - lastTs) < this.GROUP_WINDOW_MS) {
        last.groupCount = (last.groupCount || 1) + 1;
        return;
      }
    }

    // 큐 풀 — silent drop 대신 헤더 배지로 운영자 알림 (P2-3).
    if (this.queue.length >= this.MAX_QUEUE) {
      this.droppedCount += 1;
      console.warn('[AlarmPopup] queue full, dropping alarm', {
        droppedTotal: this.droppedCount,
        sensor: data.sensor_name,
        level: data.alarm_level,
      });
      this._renderDropBadge();  // 현재 팝업이 떠있으면 즉시 배지 갱신
      return;
    }
    this.queue.push(data);
    if (!this.isOpen) this._process();
  },

  // 헤더 우측 "+N건 누락" 배지를 droppedCount 상태에 맞춰 갱신.
  // _process()에서도 호출되어 새 팝업 표시 시 누적 카운트를 운영자가 확인 가능.
  _renderDropBadge() {
    const el    = document.getElementById('alarm-popup-drop-badge');
    const cntEl = document.getElementById('alarm-popup-drop-count');
    if (!el || !cntEl) return;
    if (this.droppedCount > 0) {
      cntEl.textContent = this.droppedCount;
      el.style.display = 'inline-flex';
    } else {
      el.style.display = 'none';
    }
  },

  // 그룹 카운트 우상단 원형 뱃지 갱신. groupCount ≥ 10이면 펄스.
  _renderGroupCount(groupCount) {
    const el = document.getElementById('alarm-popup-count');
    if (!el) return;
    if ((groupCount || 1) > 1) {
      el.textContent = `×${groupCount}`;
      el.style.display = 'flex';
      el.classList.toggle('pulse', groupCount >= _PULSE_COUNT_THRESHOLD);
    } else {
      el.style.display = 'none';
      el.classList.remove('pulse');
    }
  },

  _process() {
    if (this.queue.length === 0) { this.isOpen = false; return; }
    this.isOpen = true;
    const data  = this.queue.shift();
    const level = data.alarm_level;
    const cfg   = _POPUP_CFG[level] || _POPUP_CFG.danger;
    this._currentId = data.event_id || data.id || null;

    const popup = document.getElementById('alarm-popup');
    if (!popup) { this.isOpen = false; return; }

    // 위험도별 테두리·글로우 펄스 + 비프음 (P2 추가).
    popup.classList.remove('level-danger', 'level-warning');
    popup.classList.add(`level-${level}`);
    _playAlarmSound(level);

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
      actionEl.className   = `${cfg.actionClass} ${LevelMapper.toTextClass(level)}`.trim();
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
      // 센서 이름은 굵은 한 줄로 분리, 메시지 본문은 별도 행 — 가독성 향상.
      // innerHTML 대신 안전한 DOM API로 XSS 회피.
      msgEl.replaceChildren();
      if (sensor) {
        const senEl = document.createElement('strong');
        senEl.className = 'sensor-name';
        senEl.textContent = sensor;
        msgEl.appendChild(senEl);
      }
      if (msg) {
        const bodyEl = document.createElement('span');
        bodyEl.className = 'msg-body';
        bodyEl.textContent = msg;
        msgEl.appendChild(bodyEl);
      }
      // 임계값 컨텍스트 — 운영자가 정상/위험 기준을 즉시 비교 가능 (P2 추가, 피드백 #3)
      if (data.measured_value != null && data.threshold_value != null) {
        const thrEl = document.createElement('span');
        thrEl.className = 'msg-threshold';
        thrEl.textContent = `위험 기준 ${data.threshold_value} 초과 (측정 ${data.measured_value})`;
        msgEl.appendChild(thrEl);
      }
    }

    // 그룹 카운트 뱃지 + 큐 풀 누락 배지 갱신
    this._renderGroupCount(data.groupCount);
    this._renderDropBadge();

    popup.style.display = 'block';
    // 위험도별 차등 자동닫힘 — danger는 운영자 확인 시간 확보 (P2-2)
    const closeMs = _AUTO_CLOSE_MS[level] || 10000;
    this._autoCloseTimer = setTimeout(() => this.close(), closeMs);
  },

  // acknowledged=true (확인 버튼): 운영자가 알람을 인지했다는 신호 → drop 카운트 reset.
  // acknowledged=false (✕ 또는 자동닫힘): 다음 팝업까지 carry-over (운영자 미인지).
  close({ acknowledged = false } = {}) {
    clearTimeout(this._autoCloseTimer);
    if (acknowledged) {
      this.droppedCount = 0;
      this._renderDropBadge();
    }
    this._currentId = null;
    const popup = document.getElementById('alarm-popup');
    if (popup) {
      popup.style.display = 'none';
      // 글로우 펄스 애니메이션이 숨겨진 상태에서도 CPU 점유하지 않도록 정리
      popup.classList.remove('level-danger', 'level-warning');
    }
    this.isOpen = false;
    this._process();
  },

  _goDetail() {
    const id = this._currentId;
    // 큐는 유지한 채 현재 팝업만 닫고 상세 페이지로 이동.
    // 누락 카운트는 reset — 운영자가 이력 페이지에서 확인 의사.
    clearTimeout(this._autoCloseTimer);
    this._currentId = null;
    this.isOpen = false;
    this.queue = [];
    this.droppedCount = 0;
    this._renderDropBadge();
    const popup = document.getElementById('alarm-popup');
    if (popup) popup.style.display = 'none';
    window.location.href = id
      ? `/dashboard/monitoring/events/${id}/`
      : '/dashboard/monitoring/events/';
  },

  init() {
    if (this._inited) return;
    this._inited = true;
    document.getElementById('alarm-popup-close')     ?.addEventListener('click', () => this.close());
    document.getElementById('alarm-popup-confirm')   ?.addEventListener('click', () => this.close({ acknowledged: true }));
    document.getElementById('alarm-popup-detail')    ?.addEventListener('click', () => this._goDetail());
    // 누락 배지 클릭 시 이벤트 이력 페이지로 — 누락된 알람을 운영자가 확인 가능
    document.getElementById('alarm-popup-drop-badge')?.addEventListener('click', () => this._goDetail());
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
