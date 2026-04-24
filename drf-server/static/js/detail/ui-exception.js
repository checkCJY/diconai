/* ──────────────────────────────────────────────────────────
   ui-exception.js  —  UI 예외 상태 공통 처리
   적용 규칙: /skill/UI_Handling.md

   사용법:
     showChartOverlay(canvas, 'error')   → "데이터를 불러올 수 없습니다."
     showChartOverlay(canvas, 'empty')   → "데이터가 존재하지 않습니다."
     clearChartOverlay(canvas)           → 오버레이 제거
     showSkeleton(container, count)      → 스켈레톤 카드 삽입
     clearSkeleton(container)            → 스켈레톤 제거
     grayOutBadges(container)            → 상태 badge 회색 강제 변환
     restoreBadges(container)            → 회색 변환 복원
     startRetry(fetchFn, intervalMs?)    → 3초 주기 재시도, 반환값으로 stop 가능
   ────────────────────────────────────────────────────────── */

const OVERLAY_ATTR   = 'data-ui-overlay';
const SKELETON_ATTR  = 'data-ui-skeleton';
const GRAY_ATTR      = 'data-ui-gray';

const MSG = {
  error: '데이터를 불러올 수 없습니다.',
  empty: '데이터가 존재하지 않습니다.',
};

/* ── 1. Chart 오버레이 ────────────────────────────────────── */

/**
 * canvas 위에 반투명 텍스트 오버레이를 렌더링한다.
 * @param {HTMLCanvasElement} canvas
 * @param {'error'|'empty'} type
 */
function showChartOverlay(canvas, type) {
  if (!canvas) return;

  clearChartOverlay(canvas);

  const wrap = canvas.parentElement;
  if (!wrap) return;

  /* wrap 기준 좌표로 겹쳐야 하므로 position 보정 */
  const wrapPos = getComputedStyle(wrap).position;
  if (wrapPos === 'static') wrap.style.position = 'relative';

  const overlay = document.createElement('div');
  overlay.setAttribute(OVERLAY_ATTR, type);
  overlay.style.cssText = `
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 11px;
    color: #8b949e;
    opacity: 0.75;
    pointer-events: none;
    text-align: center;
    padding: 4px;
  `;
  overlay.textContent = MSG[type] ?? MSG.error;

  wrap.appendChild(overlay);
}

/**
 * canvas 부모에 붙어있는 오버레이를 제거한다.
 * @param {HTMLCanvasElement} canvas
 */
function clearChartOverlay(canvas) {
  if (!canvas) return;
  const wrap = canvas.parentElement;
  if (!wrap) return;
  wrap.querySelectorAll(`[${OVERLAY_ATTR}]`).forEach(el => el.remove());
}


/* ── 2. 스켈레톤 UI ──────────────────────────────────────── */

/**
 * container 안에 스켈레톤 카드를 count개 삽입한다.
 * container는 clearSkeleton() 호출 전까지 기존 내용이 지워진다.
 * @param {HTMLElement} container
 * @param {number} count
 */
function showSkeleton(container, count = 8) {
  if (!container) return;

  clearSkeleton(container);

  const frag = document.createDocumentFragment();
  for (let i = 0; i < count; i++) {
    const card = document.createElement('div');
    card.setAttribute(SKELETON_ATTR, '');
    card.style.cssText = `
      background: linear-gradient(90deg, #1c2128 25%, #262d36 50%, #1c2128 75%);
      background-size: 200% 100%;
      animation: skeleton-shimmer 1.4s infinite;
      border-radius: 8px;
      border: 1px solid #30363d;
    `;
    frag.appendChild(card);
  }

  /* shimmer 애니메이션 (한 번만 주입) */
  if (!document.getElementById('skeleton-style')) {
    const style = document.createElement('style');
    style.id = 'skeleton-style';
    style.textContent = `
      @keyframes skeleton-shimmer {
        0%   { background-position: 200% 0; }
        100% { background-position: -200% 0; }
      }
    `;
    document.head.appendChild(style);
  }

  container.innerHTML = '';
  container.appendChild(frag);
}

/**
 * container 안의 스켈레톤 카드를 제거한다.
 * @param {HTMLElement} container
 */
function clearSkeleton(container) {
  if (!container) return;
  container.querySelectorAll(`[${SKELETON_ATTR}]`).forEach(el => el.remove());
}


/* ── 3. Badge / Indicator 회색 강제 변환 ─────────────────── */

/**
 * container 안의 .status-badge, .card-status-dot, .dot-sq 를 회색으로 변환한다.
 * 원래 클래스는 data 속성으로 보존해 restoreBadges() 로 복원 가능.
 * @param {HTMLElement} container
 */
function grayOutBadges(container) {
  if (!container) return;

  const targets = container.querySelectorAll(
    '.status-badge, .card-status-dot, .dot-sq'
  );
  targets.forEach(el => {
    if (el.hasAttribute(GRAY_ATTR)) return;
    el.setAttribute(GRAY_ATTR, el.className);
    /* danger / caution / safe 클래스 제거 후 gray 적용 */
    el.classList.remove('danger', 'caution', 'safe');
    el.classList.add('gray');
    el.style.opacity = '0.4';
  });
}

/**
 * grayOutBadges() 로 변환된 badge를 원상 복원한다.
 * @param {HTMLElement} container
 */
function restoreBadges(container) {
  if (!container) return;

  container.querySelectorAll(`[${GRAY_ATTR}]`).forEach(el => {
    el.className = el.getAttribute(GRAY_ATTR);
    el.style.opacity = '';
    el.removeAttribute(GRAY_ATTR);
  });
}


/* ── 4. Retry 로직 ───────────────────────────────────────── */

/**
 * fetchFn 이 실패했을 때 intervalMs 주기로 재시도한다.
 * 반환된 객체의 stop() 을 호출하면 중단된다.
 *
 * 사용 예:
 *   const retry = startRetry(() => loadRealtimeData(), 3000);
 *   // 성공 후:
 *   retry.stop();
 *
 * @param {() => Promise<any>} fetchFn   - 비동기 fetch 함수 (reject 시 재시도)
 * @param {number} intervalMs            - 재시도 간격 (기본 3000ms)
 * @returns {{ stop: () => void }}
 */
function startRetry(fetchFn, intervalMs = 3000) {
  let timer = null;
  let stopped = false;

  async function attempt() {
    if (stopped) return;
    try {
      await fetchFn();
      /* 성공 시 자동 중단 */
      stopped = true;
    } catch {
      if (!stopped) {
        timer = setTimeout(attempt, intervalMs);
      }
    }
  }

  attempt();

  return {
    stop() {
      stopped = true;
      if (timer !== null) clearTimeout(timer);
    },
  };
}
