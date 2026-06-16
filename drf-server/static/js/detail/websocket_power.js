/* ──────────────────────────────────────────────────────────
   websocket_power.js  —  실시간/AI 예측 스마트 전력 현황
   WebSocket 연결 및 데이터 → power_system.js 렌더 함수 연동

   의존:
     power_system.js   (renderGrid, updateStatusBar, updateRiskSummary)
     ui-exception.js   (showSkeleton, clearSkeleton, showChartOverlay,
                        clearChartOverlay, grayOutBadges, restoreBadges)

   수신 페이로드 (/ws/sensors/, AppConfig.WS_BASE 사용):
     equipment[]: { name, watt, voltage, current, onoff,
                    sensor_status, risk_level }
       - sensor_status : 'active' | 'comm_failure'
       - risk_level    : 'normal' | 'warning' | 'danger'
     total_power_kw   : number
     power_change_pct : number

   shared/ws-client.js의 WSClient를 사용해 동일 엔드포인트(/ws/sensors/)
   중복 연결을 방지한다.
   ────────────────────────────────────────────────────────── */

'use strict';

/* ────────────────────────────────────────────
   페이로드 → renderGrid 인자 변환
   status 는 서버 risk_level 그대로 사용 (SoT).
   fastapi equipment_builder 가 채널 정격(power_facility_default %) 기반으로
   계산한 결과 — B-2 이후 클라이언트 재계산 불필요 (옛 LEGACY_FALLBACK 절대값
   기준 재계산은 정격 작은 채널을 'safe' 로 잘못 분류함).
   risk_level 매핑: danger→danger / warning→caution / normal→safe (UI 클래스).
────────────────────────────────────────────── */
const _SERVER_RISK_TO_STATUS = { danger: 'danger', warning: 'caution', normal: 'safe' };

function _mapEquipment(equipment) {
  return equipment.map(eq => {
    const isComm = eq.sensor_status === 'comm_failure';
    const watt   = isComm || eq.watt == null ? null : Math.round(eq.watt);
    return {
      name:          eq.name ?? '-',
      watt,
      status:        isComm ? 'safe' : (_SERVER_RISK_TO_STATUS[eq.risk_level] ?? 'safe'),
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

  /* 카운트: 서버 risk_level 기준 집계 (SoT — fastapi 의 채널 정격 × % 환산 결과) */
  let cntDanger = 0, cntCaution = 0, cntSafe = 0;
  equipList.forEach(eq => {
    const s = eq.sensor_status === 'comm_failure'
      ? 'safe'
      : (_SERVER_RISK_TO_STATUS[eq.risk_level] ?? 'safe');
    if      (s === 'danger')  cntDanger++;
    else if (s === 'caution') cntCaution++;
    else                      cntSafe++;
  });
  _updateRiskCount(cntDanger, cntCaution, cntSafe);

  tbody.innerHTML = equipList.map((eq, idx) => {
    const isComm = eq.sensor_status === 'comm_failure';
    const watt   = isComm || eq.watt == null ? null : Math.round(eq.watt);
    const status = isComm
      ? 'safe'
      : (_SERVER_RISK_TO_STATUS[eq.risk_level] ?? 'safe');

    const powerKw = watt != null ? `${(watt / 1000).toFixed(1)} kW` : '-';
    /* 부하율: 채널 정격(power_system.js 의 _resolveChannel) 기준. 정격 미입력 시 '-' */
    const ch = _resolveChannel(idx + 1);
    const ratedW = ch.rated_w;
    const loadPct = (watt != null && ratedW)
      ? `${Math.min(999, (watt / ratedW * 100)).toFixed(1)}%`
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

    const ws = WSClient.connect('/ws/sensors/', { attachToken: true });
    if (typeof WsConnBanner !== 'undefined') WsConnBanner.attach(ws);  // P3 공용 배너

    ws.onMessage((data) => {
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
    });

    /* 통신 장애 시 UI 갱신만. 재연결은 WSClient(3초)가 자동 처리. */
    ws.onError(() => _handleError());
    ws.onClose(() => _handleError());
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
