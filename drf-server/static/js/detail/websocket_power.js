/* ──────────────────────────────────────────────────────────
   websocket_power.js  —  실시간/AI 예측 스마트 전력 현황
   WebSocket 연결 및 데이터 → power_system.js 렌더 함수 연동

   의존:
     power_system.js   (renderGrid, updateStatusBar, updateRiskSummary)
     ui-exception.js   (showSkeleton, clearSkeleton, showChartOverlay,
                        clearChartOverlay, grayOutBadges, restoreBadges)

   수신 페이로드 (ws://127.0.0.1:8002/ws/sensors/):
     equipment[]: { name, watt, voltage, current, onoff,
                    sensor_status, risk_level }
       - sensor_status : 'active' | 'comm_failure'
       - risk_level    : 'normal' | 'warning' | 'danger'
     total_power_kw   : number
     power_change_pct : number
   ────────────────────────────────────────────────────────── */

'use strict';

const WS_URL = 'ws://127.0.0.1:8001/ws/sensors/';

/* ────────────────────────────────────────────
   페이로드 → renderGrid 인자 변환
   status는 서버 risk_level이 아닌 클라이언트 THRESHOLD 기준으로 계산
   (서버와 클라이언트 임계치가 다를 수 있으므로)
────────────────────────────────────────────── */
function _mapEquipment(equipment) {
  return equipment.map(eq => {
    const isComm = eq.sensor_status === 'comm_failure';
    const watt   = isComm || eq.watt == null ? null : Math.round(eq.watt);
    return {
      name:          eq.name ?? '-',
      watt,
      /* getStatus()는 power_system.js의 THRESHOLD 기준 */
      status:        isComm ? 'safe' : getStatus(watt),
      onoff:         eq.onoff,
      sensor_status: eq.sensor_status,
    };
  });
}

/* ────────────────────────────────────────────
   좌측 설비 테이블 렌더링
────────────────────────────────────────────── */
const _statusLabel = { danger: '위험', caution: '주의', safe: '정상' };

function _renderEquipTable(equipList) {
  const tbody = document.getElementById('equip-tbody');
  if (!tbody) return;

  if (!equipList || equipList.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;color:var(--text2);padding:12px;">데이터가 존재하지 않습니다.</td></tr>`;
    _updateRiskCount(0, 0, 0);
    return;
  }

  /* 카운트: THRESHOLD 기준 status로 집계 */
  let cntDanger = 0, cntCaution = 0, cntSafe = 0;
  equipList.forEach(eq => {
    const s = eq.sensor_status === 'comm_failure' ? 'safe' : getStatus(eq.watt);
    if      (s === 'danger')  cntDanger++;
    else if (s === 'caution') cntCaution++;
    else                      cntSafe++;
  });
  _updateRiskCount(cntDanger, cntCaution, cntSafe);

  tbody.innerHTML = equipList.map(eq => {
    const isComm = eq.sensor_status === 'comm_failure';
    const watt   = isComm || eq.watt == null ? null : Math.round(eq.watt);
    const status = isComm ? 'safe' : getStatus(watt);

    const powerKw = watt != null ? `${(watt / 1000).toFixed(1)} kW` : '-';
    /* 부하율: 위험 임계치 THRESHOLD.danger(W) 기준 */
    const loadPct = watt != null
      ? `${Math.min(100, (watt / THRESHOLD.danger * 100).toFixed(1))}%`
      : '-';

    const connBadge = isComm
      ? `<span class="status-badge danger">수신 오류</span>`
      : eq.onoff
        ? `<span class="status-badge safe">ON</span>`
        : `<span class="status-badge" style="background:rgba(139,148,158,0.15);color:var(--text2);">OFF</span>`;

    const riskBadge = isComm
      ? `<span class="status-badge" style="background:rgba(139,148,158,0.15);color:var(--text2);">-</span>`
      : `<span class="status-badge ${status}">${_statusLabel[status]}</span>`;

    return `<tr${status !== 'safe' && !isComm ? ` class="${status}-row"` : ''}>
      <td><input type="checkbox" class="equip-check" data-name="${eq.name}"></td>
      <td>${eq.name}</td>
      <td>${powerKw}</td>
      <td>${loadPct}</td>
      <td>${connBadge}</td>
      <td>${riskBadge}</td>
    </tr>`;
  }).join('');
}

function _updateRiskCount(danger, caution, safe) {
  const d = document.getElementById('cnt-danger');
  const w = document.getElementById('cnt-caution');
  const n = document.getElementById('cnt-safe');
  if (d) d.textContent = danger;
  if (w) w.textContent = caution;
  if (n) n.textContent = safe;
}

/* ────────────────────────────────────────────
   WebSocket 연결
────────────────────────────────────────────── */
function initPowerWebSocket() {
  const grid    = document.getElementById('chart-grid');
  const leftPanel = document.querySelector('.power-left .panel');

  function connect() {
    /* 로딩 중: 스켈레톤 표시 */
    showSkeleton(grid, 8);

    let ws;
    try {
      ws = new WebSocket(WS_URL);
    } catch {
      _handleError();
      return;
    }

    ws.onopen = () => {
      /* 연결 성공 → 스켈레톤 제거는 첫 데이터 수신 후 */
    };

    ws.onmessage = (e) => {
      let data;
      try { data = JSON.parse(e.data); } catch { return; }

      const equipment = data.equipment ?? [];

      /* 스켈레톤 제거 */
      clearSkeleton(grid);

      if (!equipment || equipment.length === 0) {
        /* Empty Data */
        renderGrid([]);
        _renderEquipTable([]);
        _showAllChartOverlay('empty');
        updateStatusBar(null);
        return;
      }

      /* 정상 렌더링 */
      const mapped = _mapEquipment(equipment);
      updateRealtimeGrid(mapped);
      _renderEquipTable(equipment);

      /* 가장 위험한 설비를 상태 바에 표시 */
      const mostDangerous = equipment.find(e => e.risk_level === 'danger')
        ?? equipment.find(e => e.risk_level === 'warning')
        ?? null;

      if (mostDangerous) {
        const statusMap = { danger: '재가동 필요', warning: '전력 사용량 증가', normal: '정상' };
        updateStatusBar({
          name:  mostDangerous.name,
          msg:   `전력: ${mostDangerous.watt != null ? (mostDangerous.watt/1000).toFixed(1)+' kW' : '-'}`,
          alert: statusMap[mostDangerous.risk_level] ?? '-',
        });
      } else {
        updateStatusBar({ name: '-', msg: '-', alert: '-' });
      }
    };

    ws.onerror = () => _handleError();

    /* 통신 장애: 3초 재연결 */
    ws.onclose = () => {
      _handleError();
      setTimeout(connect, 3000);
    };
  }

  function _handleError() {
    clearSkeleton(grid);
    renderGrid([]);
    _showAllChartOverlay('error');
    _updateRiskCount([], [], []);
    updateStatusBar(null);

    const tbody = document.getElementById('equip-tbody');
    if (tbody) tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;color:var(--text2);padding:12px;">데이터를 불러올 수 없습니다.</td></tr>`;
  }

  function _showAllChartOverlay(type) {
    for (let i = 0; i < 8; i++) {
      const canvas = document.getElementById(`canvas-${i}`);
      if (canvas) showChartOverlay(canvas, type);
    }
  }

  connect();
}

/* ────────────────────────────────────────────
   초기화 (DOMContentLoaded 이후)
   power_system.js 의 DOMContentLoaded 와 중복 방지:
   window.powerSystemReady 플래그로 순서 보장
────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  initPowerWebSocket();
});
