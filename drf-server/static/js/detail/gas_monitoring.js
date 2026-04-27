/* ──────────────────────────────────────────────────────────
   gas_monitoring.js  —  실시간/AI 예측 유해가스 현황
   의존: Chart.js 4.x, chartjs-plugin-annotation 3.x
   ────────────────────────────────────────────────────────── */

'use strict';

/* ── 가스 9종 설정 (임계치·단위·라벨) ── */
const GAS_CONFIG = {
  o2:  { label: 'O2(산소)',          unit: '%',   warning: 18.0, danger: 16.0, maxY: 25,   isO2: true  },
  co:  { label: 'CO(일산화탄소)',    unit: 'ppm', warning: 25,   danger: 200,  maxY: 300               },
  co2: { label: 'CO2(이산화탄소)',   unit: 'ppm', warning: 1000, danger: 5000, maxY: 6000              },
  h2s: { label: 'H2S(황화수소)',     unit: 'ppm', warning: 10,   danger: 15,   maxY: 30                },
  no2: { label: 'NO2(이산화질소)',   unit: 'ppm', warning: 3,    danger: 5,    maxY: 10                },
  so2: { label: 'SO2(이산화황)',     unit: 'ppm', warning: 2,    danger: 5,    maxY: 10                },
  o3:  { label: 'O3(오존)',          unit: 'ppm', warning: 0.06, danger: 0.12, maxY: 0.2               },
  nh3: { label: 'NH3(암모니아)',     unit: 'ppm', warning: 25,   danger: 35,   maxY: 50                },
  voc: { label: 'VOC(유기화합물)',   unit: 'ppm', warning: 0.5,  danger: 1.0,  maxY: 2.0               },
};

const GAS_KEYS = Object.keys(GAS_CONFIG);

/* ── 색상 ── */
const COLOR = {
  danger:    '#f85149',
  warning:   '#e3b341',
  normal:    '#3fb950',
  dangerBg:  'rgba(248,81,73,0.18)',
  warningBg: 'rgba(227,179,65,0.18)',
  gridLine:  'rgba(48,54,61,0.7)',
  tickText:  '#8b949e',
};

/* ── 탭 상태 ── */
let activeTab = 'realtime';

/* ── 차트 인스턴스 캐시 ── */
const chartInstances = {};

/* ── 마지막 수신 데이터 캐시 ── */
let _lastGasData = null;

/* ── 선택된 가스 (좌측 테이블 하이라이트) ── */
let _selectedGas = null;

/* ────────────────────────────────────────────
   위험도 판정
────────────────────────────────────────────── */
function getRiskFromData(gas, value, riskField) {
  if (riskField) return riskField;
  const cfg = GAS_CONFIG[gas];
  if (!cfg || value == null) return 'normal';
  if (cfg.isO2) {
    if (value < cfg.danger)  return 'danger';
    if (value < cfg.warning) return 'warning';
    return 'normal';
  }
  if (value >= cfg.danger)  return 'danger';
  if (value >= cfg.warning) return 'warning';
  return 'normal';
}

/* ────────────────────────────────────────────
   Chart.js 막대 그래프 생성
────────────────────────────────────────────── */
function createGasChart(canvasId, gas, value, risk) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  if (chartInstances[canvasId]) chartInstances[canvasId].destroy();

  const cfg     = GAS_CONFIG[gas];
  const barColor = COLOR[risk] ?? COLOR.normal;
  const barValue = value ?? 0;
  const maxY     = Math.max(cfg.maxY, barValue * 1.1);

  const annotations = {};

  if (cfg.isO2) {
    // O2: 위험 구간이 하단 (값이 낮을수록 위험)
    annotations.dangerBox  = { type: 'box', yMin: 0,           yMax: cfg.danger,  backgroundColor: COLOR.dangerBg,  borderWidth: 0 };
    annotations.warningBox = { type: 'box', yMin: cfg.danger,  yMax: cfg.warning, backgroundColor: COLOR.warningBg, borderWidth: 0 };
    annotations.dangerLine  = { type: 'line', yMin: cfg.danger,  yMax: cfg.danger,  borderColor: COLOR.danger,  borderWidth: 1, borderDash: [4,3] };
    annotations.warningLine = { type: 'line', yMin: cfg.warning, yMax: cfg.warning, borderColor: COLOR.warning, borderWidth: 1, borderDash: [4,3] };
  } else {
    annotations.dangerBox  = { type: 'box', yMin: cfg.danger,  yMax: maxY,        backgroundColor: COLOR.dangerBg,  borderWidth: 0 };
    annotations.warningBox = { type: 'box', yMin: cfg.warning, yMax: cfg.danger,  backgroundColor: COLOR.warningBg, borderWidth: 0 };
    annotations.dangerLine  = { type: 'line', yMin: cfg.danger,  yMax: cfg.danger,  borderColor: COLOR.danger,  borderWidth: 1, borderDash: [4,3] };
    annotations.warningLine = { type: 'line', yMin: cfg.warning, yMax: cfg.warning, borderColor: COLOR.warning, borderWidth: 1, borderDash: [4,3] };
  }

  const chart = new Chart(canvas, {
    type: 'bar',
    data: {
      labels: [''],
      datasets: [{
        data: [barValue],
        backgroundColor: barColor,
        borderColor:     barColor,
        borderWidth:     0,
        barPercentage:      0.5,
        categoryPercentage: 0.6,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: 'rgba(22,27,34,0.95)',
          borderColor:     'rgba(48,54,61,0.9)',
          borderWidth:     1,
          padding:         10,
          titleColor:      '#8b949e',
          bodyColor:       '#e6edf3',
          bodyFont:        { size: 11 },
          displayColors:   false,
          callbacks: {
            title: () => cfg.label,
            label: () => value != null
              ? `현재 농도   ${value} ${cfg.unit}`
              : ' 데이터 없음',
          },
        },
        annotation: { annotations },
      },
      scales: {
        x: { grid: { color: COLOR.gridLine }, ticks: { color: COLOR.tickText, font: { size: 10 } }, border: { color: '#30363d' } },
        y: {
          min: 0, max: maxY,
          grid:  { color: COLOR.gridLine },
          ticks: { color: COLOR.tickText, font: { size: 10 },
            callback: v => v >= 1000 ? `${(v/1000).toFixed(1)}k` : v,
          },
          border: { color: '#30363d' },
        },
      },
    },
  });

  chartInstances[canvasId] = chart;
  return chart;
}

/* ────────────────────────────────────────────
   차트 카드 DOM 생성
────────────────────────────────────────────── */
function buildGasCard(gas, value, risk) {
  const cfg = GAS_CONFIG[gas];
  const borderClass = risk === 'danger' ? 'border-danger' : risk === 'warning' ? 'border-caution' : '';

  const card = document.createElement('div');
  card.className = `chart-card ${borderClass}`;
  card.dataset.gas = gas;
  card.innerHTML = `
    <div class="card-title">
      <span class="card-status-dot ${risk}"></span>
      <span>${cfg.label}</span>
      <span style="margin-left:auto;font-size:11px;font-weight:400;color:var(--text2);">
        ${value != null ? value + ' ' + cfg.unit : '-'}
      </span>
    </div>
    <div class="card-chart-wrap">
      <canvas id="canvas-${gas}"></canvas>
    </div>
  `;

  card.addEventListener('click', () => _onGasCardClick(gas));
  return card;
}

/* ────────────────────────────────────────────
   차트 그리드 전체 렌더
────────────────────────────────────────────── */
function renderGasGrid(gasData = {}) {
  const grid = document.getElementById('chart-grid');
  if (!grid) return;
  grid.innerHTML = '';

  GAS_KEYS.forEach(gas => {
    const value = gasData[gas] ?? null;
    const risk  = gasData[`${gas}_risk`] ?? getRiskFromData(gas, value, null);
    const card  = buildGasCard(gas, value, risk);
    grid.appendChild(card);
  });

  // DOM 삽입 후 차트 생성
  GAS_KEYS.forEach(gas => {
    const value = gasData[gas] ?? null;
    const risk  = gasData[`${gas}_risk`] ?? 'normal';
    createGasChart(`canvas-${gas}`, gas, value, risk);
  });
}

/* ────────────────────────────────────────────
   가스 카드 클릭 → 좌측 테이블 하이라이트
────────────────────────────────────────────── */
function _onGasCardClick(gas) {
  _selectedGas = gas;

  // 카드 선택 표시
  document.querySelectorAll('.chart-card').forEach(c => c.classList.remove('selected'));
  const card = document.querySelector(`.chart-card[data-gas="${gas}"]`);
  if (card) card.classList.add('selected');

  // 좌측 가스 테이블 하이라이트
  document.querySelectorAll('#gas-tbody tr').forEach(tr => {
    tr.classList.toggle('selected', tr.dataset.gas === gas);
  });
}

/* ────────────────────────────────────────────
   좌측 가스 리스트 테이블 렌더
────────────────────────────────────────────── */
const RISK_LABEL = { danger: '위험', warning: '주의', normal: '정상' };

function renderGasListTable(gasData = {}) {
  const tbody = document.getElementById('gas-tbody');
  if (!tbody) return;

  tbody.innerHTML = GAS_KEYS.map(gas => {
    const cfg   = GAS_CONFIG[gas];
    const value = gasData[gas] ?? null;
    const risk  = gasData[`${gas}_risk`] ?? 'normal';
    const isSelected = _selectedGas === gas;

    return `<tr data-gas="${gas}" class="${isSelected ? 'selected' : ''}" onclick="onGasRowClick('${gas}')">
      <td>${cfg.label}</td>
      <td>${value != null ? value : '-'}</td>
      <td>${cfg.unit}</td>
      <td><span class="status-badge ${risk}">${RISK_LABEL[risk]}</span></td>
    </tr>`;
  }).join('');
}

function onGasRowClick(gas) {
  _onGasCardClick(gas);
}

/* ────────────────────────────────────────────
   센서 목록 테이블 렌더
────────────────────────────────────────────── */
function renderSensorTable(gasData = {}, connected = true) {
  const tbody = document.getElementById('sensor-tbody');
  if (!tbody) return;

  // 가스 중 가장 위험한 것 찾기
  let worstRisk = 'normal';
  let worstGas  = '-';
  GAS_KEYS.forEach(gas => {
    const risk = gasData[`${gas}_risk`] ?? 'normal';
    if (risk === 'danger') { worstRisk = 'danger'; worstGas = GAS_CONFIG[gas].label; }
    else if (risk === 'warning' && worstRisk !== 'danger') { worstRisk = 'warning'; worstGas = GAS_CONFIG[gas].label; }
  });

  const connBadge = connected
    ? `<span class="status-badge normal">정상</span>`
    : `<span class="status-badge offline">수신 오류</span>`;
  const riskBadge = connected
    ? `<span class="status-badge ${worstRisk}">${RISK_LABEL[worstRisk]}</span>`
    : `<span class="status-badge offline">-</span>`;

  tbody.innerHTML = `<tr class="selected">
    <td>GAS-001</td>
    <td>${connected ? worstGas : '-'}</td>
    <td>${connBadge}</td>
    <td>${riskBadge}</td>
  </tr>`;

  // 요약 카운트
  const danger  = GAS_KEYS.filter(g => (gasData[`${g}_risk`] ?? 'normal') === 'danger').length;
  const warning = GAS_KEYS.filter(g => (gasData[`${g}_risk`] ?? 'normal') === 'warning').length;
  const normal  = GAS_KEYS.length - danger - warning;
  const d = document.getElementById('cnt-danger');
  const w = document.getElementById('cnt-warning');
  const n = document.getElementById('cnt-normal');
  if (d) d.textContent = danger;
  if (w) w.textContent = warning;
  if (n) n.textContent = normal;
}

/* ────────────────────────────────────────────
   하단 상태 바 업데이트
────────────────────────────────────────────── */
function updateGasStatusBar(gasData) {
  const sensorName = document.getElementById('status-sensor-name');
  const msg        = document.getElementById('status-msg');
  const alert      = document.getElementById('status-alert');

  if (!gasData) {
    if (sensorName) sensorName.textContent = '-';
    if (msg)        msg.textContent        = '-';
    if (alert)      alert.textContent      = '-';
    return;
  }

  // 가장 위험한 가스 찾기
  let worstGas = null, worstRisk = 'normal';
  GAS_KEYS.forEach(gas => {
    const risk = gasData[`${gas}_risk`] ?? 'normal';
    if (risk === 'danger' || (risk === 'warning' && worstRisk === 'normal')) {
      worstRisk = risk;
      worstGas  = gas;
    }
  });

  if (sensorName) sensorName.textContent = 'GAS-001';
  if (msg)        msg.textContent = worstGas
    ? `${GAS_CONFIG[worstGas].label} 농도 증가`
    : '정상 범위';
  if (alert)      alert.textContent = worstGas
    ? '근처 작업자 대피 필요'
    : '';
}

/* ────────────────────────────────────────────
   탭 전환
────────────────────────────────────────────── */
function switchGasTab(tab) {
  activeTab = tab;
  document.getElementById('tab-realtime').classList.toggle('active', tab === 'realtime');
  document.getElementById('tab-ai').classList.toggle('active',       tab === 'ai');

  const banner = document.getElementById('ai-notice-banner');
  if (banner) banner.style.display = tab === 'ai' ? 'block' : 'none';

  if (tab === 'ai' && _lastGasData) renderGasGrid(_lastGasData);
}

/* ────────────────────────────────────────────
   외부(websocket_gas.js)에서 호출
────────────────────────────────────────────── */
function updateGasPage(gasData, connected = true) {
  _lastGasData = gasData;
  if (activeTab === 'realtime') renderGasGrid(gasData);
  renderGasListTable(gasData);
  renderSensorTable(gasData, connected);
  updateGasStatusBar(gasData);
}

/* ────────────────────────────────────────────
   시계
────────────────────────────────────────────── */
function startGasClock() {
  function tick() {
    const now = new Date();
    const pad = n => String(n).padStart(2, '0');
    const el  = document.getElementById('status-time');
    if (el) el.textContent = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
  }
  tick();
  setInterval(tick, 1000);
}

/* ────────────────────────────────────────────
   초기화
────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('tab-realtime')?.addEventListener('click', () => switchGasTab('realtime'));
  document.getElementById('tab-ai')?.addEventListener('click',       () => switchGasTab('ai'));

  startGasClock();
  renderGasGrid({});
  renderGasListTable({});
  renderSensorTable({}, false);
});
