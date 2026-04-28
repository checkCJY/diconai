(function () {
  const d = new Date();
  document.getElementById('checklistDate').textContent =
    `${d.getFullYear()}.${pad(d.getMonth()+1)}.${pad(d.getDate())}`;

  const allBoxes = document.querySelectorAll('.checklist-scroll input[type="checkbox"]');
  const btnNext  = document.getElementById('btnNext');

  function syncNextBtn() {
    const allChecked = [...allBoxes].every(cb => cb.checked);
    btnNext.classList.toggle('active', allChecked);
  }

  allBoxes.forEach(cb => {
    cb.addEventListener('change', function () {
      this.closest('.check-item').classList.toggle('checked', this.checked);
      syncNextBtn();
    });
  });

  document.getElementById('btnSelectAll').addEventListener('click', () => {
    allBoxes.forEach(cb => {
      cb.checked = true;
      cb.closest('.check-item').classList.add('checked');
    });
    document.querySelectorAll('.section-error').forEach(el => el.classList.remove('show'));
    syncNextBtn();
  });

  document.getElementById('btnCancel').addEventListener('click', () => {
    allBoxes.forEach(cb => {
      cb.checked = false;
      cb.closest('.check-item').classList.remove('checked');
    });
    document.querySelectorAll('.section-error').forEach(el => el.classList.remove('show'));
    syncNextBtn();
    window.location.href = '/dashboard/';
  });

  btnNext.addEventListener('click', () => {
    if (!btnNext.classList.contains('active')) {
      for (let s = 1; s <= 9; s++) {
        const boxes   = document.querySelectorAll(`input[data-section="${s}"]`);
        const allDone = [...boxes].every(cb => cb.checked);
        const errEl   = document.getElementById(`err-${s}`);
        if (errEl) errEl.classList.toggle('show', !allDone);
      }
      const firstErr = document.querySelector('.section-error.show');
      if (firstErr) firstErr.closest('.checklist-section').scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }
    document.getElementById('confirmModal').classList.add('show');
  });

  document.getElementById('btnConfirm').addEventListener('click', async () => {
    await fetch('/dashboard/api/safety-status/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: 'checklist' }),
    }).catch(() => {});
    window.location.href = '/dashboard/safety/vr/';
  });
})();
