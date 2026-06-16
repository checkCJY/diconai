/* safety_vr.js — 작업 전 안전 확인 VR 교육 페이지 클라이언트
 *
 * 핵심 동작:
 * 1) /dashboard/api/vr-content/active/ 로 본인 facility의 활성 콘텐츠를 fetch.
 *    - content_url 있음: <source> 동적 주입 + 컨테이너 노출
 *    - 없음: '등록된 VR 교육 영상이 없습니다' 빈 상태 카드 노출
 * 2) 콘텐츠 로드 후 /dashboard/api/vr-progress/ 로 (content_id, position) 복원.
 *    user_id + content_id 가드를 통과한 경우만 currentTime 적용.
 * 3) Skip 방지: seeking 모든 점프 차단 + 재생속도 1.0 고정 + 키보드/우클릭 봉쇄.
 * 4) 완료 버튼은 ended 이벤트가 발화돼야만 활성.
 * 5) 이탈/숨김 시 진행 위치를 세션에 저장.
 */
(function () {
  const VR_CONTENT_API  = '/dashboard/api/vr-content/active/';
  const VR_PROGRESS_API = '/dashboard/api/vr-progress/';

  const d = new Date();
  document.getElementById('vrDate').textContent =
    `${d.getFullYear()} / ${pad(d.getMonth() + 1)} / ${pad(d.getDate())}`;

  const video          = document.getElementById('vrVideo');
  const playOverlay    = document.getElementById('playOverlay');
  const btnDone        = document.getElementById('btnDone');
  const videoContainer = document.getElementById('videoContainer');
  const videoEmpty     = document.getElementById('videoEmpty');

  /* Skip 방지 상태 머신.
     - lastPlayheadTime: 자연 재생으로 도달한 마지막 시점. seek 시 직전 위치로 되돌림.
     - maxReached: 시청한 적이 있는 최댓값.
     - allowOneSeek: 이어보기 복원 시 1회만 seek 허용.
     - pageContentId: fetch 후 채워짐. null이면 영상 미로드 상태. */
  let lastPlayheadTime = 0;
  let maxReached       = 0;
  let allowOneSeek     = false;
  let pageContentId    = null;

  // ── 이벤트 바인딩 (콘텐츠 로드와 무관하게 1회만) ──────────
  bindVideoGuards();
  bindUiButtons();

  // ── 콘텐츠 로드 진입점 ────────────────────────────────
  loadContent();

  function loadContent() {
    Auth.apiFetch(VR_CONTENT_API)
      .then((r) => r.json())
      .then((data) => {
        if (!data || !data.content_url) {
          showEmpty();
          return;
        }
        pageContentId = data.id;
        video.dataset.contentId = String(data.id);
        const src = document.createElement('source');
        src.src = data.content_url;
        src.type = 'video/mp4';
        video.appendChild(src);
        video.load();
        if (videoContainer) videoContainer.hidden = false;
        if (videoEmpty) videoEmpty.hidden = true;
        restoreProgress();
      })
      .catch(() => showEmpty());
  }

  function showEmpty() {
    if (videoEmpty) videoEmpty.hidden = false;
    if (videoContainer) videoContainer.hidden = true;
  }

  function restoreProgress() {
    Auth.apiFetch(VR_PROGRESS_API)
      .then((r) => r.json())
      .then((data) => {
        const sameContent =
          (data.content_id === null && pageContentId === null) ||
          Number(data.content_id) === pageContentId;
        if (!(sameContent && data.position > 0)) return;
        // metadata 로드 후에만 currentTime이 정확히 적용된다.
        if (video.readyState >= 1) {
          applyResume(data.position);
        } else {
          video.addEventListener(
            'loadedmetadata',
            () => applyResume(data.position),
            { once: true },
          );
        }
      })
      .catch(() => {});
  }

  function applyResume(position) {
    allowOneSeek = true;
    video.currentTime = position;
    lastPlayheadTime = position;
    maxReached = position;
  }

  // ── Skip 방지 / 재생 가드 ─────────────────────────────
  function bindVideoGuards() {
    playOverlay.addEventListener('click', () => {
      if (!video.currentSrc) return;
      video.play();
      playOverlay.classList.add('hidden');
    });

    video.addEventListener('pause', () => {
      if (!video.ended) playOverlay.classList.remove('hidden');
    });
    video.addEventListener('play', () => playOverlay.classList.add('hidden'));

    video.addEventListener('timeupdate', () => {
      if (video.seeking) return;
      lastPlayheadTime = video.currentTime;
      if (video.currentTime > maxReached) maxReached = video.currentTime;
    });

    video.addEventListener('seeking', () => {
      if (allowOneSeek) {
        allowOneSeek = false;
        return;
      }
      if (Math.abs(video.currentTime - lastPlayheadTime) > 0.5) {
        video.currentTime = lastPlayheadTime;
      }
    });

    video.addEventListener('ratechange', () => {
      if (video.playbackRate !== 1) video.playbackRate = 1;
    });

    video.addEventListener('contextmenu', (e) => e.preventDefault());

    const BLOCKED_KEYS = new Set([
      'ArrowRight', 'ArrowLeft', 'ArrowUp', 'ArrowDown',
      'PageUp', 'PageDown', 'Home', 'End',
      'j', 'J', 'l', 'L',
      '0', '1', '2', '3', '4', '5', '6', '7', '8', '9',
    ]);
    const swallowKey = (e) => {
      const tag = (e.target.tagName || '').toLowerCase();
      if (tag === 'input' || tag === 'textarea') return;
      if (BLOCKED_KEYS.has(e.key)) {
        e.preventDefault();
        e.stopImmediatePropagation();
      }
    };
    video.addEventListener('keydown', swallowKey);
    document.addEventListener('keydown', swallowKey, true);
    video.addEventListener('focus', () => video.blur());

    video.addEventListener('ended', () => {
      btnDone.classList.add('active');
      playOverlay.classList.remove('hidden');
      saveProgress(video.duration);
    });
  }

  // ── 진행 위치 저장 ────────────────────────────────────
  function saveProgress(position) {
    if (pageContentId === null) return; // 영상 없음 — 저장 의미 없음
    const payload = JSON.stringify({
      content_id: pageContentId,
      position: position,
    });
    /* sendBeacon: 페이지 이탈 직전 안전 전송. JWT 헤더 불가하므로 아래 fallback이
       실제 저장을 담당. */
    navigator.sendBeacon(
      VR_PROGRESS_API + '?_method=POST',
      new Blob([payload], { type: 'application/json' }),
    );
    Auth.apiFetch(VR_PROGRESS_API, {
      method: 'POST',
      body: payload,
      keepalive: true,
    }).catch(() => {});
  }

  window.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') saveProgress(video.currentTime);
  });
  window.addEventListener('pagehide', () => saveProgress(video.currentTime));

  // ── 이전 / 완료 모달 ──────────────────────────────────
  function bindUiButtons() {
    document.getElementById('btnPrev').addEventListener('click', () => {
      video.pause();
      document.getElementById('prevModal').classList.add('show');
    });
    document.getElementById('prevModalCancel').addEventListener('click', () => {
      document.getElementById('prevModal').classList.remove('show');
      if (!video.ended && video.currentSrc) video.play();
    });
    document.getElementById('prevModalOk').addEventListener('click', () => {
      saveProgress(video.currentTime);
      window.location.href = '/dashboard/';
    });

    btnDone.addEventListener('click', () => {
      if (!btnDone.classList.contains('active')) return;
      document.getElementById('doneModal').classList.add('show');
    });
    document.getElementById('doneModalOk').addEventListener('click', async () => {
      /* VR 완료 상태를 먼저 저장하고, 이후 진행 위치를 0으로 초기화한다.
         순서를 지키지 않으면 keepalive fetch와 세션 경쟁이 발생해
         vr_done_date 키가 덮어쓰여 '미완료'로 표시되는 버그가 생긴다.
         Auth.apiFetch 사용 — 일반 fetch는 JWT Authorization 헤더가 빠져
         request.user가 AnonymousUser로 잡혀 DB dual-write가 silent skip된다. */
      await Auth.apiFetch('/dashboard/api/safety-status/', {
        method: 'POST',
        body: JSON.stringify({ key: 'vr' }),
      }).catch(() => {});
      await Auth.apiFetch(VR_PROGRESS_API, {
        method: 'POST',
        body: JSON.stringify({ content_id: pageContentId, position: 0 }),
        keepalive: true,
      }).catch(() => {});
      window.location.href = '/dashboard/';
    });
  }
})();
