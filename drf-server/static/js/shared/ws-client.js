/* ==========================================================
   ws-client.js — WebSocket 연결 단일 래퍼
   ==========================================================
   - URL은 AppConfig.WS_BASE를 자동 prefix (path만 넘기면 됨).
   - 동일 path의 연결은 캐시되어 한 페이지에서 중복 연결되지 않는다.
   - 자동 재연결(기본 3초). onclose 후 재시도.
   - 콜백은 add/remove로 다중 구독 가능 (한 ws가 여러 핸들러에 분배).
   - 라이프사이클 콜백(onOpen/onClose/onError)도 다중 구독 지원.

   사용 예:
     const ws = WSClient.connect('/ws/sensors/');
     const off = ws.onMessage((data) => { ... });
     ws.onOpen(() => setStatus('connected'));
     ws.onClose(() => setStatus('disconnected'));
     // 페이지 언마운트 시: off();

   상위 호환:
     - 기존 alarm-ws.js, dashboard/websocket.js의 별개 연결을 통합
     - 토큰 부착이 필요한 엔드포인트는 옵션으로 ?token=... 쿼리 추가
   ========================================================== */

'use strict';

const WSClient = (function () {
  const RECONNECT_DELAY = 3000;
  const _cache = new Map(); // key: full URL → instance

  function _resolveUrl(path, opts) {
    let base;
    if (window.AppConfig && typeof window.AppConfig.wsUrl === 'function') {
      base = window.AppConfig.wsUrl(path);
    } else {
      base = path;
    }
    if (opts && opts.attachToken && typeof Auth !== 'undefined') {
      const token = Auth.getAccessToken();
      if (token) {
        const sep = base.includes('?') ? '&' : '?';
        base += `${sep}token=${encodeURIComponent(token)}`;
      }
    }
    return base;
  }

  function _create(path, opts) {
    opts = opts || {};
    const url = _resolveUrl(path, opts);
    const cached = _cache.get(url);
    if (cached) return cached;

    const messageHandlers = new Set();
    const openHandlers    = new Set();
    const closeHandlers   = new Set();
    const errorHandlers   = new Set();
    let ws = null;
    let closed = false;
    let reconnectTimer = null;

    function _dispatch(set, ...args) {
      set.forEach((fn) => {
        try { fn(...args); } catch (e) { console.error('[WSClient] handler error', e); }
      });
    }

    function _open() {
      try {
        ws = new WebSocket(url);
      } catch (e) {
        _dispatch(errorHandlers, e);
        if (!closed) {
          reconnectTimer = setTimeout(_open, opts.reconnectDelay || RECONNECT_DELAY);
        }
        return;
      }
      ws.onopen = function () { _dispatch(openHandlers); };
      ws.onmessage = function (event) {
        let data;
        try { data = JSON.parse(event.data); } catch { return; }
        _dispatch(messageHandlers, data, event);
      };
      ws.onerror = function (e) {
        console.warn('[WSClient] error', path, e?.message || '');
        _dispatch(errorHandlers, e);
      };
      ws.onclose = function (e) {
        _dispatch(closeHandlers, e);
        if (closed) return;
        reconnectTimer = setTimeout(_open, opts.reconnectDelay || RECONNECT_DELAY);
      };
    }

    _open();

    function _addHandler(set, fn) {
      set.add(fn);
      return () => set.delete(fn);
    }

    const instance = {
      path,
      url,
      onMessage(fn) { return _addHandler(messageHandlers, fn); },
      onOpen(fn)    { return _addHandler(openHandlers, fn); },
      onClose(fn)   { return _addHandler(closeHandlers, fn); },
      onError(fn)   { return _addHandler(errorHandlers, fn); },
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
        messageHandlers.clear();
        openHandlers.clear();
        closeHandlers.clear();
        errorHandlers.clear();
        try { ws && ws.close(); } catch {}
        _cache.delete(url);
      },
      get readyState() { return ws ? ws.readyState : WebSocket.CLOSED; },
    };

    _cache.set(url, instance);
    return instance;
  }

  return {
    connect: _create,
    _cache, // 디버깅용
  };
})();
