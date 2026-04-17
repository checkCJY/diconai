/* ==========================================================
   charts.js — Chart.js 실시간 차트 (패널 13, 15)
   출처: dashboard.js CHART_DEFAULTS · initCharts · adjustYScale · initYScaleControls
   의존: Chart.js (CDN), util.js (MAX_POINTS, nowLabel, pushData)
   ========================================================== */

'use strict';

// ──────────────────────────────────────────────────────────
// Chart.js 실시간 차트 (패널 13, 15)
// MAX_POINTS / nowLabel / pushData → util.js 참조
// ──────────────────────────────────────────────────────────
const CHART_DEFAULTS = {
  animation: false, responsive: true, maintainAspectRatio: true,
  plugins: { legend: { labels: { color: '#aaa', font: { size: 10 }, boxWidth: 12 } } },
  scales: {
    x: { ticks: { color: '#666', maxTicksLimit: 6, font: { size: 9 } }, grid: { color: '#2a2a2a' } },
    y: { ticks: { color: '#666', font: { size: 9 } },                   grid: { color: '#2a2a2a' } },
  },
};

let gasChart   = null;
let powerChart = null;

function initCharts() {
  const ctxGas = document.getElementById('chartGas');
  gasChart = ctxGas ? new Chart(ctxGas, {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        { label: '현재 농도 (ppm)',      data: [], borderColor: '#f59e0b', backgroundColor: 'rgba(245,158,11,0.12)', tension: 0.4, pointRadius: 2, fill: true  },
        { label: '예측 최대 농도 (ppm)', data: [], borderColor: '#ef4444', backgroundColor: 'transparent', borderDash: [5, 3], tension: 0.4, pointRadius: 2, fill: false },
      ],
    },
    options: CHART_DEFAULTS,
  }) : null;

  const ctxPower = document.getElementById('chartPower');
  powerChart = ctxPower ? new Chart(ctxPower, {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        { label: '예상 최대 부하 (kW)', data: [], borderColor: '#ef4444', backgroundColor: 'rgba(239,68,68,0.12)', tension: 0.4, pointRadius: 2, fill: true },
      ],
    },
    options: CHART_DEFAULTS,
  }) : null;

  initYScaleControls();
}

const scaleState = { gas: null, power: null };
function adjustYScale(key, chart, direction) {
  if (!chart) return;
  const labelEl = document.getElementById(key + 'ScaleVal');
  if (direction === 0) {
    scaleState[key] = null;
    chart.options.scales.y.max = undefined;
    chart.options.scales.y.min = undefined;
    if (labelEl) labelEl.textContent = '자동';
  } else {
    const current     = scaleState[key] ?? chart.scales.y.max;
    const factor      = direction > 0 ? 0.75 : 1.35;
    scaleState[key]   = Math.max(1, Math.round(current * factor));
    chart.options.scales.y.max = scaleState[key];
    if (labelEl) labelEl.textContent = scaleState[key].toLocaleString();
  }
  chart.update('none');
}

function initYScaleControls() {
  document.getElementById('gasZoomIn')   ?.addEventListener('click', () => adjustYScale('gas',   gasChart,    +1));
  document.getElementById('gasZoomOut')  ?.addEventListener('click', () => adjustYScale('gas',   gasChart,    -1));
  document.getElementById('gasReset')    ?.addEventListener('click', () => adjustYScale('gas',   gasChart,     0));
  document.getElementById('powerZoomIn') ?.addEventListener('click', () => adjustYScale('power', powerChart, +1));
  document.getElementById('powerZoomOut')?.addEventListener('click', () => adjustYScale('power', powerChart, -1));
  document.getElementById('powerReset')  ?.addEventListener('click', () => adjustYScale('power', powerChart,  0));
}
