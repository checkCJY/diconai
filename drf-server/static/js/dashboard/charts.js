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

// ── Phase A 전력 임계치 ───────────────────────────────────
// 채널별 임계치 (W). 각 설비 페이지에서 사용.
const POWER_THRESHOLD_WARNING = 2200;
const POWER_THRESHOLD_DANGER  = Math.round(2200 * 1.3);  // 2860
// 전체 사용량 임계치 (kW). "전체 사용량" 페이지에서 사용.
// 16채널 동시 임계치 가정: 16 × 2200 ≈ 35.2, 16 × 2860 ≈ 45.76
const POWER_TOTAL_THRESHOLD_WARNING_KW = 35;
const POWER_TOTAL_THRESHOLD_DANGER_KW  = 46;

// ── Chart.js 공통 기본 옵션 ───────────────────────────────
const CHART_DEFAULTS = {
  animation: false, responsive: true, maintainAspectRatio: true,
  plugins: { legend: { labels: { color: '#aaa', font: { size: 10 }, boxWidth: 12 } } },
  scales: {
    x: { ticks: { color: '#666', maxTicksLimit: 6, font: { size: 9 } }, grid: { color: '#2a2a2a' } },
    y: { ticks: { color: '#666', font: { size: 9 } },                   grid: { color: '#2a2a2a' } },
  },
};

// 전력 차트 Y축 전용 옵션 — 1000 W 단위 눈금, 3자리 콤마 포맷 (채널별 페이지)
const POWER_CHART_Y_OPTS = {
  ticks: {
    color: '#666', font: { size: 9 },
    stepSize: 1000,
    callback: value => value.toLocaleString(),
  },
  grid: { color: '#2a2a2a' },
};

// "전체 사용량" 페이지 전용 Y축 — 10 kW 단위, 0~80 kW 가시화
const POWER_CHART_Y_OPTS_KW = {
  ticks: {
    color: '#666', font: { size: 9 },
    stepSize: 10,
    callback: value => value.toLocaleString(),
  },
  grid: { color: '#2a2a2a' },
  suggestedMin: 0,
  suggestedMax: 80,
};

let gasChart   = null;
let powerChart = null;

/* ── SoT 임계치 캐시 ───────────────────────────────────────
   detail 페이지 (gas_monitoring.js, power_system.js) 의 동일 패턴 — dashboard 도
   페이지 진입 시 1회 fetch. 가스는 9종 hardcoded 와 동일값이지만 admin 변경 시
   즉시 반영. 전력은 채널 정격(power_facility_default %) × 정격으로 환산. */
let DASH_GAS_THRESHOLDS = {};        // { co: {warning_max, danger_max, ...}, o2: {...} }
let DASH_POWER_CHANNELS = {};        // { 1: {caution, danger, name, rated_w}, ... }
let DASH_POWER_TOTAL = {              // 전체 사용량 (kW) 임계치 — 채널 정격 합 × %
  caution_kw: POWER_TOTAL_THRESHOLD_WARNING_KW,
  danger_kw: POWER_TOTAL_THRESHOLD_DANGER_KW,
};
const DASH_POWER_FALLBACK_W = { caution: POWER_THRESHOLD_WARNING, danger: POWER_THRESHOLD_DANGER };

async function loadDashboardThresholds() {
  // 1. 가스 임계치 (9가스)
  try {
    const res = await fetch('/api/monitoring/gas/thresholds/');
    if (res.ok) DASH_GAS_THRESHOLDS = await res.json();
  } catch (_) { /* fallback: 빈 객체 → updateGasThresholds 가 threshold 안 그림 */ }

  // 2. 전력 % 임계치 + 채널 정격 → 채널별 caution/danger W 환산
  try {
    const [metaRes, chanRes] = await Promise.all([
      fetch('/api/monitoring/power/threshold-meta/'),
      fetch('/api/monitoring/power/channel-meta/'),
    ]);
    if (!metaRes.ok || !chanRes.ok) return;
    const meta = await metaRes.json();
    const chanMap = await chanRes.json();
    const wattPct = meta.power_w || {};
    const pctWarn = Number(wattPct.warning_max) || 80;
    const pctDanger = Number(wattPct.danger_max) || 100;
    const firstMeta = Object.values(chanMap)[0] || {};

    let totalCaution = 0;
    let totalDanger = 0;
    for (let ch = 1; ch <= 16; ch++) {
      const entry = firstMeta[String(ch)] || {};
      const ratedW = Number(entry.rated_w) || 0;
      if (ratedW > 0) {
        const caution = Math.round(ratedW * pctWarn / 100);
        const danger = Math.round(ratedW * pctDanger / 100);
        DASH_POWER_CHANNELS[ch] = { caution, danger, name: entry.name || `CH${ch}`, rated_w: ratedW };
        totalCaution += caution;
        totalDanger += danger;
      } else {
        DASH_POWER_CHANNELS[ch] = { ...DASH_POWER_FALLBACK_W, name: entry.name || `CH${ch}`, rated_w: null };
        totalCaution += DASH_POWER_FALLBACK_W.caution;
        totalDanger += DASH_POWER_FALLBACK_W.danger;
      }
    }
    DASH_POWER_TOTAL = {
      caution_kw: Math.round(totalCaution / 100) / 10,
      danger_kw: Math.round(totalDanger / 100) / 10,
    };
  } catch (_) { /* fallback 유지 */ }
}

/* ── 임계치 → thresholdZones plugin 옵션 형식 ─────────────
   dir: 'above' — 값이 at 이상이면 위험 / 'below' — at 이하면 위험 (O2 양방향용).
   segment.borderColor 함수가 이 dir 로 임계 넘은 방향 판정. */
function _powerThresholds(warn, danger, unit) {
  if (warn == null || danger == null) return [];
  return [
    { at: warn, color: 'warn', label: `주의 ${warn}${unit}`, dir: 'above' },
    { at: danger, color: 'danger', label: `위험 ${danger}${unit}`, dir: 'above' },
  ];
}

// 가스·전력 차트를 초기화하고 전역 변수(gasChart, powerChart)에 할당한다.
// [디자인 변경 — 2026-05-27]
// 이전: annotation box (band fill) 가 차트 면적 점유 — 시각 노이즈.
// 신규: thresholdZones plugin (dashed line 만 그리고 chip 라벨은 차트 외부 — chart-helpers 의 showChip:false).
function initCharts() {
  // 2026-05-27 디자인 다듬기 2nd: 예측 라인은 노랑이 아닌 빨강 (위험 신호 명확).
  // 우리 데이터 모델은 같은 시간축에 실측+예측 동시 표시 → 예측이 곧 위험 경고.
  // brand 파랑 fill alpha 0.06 너무 옅음 → 0.14 로 키워 선명도 ↑.
  const _gasLineOpts = (color, fill, dash) => ({
    borderColor: color,
    backgroundColor: fill,
    borderWidth: 2,
    borderDash: dash,
    tension: 0.35,
    pointRadius: 0,
    pointHoverRadius: 4,
    fill: !!fill,
  });
  // ticks 톤 — chart-helpers 의 text2 (#95A0B8) 보다 더 밝게 (다크 배경 대비 ↑).
  // legend·tooltip 도 동일 톤 적용을 위해 객체로 분리.
  const _brightTickOpts = {
    color: '#C9D1D9',
    font: { size: 12 },
  };

  // brand fill 더 진하게 — chart-helpers 의 brandFill (alpha 0.14) 그대로 적합. 부족하면 인라인 강화.
  const _brandFillStrong = 'rgba(96, 165, 250, 0.18)';

  // segment.borderColor — 라인의 각 segment 끝값(p1.y)이 임계 넘으면 그 segment 만 빨강/노랑.
  // 기존 thresholdZones plugin 의 thresholds 배열 (dir 필드 포함) 을 직접 참조 — 별도 캐시 X.
  // dataset.borderColor (brand) 가 기본, segment 함수가 undefined 반환 시 그 색 유지.
  const _segmentColorFromThresholds = (ctx) => {
    const ths = ctx.chart.options.plugins?.thresholdZones?.thresholds ?? [];
    const v = ctx.p1.parsed.y;
    const hit = (color) => ths.find(t => t.color === color &&
      (t.dir === 'below' ? v <= t.at : v >= t.at));
    if (hit('danger')) return CHART_COLOR.danger;
    if (hit('warn')) return CHART_COLOR.warn;
    return undefined;
  };

  const ctxGas = document.getElementById('chartGas');
  gasChart = ctxGas ? new Chart(ctxGas, {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        { label: '현재 농도 (ppm)',      data: [], ..._gasLineOpts(CHART_COLOR.brand, _brandFillStrong, undefined),
          segment: { borderColor: _segmentColorFromThresholds } },
        // 예측은 위험 신호 — 빨강 dashed (이전 노랑 시도는 우리 데이터 모델과 안 맞음).
        { label: '예측 최대 농도 (ppm)', data: [], ..._gasLineOpts(CHART_COLOR.danger, false, [5, 4]) },
      ],
    },
    options: {
      ...CHART_DEFAULTS,
      interaction: { intersect: false, mode: 'index' },
      plugins: {
        ...CHART_DEFAULTS.plugins,
        legend: { display: true, position: 'top', align: 'end',
          labels: { color: '#C9D1D9', font: { size: 12, weight: '600' }, boxWidth: 14, boxHeight: 2, padding: 10, usePointStyle: false },
        },
        tooltip: { backgroundColor: '#1F2A48', borderColor: CHART_COLOR.border, borderWidth: 1, padding: 8 },
        thresholdZones: { thresholds: [] },  // _switchGasChart 가 가스별 임계치로 업데이트
      },
      scales: {
        x: { ticks: _brightTickOpts, grid: { color: CHART_COLOR.gridLine }, border: { display: false } },
        y: { ticks: _brightTickOpts, grid: { color: CHART_COLOR.gridLine }, border: { display: false }, beginAtZero: true },
      },
    },
  }) : null;

  const ctxPower = document.getElementById('chartPower');
  powerChart = ctxPower ? new Chart(ctxPower, {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        { label: '예상 최대 부하 (kW)', data: [], ..._gasLineOpts(CHART_COLOR.brand, _brandFillStrong, undefined),
          segment: { borderColor: _segmentColorFromThresholds } },
      ],
    },
    options: {
      ...CHART_DEFAULTS,
      interaction: { intersect: false, mode: 'index' },
      plugins: {
        ...CHART_DEFAULTS.plugins,
        legend: { display: true, position: 'top', align: 'end',
          labels: { color: '#C9D1D9', font: { size: 12, weight: '600' }, boxWidth: 14, boxHeight: 2, padding: 10, usePointStyle: false },
        },
        tooltip: { backgroundColor: '#1F2A48', borderColor: CHART_COLOR.border, borderWidth: 1, padding: 8 },
        thresholdZones: { thresholds: _powerThresholds(POWER_THRESHOLD_WARNING, POWER_THRESHOLD_DANGER, 'W') },
      },
      scales: {
        x: { ticks: _brightTickOpts, grid: { color: CHART_COLOR.gridLine }, border: { display: false } },
        y: { ...POWER_CHART_Y_OPTS, ticks: { ...(POWER_CHART_Y_OPTS.ticks || {}), ..._brightTickOpts } },
      },
    },
  }) : null;
}

// 현재 선택된 가스의 임계치로 thresholdZones 업데이트.
// _switchGasChart() 가 가스 전환 시 호출. 양방향(O2) 도 4 threshold 모두 표시.
// dir 필드 — segment.borderColor 가 위/아래 어느 쪽으로 넘었는지 판정에 사용.
function updateGasThresholds(gasKey) {
  if (!gasChart) return;
  const t = DASH_GAS_THRESHOLDS[gasKey] || {};
  const unit = t.unit || '';
  const thresholds = [];
  if (t.danger_max != null) thresholds.push({ at: t.danger_max, color: 'danger', label: `위험 ${t.danger_max}${unit}`, dir: 'above' });
  if (t.warning_max != null) thresholds.push({ at: t.warning_max, color: 'warn', label: `주의 ${t.warning_max}${unit}`, dir: 'above' });
  if (t.warning_min != null) thresholds.push({ at: t.warning_min, color: 'warn', label: `주의 ${t.warning_min}${unit}`, dir: 'below' });
  if (t.danger_min != null) thresholds.push({ at: t.danger_min, color: 'danger', label: `위험 ${t.danger_min}${unit}`, dir: 'below' });
  gasChart.options.plugins.thresholdZones = { thresholds };
  gasChart.update('none');
}

// [Phase B] 페이로드에 동적 임계치가 포함될 때 thresholds 를 실시간 교체.
// ws.onmessage 에서 data.threshold_warning_kw 가 있으면 호출 (현 시점 미사용 hook).
function updatePowerThresholds(warnKw, dangerKw) {
  if (!powerChart) return;
  powerChart.options.plugins.thresholdZones = { thresholds: _powerThresholds(warnKw, dangerKw, 'kW') };
  powerChart.update('none');
}

// 페이지 단위(kW=전체 사용량 / W=설비별)에 따라 차트의 Y축·임계치·라벨 교체.
// _switchPowerChart(idx) 가 idx=0 이면 'kW' (전체), idx>=1 이면 'W' (채널 idx).
// channel 인자 — idx>=1 일 때 채널별 SoT 임계치 lookup (DASH_POWER_CHANNELS[channel]).
function applyPowerChartUnit(unit, channel) {
  if (!powerChart) return;
  if (unit === 'kW') {
    powerChart.options.scales.y = POWER_CHART_Y_OPTS_KW;
    powerChart.options.plugins.thresholdZones = {
      thresholds: _powerThresholds(DASH_POWER_TOTAL.caution_kw, DASH_POWER_TOTAL.danger_kw, 'kW'),
    };
    powerChart.data.datasets[0].label = '예상 최대 부하 (kW)';
  } else {
    powerChart.options.scales.y = POWER_CHART_Y_OPTS;
    const ch = DASH_POWER_CHANNELS[channel] || DASH_POWER_FALLBACK_W;
    powerChart.options.plugins.thresholdZones = {
      thresholds: _powerThresholds(ch.caution, ch.danger, 'W'),
    };
    powerChart.data.datasets[0].label = '예상 최대 부하 (W)';
  }
}
