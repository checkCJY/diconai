/* ==========================================================
   ws-client.js — WebSocket 연결 단일 래퍼
   ==========================================================
   - URL은 AppConfig.WS_BASE를 자동 prefix (path만 넘기면 됨).
   - 동일 path의 연결은 캐시되어 한 페이지에서 중복 연결되지 않는다.
   - 자동 재연결: 지수 백오프 (1s → 2s → ... → 30s 상한, ±30% 지터). 최대 20회 후 포기.
   - 콜백은 add/remove로 다중 구독 가능 (한 ws가 여러 핸들러에 분배).
   - 라이프사이클 콜백(onOpen/onClose/onError/onFallbackStart/onFallbackEnd) 다중 구독.
   - 토큰 만료 (close code=1008, reason="unauthenticated") 시 Auth._refresh() 후 즉시
     재연결 — 백오프 우회. attachToken 채널 한정. fastapi websocket/auth.py 의 close
     규약과 짝.
   - disconnect 60s 지속 시 onFallbackStart 발동 (catch-up 폴링 등 degrade 시그널).
     재연결 시 onFallbackEnd 자동 발동. 일시 끊김(수초)은 무시.

   사용 예:
     // 인증 활성화된 채널은 attachToken: true 옵션으로 토큰 자동 부착
     const ws = WSClient.connect('/ws/sensors/', { attachToken: true });
     const off = ws.onMessage((data) => { ... });
     ws.onOpen(() => setStatus('connected'));
     ws.onClose(() => setStatus('disconnected'));
     ws.onFallbackStart(() => startPolling());   // 60s 지속 끊김 시 보조 모드 진입
     ws.onFallbackEnd(() => stopPolling());      // 재연결 성공 시 보조 모드 해제
     // 페이지 언마운트 시: off();

   상위 호환:
     - 기존 alarm-ws.js, dashboard/websocket.js의 별개 연결을 통합
     - attachToken: true 옵션이면 ?token=<access_token> 쿼리 자동 부착
       (서버는 settings.JWT_SIGNING_KEY 설정 시 query token 검증)
   ========================================================== */

'use strict';

const WSClient = (function () {
  // 지수 백오프: 1s → 2s → 4s → ... → 30s 상한, ±30% 지터로 분산.
  // MAX_ATTEMPTS 도달 시 재연결 포기 → onError("max_reconnect_attempts").
  const INITIAL_DELAY = 1000;
  const MAX_DELAY     = 30000;
  const MAX_ATTEMPTS  = 20;
  const JITTER        = 0.3;
  // disconnect 60s 지속 시 onFallbackStart 발동. 일시 끊김(수초)에 폴링 시작/중단을
  // 반복하면 불안정 — 시간 기반 임계로 진짜 끊김만 응답. plan/alarm-system-redesign.md
  // 의 C 옵션 (60s 지속) 결정에 따른 상수.
  const FALLBACK_DELAY_MS = 60_000;
  // cache key 는 path + opts 직렬화 — token 갱신 후 URL 이 바뀌어도 같은 path 호출이
  // 동일 instance 를 보장. 이전엔 key=full URL 이라 refresh 직후 다른 호출자가 같은
  // path 로 connect 하면 cache miss → 별개 instance → 같은 채널 두 WS 연결 race 가
  // 발생했음 (F5 분석 결과).
  const _cache = new Map(); // key: `${path}:${JSON.stringify(opts)}` → instance

  function _cacheKey(path, opts) {
    return `${path}:${JSON.stringify(opts || {})}`;
  }

  function _resolveUrl(path, opts) {
    let base;
    if (window.AppConfig && typeof window.AppConfig.wsUrl === 'function') {
      base = window.AppConfig.wsUrl(path);
    } else {
      console.warn('[WSClient] AppConfig.wsUrl unavailable, using same-origin fallback for', path);
      base = path;
    }
    if (opts && opts.attachToken) {
      if (typeof Auth === 'undefined') {
        console.warn('[WSClient] attachToken requested but Auth module not loaded');
      } else {
        const token = Auth.getAccessToken();
        if (!token) {
          console.warn('[WSClient] attachToken requested but no token in storage');
        } else {
          const sep = base.includes('?') ? '&' : '?';
          base += `${sep}token=${encodeURIComponent(token)}`;
        }
      }
    }
    return base;
  }

  function _create(path, opts) {
    opts = opts || {};
    const cacheKey = _cacheKey(path, opts);
    const cached = _cache.get(cacheKey);
    if (cached) return cached;

    const messageHandlers = new Set();
    const openHandlers    = new Set();
    const closeHandlers   = new Set();
    const errorHandlers   = new Set();
    // fallback 콜백은 errorHandlers 재사용 대신 별도 채널 — 기존 onError 구독자
    // (websocket_gas/power, dashboard/websocket 의 _handleError) 가 fallback 시그널을
    // 일반 연결 오류로 오인하지 않도록 인터페이스 분리 (F4 분석).
    const fallbackStartHandlers = new Set();
    const fallbackEndHandlers   = new Set();
    let ws = null;
    let closed = false;
    let reconnectTimer = null;
    let attempts = 0;
    // currentUrl 은 _open() 마다 _resolveUrl 로 재계산 — token 갱신 직후 새 access_token
    // 으로 connect 보장 (refresh 흐름이 옛 URL 을 그대로 쓰면 401 무한 루프).
    let currentUrl = _resolveUrl(path, opts);
    // fallback 상태 — 60s 지속 끊김 시 true 로 전이, onopen 시 false 로 복귀.
    let fallbackTimer = null;
    let inFallback = false;

    function _dispatch(set, ...args) {
      set.forEach((fn) => {
        try { fn(...args); } catch (e) { console.error('[WSClient] handler error', e); }
      });
    }

    function _scheduleReconnect() {
      if (closed) return;
      attempts += 1;
      if (attempts > MAX_ATTEMPTS) {
        console.warn('[WSClient] max reconnect attempts reached for', path);
        _dispatch(errorHandlers, new Error('max_reconnect_attempts'));
        return;
      }
      const base = Math.min(INITIAL_DELAY * Math.pow(2, attempts - 1), MAX_DELAY);
      const delay = base * (1 + (Math.random() - 0.5) * JITTER);
      reconnectTimer = setTimeout(_open, delay);
    }

    // 60s disconnect 지속 시 1회 발동. 호출자(예: AlarmPopup)가 catch-up 폴링으로 degrade.
    // 이미 타이머 가동 중이거나 fallback 진입 상태면 noop (중복 발동 차단).
    function _startFallbackTimer() {
      if (fallbackTimer || inFallback) return;
      fallbackTimer = setTimeout(() => {
        fallbackTimer = null;
        inFallback = true;
        _dispatch(fallbackStartHandlers);
      }, FALLBACK_DELAY_MS);
    }

    // 재연결 성공(onopen) 또는 instance.close() 시 호출. 진입 중이었으면 종료 시그널.
    function _clearFallbackState() {
      if (fallbackTimer) {
        clearTimeout(fallbackTimer);
        fallbackTimer = null;
      }
      if (inFallback) {
        inFallback = false;
        _dispatch(fallbackEndHandlers);
      }
    }

    function _open() {
      // 매 _open() 마다 URL 재계산 — refresh 직후 새 access_token 으로 connect 보장.
      currentUrl = _resolveUrl(path, opts);
      try {
        ws = new WebSocket(currentUrl);
      } catch (e) {
        _dispatch(errorHandlers, e);
        _scheduleReconnect();
        return;
      }
      ws.onopen = function () {
        attempts = 0;             // 정상 연결 → 백오프 리셋
        _clearFallbackState();    // 끊김 중이었다면 fallback 종료 시그널 + 타이머 cleanup
        _dispatch(openHandlers);
      };
      ws.onmessage = function (event) {
        let data;
        try { data = JSON.parse(event.data); } catch { return; }
        _dispatch(messageHandlers, data, event);
      };
      ws.onerror = function (e) {
        console.warn('[WSClient] error', path, e?.message || '');
        _dispatch(errorHandlers, e);
      };
      ws.onclose = async function (e) {
        _dispatch(closeHandlers, e);

        // JWT 만료 흐름 — fastapi/websocket/auth.py 가 unauthenticated 시
        // close(code=1008, reason="unauthenticated") 송신. attachToken 채널 한정으로
        // Auth._refresh (_refreshing Promise 가드로 race 차단됨 — F1) 호출 후 즉시 _open
        // 재진입. forbidden 은 권한 부족이라 refresh 의미 없음 → 일반 백오프로 fall through.
        if (e.code === 1008 && e.reason === 'unauthenticated' && opts.attachToken) {
          if (typeof Auth !== 'undefined' && typeof Auth._refresh === 'function') {
            const refreshed = await Auth._refresh();
            if (refreshed && !closed) {
              attempts = 0;       // refresh 성공 → 정상 흐름이라 백오프 reset
              _open();
              return;
            }
          }
        }

        _startFallbackTimer();    // 60s 지속 시 폴링 트리거 (이미 가동/진입 상태면 noop)
        _scheduleReconnect();
      };
    }

    _open();

    function _addHandler(set, fn) {
      set.add(fn);
      return () => set.delete(fn);
    }

    const instance = {
      path,
      // url 은 token 갱신 시 currentUrl 이 바뀌므로 getter 로 노출 — 호출자가 항상 최신.
      get url() { return currentUrl; },
      onMessage(fn) { return _addHandler(messageHandlers, fn); },
      onOpen(fn)    { return _addHandler(openHandlers, fn); },
      onClose(fn)   { return _addHandler(closeHandlers, fn); },
      onError(fn)   { return _addHandler(errorHandlers, fn); },
      // 60s disconnect 지속 시 1회 발동. 재연결 시 onFallbackEnd 자동 발동.
      onFallbackStart(fn) { return _addHandler(fallbackStartHandlers, fn); },
      onFallbackEnd(fn)   { return _addHandler(fallbackEndHandlers, fn); },
      send(payload) {
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(typeof payload === 'string' ? payload : JSON.stringify(payload));
          return true;
        }
        return false;
      },
      close() {
        closed = true;
        clearTimeout(reconnectTimer);
        _clearFallbackState();
        messageHandlers.clear();
        openHandlers.clear();
        closeHandlers.clear();
        errorHandlers.clear();
        fallbackStartHandlers.clear();
        fallbackEndHandlers.clear();
        try { ws && ws.close(); } catch {}
        _cache.delete(cacheKey);
      },
      get readyState() { return ws ? ws.readyState : WebSocket.CLOSED; },
    };

    _cache.set(cacheKey, instance);
    return instance;
  }

  return {
    connect: _create,
    _cache, // 디버깅용
  };
})();
