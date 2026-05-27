/* ============================================================
   chart-helpers.js — Chart.js 공통 헬퍼 (디자인 토큰 + 플러그인)

   [목적]
   - 가스/전력 detail · 메인 dashboard 의 차트 시각 표현을 일관화.
   - 기존: 페이지마다 COLOR 객체 + Chart config 분산 → 톤 어긋남.
   - 신규: 본 모듈 한 곳에서 색·플러그인·기본 옵션 정의 → 페이지는 데이터만 주입.

   [의존]
   - Chart.js 4.x (CDN, 페이지 헤더에서 로드)
   - chartjs-plugin-annotation 은 미사용 — thresholdZones 가 dashed line + chip
     으로 대체 (annotation box 가 차트 면적 점유하는 문제 해결).

   [등록 시점]
   본 파일은 페이지 진입 시 Chart 객체보다 먼저 로드되어야 한다 (Chart.register).
   ============================================================ */

'use strict';

/* ── 색상 팔레트 (단일 진실 공급원) ────────────────────────
   페이지별 분산되어 있던 COLOR 객체 통합. CSS 변수와도 페어링. */
const CHART_COLOR = {
  ok:         '#34D399',
  warn:       '#FBBF24',
  warnLine:   'rgba(251, 191, 36, 0.65)',
  warnFill:   'rgba(251, 191, 36, 0.06)',
  danger:     '#F87171',
  dangerLine: 'rgba(248, 113, 113, 0.65)',
  dangerFill: 'rgba(248, 113, 113, 0.07)',
  brand:      '#60A5FA',
  brandFill:  'rgba(96, 165, 250, 0.14)',
  text:       '#E8ECF4',
  text2:      '#95A0B8',
  text3:      '#5D6783',
  panel:      '#121A2D',
  border:     '#24304A',
  gridLine:   'rgba(255, 255, 255, 0.045)',
};

/* ── Chart.js 전역 기본값 — 페이지 로드 시 1회 적용 ───── */
function applyChartDefaults() {
  if (typeof Chart === 'undefined') return;
  Chart.defaults.color = CHART_COLOR.text2;
  Chart.defaults.borderColor = CHART_COLOR.border;
  Chart.defaults.font.family = "'Pretendard', -apple-system, system-ui, sans-serif";
  Chart.defaults.font.size = 11;
}

/* ── 칩 라벨 그리기 (플러그인 내부 공통 유틸) ─────────────
   threshold dashed 라인 우측 끝에 "주의 30ppm" 등을 작은 칩으로 표시. */
function _drawChip(ctx, xRight, y, text, color, opts) {
  opts = opts || {};
  ctx.save();
  ctx.font = '600 10px Pretendard';
  const w = ctx.measureText(text).width;
  const padX = 6, h = 16;
  const boxW = w + padX * 2;
  const x = xRight - boxW;
  ctx.fillStyle = opts.bg || CHART_COLOR.panel;
  ctx.strokeStyle = color;
  ctx.lineWidth = 1;
  ctx.beginPath();
  if (ctx.roundRect) ctx.roundRect(x, y - h / 2, boxW, h, 4);
  else ctx.rect(x, y - h / 2, boxW, h);
  ctx.fill();
  ctx.stroke();
  ctx.fillStyle = color;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(text, x + boxW / 2, y + 0.5);
  ctx.restore();
}

/* ── thresholdZones 플러그인 ───────────────────────────────
   기존: annotation box 가 차트 면적 70% 점유 → 막대가 묻힘.
   신규: dashed 라인만 그림. chip 라벨은 카드 헤더의 HTML 영역으로 이동 (chart-chips).

   options.thresholds: [{ at: number, color: 'warn'|'danger', label: string }]
   options.showChip: bool (default false) — 차트 안에 chip 도 그릴지 여부. 카드
   헤더 chip 사용 시 false 권장. line 만 그리고 라벨은 HTML 로. */
const thresholdZones = {
  id: 'thresholdZones',
  afterDatasetsDraw(chart, args, opts) {
    if (!opts || !opts.thresholds || !opts.thresholds.length) return;
    const { ctx, chartArea, scales: { y } } = chart;
    const { left, right, top, bottom } = chartArea;
    const ths = opts.thresholds;

    // dashed 임계 라인
    ths.forEach(t => {
      const yPx = y.getPixelForValue(t.at);
      if (yPx < top || yPx > bottom) return;  // 차트 영역 밖이면 skip
      const lineColor = t.color === 'danger' ? CHART_COLOR.dangerLine : CHART_COLOR.warnLine;
      ctx.save();
      ctx.strokeStyle = lineColor;
      ctx.lineWidth = 1;
      ctx.setLineDash([5, 4]);
      ctx.beginPath();
      ctx.moveTo(left, yPx);
      ctx.lineTo(right, yPx);
      ctx.stroke();
      ctx.restore();
    });

    // 차트 안 chip 라벨은 showChip=true 일 때만 (옵션). 기본은 카드 헤더 HTML 로 표시.
    if (!opts.showChip) return;

    const chips = ths
      .map(t => ({
        y: y.getPixelForValue(t.at),
        label: t.label,
        color: t.color === 'danger' ? CHART_COLOR.danger : CHART_COLOR.warn,
      }))
      .filter(c => c.y >= top && c.y <= bottom)
      .sort((a, b) => a.y - b.y);
    const minGap = 20;
    for (let i = 1; i < chips.length; i++) {
      if (chips[i].y - chips[i - 1].y < minGap) chips[i].y = chips[i - 1].y + minGap;
    }
    chips.forEach(c => {
      const yPos = Math.max(top + 10, Math.min(bottom - 10, c.y));
      _drawChip(ctx, right - 4, yPos, c.label, c.color);
    });
  },
};

/* ── 카드 헤더 chip HTML 생성 헬퍼 ─────────────────────────
   thresholdZones 와 동일한 thresholds 배열을 받아 HTML string 반환.
   buildCard 류 함수에서 헤더 영역에 삽입. CSS class .chart-chips / .chart-chip 으로
   스타일 (가로 정렬, 작은 chip).

   사용:
     <div class="card-title">...</div>
     <div class="chart-chips">${renderThresholdChipsHTML(thresholds)}</div>
*/
function renderThresholdChipsHTML(thresholds) {
  if (!thresholds || !thresholds.length) return '';
  return thresholds
    .map(t => {
      const cls = t.color === 'danger' ? 'chart-chip danger' : 'chart-chip warn';
      // 텍스트 escape — 라벨이 사용자 입력 아니므로 단순 처리
      return `<span class="${cls}">${t.label}</span>`;
    })
    .join('');
}

/* ── safeBand 플러그인 ────────────────────────────────────
   O2 같은 양방향 임계치용 — 안전 범위만 옅은 녹색 fill 로 강조.

   options: { from: number, to: number } */
const safeBand = {
  id: 'safeBand',
  beforeDatasetsDraw(chart, args, opts) {
    if (!opts || opts.from == null || opts.to == null) return;
    const { ctx, chartArea: { left, right }, scales: { y } } = chart;
    const yTop = y.getPixelForValue(opts.to);
    const yBot = y.getPixelForValue(opts.from);
    ctx.save();
    ctx.fillStyle = 'rgba(52, 211, 153, 0.10)';
    ctx.fillRect(left, yTop, right - left, yBot - yTop);
    ctx.strokeStyle = 'rgba(52, 211, 153, 0.45)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(left, yTop); ctx.lineTo(right, yTop);
    ctx.moveTo(left, yBot); ctx.lineTo(right, yBot);
    ctx.stroke();
    ctx.restore();
  },
};

/* ── barValueLabel 플러그인 ───────────────────────────────
   막대 끝(top) 에 현재 값 표시. stacked 다중 dataset 도 합계로 표시.

   options: { show: bool, color: str, fontSize: num, formatter: (v) => str } */
const barValueLabel = {
  id: 'barValueLabel',
  afterDatasetsDraw(chart, args, opts) {
    if (!opts || !opts.show) return;
    const { ctx } = chart;
    const datasets = chart.data.datasets;
    const meta0 = chart.getDatasetMeta(0);
    if (!meta0 || !meta0.data.length) return;

    meta0.data.forEach((_, i) => {
      let total = 0;
      let topY = Infinity;
      let topX = 0;
      datasets.forEach((ds, di) => {
        const v = ds.data[i] || 0;
        if (v > 0) {
          total += v;
          const bar = chart.getDatasetMeta(di).data[i];
          if (bar && bar.y < topY) { topY = bar.y; topX = bar.x; }
        }
      });
      if (topY === Infinity) return;

      ctx.save();
      ctx.fillStyle = opts.color || CHART_COLOR.text;
      ctx.font = `700 ${opts.fontSize || 13}px Pretendard`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'bottom';
      const text = opts.formatter ? opts.formatter(total) : String(total);
      ctx.fillText(text, topX, topY - 6);
      ctx.restore();
    });
  },
};

/* ── nowMarker 플러그인 ───────────────────────────────────
   라인 차트 (dashboard AI 예측) — "지금" 시점에 세로 점선 + 칩.

   options: { atIndex: number } */
const nowMarker = {
  id: 'nowMarker',
  afterDatasetsDraw(chart, args, opts) {
    if (!opts || opts.atIndex == null) return;
    const { ctx, chartArea: { top, bottom }, scales: { x } } = chart;
    const xPx = x.getPixelForValue(opts.atIndex);
    ctx.save();
    ctx.strokeStyle = 'rgba(232, 236, 244, 0.35)';
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 3]);
    ctx.beginPath();
    ctx.moveTo(xPx, top);
    ctx.lineTo(xPx, bottom);
    ctx.stroke();
    ctx.restore();
    _drawChip(ctx, xPx + 28, top + 10, '지금', CHART_COLOR.text2);
  },
};

/* ── 등록 — Chart.js 가 로드된 직후 자동 실행 ──────────── */
if (typeof Chart !== 'undefined') {
  Chart.register(thresholdZones, safeBand, barValueLabel, nowMarker);
  applyChartDefaults();
}
