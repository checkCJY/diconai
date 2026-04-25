/* ==========================================================
   charts.js — Chart.js 실시간 차트 (패널 13 가스, 15 전력)

   의존: Chart.js 4 (CDN), chartjs-plugin-annotation 3 (CDN),
         util.js (MAX_POINTS, nowLabel, pushData)

   [전력 임계치 — 2단계 관리]
     Phase A (현재): 고정값
       안전    0 ~ 2200 kW
       주의  2200 ~ 2860 kW  (2200 × 1.3)
       위험  2860 kW 이상

     Phase B (데이터 축적 후):
       페이로드에 threshold_warning_kw / threshold_danger_kw 추가 시
       updatePowerThresholds() 호출로 교체.
   ========================================================== */

'use strict';

// ── Phase A 전력 임계치 (kW) ──────────────────────────────
const POWER_THRESHOLD_WARNING = 2200;
const POWER_THRESHOLD_DANGER  = Math.round(2200 * 1.3);  // 2860

// ── Chart.js 공통 기본 옵션 ───────────────────────────────
const CHART_DEFAULTS = {
  animation: false, responsive: true, maintainAspectRatio: true,
  plugins: { legend: { labels: { color: '#aaa', font: { size: 10 }, boxWidth: 12 } } },
  scales: {
    x: { ticks: { color: '#666', maxTicksLimit: 6, font: { size: 9 } }, grid: { color: '#2a2a2a' } },
    y: { ticks: { color: '#666', font: { size: 9 } },                   grid: { color: '#2a2a2a' } },
  },
};

// 전력 차트 Y축 전용 옵션 — 1000 kW 단위 눈금, 3자리 콤마 포맷
const POWER_CHART_Y_OPTS = {
  ticks: {
    color: '#666', font: { size: 9 },
    stepSize: 1000,
    callback: value => value.toLocaleString(),
  },
  grid: { color: '#2a2a2a' },
};

let gasChart   = null;
let powerChart = null;

// 전력 임계치 annotation 설정(주의/위험 영역 띠 + 경계선)을 생성해 반환한다.
function _powerAnnotations(warnKw, dangerKw) {
  return {
    warnBand: {
      type: 'box', yMin: warnKw, yMax: dangerKw,
      backgroundColor: 'rgba(245,158,11,0.10)', borderWidth: 0,
    },
    dangerBand: {
      type: 'box', yMin: dangerKw,
      backgroundColor: 'rgba(239,68,68,0.10)', borderWidth: 0,
    },
    warnLine: {
      type: 'line', yMin: warnKw, yMax: warnKw,
      borderColor: 'rgba(245,158,11,0.55)', borderWidth: 1, borderDash: [4, 3],
      label: { content: '주의', display: true, position: 'end', color: '#f59e0b', font: { size: 9 }, backgroundColor: 'transparent', padding: 2 },
    },
    dangerLine: {
      type: 'line', yMin: dangerKw, yMax: dangerKw,
      borderColor: 'rgba(239,68,68,0.55)', borderWidth: 1, borderDash: [4, 3],
      label: { content: '위험', display: true, position: 'end', color: '#ef4444', font: { size: 9 }, backgroundColor: 'transparent', padding: 2 },
    },
  };
}

// 가스·전력 차트를 초기화하고 전역 변수(gasChart, powerChart)에 할당한다.
function initCharts() {
  const ctxGas = document.getElementById('chartGas');
  gasChart = ctxGas ? new Chart(ctxGas, {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        { label: '현재 농도 (ppm)',      data: [], borderColor: '#f59e0b', backgroundColor: 'rgba(245,158,11,0.12)', tension: 0.4, pointRadius: 2, fill: true  },
        { label: '예측 최대 농도 (ppm)', data: [], borderColor: '#ef4444', backgroundColor: 'transparent',          borderDash: [5, 3], tension: 0.4, pointRadius: 2, fill: false },
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
        annotation: { annotations: _powerAnnotations(POWER_THRESHOLD_WARNING, POWER_THRESHOLD_DANGER) },
      },
      scales: { ...CHART_DEFAULTS.scales, y: POWER_CHART_Y_OPTS },
    },
  }) : null;
}

// [Phase B] 페이로드에 동적 임계치가 포함될 때 annotation을 실시간으로 교체한다.
// ws.onmessage에서 data.threshold_warning_kw가 있으면 이 함수를 호출한다.
function updatePowerThresholds(warnKw, dangerKw) {
  if (!powerChart) return;
  powerChart.options.plugins.annotation.annotations = _powerAnnotations(warnKw, dangerKw);
  powerChart.update('none');
}
