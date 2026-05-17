/* ==========================================================
   event-panel.js — MN-03 이벤트 현황 패널
   출처: alarm_panel.html 인라인 스크립트
   의존: auth.js (Auth.apiFetch), shared/alarm-ws.js (newAlarmEvent dispatch),
        shared/level-mapper.js (LevelMapper)

   [원안 디자인 충실 구현 — 2026-05-15]
   - 알람 종류별 좌측 아이콘 (작업자/가스/전력/구역)
   - WS newAlarmEvent 실시간 prepend
   - 24h 합계 하단 배치 (원안 mockup)
   - 미확인 카운트 (active+ack+in_progress) 강조 표시
   - 새 항목 fadeIn + border 강조 (3초)
   - 개별 항목 클릭 → 이벤트 상세 페이지
   ========================================================== */

'use strict';

// ──────────────────────────────────────────────────────────
// MN-03 — 이벤트 현황 패널 (API 동적 로드 + WS 실시간 갱신)
// ──────────────────────────────────────────────────────────
const EventPanel = {

  // alarm_type → Lucide 아이콘 이름 (lucide.dev). 이모지 → 단색 SVG 로 전환 (2026-05-17).
  // CDN 은 main.html 에서 로드. 동적 추가된 element 는 addItem/addToClearGroup 끝에서
  // lucide.createIcons() 로 [data-lucide] 속성 element 를 SVG 로 replace. 색은 currentColor
  // 라 텍스트 색 (위험도) 자동 적용. 디자이너 SVG 받으면 본 매핑 그대로 갈아끼우면 됨.
  ICON_BY_TYPE: {
    gas_threshold:        'flame',
    gas_clear:            'circle-check',
    power_overload:       'zap',
    power_anomaly_ai:     'brain-circuit',
    power_clear:          'circle-check',
    geofence_intrusion:   'map-pin',
    sensor_fault:         'shield-alert',
    ppe_violation:        'hard-hat',
    vr_training_not_done: 'graduation-cap',
    safety_check_pending: 'clipboard-check',
    inspection_scheduled: 'wrench',
    batch_failed:         'circle-x',
    storage_overdue:      'package-x',
  },

  // 같은 패널 안에 동일 항목이 중복 추가되지 않도록 추적.
  // WS dispatch (실시간) 와 loadEventList (페이지 로드), 그리고 백엔드 dedup TTL
  // 만료 후 재푸시가 같은 항목을 다시 보내도 시각적으로 1번만 노출.
  // event_id 있으면 그 값을, 없는 정상화/지오펜스류는 (alarm_type, source, 분단위) 합성 키.
  _seenKeys: new Set(),

  // burst 그룹화 대상 — 정상화는 디바이스별로 N건 도착해도 패널에 1줄.
  // 백엔드 fingerprint dedup 은 source_label 단위라 가스 9 종은 이미 1건이지만
  // 전력 디바이스 N개의 동시 정상화는 N건 도착 → 본 그룹화가 같은 분(minute) 안
  // 같은 alarm_type 을 1줄로 묶고 "외 N건" 배지로 표시.
  CLEAR_TYPES: new Set(['gas_clear', 'power_clear']),

  // 정상화 burst 그룹 — key=`clear:{alarm_type}:{minute_bucket}`,
  // value={ itemEl, sources[], moreEl, moreCountEl, sourcesEl }.
  _clearGroups: new Map(),

  _clearGroupKey(data) {
    const ts = data.created_at || data.timestamp;
    const minuteBucket = ts ? Math.floor(new Date(ts).getTime() / 60_000) : 0;
    return `clear:${data.alarm_type}:${minuteBucket}`;
  },

  // [Step 2-3] data 에서 dedup 키 1개 생성. event_id 가 진리값이라 우선.
  // event_id 없는 알람 (gas_clear/power_clear/지오펜스 일부) 은 같은 발생원의 분 단위
  // 버스트 (가스 9 종 동시 정상화) 를 1줄로 합치기 위해 minute_bucket 사용.
  _dedupKey(data) {
    const eventId = data.event ?? data.event_id ?? null;
    if (eventId !== null && eventId !== undefined) return `event:${eventId}`;
    const ts = data.created_at || data.timestamp;
    const minuteBucket = ts ? Math.floor(new Date(ts).getTime() / 60_000) : 0;
    const source = data.source_label || data.sensor_name || data.power_device_name || '';
    return `${data.alarm_type || 'unknown'}:${source}:${minuteBucket}`;
  },

  // ── 이벤트 항목 1개 추가 ────────────────────────────────
  addItem(data) {
    const listEl  = document.getElementById('event-list');
    const emptyEl = document.getElementById('event-empty');
    if (!listEl) return;

    // 정상화 알람은 같은 분·같은 type 끼리 1줄 + "외 N건" 으로 묶기.
    // 일반 알람 흐름과 dedup/클릭/flash 의미가 달라 별도 경로.
    if (this.CLEAR_TYPES.has(data.alarm_type)) {
      this._addToClearGroup(data, listEl, emptyEl);
      this._trimList(listEl);
      return;
    }

    const dedupKey = this._dedupKey(data);
    // dedup — 이미 같은 키가 표시 중이면 시각 갱신 없이 skip.
    if (this._seenKeys.has(dedupKey)) return;
    this._seenKeys.add(dedupKey);

    const eventId = data.event ?? data.event_id ?? null;

    if (emptyEl) emptyEl.remove();

    const colorClass = LevelMapper.toTextClass(data.alarm_level);
    // [P0-1] label fallback 확장 — power_device_name / geofence_name / source_label 추가.
    //   이전: sensor_name || worker_name → power 알람이 "알 수 없음" 표시되던 버그.
    //   WS payload (alarm-mapper.fromSensorsAlarm) 는 source_label 만, API 응답
    //   (AlarmRecordSerializer) 은 발생원별 4 필드 → 양쪽 모두 커버.
    const label =
      data.sensor_name ||
      data.power_device_name ||
      data.worker_name ||
      data.geofence_name ||
      data.source_label ||
      '알 수 없음';
    const time = data.created_at
      ? (typeof TimeFormat !== 'undefined' ? TimeFormat.short(data.created_at) : new Date(data.created_at).toLocaleTimeString())
      : (data.timestamp
          ? (typeof TimeFormat !== 'undefined' ? TimeFormat.short(data.timestamp) : new Date(data.timestamp).toLocaleTimeString())
          : '');
    const isResolved = data.status === 'resolved';
    // fallback 'bell' — ICON_BY_TYPE 에 없는 신규 alarm_type 도 안전하게 SVG 렌더.
    const icon       = this.ICON_BY_TYPE[data.alarm_type] || 'bell';

    const item = document.createElement('div');
    item.className       = 'event-item';
    item.style.opacity   = isResolved ? '0.5' : '1';
    // dedup key 를 dataset 에 보관 — LRU 제거 시 _seenKeys 에서 같이 정리.
    item.dataset.dedupKey = dedupKey;
    if (eventId !== null) {
      // [P2-2] 클릭 시 이벤트 상세 페이지로 이동.
      item.style.cursor    = 'pointer';
      item.dataset.eventId = String(eventId);
      item.addEventListener('click', () => {
        window.location.href = `/dashboard/monitoring/events/${eventId}/`;
      });
    }
    item.innerHTML = `
      <div class="event-head">
        <span><i data-lucide="${icon}" class="event-icon"></i>${label}</span>
        <span class="sub">${time}</span>
      </div>
      <div class="${colorClass} event-desc">${data.message || data.alarm_type || ''}</div>
    `;
    listEl.insertBefore(item, listEl.firstChild);

    // [P2-1] 새 항목 3초간 강조 (CSS 애니메이션 — event-item--new).
    // resolved 항목은 강조 안 함 (이미 옅게 표시되는 항목 = 옛 상태).
    if (!isResolved) {
      item.classList.add('event-item--new');
      setTimeout(() => item.classList.remove('event-item--new'), 3000);
    }

    this._trimList(listEl);
    // [data-lucide] 속성 element 를 SVG 로 replace (idempotent — 이미 SVG 인 건 무시).
    if (typeof lucide !== 'undefined') lucide.createIcons();
  },

  // ── 정상화 burst 그룹 추가/갱신 ──────────────────────────
  // 같은 분 안 같은 alarm_type 의 정상화 push 가 들어오면 첫 항목은 일반 알람처럼
  // 추가하고, 같은 분의 다음 정상화는 첫 항목에 "외 N건" 카운터 + sources 누적.
  _addToClearGroup(data, listEl, emptyEl) {
    const groupKey = this._clearGroupKey(data);
    const source =
      data.source_label ||
      data.sensor_name ||
      data.power_device_name ||
      '알 수 없음';

    const existing = this._clearGroups.get(groupKey);
    if (existing) {
      // 같은 그룹 내 새 source — 중복 source 는 카운트 안 늘림 (백엔드 dedup 보정).
      if (!existing.sources.includes(source)) {
        existing.sources.push(source);
        this._refreshClearGroup(existing);
      }
      return;
    }

    if (emptyEl) emptyEl.remove();

    const time = data.created_at
      ? (typeof TimeFormat !== 'undefined' ? TimeFormat.short(data.created_at) : new Date(data.created_at).toLocaleTimeString())
      : '';
    const colorClass = LevelMapper.toTextClass(data.alarm_level);
    const icon       = this.ICON_BY_TYPE[data.alarm_type] || 'bell';
    const message    = data.message || '정상 복귀';

    const item = document.createElement('div');
    item.className       = 'event-item event-item--clear-group';
    item.dataset.dedupKey = groupKey;
    item.innerHTML = `
      <div class="event-head">
        <span><i data-lucide="${icon}" class="event-icon"></i><span class="event-clear-label">${source}</span></span>
        <span class="sub">${time}</span>
      </div>
      <div class="${colorClass} event-desc">
        <span>${message}</span>
        <span class="event-clear-more" hidden>외 <span class="event-clear-more-count">0</span>건</span>
      </div>
      <ul class="event-clear-sources" hidden></ul>
    `;
    listEl.insertBefore(item, listEl.firstChild);
    // [data-lucide] 속성 element 를 SVG 로 replace (idempotent).
    if (typeof lucide !== 'undefined') lucide.createIcons();

    const moreEl = item.querySelector('.event-clear-more');
    const moreCountEl = item.querySelector('.event-clear-more-count');
    const sourcesEl = item.querySelector('.event-clear-sources');
    // "외 N건" 클릭 → 디바이스 source_label 목록 펼침/접힘.
    if (moreEl && sourcesEl) {
      moreEl.style.cursor = 'pointer';
      moreEl.addEventListener('click', (ev) => {
        ev.stopPropagation();
        sourcesEl.hidden = !sourcesEl.hidden;
      });
    }

    this._clearGroups.set(groupKey, {
      itemEl: item,
      sources: [source],
      moreEl,
      moreCountEl,
      sourcesEl,
    });

    item.classList.add('event-item--new');
    setTimeout(() => item.classList.remove('event-item--new'), 3000);
  },

  _refreshClearGroup(group) {
    const extra = group.sources.length - 1;
    if (extra > 0) {
      group.moreEl.hidden = false;
      group.moreCountEl.textContent = String(extra);
    }
    // sources 목록 갱신 — textContent 로 escape (source_label 은 시스템 입력이지만
    // XSS 방어 차원).
    group.sourcesEl.innerHTML = '';
    for (const s of group.sources) {
      const li = document.createElement('li');
      li.textContent = s;
      group.sourcesEl.appendChild(li);
    }
  },

  // ── LRU 정리 — 최대 20개 유지, 제거 시 dedup set/그룹 정리 ──
  _trimList(listEl) {
    while (listEl.children.length > 20) {
      const removed = listEl.lastChild;
      const removedKey = removed?.dataset?.dedupKey;
      if (removedKey) {
        this._seenKeys.delete(removedKey);
        this._clearGroups.delete(removedKey);
      }
      listEl.removeChild(removed);
    }
  },

  // ── 24시간 요약 카운트 + 미확인 카운트 갱신 ────────────
  // [P1-4] 24h 누적 (기존) + 현재 미확인 (신규) 함께 갱신.
  // 미확인 = Event.status ∈ {active, acknowledged, in_progress} — 운영자가 처리
  // 안 한 사건. 24h 누적과 별도로 "지금 처리 필요한 건수" 를 명확히.
  async loadSummary() {
    try {
      const res  = await Auth.apiFetch('/alerts/api/alarms/summary/');
      if (!res.ok) return;
      const data = await res.json();
      const dangerEl       = document.getElementById('summary-danger');
      const warningEl      = document.getElementById('summary-warning');
      const unackEl        = document.getElementById('summary-unack');
      const unackBoxEl     = document.getElementById('summary-unack-box');
      if (dangerEl)  dangerEl.textContent  = data.last_24h_danger  || 0;
      if (warningEl) warningEl.textContent = data.last_24h_warning || 0;
      if (unackEl)   unackEl.textContent   = data.unacknowledged_event_count || 0;
      // 미확인 0건이면 박스 숨김 — 운영 평온 시 UI 깨끗.
      if (unackBoxEl) {
        const cnt = data.unacknowledged_event_count || 0;
        unackBoxEl.style.display = cnt > 0 ? '' : 'none';
      }
    } catch {
      // 실패 시 카운트 유지
    }
  },

  // ── 최근 이벤트 목록 로드 ────────────────────────────────
  // [P1-3] 위험도 + 시간 정렬. 백엔드 API ordering 미지원 시 클라이언트 정렬.
  async loadEventList() {
    try {
      const res  = await Auth.apiFetch('/alerts/api/alarms/?ordering=-created_at&limit=10');
      if (!res.ok) return;
      const data = await res.json();
      const list = Array.isArray(data) ? data : (data.results || []);
      // 위험도 우선 (danger > warning > normal), 같으면 최근 시간.
      // 백엔드 정렬은 created_at 만이라 위험도는 클라이언트 보강.
      const riskOrder = { danger: 2, warning: 1, normal: 0 };
      list.sort((a, b) => {
        const ra = riskOrder[a.alarm_level || a.risk_level] ?? 0;
        const rb = riskOrder[b.alarm_level || b.risk_level] ?? 0;
        if (rb !== ra) return rb - ra;
        return new Date(b.created_at) - new Date(a.created_at);
      });
      // insertBefore(firstChild) 가 역순으로 prepend 하므로 리스트는 reverse 후 forEach.
      list.reverse().forEach(item => this.addItem(item));
      await this.loadSummary();
    } catch {
      // 실패 시 empty 상태 유지
    }
  },

  // ── WS 실시간 갱신 핸들러 ────────────────────────────────
  // [P0-2] alarm-ws.js 가 dispatch 하는 newAlarmEvent 받아 패널 상단에 prepend.
  // is_new_event=true 든 false 든 모두 추가 (dedup 은 addItem 안에서 event_id 로).
  _onNewAlarm(evt) {
    if (!evt?.detail) return;
    this.addItem(evt.detail);
    // 미확인 카운트도 즉시 +1 효과를 위해 summary 재조회.
    // 빈번한 API 호출 우려 — debounce 1초 (다중 알람 burst 시 1회만 조회).
    if (this._summaryDebounce) clearTimeout(this._summaryDebounce);
    this._summaryDebounce = setTimeout(() => this.loadSummary(), 1000);
  },

  init() {
    this.loadEventList();
    document.addEventListener('newAlarmEvent', (e) => this._onNewAlarm(e));
  },
};
