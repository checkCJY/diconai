/* ──────────────────────────────────────────────────────────
   websocket_gas.js  —  실시간/AI 예측 유해가스 현황
   WebSocket 연결 → gas_monitoring.js 렌더 함수 연동

   수신 페이로드 (ws://127.0.0.1:8001/ws/sensors/):
     co, h2s, co2, o2, no2, so2, o3, nh3, voc  — 측정값
     co_risk, h2s_risk, ...                      — 위험도
     gas_loading                                 — stale 여부 (FastAPI)
   ────────────────────────────────────────────────────────── */

'use strict';

const GAS_WS_URL = 'ws://127.0.0.1:8001/ws/sensors/';

function initGasWebSocket() {
  const grid    = document.getElementById('chart-grid');
  const gasLeft = document.querySelector('.gas-left');
  const banner  = document.getElementById('gas-conn-banner');
  const connTxt = document.getElementById('gas-conn-text');

  let _countdownTimer = null;

  /* 배너 표시 */
  function _showBanner(text, spinning = true) {
    if (!banner) return;
    if (connTxt) connTxt.textContent = text;
    const spinner = banner.querySelector('.conn-spinner');
    if (spinner) spinner.style.display = spinning ? '' : 'none';
    banner.style.display = '';
  }

  /* 배너 숨김 + 카운트다운 정리 */
  function _hideBanner() {
    if (banner) banner.style.display = 'none';
    _clearCountdown();
  }

  function _clearCountdown() {
    if (_countdownTimer) {
      clearInterval(_countdownTimer);
      _countdownTimer = null;
    }
  }

  /* N초 카운트다운 → onDone 실행 */
  function _startCountdown(seconds, onDone) {
    _clearCountdown();
    let remaining = seconds;
    _showBanner(`${remaining}초 후 재연결 시도...`);
    _countdownTimer = setInterval(() => {
      remaining--;
      if (remaining <= 0) {
        _clearCountdown();
        onDone();
      } else {
        _showBanner(`${remaining}초 후 재연결 시도...`);
      }
    }, 1000);
  }

  /* 로딩 중: 배너 + 스켈레톤 (스펙: 로딩 중 → 스켈레톤 UI) */
  function connect() {
    _showBanner('연결 시도 중...');
    if (grid) showSkeleton(grid, 9);
    _showLeftSkeleton();
    restoreBadges(gasLeft);   // 이전 오류 상태 배지 회색화 초기화

    let ws;
    try {
      ws = new WebSocket(GAS_WS_URL);
    } catch {
      _handleError();
      return;
    }

    ws.onmessage = (e) => {
      let data;
      try { data = JSON.parse(e.data); } catch { return; }

      _hideBanner();
      if (grid) clearSkeleton(grid);

      if (!data || Object.keys(data).length === 0 || data.gas_loading) {
        /* 데이터 없음 (스펙: 데이터 없음 → 차트 틀 유지 + 오버레이 + 배지 회색화) */
        updateGasPage({}, false);
        _showAllOverlay('empty');
        grayOutBadges(gasLeft);
        return;
      }

      /* 정상 수신: 오버레이·회색화 해제 후 렌더 */
      _clearAllOverlay();
      restoreBadges(gasLeft);
      updateGasPage(data, true);
    };

    ws.onerror = () => _handleError();
    ws.onclose = () => _handleError();
  }

  /* 통신 장애 (스펙: 차트 틀 유지 + 오버레이 + 배지 회색화 + 3초 재연결) */
  function _handleError() {
    _clearCountdown();
    if (grid) clearSkeleton(grid);
    updateGasPage({}, false);
    _showAllOverlay('error');
    grayOutBadges(gasLeft);
    _startCountdown(3, connect);
  }

  /* 좌측 센서·가스 테이블 스켈레톤 행 삽입 (로딩 중 전용) */
  function _showLeftSkeleton() {
    const sensorTbody = document.getElementById('sensor-tbody');
    if (sensorTbody) {
      sensorTbody.innerHTML = `<tr>
        <td><span class="skeleton skel-text skel-sm"></span></td>
        <td><span class="skeleton skel-text skel-sm"></span></td>
        <td><span class="skeleton skel-badge"></span></td>
        <td><span class="skeleton skel-badge"></span></td>
      </tr>`;
    }
    const gasTbody = document.getElementById('gas-tbody');
    if (gasTbody) {
      const row = `<tr>
        <td><span class="skeleton skel-text"></span></td>
        <td><span class="skeleton skel-text skel-sm"></span></td>
        <td><span class="skeleton skel-text skel-sm"></span></td>
        <td><span class="skeleton skel-badge"></span></td>
      </tr>`;
      gasTbody.innerHTML = Array(9).fill(row).join('');
    }
    ['cnt-danger', 'cnt-warning', 'cnt-normal'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.textContent = '-';
    });
  }

  /* 9종 차트 카드 오버레이 표시 */
  function _showAllOverlay(type) {
    ['o2', 'co', 'co2', 'h2s', 'no2', 'so2', 'o3', 'nh3', 'voc'].forEach(gas => {
      const canvas = document.getElementById(`canvas-${gas}`);
      if (canvas) showChartOverlay(canvas, type);
    });
  }

  /* 9종 차트 카드 오버레이 제거 */
  function _clearAllOverlay() {
    ['o2', 'co', 'co2', 'h2s', 'no2', 'so2', 'o3', 'nh3', 'voc'].forEach(gas => {
      const canvas = document.getElementById(`canvas-${gas}`);
      if (canvas) clearChartOverlay(canvas);
    });
  }

  connect();
}

document.addEventListener('DOMContentLoaded', () => {
  initGasWebSocket();
});
