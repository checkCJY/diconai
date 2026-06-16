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

  // T1+T6 — alarm_type 코드 → 한국어 라벨 fallback (드물게 sensor_name/source_label
  // 누락 시 운영자가 영문 코드 보지 않도록). drf-server/apps/core/constants.py 의
  // AlarmType.choices 와 동기 유지. 본 dict 에 없으면 '알 수 없음'.
  LABEL_BY_TYPE: {
    gas_threshold:        '가스 경보',
    gas_clear:            '가스 정상 복귀',
    power_overload:       '전력 이상',
    power_anomaly_ai:     '전력 AI 이상 감지',
    power_clear:          '전력 정상 복귀',
    geofence_intrusion:   '위험구역 진입',
    sensor_fault:         '센서 이상',
    ppe_violation:        'PPE 미착용',
    vr_training_not_done: 'VR 교육 미이수',
    safety_check_pending: '작업 안전 체크리스트 미완료',
    inspection_scheduled: '점검 예정',
    batch_failed:         '배치 실패',
    storage_overdue:      '보관 주기 실패',
    gas_anomaly_ai:       '가스 AI 이상 감지',
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

  // source 단위 그룹 (2026-05-17) — 같은 가스 센서/전력 장비/지오펜스에서 30분 윈도우
  // 내 발생한 일반 알람을 1줄 + "외 N건" 으로 묶음. 정상화는 _clearGroups 로 별도.
  // 헤더 = 첫 발생 알람 (메시지·시간 고정 — 사용자 결정: 이상 추적 출발점).
  // 위험도 색상만 그룹 안 최고로 갱신. 펼치면 첫 알람 제외 추가 알람 list (최신 위).
  // value={ itemEl, items: [data], moreEl, moreCountEl, otherTypesEl, itemsEl, descEl,
  //         firstAlarmType, maxLevel, maxLevelColorClass }.
  _sourceGroups: new Map(),

  _sourceGroupKey(data) {
    const ts = data.created_at || data.timestamp;
    // 30분 bucket = floor(ts ms / 1_800_000). 같은 운영 세션 의미 단위.
    const bucket = ts ? Math.floor(new Date(ts).getTime() / 1_800_000) : 0;
    const source =
      data.source_label || data.sensor_name || data.power_device_name || 'unknown';
    return `source:${source}:${bucket}`;
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

    // event_id 기준 dedup (백엔드 dedup TTL 만료 후 재푸시 차단 — 같은 event 두 번 X).
    const dedupKey = this._dedupKey(data);
    if (this._seenKeys.has(dedupKey)) return;
    this._seenKeys.add(dedupKey);

    // source 단위 그룹화로 위임 (2026-05-17 결정):
    //   첫 도착 → 일반 줄 외형 + 그룹 데이터 등록 ("외 N건"·펼침 hidden 상태)
    //   두 번째 도착부터 → "외 N건" 보이게 + 위험도 색 갱신 + 펼침 list 채움
    // 헤더 = 첫 발생 알람 (메시지·시간 고정 — 이상 추적 출발점).
    this._addToSourceGroup(data, listEl, emptyEl);
    this._trimList(listEl);
  },

  // ── 정상화 burst 그룹 추가/갱신 ──────────────────────────
  // 같은 분 안 같은 alarm_type 의 정상화 push 가 들어오면 첫 항목은 일반 알람처럼
  // 추가하고, 같은 분의 다음 정상화는 첫 항목에 "외 N건" 카운터 + sources 누적.
  _addToClearGroup(data, listEl, emptyEl) {
    const groupKey = this._clearGroupKey(data);
    // T1+T6 — main fallback chain 과 동일. alarm_type 한글 라벨까지 fallback.
    const source =
      data.source_label ||
      data.sensor_name ||
      data.power_device_name ||
      this.LABEL_BY_TYPE[data.alarm_type] ||
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

  // ── source 단위 그룹 추가/갱신 (2026-05-17) ─────────────
  // 같은 가스 센서/전력 장비/지오펜스의 일반 알람을 30분 윈도우로 묶음.
  // 첫 도착은 일반 알람 줄과 외형 동일 ("외 N건"·펼침 hidden).
  // 두 번째부터 "외 N건" 보이게 + 다른 alarm_type 있으면 "+다른 유형 N건".
  _addToSourceGroup(data, listEl, emptyEl) {
    const groupKey = this._sourceGroupKey(data);
    const existing = this._sourceGroups.get(groupKey);

    if (existing) {
      // 두 번째 이상 도착 — 그룹 데이터 누적 + 헤더 카운트·색·펼침 list 갱신.
      // 헤더 메시지·시간은 첫 발생 고정 (사용자 결정 — 이상 추적 출발점).
      existing.items.push(data);
      this._refreshSourceGroup(existing, data);
      return;
    }

    if (emptyEl) emptyEl.remove();

    // 첫 도착 — 일반 알람 줄 외형으로 그룹 줄 생성.
    const eventId = data.event ?? data.event_id ?? null;
    const colorClass = LevelMapper.toTextClass(data.alarm_level);
    // [P0-1] label fallback 확장 — power_device_name / geofence_name / source_label 추가.
    //   WS payload (alarm-mapper.fromSensorsAlarm) 는 source_label 만, API 응답
    //   (AlarmRecordSerializer) 은 발생원별 4 필드 → 양쪽 모두 커버.
    // [P0-1] label fallback chain. T1+T6 — 최후 fallback 으로 alarm_type 한글 라벨
    // (constants.AlarmType.choices 동기, '알 수 없음' 영문 코드 노출 방지).
    const label =
      data.sensor_name ||
      data.power_device_name ||
      data.worker_name ||
      data.geofence_name ||
      data.source_label ||
      this.LABEL_BY_TYPE[data.alarm_type] ||
      '알 수 없음';
    const time = data.created_at
      ? (typeof TimeFormat !== 'undefined' ? TimeFormat.short(data.created_at) : new Date(data.created_at).toLocaleTimeString())
      : (data.timestamp
          ? (typeof TimeFormat !== 'undefined' ? TimeFormat.short(data.timestamp) : new Date(data.timestamp).toLocaleTimeString())
          : '');
    const isResolved = data.status === 'resolved';
    const icon = this.ICON_BY_TYPE[data.alarm_type] || 'bell';

    const item = document.createElement('div');
    item.className = 'event-item event-item--source-group';
    // T4 — source 가 cover 면 행 톤도 노랑 (CSS .alarm-popup-static-cover 재사용 —
    // 모달·토스트·이벤트 패널 3 곳이 같은 톤 사전).
    const tone = (typeof AlarmMapper !== 'undefined') ? AlarmMapper.sourceTone(data.alarm_source) : 'risk';
    if (tone === 'cover') item.classList.add('alarm-popup-static-cover');
    item.style.opacity = isResolved ? '0.5' : '1';
    // dataset.dedupKey = groupKey (LRU 제거 시 _sourceGroups 정리 매칭).
    item.dataset.dedupKey = groupKey;
    if (eventId !== null) {
      // 헤더 클릭 = 첫 발생 event 상세 (이상 추적 출발점).
      // "외 N건" 배지 / 펼침 list li 는 stopPropagation 으로 본 클릭 차단.
      item.style.cursor = 'pointer';
      item.dataset.eventId = String(eventId);
      item.addEventListener('click', () => {
        window.location.href = `/dashboard/monitoring/events/${eventId}/`;
      });
    }
    // T4 — cover 배지 한 줄 (사유 라벨 — "AI 미탐 의심" 등). 빈 문자열이면 미렌더.
    const coverLabel = (typeof AlarmMapper !== 'undefined') ? AlarmMapper.sourceBadge(data.alarm_source) : '';
    const coverHtml = coverLabel ? `<span class="cover-badge event-cover-badge">${coverLabel}</span>` : '';
    item.innerHTML = `
      <div class="event-head">
        <span><i data-lucide="${icon}" class="event-icon"></i>${label}</span>
        <span class="sub">${time}</span>
      </div>
      <div class="${colorClass} event-desc">
        <span>${data.message || data.alarm_type || ''}</span>
        ${coverHtml}
        <span class="event-source-more" hidden> · 외 <span class="event-source-more-count">0</span>건<span class="event-source-other-types"></span></span>
      </div>
      <ul class="event-source-items" hidden></ul>
    `;
    listEl.insertBefore(item, listEl.firstChild);
    if (typeof lucide !== 'undefined') lucide.createIcons();

    const moreEl = item.querySelector('.event-source-more');
    const moreCountEl = item.querySelector('.event-source-more-count');
    const otherTypesEl = item.querySelector('.event-source-other-types');
    const itemsEl = item.querySelector('.event-source-items');
    const descEl = item.querySelector('.event-desc');

    // "외 N건" 클릭 → 펼침/접힘 토글. stopPropagation 으로 헤더 event 상세 이동 차단.
    if (moreEl && itemsEl) {
      moreEl.style.cursor = 'pointer';
      moreEl.addEventListener('click', (ev) => {
        ev.stopPropagation();
        itemsEl.hidden = !itemsEl.hidden;
      });
    }

    this._sourceGroups.set(groupKey, {
      itemEl: item,
      items: [data],
      moreEl,
      moreCountEl,
      otherTypesEl,
      itemsEl,
      descEl,
      firstAlarmType: data.alarm_type,
      maxLevel: data.alarm_level || 'normal',
      maxLevelColorClass: colorClass,
    });

    if (!isResolved) {
      item.classList.add('event-item--new');
      setTimeout(() => item.classList.remove('event-item--new'), 3000);
    }
  },

  // 그룹 두 번째 이상 알람 도착 시 헤더 카운트·다른 유형·위험도 색·펼침 list 갱신.
  // 헤더 메시지·시간은 갱신 안 함 (첫 발생 고정).
  _refreshSourceGroup(group, newData) {
    // 첫 발생 제외 추가 건수 = items.length - 1.
    const extra = group.items.length - 1;
    group.moreEl.hidden = extra <= 0;
    group.moreCountEl.textContent = String(extra);

    // 다른 alarm_type 카운트 — 첫 발생 type 과 다른 type 의 unique 개수.
    const otherTypes = new Set();
    for (const d of group.items) {
      if (d.alarm_type && d.alarm_type !== group.firstAlarmType) {
        otherTypes.add(d.alarm_type);
      }
    }
    group.otherTypesEl.textContent =
      otherTypes.size > 0 ? ` (+다른 유형 ${otherTypes.size}건)` : '';

    // 위험도 색 갱신 — 그룹 안 최고 위험도 (메시지·시간은 첫 발생 고정).
    const levelOrder = { normal: 0, warning: 1, danger: 2 };
    const newRank = levelOrder[newData.alarm_level] ?? 0;
    const curRank = levelOrder[group.maxLevel] ?? 0;
    if (newRank > curRank) {
      const newColorClass = LevelMapper.toTextClass(newData.alarm_level);
      if (group.maxLevelColorClass) {
        group.descEl.classList.remove(group.maxLevelColorClass);
      }
      group.descEl.classList.add(newColorClass);
      group.maxLevel = newData.alarm_level;
      group.maxLevelColorClass = newColorClass;
    }

    // 펼침 list — 첫 발생 제외, 시간 내림차순 (최신 위 — 사용자 mockup).
    group.itemsEl.innerHTML = '';
    const additional = group.items.slice(1).slice().sort((a, b) => {
      const tsA = new Date(a.created_at || a.timestamp || 0).getTime();
      const tsB = new Date(b.created_at || b.timestamp || 0).getTime();
      return tsB - tsA;
    });
    for (const d of additional) {
      const li = document.createElement('li');
      const iconName = this.ICON_BY_TYPE[d.alarm_type] || 'bell';
      const liTime = d.created_at
        ? (typeof TimeFormat !== 'undefined' ? TimeFormat.short(d.created_at) : new Date(d.created_at).toLocaleTimeString())
        : '';
      const liMsg = d.message || d.alarm_type || '';
      const liEventId = d.event ?? d.event_id ?? null;
      const liColorClass = LevelMapper.toTextClass(d.alarm_level);
      li.innerHTML = `<i data-lucide="${iconName}" class="event-source-li-icon"></i><span class="${liColorClass}">${liMsg}</span><span class="event-source-li-time">${liTime}</span>`;
      if (liEventId !== null) {
        li.style.cursor = 'pointer';
        li.addEventListener('click', (ev) => {
          ev.stopPropagation();  // 헤더 클릭 (첫 event 상세) 차단
          window.location.href = `/dashboard/monitoring/events/${liEventId}/`;
        });
      }
      group.itemsEl.appendChild(li);
    }
    if (typeof lucide !== 'undefined') lucide.createIcons();
  },

  // ── LRU 정리 — 최대 20개 유지, 제거 시 dedup set/그룹 정리 ──
  _trimList(listEl) {
    while (listEl.children.length > 20) {
      const removed = listEl.lastChild;
      const removedKey = removed?.dataset?.dedupKey;
      if (removedKey) {
        this._seenKeys.delete(removedKey);
        this._clearGroups.delete(removedKey);
        // source 그룹 제거 시 그룹 안 모든 event_id 의 _seenKeys 도 같이 정리
        // (같은 알람이 후에 다시 들어오면 다시 표시 가능하도록).
        const sourceGroup = this._sourceGroups.get(removedKey);
        if (sourceGroup) {
          for (const d of sourceGroup.items) {
            const eid = d.event ?? d.event_id ?? null;
            if (eid !== null) this._seenKeys.delete(`event:${eid}`);
          }
          this._sourceGroups.delete(removedKey);
        }
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
