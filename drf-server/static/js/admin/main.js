'use strict';

(async () => {
    const me = await Auth.getMe();
    if (!me) return;

    const nameEl = document.getElementById('adminName');
    const roleEl = document.getElementById('adminRole');
    if (nameEl) nameEl.textContent = me.username ?? '';
    if (roleEl) roleEl.textContent = me.role ?? '';
})();

document.getElementById('btnHome').addEventListener('click', function () {
    window.location.href = '/dashboard/';
});

document.getElementById('btnLogout').addEventListener('click', function () {
    Auth.clear();
    window.location.href = '/accounts/login/';
});
