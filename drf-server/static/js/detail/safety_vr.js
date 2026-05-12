/* safety_vr.js — 작업 전 안전 확인 VR 교육 페이지 클라이언트
 *
 * 핵심 동작:
 * 1) 진입 시 세션의 (content_id, position)을 조회해, 현재 페이지의 콘텐츠 ID와
 *    일치할 때만 position 복원 (영상 교체 시 잘못된 위치 적용 방지).
 * 2) Skip 방지: seeking 이벤트로 maxReached 초과 점프 차단 + 재생속도 1.0 고정
 *    + 키보드 점프키 차단 + 우클릭 메뉴 차단.
 * 3) 완료 버튼은 영상 ended 이벤트가 발생해야만 활성.
 * 4) 이탈/숨김 시 진행 위치를 세션에 저장.
 */
(function () {
  const PROGRESS_API = '/dashboard/api/vr-progress/';

  const d = new Date();
  document.getElementById('vrDate').textContent =
    `${d.getFullYear()} / ${pad(d.getMonth() + 1)} / ${pad(d.getDate())}`;

  const video       = document.getElementById('vrVideo');
  const playOverlay = document.getElementById('playOverlay');
  const btnDone     = document.getElementById('btnDone');

  // 어드민이 영상을 등록하지 않은 상태 — 템플릿이 video 요소를 렌더하지 않음.
  // 이 페이지에서는 시청 자체가 불가하므로 모든 이벤트 바인딩을 건너뛰고
  // [이전]만 동작하도록 최소 처리한다.
  if (!video) {
    document.getElementById('btnPrev')?.addEventListener('click', () => {
      window.location.href = '/dashboard/';
    });
    return;
  }

  /* Skip 방지 상태 머신.
     - lastPlayheadTime: 자연 재생으로 도달한 마지막 시점. seek가 발생하면
       이 값과 어긋나므로 즉시 되돌린다.
     - maxReached: 시청한 적이 있는 최댓값. 향후 사용자가 뒤로 가도록 허용할
       경우(현재는 차단)에 활용.
     - allowOneSeek: 이어보기 복원 시 1회만 seek를 허용하는 플래그. */
  let lastPlayheadTime = 0;
  let maxReached       = 0;
  let allowOneSeek     = false;

  const rawCid = video.dataset.contentId;
  const pageContentId = rawCid === '' ? null : Number(rawCid);

  // ── 이어보기 복원 ─────────────────────────────────────
  Auth.apiFetch(PROGRESS_API)
    .then((r) => r.json())
    .then((data) => {
      const sameContent =
        (data.content_id === null && pageContentId === null) ||
        Number(data.content_id) === pageContentId;
      if (sameContent && data.position > 0) {
        allowOneSeek = true;
        video.currentTime = data.position;
        lastPlayheadTime = data.position;
        maxReached = data.position;
      }
    })
    .catch(() => {});

  // ── 재생/일시정지 오버레이 ─────────────────────────────
  playOverlay.addEventListener('click', () => {
    video.play();
    playOverlay.classList.add('hidden');
  });

  video.addEventListener('pause', () => {
    if (!video.ended) playOverlay.classList.remove('hidden');
  });

  video.addEventListener('play', () => {
    playOverlay.classList.add('hidden');
  });

  // ── Skip 방지: 모든 seek 차단 (자연 재생만 허용) ───────
  video.addEventListener('timeupdate', () => {
    if (video.seeking) return;
    lastPlayheadTime = video.currentTime;
    if (video.currentTime > maxReached) maxReached = video.currentTime;
  });

  video.addEventListener('seeking', () => {
    // 이어보기 복원처럼 코드가 명시적으로 허용한 seek는 1회 통과.
    if (allowOneSeek) {
      allowOneSeek = false;
      return;
    }
    // 자연 재생으로 흘러간 timeupdate 외 모든 점프는 직전 위치로 되돌림.
    if (Math.abs(video.currentTime - lastPlayheadTime) > 0.5) {
      video.currentTime = lastPlayheadTime;
    }
  });

  video.addEventListener('ratechange', () => {
    if (video.playbackRate !== 1) video.playbackRate = 1;
  });

  // 우클릭 메뉴(다른 이름으로 저장·반복재생 등) 차단.
  video.addEventListener('contextmenu', (e) => e.preventDefault());

  // 키보드 점프키 차단. video 요소의 native 컨트롤이 일부 키를 먼저
  // 가로채는 경우가 있어, video 자체에도 stopImmediatePropagation으로 막고
  // document 캡처 단계에서 한 번 더 막는 이중 가드.
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
  // video 포커스 자체를 거부 — focus되면 즉시 블러.
  video.addEventListener('focus', () => video.blur());

  // ── 영상 종료 → 완료 버튼 활성 ─────────────────────────
  video.addEventListener('ended', () => {
    btnDone.classList.add('active');
    playOverlay.classList.remove('hidden');
    saveProgress(video.duration);
  });

  // ── 진행 위치 저장 ────────────────────────────────────
  function saveProgress(position) {
    const payload = JSON.stringify({
      content_id: pageContentId,
      position: position,
    });
    /* sendBeacon: 페이지 이탈 직전에도 안전하게 전송. 커스텀 헤더는 불가하므로
       JWT 인증이 필요한 환경에서는 아래 Auth.apiFetch fallback이 실제 저장을 담당. */
    navigator.sendBeacon(
      PROGRESS_API + '?_method=POST',
      new Blob([payload], { type: 'application/json' }),
    );
    Auth.apiFetch(PROGRESS_API, {
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
  document.getElementById('btnPrev').addEventListener('click', () => {
    video.pause();
    document.getElementById('prevModal').classList.add('show');
  });
  document.getElementById('prevModalCancel').addEventListener('click', () => {
    document.getElementById('prevModal').classList.remove('show');
    if (!video.ended) video.play();
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
       vr_done_date 키가 덮어쓰여 '미완료'로 표시되는 버그가 생긴다. */
    await fetch('/dashboard/api/safety-status/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: 'vr' }),
    }).catch(() => {});
    await Auth.apiFetch(PROGRESS_API, {
      method: 'POST',
      body: JSON.stringify({ content_id: pageContentId, position: 0 }),
      keepalive: true,
    }).catch(() => {});
    window.location.href = '/dashboard/';
  });
})();
