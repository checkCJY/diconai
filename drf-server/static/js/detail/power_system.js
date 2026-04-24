/* ──────────────────────────────────────────────────────────
   power_system.js  —  실시간/AI 예측 스마트 전력 현황
   의존: Chart.js 4.x, chartjs-plugin-annotation 3.x
   ────────────────────────────────────────────────────────── */

/* ── Phase A 임계치 고정값 (단위: kW) ── */
const THRESHOLD = {
  caution: 2200,          // 안전 → 주의 경계
  danger:  2860,          // 주의 → 위험 경계  (2200 × 1.3)
  maxY:    3500,          // Y축 최대값
};

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
function getStatus(kw) {
  if (kw === null || kw === undefined) return 'safe';
  if (kw >= THRESHOLD.danger)  return 'danger';
  if (kw >= THRESHOLD.caution) return 'caution';
  return 'safe';
}

function getBarColor(status) {
  return COLOR[status] ?? COLOR.safe;
}

/* ────────────────────────────────────────────
   Chart.js 막대 그래프 생성
   - annotation 플러그인으로 주의/위험 임계치 점선 표시
   - 주의/위험 범위는 배경 annotation box로 표시
────────────────────────────────────────────── */
function createBarChart(canvasId, kw) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;

  /* 기존 차트 파괴 */
  if (chartInstances[canvasId]) {
    chartInstances[canvasId].destroy();
  }

  const status   = getStatus(kw);
  const barColor = getBarColor(status);
  const barValue = kw ?? 0;

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
          callbacks: {
            label: (ctx) =>
              kw !== null && kw !== undefined
                ? ` ${kw.toLocaleString()} kW`
                : ' 데이터 없음',
          },
        },
        annotation: {
          annotations: {
            /* 위험 범위 배경 박스 */
            dangerBox: {
              type:        'box',
              yMin:        THRESHOLD.danger,
              yMax:        THRESHOLD.maxY,
              backgroundColor: COLOR.dangerBg,
              borderWidth: 0,
            },
            /* 주의 범위 배경 박스 */
            cautionBox: {
              type:        'box',
              yMin:        THRESHOLD.caution,
              yMax:        THRESHOLD.danger,
              backgroundColor: COLOR.cautionBg,
              borderWidth: 0,
            },
            /* 위험 임계치 점선 */
            dangerLine: {
              type:        'line',
              yMin:        THRESHOLD.danger,
              yMax:        THRESHOLD.danger,
              borderColor: COLOR.danger,
              borderWidth: 1,
              borderDash:  [4, 3],
              label: {
                display:    false,
              },
            },
            /* 주의 임계치 점선 */
            cautionLine: {
              type:        'line',
              yMin:        THRESHOLD.caution,
              yMax:        THRESHOLD.caution,
              borderColor: COLOR.caution,
              borderWidth: 1,
              borderDash:  [4, 3],
              label: {
                display:    false,
              },
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
          max:  THRESHOLD.maxY,
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
  const kw     = equipData?.power ?? null;
  const status = getStatus(kw);
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
   equipList: [{ name, power }, ...] 길이 최대 8
────────────────────────────────────────────── */
function renderGrid(equipList = []) {
  const grid = document.getElementById('chart-grid');
  grid.innerHTML = '';

  const SLOT_COUNT = 8;
  for (let i = 0; i < SLOT_COUNT; i++) {
    const data = equipList[i] ?? null;
    const card = buildCard(i, data);
    grid.appendChild(card);
  }

  /* 차트는 DOM 삽입 후 생성 */
  for (let i = 0; i < SLOT_COUNT; i++) {
    const kw = equipList[i]?.power ?? null;
    createBarChart(`canvas-${i}`, kw);
  }
}

/* ────────────────────────────────────────────
   탭 전환
────────────────────────────────────────────── */
function switchTab(tab) {
  activeTab = tab;
  document.getElementById('tab-realtime').classList.toggle('active', tab === 'realtime');
  document.getElementById('tab-ai').classList.toggle('active',       tab === 'ai');

  if (tab === 'realtime') {
    loadRealtimeData();
  } else {
    loadAiData();
  }
}

/* ────────────────────────────────────────────
   데이터 로드 (스텁 — 실제 API 연동 시 교체)
────────────────────────────────────────────── */
function loadRealtimeData() {
  /* TODO: WebSocket 또는 REST API 연동 */
  renderGrid([]);
  updateStatusBar(null);
}

function loadAiData() {
  /* TODO: AI 예측 API 연동 */
  renderGrid([]);
  updateStatusBar(null);
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
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('tab-realtime')
    .addEventListener('click', () => switchTab('realtime'));
  document.getElementById('tab-ai')
    .addEventListener('click', () => switchTab('ai'));

  startClock();
  loadRealtimeData();
});
