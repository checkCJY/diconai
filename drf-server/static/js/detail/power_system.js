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
   Chart.js 막대 그래프 생성
   @param canvasId  - canvas 요소 id
   @param watt      - 전력값 (W 단위, null이면 빈 차트)
   @param status    - 'danger'|'caution'|'safe' (서버 risk_level 기반)
   @param channel   - 채널 번호 (1~16) — CHANNEL_THRESHOLDS 룩업 키. 임계 라인·Y축이 채널 정격×% 환산값 사용.
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
              const pct = t.rated_w ? ((watt / t.rated_w) * 100).toFixed(1) + '%' : '-';
              return [
                `현재 사용 전력량   ${(watt / 1000).toFixed(2)} kW (${pct})`,
              ];
            },
          },
        },
        annotation: {
          annotations: {
            dangerBox: {
              type:            'box',
              yMin:            dangerY,
              yMax:            maxY,
              backgroundColor: COLOR.dangerBg,
              borderWidth:     0,
            },
            cautionBox: {
              type:            'box',
              yMin:            cautionY,
              yMax:            dangerY,
              backgroundColor: COLOR.cautionBg,
              borderWidth:     0,
            },
            dangerLine: {
              type:        'line',
              yMin:        dangerY,
              yMax:        dangerY,
              borderColor: COLOR.danger,
              borderWidth: 1,
              borderDash:  [4, 3],
              label: { display: false },
            },
            cautionLine: {
              type:        'line',
              yMin:        cautionY,
              yMax:        cautionY,
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
            // 1000 이상은 "k" 단위 + 1자리 소수 (트레일링 .0 제거). 부동소수점 노이즈 방지.
            callback: (v) => {
              if (v >= 1000) {
                const k = (v / 1000).toFixed(1).replace(/\.0$/, '');
                return `${k}k`;
              }
              return v;
            },
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
