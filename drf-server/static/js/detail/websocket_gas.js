/* ──────────────────────────────────────────────────────────
   websocket_gas.js  —  실시간/AI 예측 유해가스 현황
   WebSocket 연결 → gas_monitoring.js 렌더 함수 연동

   수신 페이로드 (/ws/sensors/, AppConfig.WS_BASE 사용):
     co, h2s, co2, o2, no2, so2, o3, nh3, voc  — 측정값
     co_risk, h2s_risk, ...                      — 위험도
     gas_loading                                 — stale 여부 (FastAPI)

   shared/ws-client.js의 WSClient를 사용해 dashboard/websocket.js 등과
   동일 엔드포인트(/ws/sensors/) 중복 연결을 방지한다.
   ────────────────────────────────────────────────────────── */

'use strict';

function initGasWebSocket() {
  const grid    = document.getElementById('chart-grid');
  const gasLeft = document.querySelector('.gas-left');
  const banner  = document.getElementById('gas-conn-banner');
  const connTxt = document.getElementById('gas-conn-text');

  /* 배너 표시 */
  function _showBanner(text, spinning = true) {
    if (!banner) return;
    if (connTxt) connTxt.textContent = text;
    const spinner = banner.querySelector('.conn-spinner');
    if (spinner) spinner.style.display = spinning ? '' : 'none';
    banner.style.display = '';
  }

  /* 배너 숨김 */
  function _hideBanner() {
    if (banner) banner.style.display = 'none';
  }

  /* 로딩 중: 배너 + 스켈레톤 (스펙: 로딩 중 → 스켈레톤 UI) */
  function connect() {
    _showBanner('연결 시도 중...');
    if (grid) showSkeleton(grid, 9);
    _showLeftSkeleton();
    restoreBadges(gasLeft);   // 이전 오류 상태 배지 회색화 초기화

    const ws = WSClient.connect('/ws/sensors/', { attachToken: true });

    ws.onMessage((data) => {
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
    });

    /* 통신 장애 시 UI만 갱신. 재연결은 WSClient(3초)가 자동 처리. */
    ws.onError(() => _handleError());
    ws.onClose(() => _handleError());
  }

  /* 통신 장애 표시. 실제 재연결은 WSClient(3초)가 자동 처리. */
  function _handleError() {
    if (grid) clearSkeleton(grid);
    updateGasPage({}, false);
    _showAllOverlay('error');
    grayOutBadges(gasLeft);
    _showBanner('재연결 시도 중...');
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
