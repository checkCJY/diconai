'use strict';

(async () => {
    const me = await Auth.getMe();
    if (!me) return;

    const nameEl = document.getElementById('adminName');
    const roleEl = document.getElementById('adminRole');
    if (nameEl) nameEl.textContent = me.username ?? '';
    if (roleEl) roleEl.textContent = me.role ?? '';
    Auth.setRole(me.role);
})();

document.getElementById('btnHome').addEventListener('click', function () {
    window.location.href = '/dashboard/';
});

document.getElementById('btnLogout').addEventListener('click', function () {
    Auth.clear();
    window.location.href = '/accounts/login/';
});

const AdminSNB = {
    drawer:  document.getElementById('adminSnbDrawer'),
    overlay: document.getElementById('adminSnbOverlay'),
    open()   { this.drawer.classList.add('open');    this.overlay.classList.add('open'); },
    close()  { this.drawer.classList.remove('open'); this.overlay.classList.remove('open'); },
    toggle() { this.drawer.classList.contains('open') ? this.close() : this.open(); },
    init() {
        document.getElementById('adminHamburger')?.addEventListener('click', () => this.toggle());
        this.overlay?.addEventListener('click', () => this.close());
    },
};
AdminSNB.init();

// ── 페이지 접근 권한 체크 ────────────────────────────────────
const AdminAccess = {
  async check(allowedRoles = ['super_admin', 'facility_admin']) {
    let role = Auth.getRole();
    if (!role) {
      const me = await Auth.getMe();
      if (!me) { Auth.redirectLogin(); return false; }
      role = me.role;
      Auth.setRole(role);
    }
    if (!allowedRoles.includes(role)) {
      this._showDenied();
      return false;
    }
    return true;
  },

  _showDenied() {
    const el = document.createElement('div');
    el.id = 'accessDeniedOverlay';
    el.style.cssText = [
      'position:fixed', 'inset:0', 'background:rgba(0,0,0,0.45)',
      'display:flex', 'align-items:center', 'justify-content:center', 'z-index:9999'
    ].join(';');
    el.innerHTML = `
      <div style="background:#fff;border-radius:12px;width:360px;padding:36px 28px;
                  text-align:center;box-shadow:0 20px 60px rgba(0,0,0,0.18);">
        <div style="font-size:40px;margin-bottom:14px;">🔒</div>
        <h3 style="font-size:17px;font-weight:700;color:#111827;margin:0 0 8px;">접근 권한이 없습니다</h3>
        <p style="font-size:13px;color:#6b7280;margin:0 0 24px;line-height:1.6;">
          이 페이지는 슈퍼관리자 또는<br>공장관리자만 접근할 수 있습니다.
        </p>
        <button id="btnAccessDeniedOk"
          style="width:100%;padding:10px;background:#2563eb;color:#fff;border:none;
                 border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;">
          대시보드로 이동
        </button>
      </div>`;
    document.body.appendChild(el);
    document.getElementById('btnAccessDeniedOk').addEventListener('click', () => {
      window.location.href = '/dashboard/';
    });
  },
};

// 사이드바 그룹 토글
document.addEventListener('DOMContentLoaded', () => {
    const toggle = document.getElementById('snbLogToggle');
    if (toggle) {
        toggle.addEventListener('click', () => {
            document.getElementById('snbLogGroup').classList.toggle('open');
        });
    }
});
