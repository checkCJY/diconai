/* ──────────────────────────────────────────────────────────
   gas_monitoring.js  —  실시간/AI 예측 유해가스 현황
   의존: Chart.js 4.x, chartjs-plugin-annotation 3.x
   ────────────────────────────────────────────────────────── */

'use strict';

/* ── 가스 9종 표시 메타 (라벨·단위·차트 maxY fallback) ──────
   임계치 (warning/danger) 는 DB(gas_legal 그룹) 의 SoT 를 API 로 fetch 후 덮어씀.
   o2 만 양방향 (값 ↑/↓ 모두 위험) — isO2 플래그로 분기. */
const GAS_CONFIG = {
  o2:  { label: 'O2(산소)',          unit: '%',   maxY: 25,   isO2: true },
  co:  { label: 'CO(일산화탄소)',    unit: 'ppm', maxY: 300              },
  co2: { label: 'CO2(이산화탄소)',   unit: 'ppm', maxY: 6000             },
  h2s: { label: 'H2S(황화수소)',     unit: 'ppm', maxY: 30               },
  no2: { label: 'NO2(이산화질소)',   unit: 'ppm', maxY: 10               },
  so2: { label: 'SO2(이산화황)',     unit: 'ppm', maxY: 10               },
  o3:  { label: 'O3(오존)',          unit: 'ppm', maxY: 0.2              },
  nh3: { label: 'NH3(암모니아)',     unit: 'ppm', maxY: 50               },
  voc: { label: 'VOC(유기화합물)',   unit: 'ppm', maxY: 2.0              },
};

const GAS_KEYS = Object.keys(GAS_CONFIG);

/* ── 임계치 캐시: { co: {warning_max, danger_max, ...}, o2: {...}, ... }
   GET /api/monitoring/gas/thresholds/ 로 페이지 진입 시 1회 fetch. */
let GAS_THRESHOLDS = {};

async function loadGasThresholds() {
  try {
    const res = await fetch('/api/monitoring/gas/thresholds/');
    if (!res.ok) return;
    GAS_THRESHOLDS = await res.json();
  } catch (_) { /* 실패 시 빈 캐시 — _resolveGas 가 GAS_CONFIG.maxY fallback */ }
}

/* GAS_CONFIG (표시 메타) + GAS_THRESHOLDS (DB SoT) → 차트용 통합 설정.
   단방향 (8가스): { warn, danger, maxY } — warn/danger 는 warning_max/danger_max.
   양방향 (o2):    { warnLow, warnHigh, dangerLow, dangerHigh, maxY }.
   DB 미입력 부분은 hardcoded fallback. */
function _resolveGas(gas) {
  const cfg = GAS_CONFIG[gas];
  const t = GAS_THRESHOLDS[gas] || {};
  if (cfg.isO2) {
    return {
      label: cfg.label,
      unit: cfg.unit,
      isO2: true,
      warnLow:   t.warning_min ?? 18,
      warnHigh:  t.warning_max ?? 23.5,
      dangerLow: t.danger_min ?? 16,
      dangerHigh: t.danger_max ?? cfg.maxY,  // DB 미입력 시 차트 상단까지 위험 없음으로 간주
      maxY: t.chart_max ?? cfg.maxY,
    };
  }
  const warn = t.warning_max ?? null;
  const danger = t.danger_max ?? null;
  return {
    label: cfg.label,
    unit: cfg.unit,
    isO2: false,
    warn,
    danger,
    maxY: t.chart_max ?? cfg.maxY,
  };
}

/* ── 기타 색상 (chart-helpers 의 CHART_COLOR 외 페이지 고유) ── */
const COLOR = {
  danger:   CHART_COLOR.danger,
  warning:  CHART_COLOR.warn,
  normal:   CHART_COLOR.ok,
  gridLine: CHART_COLOR.gridLine,
  tickText: CHART_COLOR.text3,
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
  const r = _resolveGas(gas);
  if (value == null) return 'normal';
  if (r.isO2) {
    if (value <= r.dangerLow || value >= r.dangerHigh) return 'danger';
    if (value <= r.warnLow || value >= r.warnHigh) return 'warning';
    return 'normal';
  }
  if (r.danger != null && value >= r.danger) return 'danger';
  if (r.warn != null && value >= r.warn) return 'warning';
  return 'normal';
}

/* ────────────────────────────────────────────
   Chart.js 막대 그래프 생성 — 시안 패턴
   단방향 8가스: 3-segment stacked (정상/주의/위험 색 분리) + dashed line + chip
   양방향 O2:    단일 막대 + safeBand (안전 범위 강조) + dashed line × 4
────────────────────────────────────────────── */
function createGasChart(canvasId, gas, value, risk) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  if (chartInstances[canvasId]) chartInstances[canvasId].destroy();

  const r = _resolveGas(gas);
  const v = value ?? 0;
  const status = getRiskFromData(gas, value, risk);

  const labelColor = status === 'danger' ? CHART_COLOR.danger
                   : status === 'warning' ? CHART_COLOR.warn
                   : CHART_COLOR.text;

  const baseOpts = {
    responsive: true,
    maintainAspectRatio: false,
    layout: { padding: { top: 18, right: 4, left: 0, bottom: 0 } },
    animation: { duration: 600, easing: 'easeOutCubic' },
    scales: {
      x: {
        grid: { display: false }, ticks: { display: false }, border: { display: false },
        stacked: !r.isO2,
      },
      y: {
        stacked: !r.isO2,
        min: 0, max: r.maxY, beginAtZero: true,
        grid: { color: CHART_COLOR.gridLine, drawTicks: false },
        border: { display: false },
        ticks: {
          color: CHART_COLOR.text3, font: { size: 10 }, padding: 6, maxTicksLimit: 5,
          callback: (val) => val >= 1000
            ? `${(val / 1000).toFixed(1).replace(/\.0$/, '')}k`
            : val,
        },
      },
    },
  };

  let chartConfig;
  if (r.isO2) {
    // O2 양방향: 단일 막대 + safeBand + dashed line × 4
    const barColor = status === 'danger' ? CHART_COLOR.danger
                   : status === 'warning' ? CHART_COLOR.warn
                   : CHART_COLOR.ok;
    const thresholds = [
      { at: r.dangerHigh, color: 'danger', label: `위험 ${r.dangerHigh}${r.unit}` },
      { at: r.warnHigh,   color: 'warn',   label: `주의 ${r.warnHigh}${r.unit}` },
      { at: r.warnLow,    color: 'warn',   label: `주의 ${r.warnLow}${r.unit}` },
      { at: r.dangerLow,  color: 'danger', label: `위험 ${r.dangerLow}${r.unit}` },
    ];
    chartConfig = {
      type: 'bar',
      data: {
        labels: [''],
        datasets: [{
          data: [v],
          backgroundColor: barColor,
          borderRadius: 4, borderSkipped: false,
          barPercentage: 0.42, categoryPercentage: 1,
        }],
      },
      options: {
        ...baseOpts,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: '#1F2A48', borderColor: CHART_COLOR.border, borderWidth: 1, padding: 8,
            callbacks: {
              title: () => r.label,
              label: () => value != null ? `${value} ${r.unit}` : ' 데이터 없음',
            },
          },
          safeBand: { from: r.warnLow, to: r.warnHigh },
          thresholdZones: { thresholds },
          barValueLabel: {
            show: value != null,
            color: labelColor,
            formatter: () => `${value}${r.unit}`,
          },
        },
      },
    };
  } else {
    // 단방향 8가스: 3-segment stacked
    const warn = r.warn ?? r.maxY;
    const danger = r.danger ?? r.maxY;
    const normalSeg = Math.min(v, warn);
    const warnSeg = Math.max(0, Math.min(v, danger) - warn);
    const dangerSeg = Math.max(0, v - danger);
    const topR = { topLeft: 4, topRight: 4, bottomLeft: 0, bottomRight: 0 };
    const noR = 0;
    const rNormal = warnSeg === 0 && dangerSeg === 0 ? topR : noR;
    const rWarn = warnSeg > 0 && dangerSeg === 0 ? topR : noR;
    const rDanger = dangerSeg > 0 ? topR : noR;

    const thresholds = [];
    if (r.danger != null) thresholds.push({ at: r.danger, color: 'danger', label: `위험 ${r.danger}${r.unit}` });
    if (r.warn != null) thresholds.push({ at: r.warn, color: 'warn', label: `주의 ${r.warn}${r.unit}` });

    chartConfig = {
      type: 'bar',
      data: {
        labels: [''],
        datasets: [
          { label: '정상', data: [normalSeg], backgroundColor: CHART_COLOR.ok, stack: 's',
            borderRadius: rNormal, borderSkipped: false,
            barPercentage: 0.42, categoryPercentage: 1 },
          { label: '주의', data: [warnSeg], backgroundColor: CHART_COLOR.warn, stack: 's',
            borderRadius: rWarn, borderSkipped: false,
            barPercentage: 0.42, categoryPercentage: 1 },
          { label: '위험', data: [dangerSeg], backgroundColor: CHART_COLOR.danger, stack: 's',
            borderRadius: rDanger, borderSkipped: false,
            barPercentage: 0.42, categoryPercentage: 1 },
        ],
      },
      options: {
        ...baseOpts,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: '#1F2A48', borderColor: CHART_COLOR.border, borderWidth: 1, padding: 8,
            filter: (item) => item.parsed.y > 0,
            callbacks: {
              title: () => r.label,
              label: (ctx) => value != null
                ? `${ctx.dataset.label}: ${ctx.parsed.y} ${r.unit}`
                : ' 데이터 없음',
              footer: () => value != null ? `현재 ${value} ${r.unit}` : '',
            },
          },
          thresholdZones: { thresholds },
          barValueLabel: {
            show: value != null,
            color: labelColor,
            formatter: () => `${value}${r.unit}`,
          },
        },
      },
    };
  }

  const chart = new Chart(canvas, chartConfig);
  chartInstances[canvasId] = chart;
  return chart;
}

/* ────────────────────────────────────────────
   차트 카드 DOM 생성
────────────────────────────────────────────── */
function buildGasCard(gas, value, risk) {
  const cfg = GAS_CONFIG[gas];
  const borderClass = risk === 'danger' ? 'border-danger' : risk === 'warning' ? 'border-caution' : '';

  // 카드 헤더 chip — 차트 안에 그리던 라벨을 외부로 이동 (양방향 O2 가 chip 4개로 차트 면적 점유하던 문제 해소).
  const r = _resolveGas(gas);
  const thresholds = r.isO2
    ? [
        { at: r.dangerHigh, color: 'danger', label: `위험 ${r.dangerHigh}${r.unit}` },
        { at: r.warnHigh,   color: 'warn',   label: `주의 ${r.warnHigh}${r.unit}` },
        { at: r.warnLow,    color: 'warn',   label: `주의 ${r.warnLow}${r.unit}` },
        { at: r.dangerLow,  color: 'danger', label: `위험 ${r.dangerLow}${r.unit}` },
      ]
    : [
        ...(r.warn != null ? [{ at: r.warn, color: 'warn', label: `주의 ${r.warn}${r.unit}` }] : []),
        ...(r.danger != null ? [{ at: r.danger, color: 'danger', label: `위험 ${r.danger}${r.unit}` }] : []),
      ];

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
    <div class="chart-chips">${renderThresholdChipsHTML(thresholds)}</div>
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
    const risk  = _normalizeRisk(gasData[`${gas}_risk`]) || getRiskFromData(gas, value, null);
    const card  = buildGasCard(gas, value, risk);
    grid.appendChild(card);
  });

  // DOM 삽입 후 차트 생성
  GAS_KEYS.forEach(gas => {
    const value = gasData[gas] ?? null;
    const risk  = _normalizeRisk(gasData[`${gas}_risk`]) || 'normal';
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
const RISK_LABEL = { danger: '위험', warning: '주의', normal: '정상', safe: '정상' };

/* 서버에서 'safe'가 내려올 수 있으므로 'normal'로 통일한다 */
function _normalizeRisk(risk) {
  return (risk === 'safe' || !risk) ? 'normal' : risk;
}

function renderGasListTable(gasData = {}) {
  const tbody = document.getElementById('gas-tbody');
  if (!tbody) return;

  tbody.innerHTML = GAS_KEYS.map(gas => {
    const cfg   = GAS_CONFIG[gas];
    const value = gasData[gas] ?? null;
    const risk  = _normalizeRisk(gasData[`${gas}_risk`]);
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
    const risk = _normalizeRisk(gasData[`${gas}_risk`]);
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
document.addEventListener('DOMContentLoaded', async () => {
  document.getElementById('tab-realtime')?.addEventListener('click', () => switchGasTab('realtime'));
  document.getElementById('tab-ai')?.addEventListener('click',       () => switchGasTab('ai'));

  // 임계치 fetch 먼저 — 빈 캐시 상태에서 차트 그리면 임계 라인 hardcoded fallback 으로 잘못 표시.
  await loadGasThresholds();

  startGasClock();
  renderGasGrid({});
  renderGasListTable({});
  renderSensorTable({}, false);
});
