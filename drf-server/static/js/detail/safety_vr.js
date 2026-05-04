(function () {
  const PROGRESS_API = '/dashboard/api/vr-progress/';

  const d = new Date();
  document.getElementById('vrDate').textContent =
    `${d.getFullYear()} / ${pad(d.getMonth()+1)} / ${pad(d.getDate())}`;

  const video       = document.getElementById('vrVideo');
  const playOverlay = document.getElementById('playOverlay');
  const btnDone     = document.getElementById('btnDone');
  let maxReached    = 0;

  Auth.apiFetch(PROGRESS_API)
    .then(r => r.json())
    .then(data => {
      if (data.position > 0) {
        video.currentTime = data.position;
        maxReached = data.position;
      }
    })
    .catch(() => {});

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

  /* 앞으로 건너뛰기 방지 */
  video.addEventListener('seeking', () => {
    if (video.currentTime > maxReached + 0.5) {
      video.currentTime = maxReached;
    }
  });

  video.addEventListener('timeupdate', () => {
    if (video.currentTime > maxReached) maxReached = video.currentTime;
  });

  video.addEventListener('ended', () => {
    btnDone.classList.add('active');
    playOverlay.classList.remove('hidden');
    saveProgress(video.duration);
  });

  function saveProgress(position) {
    navigator.sendBeacon(PROGRESS_API + '?_method=POST',
      new Blob([JSON.stringify({ position })], { type: 'application/json' })
    );
    /* sendBeacon은 커스텀 헤더 불가 — fallback으로 Auth.apiFetch 사용 */
    Auth.apiFetch(PROGRESS_API, {
      method: 'POST',
      body: JSON.stringify({ position }),
      keepalive: true,
    }).catch(() => {});
  }

  window.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') saveProgress(video.currentTime);
  });
  window.addEventListener('pagehide', () => saveProgress(video.currentTime));

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
    /* VR 완료 상태를 먼저 저장하고, 이후 진행 위치를 초기화한다.
       순서를 지키지 않으면 keepalive fetch와 세션 경쟁이 발생해
       vr_done_date 키가 덮어쓰여 '미완료'로 표시되는 버그가 생긴다. */
    await fetch('/dashboard/api/safety-status/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: 'vr' }),
    }).catch(() => {});
    await Auth.apiFetch(PROGRESS_API, {
      method: 'POST',
      body: JSON.stringify({ position: 0 }),
      keepalive: true,
    }).catch(() => {});
    window.location.href = '/dashboard/';
  });
})();
