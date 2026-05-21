# 알람 Phase 2 완성 + 이벤트 패널 UX — 데이터 흐름 + 중요 함수 분석

작성일: 2026-05-17
대상 작업: `feature/alarm-phase2-global-loading` 의 7 commit (830a769 ~ 56b0c1b)
관련 문서: [`drf-server/docs/refactoring/alarm-phase2-completion-2026-05-17.md`](../../../drf-server/docs/refactoring/alarm-phase2-completion-2026-05-17.md) (배경·결정·검증)

본 문서는 **"코드가 어떻게 흐르는지"** 와 **"어떤 함수가 핵심인지"** 에 집중. 변경 의도·결정 근거는 위 refactoring 문서 참조.

---

## 1. 범위 — 변경 영역

```
drf-server (Django + DRF)                fastapi-server (FastAPI)
├── apps/alerts/                         ├── power/services/
│   ├── models/
│   │   └── alarm_record.py ★            │   └── power_service.py
│   ├── migrations/
│   │   └── 0016_alarmrecord_channel.py ★★
│   ├── serializers/
│   │   └── anomaly_alarm_record.py
│   ├── services/event_service.py
│   ├── tasks.py
│   ├── views/anomaly_alarm_record.py
│   └── views/alarm_record.py
├── apps/facilities/models/devices.py ★★ (PowerDevice 메서드 신규)
├── apps/monitoring/services/power_alarm.py
├── static/js/shared/
│   ├── ws-client.js ★★ (가장 큰 변경)
│   └── alarm-popup.js ★
├── static/js/dashboard/panels/event-panel.js ★★
├── static/css/components/header.css ★ (스크롤바)
├── static/css/admin.css ★ (스크롤바)
├── static/css/dashboard.css ★ (event-icon SVG / source-group)
└── templates/dashboard/main.html (Lucide CDN)

★★ 큰 변경 / 신규 메서드 / 신규 migration
★ 주요 변경
```

---

## 2. 데이터 흐름

본 세션 작업은 **4 개의 독립 흐름** + **1 개의 정적 디자인 변경** 으로 분리해서 추적.

### 2.1 WS 재연결 — 토큰 만료 자동 refresh (묶음 A)

```
[브라우저 — WebSocket 사용 페이지 시작]
     │
     ▼
[WSClient.connect(path, { attachToken: true })]
     │ cacheKey = `${path}:${JSON.stringify(opts)}`
     │ ↑ 변경: 이전 key=full URL → token 갱신 후 race 가능
     │ _cache.get(cacheKey) 또는 신규 instance 생성 (closure)
     ▼
[_open()]
     │ currentUrl = _resolveUrl(path, opts)
     │ ↑ 변경: 매번 재계산 — refresh 직후 새 토큰 보장
     │ ws = new WebSocket(currentUrl)
     ▼
[정상 연결 시 ws.onopen]
     │ attempts = 0 (백오프 리셋)
     │ _clearFallbackState() (끊김 중이면 fallback 종료 시그널)
     │ _dispatch(openHandlers)
     │
     │ ───────────────────────────────────────
     │
[비정상 close 시 ws.onclose async]
     │ _dispatch(closeHandlers, e)
     │
     ├─ if (e.code===1008 && e.reason==="unauthenticated" && opts.attachToken)
     │    │ ▶ 토큰 만료 분기 (신규)
     │    │ Auth._refresh()  ← _refreshing Promise 가드로 동시 호출 시 1회만
     │    │   ├─ fetch POST /api/auth/token/refresh/
     │    │   ├─ localStorage.access_token 갱신
     │    │   └─ true 반환
     │    │ if (refreshed && !closed) {
     │    │     attempts = 0
     │    │     _open()  ← 새 토큰으로 즉시 재연결, 백오프 우회
     │    │     return
     │    │ }
     │    │
     │    │ refresh 실패면 fall through
     │    ▼
     │
     ├─ _startFallbackTimer()  ← 60s 지속 시 발동, 이미 가동/진입 상태면 noop
     │    │ setTimeout(60_000, () => {
     │    │     inFallback = true
     │    │     _dispatch(fallbackStartHandlers)
     │    │ })
     │
     └─ _scheduleReconnect()
          │ attempts++
          │ delay = INITIAL_DELAY * 2^(attempts-1), MAX 30s, jitter ±30%
          │ setTimeout(_open, delay)
```

#### 핵심 변경점
1. **cache key 변경** (`ws-client.js:32`) — URL → (path + opts hash). token 갱신 후 race 차단
2. **`_open()` 안 URL 재계산** — refresh 직후 새 토큰으로 connect
3. **onclose async + token refresh 분기** — code/reason 검사 → `Auth._refresh()` 호출
4. **신규 fallback 인프라** — `_startFallbackTimer`, `_clearFallbackState`, `fallbackStartHandlers/EndHandlers`, `onFallbackStart/End` 메서드

### 2.2 60s 끊김 fallback 폴링 (묶음 A)

```
[fastapi 다운 또는 네트워크 끊김]
     │
     ▼
[WSClient.ws.onclose 발동 (60s 지속)]
     │ _startFallbackTimer() — 첫 close 시점부터 60s 타이머
     │ ...
     │ 60s 경과 후
     │ inFallback = true
     │ _dispatch(fallbackStartHandlers)
     ▼
[AlarmPopup._startFallbackPolling]  ← onFallbackStart 구독
     │ console.info("[AlarmPopup] WS 60s 지속 끊김 — catch-up 폴링 시작 (30s 주기)")
     │ this._fallbackPollingTimer = setInterval(_runCatchUp, 30_000)
     ▼
[_runCatchUp 호출 (30s 마다)]
     │ lastSeen = _LastSeen.read()  ← localStorage 의 마지막 알람 timestamp
     │ if (!lastSeen) return  ← 초기 방문 — catch-up 의미 없음
     │ Auth.apiFetch(`/alerts/api/alarms/catch-up/?since=${lastSeen}`)
     ▼
[drf-server alarm_record.AlarmRecordViewSet.catch_up]
     │ since_dt = datetime.fromtimestamp(float(since_str))
     │ floor = now - 24h
     │ since_dt = max(since_dt, floor)  ← 24h 클램프
     │ alarms = AlarmRecord.objects
     │     .filter(created_at__gte=since_dt)
     │     .select_related("event", "power_device")  ← N+1 회피
     │     .order_by("created_at")[:100]
     │ return [
     │     { event_id, alarm_type, risk_level, source_label, summary,
     │       message: a.get_short_message(), ... }
     │     for a in alarms
     │ ]
     ▼
[AlarmPopup._runCatchUp 본문]
     │ for a in alarms:
     │     window.dispatchEvent(new CustomEvent('newAlarmEvent', { detail: a }))
     │     _LastSeen.write(Math.floor(new Date(a.created_at).getTime() / 1000))
     ▼
[EventPanel.addItem (newAlarmEvent listener)]
     │ — 일반 알람 흐름: _addToSourceGroup 으로 위임 (2.3 참조)
     │ — is_new_event=false 라 팝업은 자연 skip (지나간 알람)

[연결 복귀 시 ws.onopen]
     │ _clearFallbackState()
     │ ├─ clearTimeout(fallbackTimer)
     │ └─ if (inFallback) {
     │       inFallback = false
     │       _dispatch(fallbackEndHandlers)
     │   }
     ▼
[AlarmPopup._stopFallbackPolling]  ← onFallbackEnd 구독
     │ clearInterval(this._fallbackPollingTimer)
     │ console.info("[AlarmPopup] WS 재연결 — fallback 폴링 중단")
```

### 2.3 이벤트 패널 source 단위 그룹화 (묶음 B)

```
[WS broadcast 또는 페이지 load API]
     │ 알람 도착
     ▼
[event-panel.js EventPanel.addItem(data)]
     │
     ├─ if (CLEAR_TYPES.has(data.alarm_type))
     │    ▶ 정상화 burst 경로 — _addToClearGroup (변경 없음)
     │    return
     │
     │ event_id 기준 dedup
     │ dedupKey = `event:${event_id}` 또는 합성 키
     │ if (_seenKeys.has(dedupKey)) return
     │ _seenKeys.add(dedupKey)
     ▼
[_addToSourceGroup(data, listEl, emptyEl)]
     │ groupKey = `source:${source_label}:${30min_bucket}`  ★ 신규
     │ existing = _sourceGroups.get(groupKey)
     │
     ├─ if (existing)
     │    ▶ 두 번째 이상 도착 — 그룹 갱신
     │    existing.items.push(data)
     │    _refreshSourceGroup(existing, data)  ← 2.3a 참조
     │    return
     │
     │ ▶ 첫 도착 — 일반 알람 줄 외형으로 그룹 줄 생성
     │ item = createElement('div')
     │ item.className = 'event-item event-item--source-group'
     │ item.innerHTML = `
     │   <div class="event-head">
     │     <span><i data-lucide="${icon}" class="event-icon"></i>${label}</span>
     │     <span class="sub">${time}</span>
     │   </div>
     │   <div class="${colorClass} event-desc">
     │     <span>${message}</span>
     │     <span class="event-source-more" hidden>
     │       · 외 <span class="event-source-more-count">0</span>건
     │       <span class="event-source-other-types"></span>
     │     </span>
     │   </div>
     │   <ul class="event-source-items" hidden></ul>
     │ `
     │ listEl.insertBefore(item, listEl.firstChild)
     │ lucide.createIcons()  ← [data-lucide] → SVG replace
     │
     │ moreEl.addEventListener('click', e.stopPropagation + 펼침 토글)
     │ item.addEventListener('click', e => window.location = `/.../events/${first_event_id}/`)
     │
     │ _sourceGroups.set(groupKey, {
     │     itemEl, items: [data], moreEl, moreCountEl, otherTypesEl, itemsEl,
     │     descEl, firstAlarmType, maxLevel, maxLevelColorClass
     │ })
     ▼
[_trimList(listEl)]
     │ while (listEl.children.length > 20)
     │     removed = listEl.lastChild
     │     removedKey = removed.dataset.dedupKey
     │     _seenKeys.delete(removedKey)
     │     _clearGroups.delete(removedKey)
     │     # source 그룹 정리 — 그룹 안 모든 event_id 의 _seenKeys 도 같이 정리 ★ 신규
     │     sourceGroup = _sourceGroups.get(removedKey)
     │     if (sourceGroup) {
     │         for (d of sourceGroup.items)
     │             _seenKeys.delete(`event:${d.event_id}`)
     │         _sourceGroups.delete(removedKey)
     │     }
     │     listEl.removeChild(removed)
```

#### 2.3a `_refreshSourceGroup(group, newData)` — 두 번째 이상 도착 시

```
[그룹에 새 알람 추가]
     │
     │ extra = group.items.length - 1  ← 첫 발생 제외 추가 건수
     │ group.moreEl.hidden = extra <= 0
     │ group.moreCountEl.textContent = String(extra)
     │
     │ otherTypes = Set(d.alarm_type for d in items if d.alarm_type !== firstAlarmType)
     │ group.otherTypesEl.textContent = otherTypes.size > 0
     │     ? ` (+다른 유형 ${otherTypes.size}건)` : ''
     │
     │ # 위험도 색 갱신 — 그룹 안 최고 위험도 (메시지·시간은 첫 발생 고정)
     │ levelOrder = { normal: 0, warning: 1, danger: 2 }
     │ if (levelOrder[newData.alarm_level] > levelOrder[group.maxLevel]) {
     │     newColorClass = LevelMapper.toTextClass(newData.alarm_level)
     │     group.descEl.classList.remove(group.maxLevelColorClass)
     │     group.descEl.classList.add(newColorClass)
     │     group.maxLevel = newData.alarm_level
     │     group.maxLevelColorClass = newColorClass
     │ }
     │
     │ # 펼침 list — 첫 발생 제외, 시간 내림차순 (최신 위)
     │ group.itemsEl.innerHTML = ''
     │ additional = group.items.slice(1).sort((a, b) => tsB - tsA)
     │ for (d of additional)
     │     li = createElement('li')
     │     li.innerHTML = `<i data-lucide="${icon}"></i>
     │                     <span class="${liColorClass}">${liMsg}</span>
     │                     <span class="event-source-li-time">${liTime}</span>`
     │     li.addEventListener('click', e.stopPropagation + window.location = `/.../events/${d.event_id}/`)
     │     group.itemsEl.appendChild(li)
     │ lucide.createIcons()
```

### 2.4 채널 라벨 — 백엔드에서 message 까지 (묶음 B)

```
[Celery worker — fire_power_danger_task(device_id, channel, value, ...)]
     │ ← channel 이미 인자로 받고 있었음 (변경 없음)
     ▼
[event_service.create_alarm_and_event(..., channel=channel)]  ★ 인자 추가
     │
     ▼
[AlarmRecord.objects.create(..., channel=channel)]  ★ 필드 신규
     │ DB: alarm_record.channel = 2 (PostgreSQL/SQLite 양쪽 호환)
     │
     ▼
[Celery worker — _push_to_ws({..., "message": alarm.get_short_message()})]
     │
     ▼
[AlarmRecord.get_short_message() 호출 — 본 commit 8976109 시점]
     │ if power_device_id and measured_value is not None:
     │     prefix = ""
     │     if self.channel is not None and self.power_device is not None:
     │         prefix = f"{self.power_device.get_channel_label(self.channel)} "
     │     # ↑ channel_meta 조회 — select_related 로 N+1 회피
     │     if alarm_type == "power_anomaly_ai":
     │         return f"{prefix}AI 이상 패턴 감지 ({self.measured_value} W)"
     │     return f"{prefix}전력 임계치 초과 ({self.measured_value} W)"
     │
     │ ▶ 후속 변경 (2026-05-18 W4, commit 2df4fe4):
     │   AI 알람 분기에 ALGORITHM_SOURCE_LABEL 매핑 한 단계 추가 —
     │     label = ALGORITHM_SOURCE_LABEL.get(self.algorithm_source or "", "AI")
     │     return f"{prefix}{label} 이상 감지 ({measured_value} W)"
     │   채널 prefix 흐름은 그대로. 결과 예시:
     │   - "송풍기A IF+ARIMA 이상 감지 (7925.8 W)"
     │   - "송풍기A IF 이상 감지 (8000.0 W)"
     │   - algorithm_source NULL / 미매핑 → "AI" fallback
     ▼
[PowerDevice.get_channel_label(channel)]  ★ 모델 메서드 신규
     │ meta = (self.channel_meta or {}).get(str(channel)) or {}
     │ return meta.get("name") or f"CH{channel}"
     │ # 결과: "보조 모터 1" (등록) 또는 "CH2" (미등록 폴백)
     │
     ▼
[fastapi alarm_router → Redis push_alarm → alarm_flush_loop → 브라우저]
     │ payload.message = "보조 모터 1 전력 임계치 초과 (15.58 W)"
     │ (W4 후속 — AI 알람의 경우 "송풍기A IF+ARIMA 이상 감지 (7925.8 W)")
     │
     ▼
[alarm-mapper.fromSensorsAlarm(raw) → EventPanel.addItem]
     │ data.message = raw.message  ← inline 사용 (별도 처리 없음)
     │
     ▼
[event-panel.js DOM 렌더]
     │ <div class="event-desc">${data.message}</div>
     │ → 화면에 "보조 모터 1 전력 임계치 초과 (15.58 W)" 표시
```

#### 부수 흐름 — AI 이상 알람 (fastapi)

```
[fastapi power_service.process_anomaly_inference]
     │ IF 추론 → combined risk → 발화 조건 체크
     │
     ▼
[forward_inference_e2e(ml_payload, alarm_payload={..., channel}, push_payload, should_fire)]
     │ ↑ alarm_payload 에 channel 추가 (anomaly_meta 에 있던 channel 활용)
     ▼
[POST /alerts/api/anomaly-alarm-records/]
     │
     ▼
[drf AnomalyAlarmRecordCreateView]
     │ serializer = AnomalyAlarmRecordPayloadSerializer
     │ ↑ channel 필드 추가 (1~255, null 허용)
     │ create_alarm_and_event(..., channel=data.get("channel"))
     │ → 위 2.4 같은 흐름으로 AlarmRecord.channel 저장 + message 생성
```

### 2.5 정적 디자인 변경 — Lucide 아이콘 + 스크롤바

#### Lucide 아이콘
```
[main.html <head>]
     │ <script src="https://unpkg.com/lucide@latest"></script>
     │
[event-panel.js addItem / _addToClearGroup / _refreshSourceGroup]
     │ item.innerHTML = `... <i data-lucide="${iconName}"></i> ...`
     │ listEl.insertBefore(item, ...)
     │ lucide.createIcons()  ← idempotent — [data-lucide] 속성 element 만 <svg> 로 replace
     │
[CSS .event-icon]
     │ display: inline-block;
     │ width: 16px; height: 16px;
     │ stroke-width: 1.75;
     │ flex-shrink: 0;
     │ # stroke 는 currentColor (부모 텍스트 색 따라감)
```

#### 스크롤바
```
[header.css 또는 admin.css — 사이트별 공용 진입점]
     │ ::-webkit-scrollbar { width: 6px; height: 6px; }
     │ ::-webkit-scrollbar-track { background: transparent; }
     │ ::-webkit-scrollbar-thumb {
     │     background: var(--border);          ← 다크 (header.css)
     │     background: #cbd5e1;                ← 라이트 (admin.css)
     │     border-radius: 3px;
     │ }
     │ ::-webkit-scrollbar-thumb:hover {
     │     background: var(--text2);           ← 다크
     │     background: #94a3b8;                ← 라이트
     │ }
     │ * { scrollbar-width: thin; scrollbar-color: var(--border) transparent; }
     │
     │ # 브라우저 호환:
     │ #   - Webkit (Chrome/Edge/Safari): ::-webkit-scrollbar-* 의사 요소
     │ #   - Firefox: scrollbar-width / scrollbar-color (단순)
     │ #   - IE/legacy Edge: 미지원 — OS 기본 스크롤바 표시
```

---

## 3. 핵심 함수 / 메서드 list

### 3.1 ws-client.js (신규/변경 함수)

| 함수 | 위치 | 역할 | 의존성 |
|---|---|---|---|
| `_cacheKey(path, opts)` | ws-client.js:39 | path + opts 직렬화로 cache key 생성 | — |
| `_open()` | ws-client.js:115 | 매번 `_resolveUrl` 재호출 + WS 생성 + 이벤트 핸들러 등록. token refresh 분기 포함 | `_resolveUrl`, `Auth._refresh`, `_scheduleReconnect`, `_startFallbackTimer`, `_clearFallbackState` |
| `_startFallbackTimer()` | ws-client.js:96 | 60s setTimeout — 중복 발동 차단 (`fallbackTimer\|\|inFallback` 가드) | — |
| `_clearFallbackState()` | ws-client.js:105 | onopen / close() 시 호출 — timer cleanup + fallback 종료 dispatch | `_dispatch(fallbackEndHandlers)` |
| `onFallbackStart(fn)` | ws-client.js:163 | 신규 콜백 등록 — fallback 모드 진입 시 발동 | `_addHandler` |
| `onFallbackEnd(fn)` | ws-client.js:164 | 신규 콜백 등록 — fallback 모드 해제 시 발동 | `_addHandler` |

### 3.2 alarm-popup.js (신규 함수)

| 함수 | 위치 | 역할 | 의존성 |
|---|---|---|---|
| `_startFallbackPolling()` | alarm-popup.js:468 | `setInterval(_runCatchUp, 30_000)` 시작 | `_runCatchUp` |
| `_stopFallbackPolling()` | alarm-popup.js:474 | clearInterval + 상태 cleanup | — |
| `init()` 안 WSClient hook | alarm-popup.js:546 | sensors WS 의 `onOpen` / `onFallbackStart` / `onFallbackEnd` 구독 | `WSClient`, `_runCatchUp`, `_startFallbackPolling`, `_stopFallbackPolling` |

### 3.3 event-panel.js (신규 함수)

| 함수 | 위치 | 역할 | 의존성 |
|---|---|---|---|
| `_sourceGroupKey(data)` | event-panel.js:67 | `source:${source_label}:${30min_bucket}` 생성 | — |
| `_addToSourceGroup(data, listEl, emptyEl)` | event-panel.js:243 | 첫 도착 = 그룹 줄 생성, 두 번째 이상 = `_refreshSourceGroup` 위임 | `_sourceGroupKey`, `_refreshSourceGroup`, `lucide.createIcons` |
| `_refreshSourceGroup(group, newData)` | event-panel.js:336 | 카운트·다른 유형·위험도 색·펼침 list 갱신. 헤더 메시지·시간 갱신 안 함 (첫 발생 고정) | `LevelMapper`, `TimeFormat`, `lucide.createIcons` |
| `_trimList(listEl)` | event-panel.js:404 | LRU + `_sourceGroups` 정리 (그룹 안 모든 event_id 의 `_seenKeys` cleanup) | — |

### 3.4 백엔드 (신규/변경 메서드)

| 메서드 | 위치 | 역할 | 호출자 |
|---|---|---|---|
| `PowerDevice.get_channel_label(channel)` | facilities/models/devices.py:215 | channel_meta[str(ch)]["name"] 우선, 폴백 "CHn" | `power_alarm._channel_label`, `AlarmRecord.get_short_message` |
| `AlarmRecord.get_short_message` | alerts/models/alarm_record.py:128 | message 생성 — channel + `get_channel_label` prefix. (W4 후속: AI 알람 분기에 `ALGORITHM_SOURCE_LABEL` 매핑 추가 — "AI 이상 패턴 감지" → "IF+ARIMA 이상 감지" 등) | `tasks._push_to_ws` payload, `AlarmRecordSerializer.get_message`, `catch_up` endpoint |
| `create_alarm_and_event(..., channel=None)` | alerts/services/event_service.py:21 | AlarmRecord + Event 생성/병합 — 2 군데 `AlarmRecord.create()` 에 channel 전달 | `tasks.fire_power_*`, `AnomalyAlarmRecordCreateView.post` |
| `_channel_label(device, channel)` | monitoring/services/power_alarm.py:92 | `device.get_channel_label(channel)` thin wrapper — 시그니처 보존, 호출자 영향 0 | `power_alarm.py` 내부 (label 변수) |

---

## 4. 재활용 자산 (본 세션 핵심 학습 포인트)

본 세션 작업은 **기존 코드 재활용을 우선** ([memory `code_reuse_preference`](/home/cjy/.claude/projects/-home-cjy-diconai/memory/code_reuse_preference.md)) 한 결과로 신규 작성 라인 ↓.

### 4.1 Auth._refresh — race 가드 그대로 활용
```js
// Auth._refresh 의 _refreshing Promise 가드 (auth.js:51-77)
this._refreshing = (async () => { ... })();
try { return await this._refreshing; }
finally { this._refreshing = null; }
```
WSClient 가 자체 race 처리 안 하고 `Auth._refresh()` 직접 호출. 같은 페이지 sensors + positions + worker 3 WS 동시 만료 시 refresh 1회만 발생 — 검증 T4 통과.

### 4.2 _runCatchUp — 폴링 함수 재작성 X
```js
// alarm-popup.js:_runCatchUp (기존)
async _runCatchUp() {
    const lastSeen = _LastSeen.read();
    if (!lastSeen) return;
    const res = await Auth.apiFetch(`/alerts/api/alarms/catch-up/?since=${lastSeen}`);
    // ... newAlarmEvent dispatch + lastSeen 갱신
}
```
fallback 폴링은 같은 함수를 `setInterval` 로 호출. since= 자동 갱신, EventPanel dedup 자연, 신규 폴링 함수 작성 X.

### 4.3 정상화 burst (_clearGroups) → source 그룹 (_sourceGroups) 패턴
```js
// 같은 자료구조 패턴
_clearGroups: new Map()  // key=`clear:${alarm_type}:${minute_bucket}`
_sourceGroups: new Map()  // key=`source:${source_label}:${30min_bucket}`

// 같은 흐름 — 첫 도착 = 그룹 객체 등록, 두 번째 이상 = refresh 위임
_addToClearGroup(data, listEl, emptyEl)
_addToSourceGroup(data, listEl, emptyEl)
```

CSS 도 같은 패턴 — `.event-clear-more / .event-clear-sources` → `.event-source-more / .event-source-items`. CSS 규칙 따로 짜야 하지만 의도 명확 + 디자인 톤 일관.

### 4.4 power_alarm.\_channel_label → PowerDevice.get_channel_label
```python
# 기존 (monitoring/services/power_alarm.py:92)
def _channel_label(device, channel: int) -> str:
    meta = (device.channel_meta or {}).get(str(channel)) or {}
    return meta.get("name") or f"CH{channel}"

# 변경 후 — 모델 메서드로 끌어올림 (재활용 자산화)
# devices.py:215
def get_channel_label(self, channel: int) -> str:
    meta = (self.channel_meta or {}).get(str(channel)) or {}
    return meta.get("name") or f"CH{channel}"

# power_alarm.py:92 — thin wrapper 유지 (시그니처 보존)
def _channel_label(device, channel: int) -> str:
    return device.get_channel_label(channel)
```
같은 라벨 규칙이 두 곳 (서비스 + 모델 메서드) 에 있을 뻔한 중복을 단일화. `AlarmRecord.get_short_message` 도 `power_device.get_channel_label()` 호출 — single source of truth.

### 4.5 reconnectTimer 패턴 → fallbackTimer
```js
// 같은 setTimeout/clearTimeout 패턴
let reconnectTimer = null
let fallbackTimer = null  // 신규

function _scheduleReconnect() { reconnectTimer = setTimeout(_open, delay) }
function _startFallbackTimer() { fallbackTimer = setTimeout(() => dispatch, 60_000) }
```

### 4.6 `_dispatch(set, ...args)` + `_addHandler(set, fn)` 헬퍼
신규 콜백 `onFallbackStart/End` 의 등록·dispatch 가 기존 헬퍼 그대로 활용. 새 디스패치 시스템 작성 X.

---

## 5. 코드리뷰 관점

### 5.1 잘 된 점

1. **인터페이스 분리** — fallback 시그널을 `errorHandlers` 재사용이 아니라 신규 `onFallbackStart/End`. 기존 onError 구독자 (3 페이지) 무영향 + 의도 명확
2. **cache key 일관성** — token 갱신 race 사전 차단 (F5 분석). 같은 path 호출이 같은 instance 보장 — alarm-popup + alarm-ws + dashboard/websocket 등 다중 호출자 안전
3. **재활용 우선** — `Auth._refresh`, `_runCatchUp`, 정상화 burst 패턴, `_channel_label` 함수 통합. 새 시스템 도입 시 기존 자산 식별 → grep 흐름 확립
4. **사용자 결정 매트릭스 명시** — refactoring 문서에 각 결정 (그룹화 단위, 헤더 정책, 옵션 선택) 의 근거 + 거부한 옵션 기록 → 향후 재검토 시 컨텍스트 보존
5. **commit 메시지에 의도·결정·검증** — 코드 안 보고도 의도 파악 가능 ([memory `team_collaboration_style`](/home/cjy/.claude/projects/-home-cjy-diconai/memory/team_collaboration_style.md))
6. **single source of truth** (메시지) — `get_short_message` 한 곳에서 채널 라벨 prefix 생성 → 패널·팝업·토스트·이력 페이지 모두 자동 적용 + 프론트 영향 0

### 5.2 잠재 리스크

| 리스크 | 영향 | 대응 방향 |
|---|---|---|
| Lucide `@latest` CDN — 메이저 업그레이드 시 호환 깨질 가능성 | 시연 전 발생 시 아이콘 안 보일 수 있음 | main.html 주석에 "시연 직전 0.x 고정 권장" 명시. 시연 D-7 에 `lucide@0.479.0` 등 고정 |
| WSClient `_open()` 안 매번 `_resolveUrl` 호출 — 미세 비용 | reconnect 빈도 ↑ 시 약간의 CPU | 무시 가능 — `_resolveUrl` 자체가 가벼움 (string concat 수준) |
| `_sourceGroups` LRU 정리 시 그룹 안 event_id 들의 `_seenKeys` 정리 누락 가능성 (group 객체 없는 경우) | 같은 알람이 다시 표시될 수 있음 | `_trimList` 안에서 `_sourceGroups.get(removedKey)` 가드 — 정리 시 group 없으면 skip. 안전 fallback |
| channel_meta JSON 구조 변경 시 `get_channel_label` 영향 | 라벨이 "CHn" 폴백으로 떨어짐 | `clean()` validator 가 이미 검증 ({"name": ...} 필수). 마이그 시 backfill 검토 |
| 60s 끊김 임계가 너무 길어 알람 누락 가능 (최대 90s) | 산업 안전 환경에 따라 부적절할 수 있음 | 운영 단계에서 운영자 피드백 받아 `FALLBACK_DELAY_MS` 조정. 또는 env 변수화 |

### 5.3 다음 작업자 가이드

1. **Lucide → 디자이너 SVG 교체 시**:
   - `event-panel.js` `ICON_BY_TYPE` 매핑 갈아끼움 (Lucide name → 파일 경로)
   - DOM 렌더 — `<i data-lucide="...">` → `<img src="..." class="event-icon">` 또는 inline SVG
   - `main.html` 의 `<script src="lucide">` 제거
   - 호출자 (`addItem`, `_addToClearGroup`, `_addToSourceGroup`, `_refreshSourceGroup`) 안 `lucide.createIcons()` 호출 제거

2. **channel_meta 운영자 등록 UI 작업 시**:
   - `admin_panel` 의 PowerDevice 편집 폼에 `channel_meta` JSONField 입력 UI 추가
   - 본 작업에서 백엔드 이미 활용 — UI 만 만들면 됨
   - 검증: 등록 후 새 알람 발생 시 라벨이 "송풍기A" 등으로 자동 표시

3. **D 옵션 본격 (60s 클라 dedup + 헤더 미확인 배지) 진입 시**:
   - alarm-popup.js 가 이미 hook 기반 — WSClient.onOpen / onFallbackStart 가 정착됨. 헤더 배지 hook 추가 자연
   - localStorage 키 prefix `diconai:alarm:popup:*` 컨벤션 추천
   - 디자인 결정 5건 (D1~D5) 선행 — refactoring 문서 의 Open Questions 참조

4. **Phase 3 작업자 라우팅 진입 시**:
   - 본 세션의 `AlarmRecord.channel` 이 권한 라우팅에 활용 가능 (특정 channel 만 모니터링 권한 부여 등)
   - `EventAcknowledgement` 모델 (Phase 1) + `AlarmRecord.channel` (본 세션) 결합 가능

5. **monitoring_events / event_detail 의 alarm_stack 전환 위생 작업**:
   - 두 페이지에서 `alarm-ws.js` 직접 include 제거 → `{% include "components/alarm_stack.html" %}`
   - 다만 dashboard 메인은 alarm_stack 안 씀 (자체 websocket.js — alarm_stack 코멘트 참조)

---

## 6. 부록

### 6.1 Lucide CDN 매핑 (현재 사용 중)

```
gas_threshold       → flame
gas_clear           → circle-check
power_overload      → zap
power_anomaly_ai    → brain-circuit
power_clear         → circle-check
geofence_intrusion  → map-pin
sensor_fault        → shield-alert
ppe_violation       → hard-hat
vr_training_not_done → graduation-cap
safety_check_pending → clipboard-check
inspection_scheduled → wrench
batch_failed        → circle-x
storage_overdue     → package-x
(fallback)          → bell
```

확인: https://lucide.dev/icons/

### 6.2 channel_meta 구조

```json
{
  "1": {"name": "송풍기A"},
  "2": {"name": "압연기B"},
  "3": {"name": "보조 모터 1"}
}
```

- `PowerDevice.channel_meta` (`facilities/models/devices.py:172`) — JSONField
- `PowerDevice.clean()` 가 validator (`devices.py:230`) — 키 = 채널 번호 (1~`channel_count`), 값 = `{"name": ...}`
- 미등록 채널 → `get_channel_label` 폴백 `"CH${n}"`

### 6.3 scrollbar CSS 변수 의존성

| 위치 | thumb | thumb hover | track |
|---|---|---|---|
| `header.css` (dashboard / snb_details) | `var(--border, #30363d)` | `var(--text2, #6e7681)` | transparent |
| `admin.css` (admin_panel) | `#cbd5e1` | `#94a3b8` | transparent |

CSS 변수는 `dashboard.css :root` 에 정의. `header.css` 가 load 순서상 dashboard.css 뒤라 변수 활용 가능. admin.css 는 별개 디자인 시스템.

### 6.4 신규 settings / env 변수

본 세션은 신규 env 변수 없음. 선행 작업 (Phase 1) 의 `ALARM_REPOPUP_COOLDOWN_SEC` 그대로 활용.

### 6.5 신규 WS 채널 / endpoint

본 세션은 신규 채널 없음. 기존 채널 활용:
- `/ws/sensors/` — 전체 broadcast (sensor_clients)
- `/ws/positions/` — 위치 별도
- `/ws/worker/{user_id}/` — 작업자 개인 (workspace dict)
- `/alerts/api/alarms/catch-up/?since=` — 폴링 fallback 도 같은 endpoint 활용

### 6.6 commit 흐름

```
830a769 feat(shared): WSClient 토큰 만료 자동 refresh + 60s 지속 끊김 fallback 인프라
        ↓ (인프라 도입 — 묶음 A 1)
f6aa032 feat(dashboard): 알람 팝업 WS 재연결 catch-up + fallback 폴링 구독 (Phase 2)
        ↓ (구독 부착 — 묶음 A 2)
a2bd68a feat(dashboard): 이벤트 패널 아이콘 이모지 → Lucide SVG (임시안)
        ↓ (UX 시각 변경 — 묶음 B 1)
bc0623f feat(dashboard): 이벤트 패널 source 단위 그룹화 + "외 N건" 펼침 (Phase 2)
        ↓ (UX 구조 변경 — 묶음 B 2, 의존 a2bd68a 의 lucide.createIcons)
8976109 feat(alerts): AlarmRecord.channel + channel_meta 기반 채널 라벨 표시
        ↓ (UX 데이터 보강 — 묶음 B 3, 의존 bc0623f 의 그룹 펼침)
d624531 style(dashboard): main.html Lucide 주석 Django {# #} → HTML <!-- -->
        ↓ (사용자 직접 변경 — 별도 commit 분리)
56b0c1b style: 사이트 전체 스크롤바 일관화 — 다크/라이트 테마 별 6px (Phase 2)
        ↓ (디자인 시스템 보강 — 묶음 B 4)
```

전체 7 commit, 머지 시 `git log --oneline 830a769^..56b0c1b` 로 추적 가능.

### 6.7 후속 변경 (2026-05-18 W4) — `algorithm_source` 라벨

본 세션 작업 후 ARIMA Un-격하 plan §8 의 W4 작업자가 같은 영역을 보강. 본 문서가 인용하는 코드의 stale 부분을 추적하기 위한 참조.

#### W4 가 우리 흐름에 미친 영향

| 본 문서 위치 | 본 commit (8976109) 시점 | W4 후속 변경 |
|---|---|---|
| 2.4 — `AlarmRecord.get_short_message` AI 분기 | `f"{prefix}AI 이상 패턴 감지 ..."` 단일 문자열 | `ALGORITHM_SOURCE_LABEL[algorithm_source]` 매핑 한 단계 추가 — `f"{prefix}{label} 이상 감지 ..."` |
| 2.4 — 가스 anomaly_ai 분기 | 본 commit 무관 (W4 신설) | `gas_anomaly_ai` 도 같은 algorithm 라벨 prefix — `"CO IF 이상 감지 (290.0 ppm)"` |
| 2.4 — 메시지 예시 | "보조 모터 1 전력 임계치 초과 (15.58 W)" | AI 알람의 경우 "송풍기A IF+ARIMA 이상 감지 (7925.8 W)" 같은 더 구체적 라벨 |
| 3.4 — `create_alarm_and_event` 시그니처 | `(..., channel=)` 인자 추가 (본 commit) | `(..., algorithm_source=)` 인자 추가 (W4) — 두 파라미터 독립 동작 |
| 2.4 fastapi 측 — `power_service.forward_inference_e2e` | `alarm_payload` 에 `channel` 추가 (본 commit) | `alarm_payload` 에 `algorithm_source` 도 추가 (W4) — fastapi 가 priority (night_abnormal > combined > arima > isolation_forest) 결정 후 전달 |

#### W4 추가 자료구조

```
AlarmRecord (W4 후 모델 전체 알람 필드)
├── channel (본 commit) — PowerDevice 채널 1~16
├── algorithm_source (W4 신규) — "isolation_forest" | "arima" | "combined" | "night_abnormal" | ""
│   └── 룰 알람: 빈 문자열, AI 알람: 4 종 중 하나
└── (기존) facility / event / sensor / power_device / geofence / worker / ml_anomaly_result / ...

constants.ALGORITHM_SOURCE_LABEL (W4 신규)
├── "isolation_forest" → "IF"
├── "arima" → "ARIMA"
├── "combined" → "IF+ARIMA"
└── "night_abnormal" → "야간 가동"
```

#### 관련 commit

```
2205a13 feat(alerts): W4 — AlarmRecord.algorithm_source + AI_TO_RULE_LEVEL 중복 정리
        ↓ (모델 + migration 0017 + constants)
2df4fe4 feat(alerts): AI 추론 가시성 — algorithm 라벨 + serializer + WS push payload
        ↓ (get_short_message 분기 + serializer 노출 + fastapi push_payload)
ccd15aa fix(ai): ARIMA 실동작 보강 + 토스트 algorithm 라벨
        (ARIMA 학습 흐름 보강)
```

본 문서는 본 commit (8976109) 단위 인계서라 W4 의 본격 흐름은 ARIMA Un-격하 plan §8 또는 별도 W4 기술문서 참조. 본 노트는 stale 코드 인용 추적 목적.
