/* ==========================================================
   alarm-badge.js — 헤더 미확인 알람 배지 (D 옵션 본격, 2026-05-17)
   ==========================================================
   사이트 전체 헤더 우측 (header.html 의 #btnAlarmBadge) 의 "🔔 N" 배지 관리.

   [흐름]
   1. 페이지 load 시 /alerts/api/alarms/summary/ 호출 → user_unread_event_count
      필드로 초기값 set (Phase 1 EventAcknowledgement 활용 — 본인 ack 안 한
      활성 이벤트 수만).
   2. newAlarmEvent CustomEvent 수신 마다 카운터 ↑ — alarm-ws/worker-ws/
      alarm-popup 의 catch-up 모두 같은 이벤트 dispatch 라 일관 동작.
   3. 배지 클릭 → /dashboard/monitoring/events/ 로 이동 + 카운터 reset.
   4. 카운트가 0 이면 배지 hidden, 1 이상이면 표시 (header.css .alarm-badge-count).

   [재활용 자산]
   - droppedCount + _renderDropBadge 패턴 (alarm-popup.js:251,317)
   - newAlarmEvent CustomEvent — alarm-ws.js, worker-ws.js, alarm-popup.js
     의 _runCatchUp 이 발행 — 본 모듈은 listen 만
   - .badge / .alarm-badge-count CSS — header.css

   [의존]
   auth.js (Auth.apiFetch), header.html (#btnAlarmBadge, .alarm-badge-count).
   AlarmPopup·WSClient 와 독립 — WSClient 미로드 페이지 (로그인 등) 에선
   summary fetch 실패 시 silent skip.
   ========================================================== */

'use strict';

const AlarmBadge = (function () {
  let _count = 0;
  let _btnEl = null;
  let _countEl = null;
  let _inited = false;

  function _resolveEls() {
    if (_btnEl && _countEl) return true;
    _btnEl   = document.getElementById('btnAlarmBadge');
    _countEl = _btnEl ? _btnEl.querySelector('.alarm-badge-count') : null;
    return Boolean(_btnEl && _countEl);
  }

  // count 상태 → DOM 반영. 종 버튼은 항상 표시 (관리 시스템 컨벤션 — 운영자가
  // 알람 채널이 살아있음을 항상 인지). 카운트 동그라미만 count ≥ 1 일 때 노출,
  // 99+ 면 "99+" 로 캡 (디자인 보호).
  function _render() {
    if (!_resolveEls()) return;
    if (_count <= 0) {
      _countEl.hidden = true;
    } else {
      _countEl.hidden = false;
      _countEl.textContent = _count > 99 ? '99+' : String(_count);
    }
  }

  // 초기값 fetch — summary API 의 user_unread_event_count (Phase 1 EventAcknowledgement
  // 활용 — 본인 ack 안 한 active/acknowledged/in_progress event 수).
  // 401 등 인증 실패는 Auth.apiFetch 가 처리 — 본 모듈은 silent fail.
  // [race 보정] alarm-popup.js 의 _runCatchUp 이 init 시점에 fire-and-forget 으로
  // newAlarmEvent dispatch 가능 — 본 fetch 결과로 _count 단순 덮어쓰면 그 dispatch
  // 누적이 사라짐. Math.max 로 둘 중 큰 값 유지.
  async function _fetchInitial() {
    if (typeof Auth === 'undefined' || !Auth.apiFetch) return;
    try {
      const res = await Auth.apiFetch('/alerts/api/alarms/summary/');
      if (!res || !res.ok) return;
      const data = await res.json();
      const n = Number(data.user_unread_event_count);
      if (Number.isFinite(n) && n >= 0) {
        _count = Math.max(_count, n);
        _render();
      }
    } catch (e) {
      console.warn('[AlarmBadge] initial fetch failed:', e);
    }
  }

  // 새 알람 도착 — alarm-ws/worker-ws/alarm-popup catch-up 이 dispatch 하는
  // newAlarmEvent 수신. catch-up 알람 (is_new_event=false) 도 운영자 미확인이라
  // 같이 카운트 — 운영자가 자리 비웠다가 돌아왔을 때 인지 보장.
  function _onNewAlarm(_ev) {
    _count += 1;
    _render();
  }

  // 배지 클릭 — 이력 페이지로 이동하면서 카운터 reset (운영자 확인 의사 표명).
  // 페이지 이동 후 reload 되므로 reset 은 visual 만 (count 변수는 다음 페이지 load
  // 시 _fetchInitial 로 재산정 — 그동안 운영자가 본 event 들이 ack 됐다면 ↓).
  function _onBadgeClick() {
    _count = 0;
    _render();
    window.location.href = '/dashboard/monitoring/events/';
  }

  function init() {
    if (_inited) return;
    _inited = true;
    if (!_resolveEls()) return;  // 헤더 없는 페이지 (로그인 등) 는 skip
    _btnEl.addEventListener('click', _onBadgeClick);
    document.addEventListener('newAlarmEvent', _onNewAlarm);
    window.addEventListener('newAlarmEvent', _onNewAlarm);  // alarm-popup catch-up 은 window 대상
    _fetchInitial();
  }

  return {
    init,
    // 테스트·디버깅용 — 외부 코드가 count 강제 변경 (예: 이력 페이지에서 강제 reset)
    setCount(n) {
      if (Number.isFinite(n) && n >= 0) {
        _count = n;
        _render();
      }
    },
    getCount() { return _count; },
  };
})();

document.addEventListener('DOMContentLoaded', () => AlarmBadge.init());
