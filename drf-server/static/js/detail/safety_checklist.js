/* detail/safety_checklist.js — 작업 전 안전 점검 체크리스트 (운영자용)
 *
 * 어드민이 발행한 SafetyChecklistRevision의 스냅샷을 받아와 섹션·문항을 렌더링한다.
 * 모든 항목 체크 시 [다음]이 활성화되고, 확인 모달 → /api/safety-status/ 기록 →
 * VR 페이지로 이동.
 *
 * API:
 *   GET  /api/safety/checklist/active/        (인증 사용자 공용)
 *   POST /dashboard/api/safety-status/        (세션 기반 완료 표시)
 *
 * 렌더링 정책:
 *   - 동적 섹션: 활성 Revision JSON의 sections를 그대로 1, 2, 3, ... 번호 부여
 *   - 마지막에 항상 "최종 확인 및 서약" 섹션 추가 (PLEDGE_TEXT 상수, 어드민에서
 *     편집 불가 — 코드 내 고정 문구로 유지하기로 결정).
 *   - 활성 Revision이 없으면 안내 메시지 + [다음] 비활성. 어드민이 [반영 저장]을
 *     누르기 전까지는 작업자 페이지가 빈 상태로 보임이 정상 동작.
 */
(function () {
  const PLEDGE_TEXT =
    '상기 체크리스트를 모두 확인하였으며 작업 전 안전 기준을 준수하겠습니다.';

  const scroll = document.getElementById('checklistScroll');
  const btnNext = document.getElementById('btnNext');
  const btnSelectAll = document.getElementById('btnSelectAll');
  const btnCancel = document.getElementById('btnCancel');

  document.getElementById('checklistDate').textContent =
    `${new Date().getFullYear()}.${pad(new Date().getMonth() + 1)}.${pad(new Date().getDate())}`;

  function escape(s) {
    return String(s ?? '').replace(/[&<>"']/g, (c) => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    })[c]);
  }

  function showState(message) {
    scroll.innerHTML = `<div class="checklist-loading">${escape(message)}</div>`;
  }

  function getAllBoxes() {
    return scroll.querySelectorAll('input[type="checkbox"]');
  }

  function syncNextBtn() {
    const boxes = getAllBoxes();
    if (boxes.length === 0) {
      btnNext.classList.remove('active');
      return;
    }
    const allChecked = [...boxes].every((cb) => cb.checked);
    btnNext.classList.toggle('active', allChecked);
  }

  function bindCheckbox(cb) {
    cb.addEventListener('change', function () {
      this.closest('.check-item').classList.toggle('checked', this.checked);
      const sec = this.closest('.checklist-section');
      const err = sec && sec.querySelector('.section-error');
      if (err) {
        const sectionBoxes = sec.querySelectorAll('input[type="checkbox"]');
        const allDone = [...sectionBoxes].every((c) => c.checked);
        if (allDone) err.classList.remove('show');
      }
      syncNextBtn();
    });
  }

  function renderChecklist(data) {
    const sections = data.sections || [];
    if (sections.length === 0) {
      showState('현재 활성화된 체크리스트 항목이 없습니다. 관리자에게 문의해 주세요.');
      btnNext.classList.remove('active');
      return;
    }

    // 본 섹션들 + 마지막 서약 섹션(고정)
    const html =
      sections
        .map(
          (section, sIdx) => `
        <div class="checklist-section" data-section-key="${sIdx + 1}">
          <div class="section-title">
            ${sIdx + 1}. ${escape(section.name)}
            <span class="section-error">모든 항목을 체크해 주세요.</span>
          </div>
          ${(section.items || [])
            .map(
              (it) => `
            <label class="check-item">
              <input type="checkbox" data-section="${sIdx + 1}"> ${escape(it.title)}
            </label>`,
            )
            .join('')}
        </div>`,
        )
        .join('') +
      `
      <div class="checklist-section" data-section-key="pledge">
        <div class="section-title">
          ${sections.length + 1}. 최종 확인 및 서약
          <span class="section-error">서약 항목을 체크해 주세요.</span>
        </div>
        <label class="check-item">
          <input type="checkbox" data-section="pledge"> ${escape(PLEDGE_TEXT)}
        </label>
      </div>`;

    scroll.innerHTML = html;
    getAllBoxes().forEach(bindCheckbox);
    syncNextBtn();
  }

  async function loadChecklist() {
    try {
      const res = await Auth.apiFetch('/api/safety/checklist/active/');
      if (res.status === 404) {
        const body = await res.json().catch(() => ({}));
        const msg =
          body.code === 'no_active_revision'
            ? '아직 발행된 안전 체크리스트가 없습니다. 관리자가 [반영 저장]을 진행한 뒤 다시 시도해 주세요.'
            : body.detail || '체크리스트를 불러올 수 없습니다.';
        showState(msg);
        btnNext.classList.remove('active');
        return;
      }
      if (!res.ok) {
        showState('체크리스트를 불러오는 중 오류가 발생했습니다.');
        return;
      }
      const data = await res.json();
      renderChecklist(data);
    } catch (err) {
      console.error(err);
      showState('체크리스트를 불러오는 중 오류가 발생했습니다.');
    }
  }

  // ── 하단 버튼 ────────────────────────────────────────────
  btnSelectAll.addEventListener('click', () => {
    getAllBoxes().forEach((cb) => {
      cb.checked = true;
      cb.closest('.check-item').classList.add('checked');
    });
    scroll.querySelectorAll('.section-error').forEach((el) => el.classList.remove('show'));
    syncNextBtn();
  });

  btnCancel.addEventListener('click', () => {
    getAllBoxes().forEach((cb) => {
      cb.checked = false;
      cb.closest('.check-item').classList.remove('checked');
    });
    scroll.querySelectorAll('.section-error').forEach((el) => el.classList.remove('show'));
    syncNextBtn();
    window.location.href = '/dashboard/';
  });

  btnNext.addEventListener('click', () => {
    if (!btnNext.classList.contains('active')) {
      scroll.querySelectorAll('.checklist-section').forEach((sec) => {
        const boxes = sec.querySelectorAll('input[type="checkbox"]');
        if (boxes.length === 0) return;
        const allDone = [...boxes].every((cb) => cb.checked);
        const errEl = sec.querySelector('.section-error');
        if (errEl) errEl.classList.toggle('show', !allDone);
      });
      const firstErr = scroll.querySelector('.section-error.show');
      if (firstErr) {
        firstErr
          .closest('.checklist-section')
          .scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
      return;
    }
    document.getElementById('confirmModal').classList.add('show');
  });

  document.getElementById('btnConfirm').addEventListener('click', async () => {
    /* Auth.apiFetch 사용 — 일반 fetch는 JWT Authorization 헤더가 빠져
       request.user가 AnonymousUser로 잡혀 DB dual-write(SafetyCheckSession)가
       silent skip된다. 그러면 안전 확인 이력 캘린더에 ✓가 안 찍힌다. */
    await Auth.apiFetch('/dashboard/api/safety-status/', {
      method: 'POST',
      body: JSON.stringify({ key: 'checklist' }),
    }).catch(() => {});
    window.location.href = '/dashboard/safety/vr/';
  });

  loadChecklist();
})();
