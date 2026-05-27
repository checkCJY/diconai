/* ──────────────────────────────────────────────────────────
   power_system.js  —  실시간/AI 예측 스마트 전력 현황
   의존: Chart.js 4.x, chartjs-plugin-annotation 3.x
   ────────────────────────────────────────────────────────── */

/* ── 전력 임계치 (채널별 W) ──────────────────────────────────────────
   단일 진실 공급원:
     1. % 임계치 (group="power_facility_default", item="power_w")
        → /api/monitoring/power/threshold-meta/
     2. 채널 정격 (PowerDevice.channel_meta[ch].rated_w)
        → /api/monitoring/power/channel-meta/
   환산: warning_w = rated_w × warning_max / 100  (fastapi equipment_builder 와 동일 시맨틱)
   정격 미입력 채널은 LEGACY_FALLBACK (power_default 그룹의 절대값) 사용. */

const LEGACY_FALLBACK = { caution: 2200, danger: 2860, maxY: 3500 };

/* 채널별 임계치 캐시: { 1: { caution, danger, maxY, name, rated_w }, 2: ..., } */
let CHANNEL_THRESHOLDS = {};

/* 전체 사용량(kW) 임계치 — 채널 정격 합 × % */
let TOTAL_KW_THRESHOLD = {
  caution_kw: LEGACY_FALLBACK.caution * 16 / 1000,
  danger_kw: LEGACY_FALLBACK.danger * 16 / 1000,
  max_kw: LEGACY_FALLBACK.maxY * 16 / 1000,
};

function _resolveChannel(ch) {
  return CHANNEL_THRESHOLDS[ch] || { ...LEGACY_FALLBACK, name: `CH${ch}`, rated_w: null };
}

async function loadThresholds() {
  try {
    const [metaRes, chanRes] = await Promise.all([
      fetch('/api/monitoring/power/threshold-meta/'),
      fetch('/api/monitoring/power/channel-meta/'),
    ]);
    if (!metaRes.ok || !chanRes.ok) return;
    const meta = await metaRes.json();
    const chanMap = await chanRes.json();  // { device_id: { "1": {...}, ... } }

    const wattPct = meta.power_w || {};
    const pctWarn = Number(wattPct.warning_max) || 80;
    const pctDanger = Number(wattPct.danger_max) || 100;

    // PowerDevice 단일 가정 (현재 1개) — 첫 device 의 channel_meta 사용. 시연 후 다공장은 facility 컨텍스트로 분기.
    const firstMeta = Object.values(chanMap)[0] || {};

    const next = {};
    let totalCautionW = 0;
    let totalDangerW = 0;
    for (let ch = 1; ch <= 16; ch++) {
      const entry = firstMeta[String(ch)] || {};
      const ratedW = Number(entry.rated_w) || 0;
      if (ratedW > 0) {
        const caution = Math.round(ratedW * pctWarn / 100);
        const danger = Math.round(ratedW * pctDanger / 100);
        // maxY 는 위 100 단위 올림 — 부동소수점 노이즈 제거 + 깔끔한 축 라벨
        const rawMax = danger * 1.15;
        next[ch] = {
          caution,
          danger,
          maxY: Math.ceil(rawMax / 100) * 100,
          name: entry.name || `CH${ch}`,
          rated_w: ratedW,
        };
        totalCautionW += caution;
        totalDangerW += danger;
      } else {
        // 정격 미입력 — power_default 그룹의 절대값 fallback
        next[ch] = { ...LEGACY_FALLBACK, name: entry.name || `CH${ch}`, rated_w: null };
        totalCautionW += LEGACY_FALLBACK.caution;
        totalDangerW += LEGACY_FALLBACK.danger;
      }
    }
    CHANNEL_THRESHOLDS = next;
    TOTAL_KW_THRESHOLD = {
      caution_kw: Math.round(totalCautionW / 100) / 10,  // 1자리 소수
      danger_kw: Math.round(totalDangerW / 100) / 10,
      max_kw: Math.ceil(totalDangerW * 1.15 / 1000),  // 정수 kW
    };
  } catch (_) { /* 네트워크 오류 시 LEGACY_FALLBACK 만으로 동작 */ }
}

/* ── 색상 팔레트 (CSS 변수와 동일) ── */
const COLOR = {
  danger:       '#f85149',
  caution:      '#e3b341',
  safe:         '#3fb950',
  dangerBg:     'rgba(248,81,73,0.20)',
  cautionBg:    'rgba(227,179,65,0.20)',
  gridLine:     'rgba(48,54,61,0.7)',
  tickText:     '#8b949e',
};

/* ── 현재 활성 탭 ── */
let activeTab = 'realtime';

/* ── 차트 인스턴스 캐시 ── */
const chartInstances = {};

/* ────────────────────────────────────────────
   유틸
────────────────────────────────────────────── */
/* watt(W) 기준 상태 계산 — 서버 risk_level 없을 때만 사용. 정격 모르므로 LEGACY_FALLBACK 절대값. */
function getStatus(watt) {
  if (watt === null || watt === undefined) return 'safe';
  if (watt >= LEGACY_FALLBACK.danger)  return 'danger';
  if (watt >= LEGACY_FALLBACK.caution) return 'caution';
  return 'safe';
}

function getBarColor(status) {
  return COLOR[status] ?? COLOR.safe;
}

/* ────────────────────────────────────────────
   Chart.js 막대 그래프 생성 — 시안 패턴 (3-segment stacked + dashed line + chip)

   [디자인 변경 — 2026-05-27]
   기존: 단일 색 막대 + caution/danger box(annotation) — band 가 면적 70% 점유
   신규: 정상/주의/위험 3-segment stacked 막대 + dashed 임계 라인 + 우측 칩
         + 막대 위 값 라벨. annotation 박스 제거.

   @param canvasId  - canvas 요소 id
   @param watt      - 전력값 (W 단위, null이면 빈 차트)
   @param status    - 'danger'|'caution'|'safe' (서버 risk_level 기반)
   @param channel   - 채널 번호 (1~16) — CHANNEL_THRESHOLDS 룩업 키
────────────────────────────────────────────── */
function createBarChart(canvasId, watt, status = 'safe', channel) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;

  if (chartInstances[canvasId]) {
    chartInstances[canvasId].destroy();
  }

  const t = _resolveChannel(channel);
  const cautionY = t.caution;
  const dangerY = t.danger;
  const maxY = t.maxY;

  // 3-segment 분할 (값이 null/없음 이면 0 → 빈 차트)
  const v = watt ?? 0;
  const normalSeg = Math.min(v, cautionY);
  const warnSeg = Math.max(0, Math.min(v, dangerY) - cautionY);
  const dangerSeg = Math.max(0, v - dangerY);

  // top 모서리 둥글기 — 가장 위 segment 에만 적용
  const topR = { topLeft: 4, topRight: 4, bottomLeft: 0, bottomRight: 0 };
  const noR = 0;
  const rNormal = warnSeg === 0 && dangerSeg === 0 ? topR : noR;
  const rWarn = warnSeg > 0 && dangerSeg === 0 ? topR : noR;
  const rDanger = dangerSeg > 0 ? topR : noR;

  // 막대 값 라벨 색 — status 따라
  const labelColor = status === 'danger' ? CHART_COLOR.danger
                   : status === 'caution' || status === 'warn' ? CHART_COLOR.warn
                   : CHART_COLOR.text;

  const chart = new Chart(canvas, {
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
      responsive: true,
      maintainAspectRatio: false,
      layout: { padding: { top: 18, right: 4, left: 0, bottom: 0 } },
      animation: { duration: 600, easing: 'easeOutCubic' },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#1F2A48', borderColor: CHART_COLOR.border, borderWidth: 1,
          padding: 8,
          filter: (item) => item.parsed.y > 0,  // 값 있는 segment 만
          callbacks: {
            title: () => '',
            label: (ctx) => {
              if (watt == null) return ' 데이터 없음';
              return `${ctx.dataset.label}: ${ctx.parsed.y} W`;
            },
            footer: () => {
              if (watt == null) return '';
              const pct = t.rated_w ? ((watt / t.rated_w) * 100).toFixed(1) + '%' : '-';
              return `합계 ${(watt / 1000).toFixed(2)} kW (부하 ${pct})`;
            },
          },
        },
        thresholdZones: {
          thresholds: [
            { at: dangerY, color: 'danger', label: `위험 ${(dangerY / 1000).toFixed(1).replace(/\.0$/, '')}k W` },
            { at: cautionY, color: 'warn', label: `주의 ${(cautionY / 1000).toFixed(1).replace(/\.0$/, '')}k W` },
          ],
        },
        barValueLabel: {
          show: watt != null,
          color: labelColor,
          formatter: () => `${(watt / 1000).toFixed(2)} kW`,
        },
      },
      scales: {
        x: {
          stacked: true,
          grid: { display: false }, ticks: { display: false }, border: { display: false },
        },
        y: {
          stacked: true,
          min: 0, max: maxY, beginAtZero: true,
          grid: { color: CHART_COLOR.gridLine, drawTicks: false },
          border: { display: false },
          ticks: {
            color: CHART_COLOR.text3, font: { size: 10 }, padding: 6, maxTicksLimit: 5,
            // 1000 이상은 "k" 단위, 1자리 소수 (트레일링 .0 제거).
            callback: (val) => {
              if (val >= 1000) {
                const k = (val / 1000).toFixed(1).replace(/\.0$/, '');
                return `${k}k`;
              }
              return val;
            },
          },
        },
      },
    },
  });

  chartInstances[canvasId] = chart;
  return chart;
}

/* ────────────────────────────────────────────
   카드 DOM 생성
────────────────────────────────────────────── */
function buildCard(index, equipData) {
  /* status: 서버 risk_level 우선, 없으면 watt 기준 계산 */
  const status = equipData?.status ?? getStatus(equipData?.watt ?? null);
  const label  = equipData?.name ?? `설비 ${index + 1}`;

  const borderClass = {
    danger:  'border-danger',
    caution: 'border-caution',
    safe:    '',
  }[status];

  // 카드 헤더 chip — 차트 안 라벨을 외부로 (가스 detail 과 동일 패턴). 채널 정격 × % 환산 값.
  const t = _resolveChannel(index + 1);
  const thresholds = [
    { at: t.caution, color: 'warn', label: `주의 ${(t.caution / 1000).toFixed(1).replace(/\.0$/, '')}k W` },
    { at: t.danger, color: 'danger', label: `위험 ${(t.danger / 1000).toFixed(1).replace(/\.0$/, '')}k W` },
  ];

  const card = document.createElement('div');
  card.className = `chart-card ${borderClass}`;
  card.dataset.index = index;

  card.innerHTML = `
    <div class="card-title">
      <span class="card-status-dot ${status}"></span>
      <span>${label}</span>
    </div>
    <div class="chart-chips">${renderThresholdChipsHTML(thresholds)}</div>
    <div class="card-chart-wrap">
      <canvas id="canvas-${index}"></canvas>
    </div>
  `;

  return card;
}

/* ────────────────────────────────────────────
   그리드 전체 렌더
   equipList: [{ name, watt(W), status }, ...]
────────────────────────────────────────────── */
function renderGrid(equipList = []) {
  const grid = document.getElementById('chart-grid');
  grid.innerHTML = '';

  // 실제 데이터 길이 우선. 미수신 시 CHANNEL_THRESHOLDS 로드 결과 (16) 또는 16 fallback.
  // 기존 매직 넘버 8 은 8채널 가정 시절의 잔재 — channel_count=16 으로 변경됨에 따라 수정.
  const count = equipList.length || Object.keys(CHANNEL_THRESHOLDS).length || 16;

  for (let i = 0; i < count; i++) {
    const data = equipList[i] ?? null;
    const card = buildCard(i, data);
    grid.appendChild(card);
  }

  /* 차트는 DOM 삽입 후 생성. channel = index+1 — CHANNEL_THRESHOLDS 의 채널 정격×% 환산 임계치 사용. */
  for (let i = 0; i < count; i++) {
    const eq = equipList[i];
    createBarChart(`canvas-${i}`, eq?.watt ?? null, eq?.status ?? 'safe', i + 1);
  }
}

/* ────────────────────────────────────────────
   탭 전환
────────────────────────────────────────────── */

/* 마지막으로 수신한 실시간 equipment 캐시 (AI 탭에서 대체 표시용) */
let _lastEquipCache = [];

function switchTab(tab) {
  activeTab = tab;
  document.getElementById('tab-realtime').classList.toggle('active', tab === 'realtime');
  document.getElementById('tab-ai').classList.toggle('active',       tab === 'ai');

  const banner = document.getElementById('ai-notice-banner');
  if (banner) banner.style.display = tab === 'ai' ? 'block' : 'none';

  if (tab === 'ai') {
    /* AI 모델 미연동 — 실시간 캐시 데이터로 대체 표시
       TODO (4차 프로젝트): AI 예측 API 연동으로 교체 */
    renderGrid(_lastEquipCache);
  }
}

/* ────────────────────────────────────────────
   데이터 로드 (WebSocket 연동은 websocket_power.js)
────────────────────────────────────────────── */
function loadRealtimeData() {
  renderGrid([]);
  updateStatusBar(null);
}

/* 외부(websocket_power.js)에서 실시간 데이터 수신 시 호출 */
function updateRealtimeGrid(equipList) {
  _lastEquipCache = equipList;
  if (activeTab === 'realtime') {
    renderGrid(equipList);
  }
}

/* ────────────────────────────────────────────
   하단 상태 바 업데이트
────────────────────────────────────────────── */
function updateStatusBar(equipData) {
  document.getElementById('status-equip-name').textContent = equipData?.name  ?? '-';
  document.getElementById('status-msg').textContent        = equipData?.msg   ?? '-';
  document.getElementById('status-alert').textContent      = equipData?.alert ?? '-';
}

/* ────────────────────────────────────────────
   시계
────────────────────────────────────────────── */
function startClock() {
  function tick() {
    const now = new Date();
    const pad = (n) => String(n).padStart(2, '0');
    document.getElementById('status-time').textContent =
      `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
  }
  tick();
  setInterval(tick, 1000);
}

/* ────────────────────────────────────────────
   초기화
────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', async () => {
  document.getElementById('tab-realtime')
    .addEventListener('click', () => switchTab('realtime'));
  document.getElementById('tab-ai')
    .addEventListener('click', () => switchTab('ai'));

  await loadThresholds();
  startClock();
  loadRealtimeData();
});
