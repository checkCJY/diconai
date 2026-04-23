/* ==========================================================
   charts_CJY.js — Chart.js 실시간 차트 + 임계치 영역 (전력 패널)
   charts.js 베이스에 chartjs-plugin-annotation 추가.

   의존: Chart.js 4 (CDN), chartjs-plugin-annotation 3 (CDN),
         util.js (MAX_POINTS, nowLabel, pushData)

   [임계치 관리 — 2단계]
     Phase A (현재): 채널별 서버 기준을 합산 환산한 고정값
       주의 20 kW  = 8채널 × 2500 W  (_build_equipment warning 기준)
       위험 28 kW  = 7채널 × 4000 W  (_build_equipment danger  기준)

     Phase B (데이터 축적 후):
       페이로드에 threshold_warning_kw / threshold_danger_kw 추가 시
       ws.onmessage 에서 updatePowerThresholds() 호출로 교체.
       websocket_CJY.py _build_broadcast_payload() 에 두 키 추가 필요.
   ========================================================== */

'use strict';

// ── Phase A 고정 임계치 (kW) ───────────────────────────────
// Phase B: 페이로드 수신 값으로 교체 → updatePowerThresholds() 참조
const POWER_THRESHOLD_WARNING = 20;   // kW — 주의 하한
const POWER_THRESHOLD_DANGER  = 28;   // kW — 위험 하한

// ──────────────────────────────────────────────────────────
// Chart.js 공통 기본값
// ──────────────────────────────────────────────────────────
const CHART_DEFAULTS = {
  animation: false, responsive: true, maintainAspectRatio: true,
  plugins: { legend: { labels: { color: '#aaa', font: { size: 10 }, boxWidth: 12 } } },
  scales: {
    x: { ticks: { color: '#666', maxTicksLimit: 6, font: { size: 9 } }, grid: { color: '#2a2a2a' } },
    y: { ticks: { color: '#666', font: { size: 9 } },                   grid: { color: '#2a2a2a' } },
  },
};

const POWER_CHART_Y_OPTS = {
  ticks: {
    color: '#666',
    font: { size: 9 },
    stepSize: 10000,
    callback: value => value.toLocaleString(),
  },
  grid: { color: '#2a2a2a' },
};

let gasChart   = null;
let powerChart = null;

// ── 전력 임계치 annotation 설정 생성 ──────────────────────
function _powerAnnotations(warnKw, dangerKw) {
  return {
    // 주의 영역 (가로 띠)
    warnBand: {
      type: 'box',
      yMin: warnKw, yMax: dangerKw,
      backgroundColor: 'rgba(245,158,11,0.10)',
      borderWidth: 0,
    },
    // 위험 영역 (가로 띠 — yMax 생략 시 차트 상단까지)
    dangerBand: {
      type: 'box',
      yMin: dangerKw,
      backgroundColor: 'rgba(239,68,68,0.10)',
      borderWidth: 0,
    },
    // 주의 경계선
    warnLine: {
      type: 'line',
      yMin: warnKw, yMax: warnKw,
      borderColor: 'rgba(245,158,11,0.55)',
      borderWidth: 1,
      borderDash: [4, 3],
      label: {
        content: '주의',
        display: true,
        position: 'end',
        color: '#f59e0b',
        font: { size: 9 },
        backgroundColor: 'transparent',
        padding: 2,
      },
    },
    // 위험 경계선
    dangerLine: {
      type: 'line',
      yMin: dangerKw, yMax: dangerKw,
      borderColor: 'rgba(239,68,68,0.55)',
      borderWidth: 1,
      borderDash: [4, 3],
      label: {
        content: '위험',
        display: true,
        position: 'end',
        color: '#ef4444',
        font: { size: 9 },
        backgroundColor: 'transparent',
        padding: 2,
      },
    },
  };
}

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
    options: {
      ...CHART_DEFAULTS,
      plugins: {
        ...CHART_DEFAULTS.plugins,
        annotation: {
          annotations: _powerAnnotations(POWER_THRESHOLD_WARNING, POWER_THRESHOLD_DANGER),
        },
      },
      scales: {
        ...CHART_DEFAULTS.scales,
        y: POWER_CHART_Y_OPTS,
      },
    },
  }) : null;

  initYScaleControls();
}

// ── Phase B 진입 시 호출 ────────────────────────────────────
// ws.onmessage 에서:
//   if (data.threshold_warning_kw !== undefined)
//     updatePowerThresholds(data.threshold_warning_kw, data.threshold_danger_kw);
function updatePowerThresholds(warnKw, dangerKw) {
  if (!powerChart) return;
  powerChart.options.plugins.annotation.annotations =
    _powerAnnotations(warnKw, dangerKw);
  powerChart.update('none');
}

// ──────────────────────────────────────────────────────────
// Y축 수동 스케일 조절 (줌 버튼)
// ──────────────────────────────────────────────────────────
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
    const isPower = key === 'power';
    const step    = isPower ? 10000 : 10;
    const current = scaleState[key] ?? chart.scales.y.max;
    const next    = direction > 0 ? current - step : current + step;
    scaleState[key] = Math.max(step, isPower ? Math.round(next / step) * step : Math.round(next));
    chart.options.scales.y.max = scaleState[key];
    if (labelEl) labelEl.textContent = scaleState[key].toLocaleString();
  }
  chart.update('none');
}

function initYScaleControls() {
  document.getElementById('gasZoomIn') ?.addEventListener('click', () => adjustYScale('gas', gasChart, +1));
  document.getElementById('gasZoomOut')?.addEventListener('click', () => adjustYScale('gas', gasChart, -1));
  document.getElementById('gasReset')  ?.addEventListener('click', () => adjustYScale('gas', gasChart,  0));
}
