/* ==========================================================
   alarm-popup.js — CM-07 실시간 알림 팝업 + 정상화 토스트
   의존: templates/alarm_popup.html (팝업 · 토스트 DOM)
   ========================================================== */

'use strict';

// ── 2026-05-15 알람 재설계: 클라이언트 측 user-scoped ack store ──
// 본인이 "확인 완료" 한 event_id 를 localStorage 에 영속화. 같은 event_id 알람이
// 백엔드 broadcast 로 다시 와도 이 클라에서만 팝업 skip. 다른 사용자 클라는 영향 0.
// Phase 3 의 서버 측 ack 분기 (옵션 B) 가 들어오면 이 Set 은 보강재로 유지.
const _ACK_STORE_KEY = 'diconai:alarm:acked_event_ids';
const _LAST_SEEN_KEY = 'diconai:alarm:last_seen_ts';
// T5 (2026-05-20) — 24h → 60s 단축. 24h 영구 차단 가설 (진단 문서 §3.1) 이 시연
// 중 모달 클릭 한 번이 24시간 침묵을 만들 위험. 60s 면 RESOLVED 안 눌러도 다음
// repopup cooldown (settings.ALARM_REPOPUP_COOLDOWN_SEC=60s) 직후 자연 회복.
// RESOLVED 즉시 해제는 _handleResolved 안 _AckStore.remove(eventId) 가 처리.
const _ACK_TTL_MS    = 60_000;  // 60s — 진단 문서 §7 옵션 (a)

const _AckStore = {
  _map: null,  // Map<event_id, ack_ts_ms>

  _load() {
    if (this._map !== null) return this._map;
    try {
      const raw = localStorage.getItem(_ACK_STORE_KEY);
      const arr = raw ? JSON.parse(raw) : [];
      const now = Date.now();
      const fresh = arr.filter(e => (now - e.ts) < _ACK_TTL_MS);
      this._map = new Map(fresh.map(e => [e.id, e.ts]));
      if (fresh.length !== arr.length) this._persist();
    } catch (e) {
      this._map = new Map();
    }
    return this._map;
  },

  has(eventId) {
    return eventId != null && this._load().has(eventId);
  },

  add(eventId) {
    if (eventId == null) return;
    this._load().set(eventId, Date.now());
    this._persist();
  },

  // T5 — RESOLVED 시 동기 삭제 (_handleResolved 호출). 운영자가 "조치 완료" 누른
  // 시점에 본인 ack 도 같이 해제 — 멘탈 모델 정합 (진단 문서 §7 옵션 b).
  remove(eventId) {
    if (eventId == null) return;
    const map = this._load();
    if (map.delete(eventId)) this._persist();
  },

  _persist() {
    try {
      const arr = Array.from(this._map.entries()).map(([id, ts]) => ({ id, ts }));
      localStorage.setItem(_ACK_STORE_KEY, JSON.stringify(arr));
    } catch (e) {
      console.warn('[AlarmPopup] ack store persist failed:', e);
    }
  },
};

// ── 2026-05-17 D 옵션 — 60s 클라이언트 dedup ─────────────────
// 같은 (alarm_type, source, level) 알람이 60s 안 재발생 시 팝업 skip (operator UX).
// 백엔드 ALARM_REPOPUP_COOLDOWN_SEC (기본 60s) 와 일치 — 백엔드가 60s 후
// 재푸시한 시점에 클라 TTL 만료라 자연 재발화 (차단형 정책 자동 충족).
// T3 (2026-05-19): 30s 하향 검토 후 60s 유지 결정 — "폭주 회피" 우선.
// _AckStore 와 같은 패턴 — localStorage 영속화 + JSON 직렬화 + TTL + silent fail.
const _DEDUP_STORE_KEY = 'diconai:alarm:popup:dedup';
const _DEDUP_TTL_MS    = 60_000;

const _DedupStore = {
  _map: null,  // Map<key, ts_ms>

  _load() {
    if (this._map !== null) return this._map;
    try {
      const raw = localStorage.getItem(_DEDUP_STORE_KEY);
      const arr = raw ? JSON.parse(raw) : [];
      const now = Date.now();
      const fresh = arr.filter(e => (now - e.ts) < _DEDUP_TTL_MS);
      this._map = new Map(fresh.map(e => [e.k, e.ts]));
      if (fresh.length !== arr.length) this._persist();
    } catch (e) {
      this._map = new Map();
    }
    return this._map;
  },

  // key 가 60s 안 도착했으면 true. fresh (60s 경과) 면 stale 정리 후 false.
  has(key) {
    if (!key) return false;
    const map = this._load();
    const ts = map.get(key);
    if (ts == null) return false;
    if ((Date.now() - ts) >= _DEDUP_TTL_MS) {
      map.delete(key);
      this._persist();
      return false;
    }
    return true;
  },

  add(key) {
    if (!key) return;
    this._load().set(key, Date.now());
    this._persist();
  },

  _persist() {
    try {
      const arr = Array.from(this._map.entries()).map(([k, ts]) => ({ k, ts }));
      localStorage.setItem(_DEDUP_STORE_KEY, JSON.stringify(arr));
    } catch (e) { /* silent */ }
  },
};

// dedup 키 — event_id 우선, 없으면 (alarm_type, source, level) 합성.
// event-panel.js 의 _dedupKey 와 같은 컨벤션.
// T3 (2026-05-19) — RESOLVED 신호 (event_resolved_at 박힘) 는 알람과 다른 의미.
// dedup TTL 안이라도 운영자가 "위험 해소" 인지 필수. timestamp suffix 로 별도 key.
function _popupDedupKey(data) {
  const eventId = data.event_id || data.id;
  const resolvedSuffix = data.event_resolved_at
    ? `:resolved:${data.event_resolved_at}`
    : '';
  if (eventId != null) return `event:${eventId}${resolvedSuffix}`;
  return `${data.alarm_type || 'unknown'}:${data.sensor_name || data.source_label || ''}:${data.alarm_level || ''}${resolvedSuffix}`;
}

// T3 (2026-05-19) — 다중 관리자 환경 ack 시그널 텍스트 생성.
// 백엔드 push_payload.event_ack_users 가 비어있으면 빈 문자열 (시그널 미표시).
// 1명: "(홍길동 확인 중)" / 2명: "(홍길동, 김민수 확인 중)" / 3명+: "(홍길동 외 N명 확인 중)"
function _formatAckSignal(ackUsers) {
  if (!Array.isArray(ackUsers) || ackUsers.length === 0) return '';
  if (ackUsers.length === 1) return `(${ackUsers[0]} 확인 중)`;
  if (ackUsers.length === 2) return `(${ackUsers[0]}, ${ackUsers[1]} 확인 중)`;
  return `(${ackUsers[0]} 외 ${ackUsers.length - 1}명 확인 중)`;
}

// 마지막 수신 알람 시각 (unix sec). WS 끊김 후 재연결·페이지 새로고침 시
// /alerts/api/alarms/catch-up/?since=<ts> 호출로 미수신 알람 보충 (시연 안전망).
const _LastSeen = {
  read() {
    try {
      const raw = localStorage.getItem(_LAST_SEEN_KEY);
      const n = raw ? Number(raw) : 0;
      return Number.isFinite(n) ? n : 0;
    } catch (e) { return 0; }
  },
  write(unixSec) {
    if (!Number.isFinite(unixSec)) return;
    try {
      const prev = this.read();
      if (unixSec > prev) localStorage.setItem(_LAST_SEEN_KEY, String(unixSec));
    } catch (e) { /* localStorage quota / disabled — silent */ }
  },
};

// ── 2026-05-15 Phase 2 A-mini: admin-panel UX 차별화 ────────
// admin-panel/* 페이지에선 차단형 모달이 운영 워크플로우 (폼 작성·지도 편집 등) 를
// 차단하던 문제 해결. 우상단 토스트 stack 으로 비차단 표시 + DANGER 무응답 시 격상.
// 모니터링 페이지 (dashboard / snb_details / event_detail 등) 는 기존 모달 유지.
const _ADMIN_PATH_PREFIX = '/admin-panel/';
// DANGER 토스트 무응답 → 모달 격상까지 (2026-05-17 변경: 10s → 60s).
// 10초는 너무 짧아 폼 작성 중 운영자가 의도적 무시할 시간조차 부족했음. 1분으로
// 늘려 운영자가 정상 작업하다가 60s 안 토스트 확인 못 한 진짜 무응답 케이스에만
// 격상. 동시에 백엔드 ALARM_REPOPUP_COOLDOWN_SEC (기본 60s) · 클라 _DEDUP_TTL_MS
// (60s) 와 시간 척도 일관.
const _TOAST_ESCALATE_MS = 60000;
const _TOAST_TTL_MS      = { danger: 15000, warning: 10000 };

function _resolveDisplayMode() {
  return window.location.pathname.startsWith(_ADMIN_PATH_PREFIX) ? 'toast' : 'modal';
}

const AlarmToastStack = {
  _items: new Map(),   // event_id → element (같은 event 중복 push 차단)

  push(data) {
    const eventId = data.event_id || data.id;
    const level = data.alarm_level;
    if (level !== 'danger' && level !== 'warning') return;

    // 위험도 격상 — 같은 event 의 warning → danger 면 기존 토스트 dismiss 후 새로 띄움.
    // 동일/하향은 기존 dedup 유지 (스팸 방지).
    if (eventId != null && this._items.has(eventId)) {
      const existing = this._items.get(eventId);
      const existingLevel = existing.dataset.alarmLevel;
      if (level === 'danger' && existingLevel === 'warning') {
        this._dismiss(eventId, existing);
        // fallthrough — 아래에서 새 토스트 생성
      } else {
        return;
      }
    }

    const container = this._ensureContainer();
    const item = this._createItem(data, level);
    item.dataset.alarmLevel = level;     // 다음 격상 비교용
    container.appendChild(item);
    if (eventId != null) this._items.set(eventId, item);

    // 자동 사라짐 / 격상 timer 분기 (2026-05-17 수정):
    //   DANGER → escalate timer 만 (60s) — dismiss 는 격상 시점에 _dismiss 가 처리
    //   WARNING → dismiss timer 만 (10s) — 격상 없음
    // 이전엔 DANGER 도 dismiss(15s) + escalate(원래 10s) 둘 다 set 했는데, 격상
    // 시간을 10s → 60s 로 변경한 뒤로 dismiss(15s) 가 먼저 fire 되어 _dismiss 가
    // escalate 를 clearTimeout — 격상이 안 되는 race 가 발생했음.
    item._timers = {};
    if (level === 'danger') {
      item._timers.escalate = setTimeout(() => {
        this._dismiss(eventId, item);
        AlarmPopup.show(Object.assign({}, data, { __forceModal: true }));
      }, _TOAST_ESCALATE_MS);
    } else {
      const ttl = _TOAST_TTL_MS[level] || 10000;
      item._timers.dismiss = setTimeout(() => this._dismiss(eventId, item), ttl);
    }
  },

  _ensureContainer() {
    let el = document.getElementById('alarm-toast-stack');
    if (!el) {
      el = document.createElement('div');
      el.id = 'alarm-toast-stack';
      document.body.appendChild(el);
    }
    return el;
  },

  _createItem(data, level) {
    const item = document.createElement('div');
    item.className = `alarm-toast-stack-item ${level}`;
    // T4 — cover 톤 클래스 추가 (CSS 가 노랑 톤 진정 + cover-badge 노출).
    const tone = AlarmMapper.sourceTone(data.alarm_source);
    if (tone === 'cover') item.classList.add('alarm-popup-static-cover');
    const sensor = data.sensor_name || data.source_label || '';
    const msg    = data.message     || data.summary      || '';
    const badge  = (level === 'danger') ? '⚠ 위험' : '⚠ 주의';

    // 안전한 DOM API — innerHTML 회피 (XSS 방지, alarm-popup.js 의 _process 와 동일 패턴)
    const header = document.createElement('div');
    header.className = 'alarm-toast-stack-header';
    const badgeEl = document.createElement('span');
    badgeEl.className = 'alarm-toast-stack-badge';
    badgeEl.textContent = badge;
    const closeBtn = document.createElement('button');
    closeBtn.className = 'alarm-toast-stack-close';
    closeBtn.type = 'button';
    closeBtn.textContent = '✕';
    closeBtn.addEventListener('click', () => {
      this._dismiss(data.event_id || data.id, item);
    });
    header.append(badgeEl, closeBtn);

    const sensorEl = document.createElement('div');
    sensorEl.className = 'alarm-toast-stack-sensor';
    sensorEl.textContent = sensor;

    const msgEl = document.createElement('div');
    msgEl.className = 'alarm-toast-stack-msg';
    msgEl.textContent = msg;

    // T3 — 다중 관리자 환경 ack 시그널. 0명이면 미렌더 (단일 운영자 환경 영향 0).
    const ackText = _formatAckSignal(data.event_ack_users);
    let ackEl = null;
    if (ackText) {
      ackEl = document.createElement('div');
      ackEl.className = 'alarm-toast-stack-ack';
      ackEl.textContent = ackText;
    }

    // T4 — cover 배지 + reason 문구. 토스트도 모달과 동일 패턴.
    // wrapper div 안 inner span — wrapper 가 줄바꿈 보장, inner 가 노랑 칩 시각.
    const coverBadge = AlarmMapper.sourceBadge(data.alarm_source);
    let coverBadgeEl = null;
    if (coverBadge) {
      coverBadgeEl = document.createElement('div');
      coverBadgeEl.className = 'alarm-toast-stack-cover-badge';
      const innerCB = document.createElement('span');
      innerCB.className = 'cover-badge';
      innerCB.textContent = coverBadge;
      coverBadgeEl.appendChild(innerCB);
    }
    let reasonEl = null;
    if (data.alarm_reason) {
      reasonEl = document.createElement('div');
      reasonEl.className = 'alarm-toast-stack-cover-reason';
      reasonEl.textContent = data.alarm_reason;
    }

    item.append(header, sensorEl, msgEl);
    if (coverBadgeEl) item.append(coverBadgeEl);
    if (reasonEl) item.append(reasonEl);
    if (ackEl) item.append(ackEl);
    // 토스트 클릭 — 격상 즉시 트리거 (사용자가 본 것으로 인지)
    item.addEventListener('click', (ev) => {
      if (ev.target === closeBtn) return;
      if (item._timers) {
        clearTimeout(item._timers.dismiss);
        clearTimeout(item._timers.escalate);
      }
      this._dismiss(data.event_id || data.id, item);
      AlarmPopup.show(Object.assign({}, data, { __forceModal: true }));
    });
    return item;
  },

  _dismiss(eventId, item) {
    if (eventId != null) this._items.delete(eventId);
    if (item._timers) {
      clearTimeout(item._timers.dismiss);
      clearTimeout(item._timers.escalate);
      item._timers = null;
    }
    item.classList.add('dismissing');
    setTimeout(() => item.remove(), 300);
  },
};

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

// T2+T6 (2026-05-20) — 도메인별 행동 안내. 운영자가 알람 보고 "무엇을 해야 하는가"
// 즉시 인지하도록 alarm_type × level 매트릭스. 미정의 type 은 _POPUP_CFG default
// actionText 로 fallback (기존 "즉시 대피하세요! / 주의하세요!"). clear 알람은 modal
// 안 띄우므로 본 dict 미정의 (토스트만, 별 sprint 확장).
const _ACTION_TEXT = {
  gas_threshold: {
    danger:  '작업자 즉시 대피 / 외부 환기 가동 · 책임자 통보',
    warning: '작업 중단 + 환기 / 농도 추이 확인',
  },
  gas_anomaly_ai: {
    danger:  '해당 구역 작업자 대피 / AI 누출 의심 — 센서 위치 확인',
    warning: '해당 센서 농도 모니터링 / 이상 지속 시 점검',
  },
  power_overload: {
    danger:  '해당 설비 즉시 정지 / 부하·발열 점검',
    warning: '설비 부하·온도 확인',
  },
  power_anomaly_ai: {
    danger:  '설비 정지 후 정밀 점검 (AI 이상 패턴)',
    warning: '부하·발열 추이 확인 / 이상 지속 시 정지',
  },
  geofence_intrusion: {
    danger:  '해당 작업자 즉시 이탈 지시 / 위치·안전 확인',
    warning: '작업자 위치 확인 / 구역 이탈 안내',
  },
  ppe_violation: {
    danger:  'PPE 착용 지시',
    warning: 'PPE 착용 지시',
  },
  sensor_fault: {
    danger:  '센서 통신 상태 확인 / 지속 시 설비팀 연락',
    warning: '센서 통신 상태 확인 / 지속 시 설비팀 연락',
  },
  batch_failed: {
    danger:  '배치 로그 확인 + 재실행',
    warning: '배치 로그 확인 + 재실행',
  },
  storage_overdue: {
    danger:  '보관 주기 도래 — 점검·갱신 처리',
    warning: '보관 주기 도래 — 점검·갱신 처리',
  },
};

// 위험도별 자동닫힘 (ms) — danger는 운영자 확인 시간 충분 확보 (P2-2).
// T5 (2026-05-20) — warning 10s → 30s. 10s 는 운영자가 메시지 읽기 전 사라짐.
// 30s 면 텍스트 확인 + 확인 완료 클릭 충분. danger 는 15s 유지 (격상 펄스 → 모달).
const _AUTO_CLOSE_MS = { danger: 15000, warning: 30000 };
const _PULSE_COUNT_THRESHOLD = 10;  // 그룹 카운트 ≥ 이 값이면 펄스 애니메이션

// 수동 ack/✕ 로 팝업을 닫을 때 다음 팝업까지 두는 최소 텀(ms). 0ms 동기 연쇄
// (확인 클릭 즉시 다음 팝업 + 비프) 가 "버튼 누르면 폭격" 체감을 주던 문제 완화.
// 자동닫힘은 이미 _AUTO_CLOSE_MS 만큼 떨어져 있어 본 텀과 무관. 격상은 immediate 로 우회.
const _PROCESS_GAP_MS = 700;

// 위험도별 비프음 — Web Audio API로 합성 (외부 mp3 의존 없음).
// danger: 880Hz × 3펄스 / warning: 660Hz × 2펄스.
// 브라우저 자동재생 정책 — AudioContext는 user gesture 후에만 시작되므로
// 첫 클릭/키 입력 후부터 작동. 페이지 로드 직후 알람은 silent fallback.
const _SOUND_CFG = {
  danger:  { freq: 880, repeat: 3, interval: 0.22, duration: 0.18, volume: 0.32 },
  warning: { freq: 660, repeat: 2, interval: 0.28, duration: 0.20, volume: 0.22 },
};
let _audioCtx = null;
// 연속 팝업 시 비프 폭격 방지 — 마지막 재생 후 이 간격(ms) 안이면 skip.
const _BEEP_THROTTLE_MS = 1500;
let _lastBeepAt = 0;
function _playAlarmSound(level) {
  const cfg = _SOUND_CFG[level];
  if (!cfg) return;
  // 연속 팝업 비프 폭격 방지 — 마지막 재생 후 _BEEP_THROTTLE_MS 안이면 skip.
  const _nowMs = Date.now();
  if (_nowMs - _lastBeepAt < _BEEP_THROTTLE_MS) return;
  _lastBeepAt = _nowMs;
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
  _currentLevel: null,    // 격상 비교용 — 현재 떠있는 모달의 risk_level
  _currentChannel: null,  // 격상 매칭 fallback — push payload 에 event_id 가 없는
  _currentAlarmType: null,// 케이스 (예: power_anomaly_ai 의 forward race timeout)
                          // event_id 우선, 없으면 alarm_type+channel 로 매칭
  droppedCount: 0,           // 큐 풀 시 누적 (운영 가시성 — 03 R2)
  MAX_QUEUE:    30,          // 다채널 동시 발화 폭주 시 drop 회피 (5 → 30)
  GROUP_WINDOW_MS: 5000,     // 같은 센서·동일 레벨 연속 알람 그룹핑 윈도우

  show(data) {
    // 2026-05-15 알람 재설계: 모든 수신 알람의 시각으로 last_seen 갱신 — skip 여부 무관.
    // catch-up 정확도 (다음 reconnect 시 since 기준점) 를 위해 모든 path 에서 기록.
    const tsRaw = data.timestamp || data.created_at;
    if (tsRaw) {
      const tsMs = new Date(tsRaw).getTime();
      if (Number.isFinite(tsMs)) _LastSeen.write(Math.floor(tsMs / 1000));
    }

    // RESOLVED 신호 — 알람 자체가 아니라 "위험 해소" 메타 신호. 같은 event_id 떠있는
    // 팝업 close + 큐에서 제거 + 우하단 짧은 토스트. alarm-popup.html 의 토스트 DOM 재사용.
    if (data.event_resolved_at) {
      this._handleResolved(data);
      return;
    }

    const level = data.alarm_level;
    if (level !== 'danger' && level !== 'warning') return;

    // user-scoped ack 분기 (Phase 1 옵션 A) — 본인이 이미 ack 한 event 면 팝업 skip.
    // 이벤트 패널 표시 (newAlarmEvent) 는 alarm-ws.js 가 별도로 발행하므로 영향 없음.
    const eventId = data.event_id || data.id;

    // 위험도 격상 — 같은 event 가 warning → danger 로 올라온 경우 현재 모달 강제 교체.
    // dedup/큐 우회: 운영자 시각에 격상 즉시 반영. ack 무시 (격상은 더 큰 위험).
    //
    // 매칭 전략:
    //   (1) event_id 매칭 (정상 경로) — 가스/전력 룰 / 전력 AI 의 forward race 정상 case
    //   (2) channel+alarm_type fallback — event_id 둘 다 null 일 때 (전력 AI 의 forward
    //       race 가 500ms 안 응답 못 받은 case). 같은 채널의 warning → danger 만 매칭.
    const sameEvent = (
      eventId != null && eventId === this._currentId
    );
    const sameChannelFallback = (
      eventId == null
      && this._currentId == null
      && data.alarm_type != null
      && data.alarm_type === this._currentAlarmType
      && data.channel != null
      && data.channel === this._currentChannel
    );
    if (
      this.isOpen
      && this._currentLevel === 'warning'
      && level === 'danger'
      && (sameEvent || sameChannelFallback)
    ) {
      this.queue.unshift(data);          // 큐 맨 앞에 — close 후 _process 가 즉시 픽업
      this.close({ acknowledged: false, immediate: true });  // 격상은 텀 없이 즉시
      return;
    }

    if (_AckStore.has(eventId)) return;

    // 2026-05-17 D 옵션 — 60s 클라 dedup. 같은 알람이 60s 안 재도착하면 팝업 skip
    // (백엔드가 다중 페이지·다중 탭 에서 받게 한 경우 + 백엔드 cooldown 통과 직후 burst).
    // 백엔드 ALARM_REPOPUP_COOLDOWN_SEC 와 일치 — 60s 후 재푸시 시점에 TTL 만료라
    // 자연 재발화 (차단형 정책 자동 충족). 카운터 ↑ 는 alarm-badge.js 가 newAlarmEvent
    // 구독으로 별도 처리 (dedup 무관 — 운영자 누적 인지).
    const dedupKey = _popupDedupKey(data);
    if (_DedupStore.has(dedupKey)) return;
    _DedupStore.add(dedupKey);

    // 2026-05-15 Phase 2 A-mini: admin-panel/* 페이지는 차단형 모달이 폼 입력 손실 +
    // 운영자 무지성 닫기 학습을 유발 — 우상단 토스트 stack 으로 비차단 표시.
    // DANGER 토스트는 10초 무응답 시 모달 격상 (__forceModal 플래그로 재진입).
    // __forceModal 박힌 호출은 격상 경로라 분기 skip.
    if (!data.__forceModal && _resolveDisplayMode() === 'toast') {
      AlarmToastStack.push(data);
      return;
    }

    // 같은 센서·동일 레벨 group window — 위험은 1초로 짧게 (재팝업 빠른 반응),
    // 그 외(주의)는 기존 5초 유지 (전기 노이즈 등 burst 보호).
    const windowMs = (level === 'danger') ? 1000 : this.GROUP_WINDOW_MS;
    const last = this.queue[this.queue.length - 1];
    if (last && last.sensor_name === data.sensor_name && last.alarm_level === data.alarm_level) {
      const lastTs = new Date(last.timestamp).getTime();
      if (Number.isFinite(lastTs) && (Date.now() - lastTs) < windowMs) {
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
    this._currentLevel = level;
    this._currentChannel = data.channel ?? null;
    this._currentAlarmType = data.alarm_type ?? null;

    const popup = document.getElementById('alarm-popup');
    if (!popup) { this.isOpen = false; return; }

    // 위험도별 테두리·글로우 펄스 + 비프음 (P2 추가).
    popup.classList.remove('level-danger', 'level-warning');
    popup.classList.add(`level-${level}`);
    _playAlarmSound(level);

    // T4 — source 별 시각 톤. 'cover' = AI 미탐/실패/워밍업 보완 알람 (노랑 + 배지).
    // 'risk' = 기존 위험도 분기 그대로. cover 톤은 alarm-popup-static-cover 클래스
    // 가 빨강·노랑 펄스를 진정시켜 운영자가 "주역 vs 보조" 즉시 구분.
    popup.classList.remove('alarm-popup-static-cover');
    const tone = AlarmMapper.sourceTone(data.alarm_source);
    if (tone === 'cover') popup.classList.add('alarm-popup-static-cover');

    const timeEl = document.getElementById('alarm-popup-time');
    if (timeEl) {
      const ts = data.timestamp || data.created_at;
      // KST 라벨 + 통일 포맷 (Phase 2 P5)
      timeEl.textContent = (typeof TimeFormat !== 'undefined') ? TimeFormat.abs(ts) : (ts || '--');
    }

    const iconEl = document.getElementById('alarm-popup-icon');
    if (iconEl) iconEl.className = `alarm-popup-icon ${cfg.iconClass}`.trim();

    const typeEl = document.getElementById('alarm-popup-type-label');
    if (typeEl) typeEl.textContent = cfg.typeLabel;

    const actionEl = document.getElementById('alarm-popup-action');
    if (actionEl) {
      // T2+T6 — alarm_type 별 행동 안내 우선. fallback cfg.actionText (기존 워딩).
      // _ACTION_TEXT 에 없는 type (vr_training_not_done / inspection_scheduled 등)
      // 은 default "즉시 대피하세요! / 주의하세요!" 그대로 — 시연 가능성 낮은 영역.
      const actionText = _ACTION_TEXT[data.alarm_type]?.[level] || cfg.actionText;
      actionEl.textContent = actionText;
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
      // 임계값 컨텍스트 — 운영자가 정상/위험 기준을 즉시 비교 가능 (P2 추가, 피드백 #3).
      // T2+T6 (2026-05-20) — label level 분기. 기존 "위험 기준" 하드코딩이 warning
      // 알람에도 표시되던 톤 불일치 해소.
      if (data.measured_value != null && data.threshold_value != null) {
        const thrEl = document.createElement('span');
        thrEl.className = 'msg-threshold';
        const thrLabel = level === 'danger' ? '위험 기준' : '주의 기준';
        thrEl.textContent = `${thrLabel} ${data.threshold_value} 초과 (측정 ${data.measured_value})`;
        msgEl.appendChild(thrEl);
      }
      // T3 — 다중 관리자 환경 ack 시그널 (모달도 토스트와 동일 패턴).
      const ackText = _formatAckSignal(data.event_ack_users);
      if (ackText) {
        const ackEl = document.createElement('span');
        ackEl.className = 'msg-ack-signal';
        ackEl.textContent = ackText;
        msgEl.appendChild(ackEl);
      }

      // T4 — source 가 cover 면 배지 + reason 문구 렌더. AI 단독·일반 룰 알람은 미렌더.
      // div 사용 — 부모가 flex 등이어도 줄바꿈 보장 (span 인접 렌더 버그 fix).
      const badgeLabel = AlarmMapper.sourceBadge(data.alarm_source);
      if (badgeLabel) {
        const badgeEl = document.createElement('div');
        badgeEl.className = 'msg-cover-badge';
        const inner = document.createElement('span');
        inner.className = 'cover-badge';
        inner.textContent = badgeLabel;
        badgeEl.appendChild(inner);
        msgEl.appendChild(badgeEl);
      }
      if (data.alarm_reason) {
        const reasonEl = document.createElement('div');
        reasonEl.className = 'msg-cover-reason';
        reasonEl.textContent = data.alarm_reason;
        msgEl.appendChild(reasonEl);
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
  close({ acknowledged = false, immediate = false } = {}) {
    clearTimeout(this._autoCloseTimer);
    clearTimeout(this._gapTimer);
    if (acknowledged) {
      this.droppedCount = 0;
      this._renderDropBadge();
    }
    this._currentId = null;
    this._currentLevel = null;
    this._currentChannel = null;
    this._currentAlarmType = null;
    const popup = document.getElementById('alarm-popup');
    if (popup) {
      popup.style.display = 'none';
      // 글로우 펄스 애니메이션이 숨겨진 상태에서도 CPU 점유하지 않도록 정리
      popup.classList.remove('level-danger', 'level-warning');
    }
    this.isOpen = false;
    // 격상(immediate)은 즉시, 그 외(수동 ack/✕/자동닫힘)는 _PROCESS_GAP_MS 텀 후
    // 다음 팝업 — 확인 클릭이 다음 팝업+비프를 0ms 로 들이밀던 "폭격" 체감 제거.
    if (immediate) {
      this._process();
    } else {
      this._scheduleProcess();
    }
  },

  // 다음 팝업을 _PROCESS_GAP_MS 텀 후 표시. 텀 동안 isOpen=true 로 잡아둬 들어오는
  // show() 가 큐에만 쌓이고 갭을 건너뛰어 즉시 뜨지 않게 한다 (show 의
  // `if(!this.isOpen) this._process()` 가드 우회 방지). 큐가 비어 있으면 idle 복귀.
  _scheduleProcess() {
    if (this.queue.length === 0) { this.isOpen = false; return; }
    this.isOpen = true;
    clearTimeout(this._gapTimer);
    this._gapTimer = setTimeout(() => {
      this.isOpen = false;
      this._process();
    }, _PROCESS_GAP_MS);
  },

  // RESOLVED 신호 처리 — 같은 event_id 떠있는 팝업 close + 큐 제거 + 위험 해소 토스트.
  // close()는 acknowledged=false 로 호출 (운영자 자발 확인이 아닌 자동 해소).
  _handleResolved(data) {
    const eventId = data.event_id;
    if (eventId == null) return;
    if (this.isOpen && this._currentId === eventId) {
      this.close({ acknowledged: false });
    }
    // 큐에 같은 event_id 가 남아있어도 자연 닫힘
    this.queue = this.queue.filter(d => (d.event_id || d.id) !== eventId);
    // T5 — 운영자가 "조치 완료" 누른 시점에 본인 _AckStore 도 동기 삭제. 같은
    // source 다음 신규 Event 가 (다른 event_id) 도착하면 _AckStore 통과 → 모달
    // 정상 등장. 진단 문서 §7 옵션 (b) — 멘탈 모델 정합.
    _AckStore.remove(eventId);
    // 우하단 토스트로 "위험 해소" 안내 (AlarmToast 재사용)
    if (typeof AlarmToast !== 'undefined') {
      AlarmToast.show({
        source_label: data.source_label || data.sensor_name || '',
        message: '위험 해소',
      });
    }
  },

  // fallback 폴링 — WS 가 60s 이상 끊긴 상태 지속 시 시작, 재연결 시 중단.
  // ws-client.js 의 onFallbackStart/End 콜백이 트리거. catch-up endpoint 를 30s 주기로
  // 호출해 _runCatchUp 흐름 그대로 재활용 (lastSeen 자동 갱신 + newAlarmEvent dispatch).
  _fallbackPollingTimer: null,

  _startFallbackPolling() {
    if (this._fallbackPollingTimer) return;     // 중복 시작 차단
    console.info('[AlarmPopup] WS 60s 지속 끊김 — catch-up 폴링 시작 (30s 주기)');
    this._fallbackPollingTimer = setInterval(() => this._runCatchUp(), 30_000);
  },

  _stopFallbackPolling() {
    if (!this._fallbackPollingTimer) return;
    clearInterval(this._fallbackPollingTimer);
    this._fallbackPollingTimer = null;
    console.info('[AlarmPopup] WS 재연결 — fallback 폴링 중단');
  },

  // 페이지 load / WS 재연결 시점 catch-up — drf 의 /alerts/api/alarms/catch-up/?since=
  // 을 호출해서 끊김 중 발생한 알람을 보충. 받은 알람은 newAlarmEvent CustomEvent 로
  // 발행하여 이벤트 패널에 누적 (is_new_event=false 라 팝업은 자연 skip — 지나간 알람).
  async _runCatchUp() {
    const lastSeen = _LastSeen.read();
    if (!lastSeen) return;  // 초기 방문 — catch-up 의미 없음
    try {
      const url = `/alerts/api/alarms/catch-up/?since=${lastSeen}`;
      const res = (typeof Auth !== 'undefined' && Auth.apiFetch)
        ? await Auth.apiFetch(url)
        : await fetch(url, { credentials: 'include' });
      if (!res || !res.ok) return;
      const body = await res.json();
      const alarms = body.alarms || [];
      if (alarms.length === 0) return;
      console.info(`[AlarmPopup] catch-up: ${alarms.length} missed alarms restored`);
      for (const a of alarms) {
        window.dispatchEvent(new CustomEvent('newAlarmEvent', { detail: a }));
        // last_seen 갱신은 dispatched 측에서 처리되지 않을 수도 있으니 안전하게 직접
        const tsMs = new Date(a.created_at).getTime();
        if (Number.isFinite(tsMs)) _LastSeen.write(Math.floor(tsMs / 1000));
      }
    } catch (e) {
      console.warn('[AlarmPopup] catch-up failed:', e);
    }
  },

  _goDetail() {
    const id = this._currentId;
    // 큐는 유지한 채 현재 팝업만 닫고 상세 페이지로 이동.
    // 누락 카운트는 reset — 운영자가 이력 페이지에서 확인 의사.
    clearTimeout(this._autoCloseTimer);
    clearTimeout(this._gapTimer);
    this._currentId = null;
    this._currentLevel = null;
    this._currentChannel = null;
    this._currentAlarmType = null;
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
    // "확인 완료" — 2026-05-15 알람 재설계:
    //   1) 로컬 Set 즉시 추가 (서버 응답 대기 X — UI 반응성)
    //   2) 백엔드 ack API 호출 (EventAcknowledgement row 생성, 운영 이력)
    //   3) 팝업 close + droppedCount reset
    // fire-and-forget — 네트워크 실패해도 로컬 Set 으로 본인 클라 표시는 정상 차단.
    document.getElementById('alarm-popup-confirm')?.addEventListener('click', () => {
      const eventId = this._currentId;
      if (eventId != null) {
        _AckStore.add(eventId);
        const url = `/alerts/api/events/${eventId}/ack/`;
        const promise = (typeof Auth !== 'undefined' && Auth.apiFetch)
          ? Auth.apiFetch(url, { method: 'POST' })
          : fetch(url, { method: 'POST', credentials: 'include' });
        Promise.resolve(promise).catch(err => {
          console.warn('[AlarmPopup] ack API failed:', err);
        });
      }
      this.close({ acknowledged: true });
    });
    document.getElementById('alarm-popup-detail')    ?.addEventListener('click', () => this._goDetail());
    // 누락 배지 클릭 시 이벤트 이력 페이지로 — 누락된 알람을 운영자가 확인 가능
    document.getElementById('alarm-popup-drop-badge')?.addEventListener('click', () => this._goDetail());

    // 페이지 load 시점에 WS 끊김 중 미수신 알람 보충 (비동기 fire-and-forget).
    this._runCatchUp();

    // Phase 2 — WS 라이프사이클 hook (alarm-system-redesign.md C 옵션):
    //   • onOpen        — 재연결마다 catch-up 재호출 (token 만료 → refresh 후 재연결 포함)
    //   • onFallbackStart — 60s 지속 끊김 → 30s 폴링으로 degrade
    //   • onFallbackEnd   — 재연결 성공 → 폴링 중단
    // WSClient cache 가 path 기반(F5 보강)이라 alarm-ws.js 와 같은 instance 공유 — 중복
    // 연결 발생 안 함. WSClient 미로드 페이지(예: 로그인 화면)는 silent skip.
    if (typeof WSClient !== 'undefined') {
      const ws = WSClient.connect('/ws/sensors/', { attachToken: true });
      ws.onOpen(() => this._runCatchUp());
      ws.onFallbackStart(() => this._startFallbackPolling());
      ws.onFallbackEnd(() => this._stopFallbackPolling());
    }
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
