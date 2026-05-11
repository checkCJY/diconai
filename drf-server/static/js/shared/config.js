// shared/config.js — 백엔드/WebSocket 베이스 URL 노출
//
// Django 템플릿(components/app_config.html)이 <script>로 window.AppConfig를 먼저 정의한다.
// 이 파일은 fallback과 헬퍼를 제공해 다른 shared/* 모듈이 안전하게 사용할 수 있게 한다.

if (!window.AppConfig) {
  console.warn('[AppConfig] not defined by template, using localhost fallback (dev only)');
  window.AppConfig = {
    API_BASE: "",                       // 빈 문자열 = same-origin
    WS_BASE:  "ws://127.0.0.1:8001"     // 로컬 개발 기본값
  };
}

// 운영 환경 가드: localhost가 아닌 host에서 WS_BASE가 localhost면 경고
if (window.AppConfig.WS_BASE &&
    window.AppConfig.WS_BASE.includes('127.0.0.1') &&
    window.location.hostname !== 'localhost' &&
    window.location.hostname !== '127.0.0.1') {
  console.error('[AppConfig] WS_BASE points to localhost in non-local environment:',
    window.AppConfig.WS_BASE);
}

window.AppConfig.apiUrl = function (path) {
  if (!path) return window.AppConfig.API_BASE;
  if (/^https?:\/\//i.test(path)) return path;        // 절대 URL은 그대로
  if (!window.AppConfig.API_BASE) return path;        // same-origin → 상대 경로 유지
  return window.AppConfig.API_BASE.replace(/\/$/, "") + (path.startsWith("/") ? path : "/" + path);
};

window.AppConfig.wsUrl = function (path) {
  if (!path) return window.AppConfig.WS_BASE;
  if (/^wss?:\/\//i.test(path)) return path;
  return window.AppConfig.WS_BASE.replace(/\/$/, "") + (path.startsWith("/") ? path : "/" + path);
};
