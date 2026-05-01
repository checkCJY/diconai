/* ──────────────────────────────────────────────────────────
   power_system.js  —  실시간/AI 예측 스마트 전력 현황
   의존: Chart.js 4.x, chartjs-plugin-annotation 3.x
   ────────────────────────────────────────────────────────── */

/* ── 전력 임계치 (W) — GET /api/monitoring/power/thresholds/ 에서 로드 ── */
let THRESHOLD = {
  caution: 2200,
  danger:  2860,
  maxY:    3500,
};

async function loadThresholds() {
  try {
    const res = await fetch('/api/monitoring/power/thresholds/');
    if (!res.ok) return;
    const data = await res.json();
    THRESHOLD = { caution: data.caution, danger: data.danger, maxY: data.maxY };
  } catch (_) { /* 네트워크 오류 시 기본값 유지 */ }
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
/* watt(W) 기준 상태 계산 — 서버 risk_level 없을 때만 사용 */
function getStatus(watt) {
  if (watt === null || watt === undefined) return 'safe';
  if (watt >= THRESHOLD.danger)  return 'danger';
  if (watt >= THRESHOLD.caution) return 'caution';
  return 'safe';
}

function getBarColor(status) {
  return COLOR[status] ?? COLOR.safe;
}

/* ────────────────────────────────────────────
   Chart.js 막대 그래프 생성
   @param canvasId  - canvas 요소 id
   @param watt      - 전력값 (W 단위, null이면 빈 차트)
   @param status    - 'danger'|'caution'|'safe' (서버 risk_level 기반)
   @param maxY      - Y축 최대값 (W, 미전달 시 THRESHOLD.maxY)
────────────────────────────────────────────── */
function createBarChart(canvasId, watt, status = 'safe', maxY = THRESHOLD.maxY) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;

  if (chartInstances[canvasId]) {
    chartInstances[canvasId].destroy();
  }

  const barColor = getBarColor(status);
  const barValue = watt ?? 0;

  const chart = new Chart(canvas, {
    type: 'bar',
    data: {
      labels: [''],
      datasets: [{
        label: '전력 사용량',
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
          titleFont:       { size: 10 },
          bodyColor:       '#e6edf3',
          bodyFont:        { size: 11 },
          bodySpacing:     5,
          displayColors:   false,
          callbacks: {
            title: () => '',
            label: () => {
              if (watt === null || watt === undefined) return ' 데이터 없음';
              return [
                `현재 사용 전력량   ${(watt / 1000).toFixed(2)} kW`,
              ];
            },
          },
        },
        annotation: {
          annotations: {
            dangerBox: {
              type:            'box',
              yMin:            THRESHOLD.danger,
              yMax:            maxY,
              backgroundColor: COLOR.dangerBg,
              borderWidth:     0,
            },
            cautionBox: {
              type:            'box',
              yMin:            THRESHOLD.caution,
              yMax:            THRESHOLD.danger,
              backgroundColor: COLOR.cautionBg,
              borderWidth:     0,
            },
            dangerLine: {
              type:        'line',
              yMin:        THRESHOLD.danger,
              yMax:        THRESHOLD.danger,
              borderColor: COLOR.danger,
              borderWidth: 1,
              borderDash:  [4, 3],
              label: { display: false },
            },
            cautionLine: {
              type:        'line',
              yMin:        THRESHOLD.caution,
              yMax:        THRESHOLD.caution,
              borderColor: COLOR.caution,
              borderWidth: 1,
              borderDash:  [4, 3],
              label: { display: false },
            },
          },
        },
      },
      scales: {
        x: {
          grid:   { color: COLOR.gridLine },
          ticks:  { color: COLOR.tickText, font: { size: 10 } },
          border: { color: '#30363d' },
        },
        y: {
          min:  0,
          max:  maxY,
          grid:   { color: COLOR.gridLine },
          ticks:  {
            color:    COLOR.tickText,
            font:     { size: 10 },
            callback: (v) => v >= 1000 ? `${v/1000}k` : v,
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

  const card = document.createElement('div');
  card.className = `chart-card ${borderClass}`;
  card.dataset.index = index;

  card.innerHTML = `
    <div class="card-title">
      <span class="card-status-dot ${status}"></span>
      <span>${label}</span>
    </div>
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

  const count = equipList.length || 8;

  /* 전체 중 최대 watt 기준 Y축 최대값 계산
     - THRESHOLD.maxY 이상 보장 (임계치 라인이 항상 보이도록)
     - 실제 최대값이 더 크면 10% 여유 추가 후 올림 */
  const maxWatt = Math.max(...equipList.map(e => e.watt ?? 0), 0);
  const dynamicMaxY = maxWatt > THRESHOLD.maxY
    ? Math.ceil(maxWatt * 1.1 / 100) * 100
    : THRESHOLD.maxY;

  for (let i = 0; i < count; i++) {
    const data = equipList[i] ?? null;
    const card = buildCard(i, data);
    grid.appendChild(card);
  }

  /* 차트는 DOM 삽입 후 생성 */
  for (let i = 0; i < count; i++) {
    const eq = equipList[i];
    createBarChart(`canvas-${i}`, eq?.watt ?? null, eq?.status ?? 'safe', dynamicMaxY);
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
