/* ==========================================================
   layout.js — SNB 토글 / 메뉴 렌더링 / 헤더
   출처: dashboard.js SNB · Menu · Header 모듈
   의존: auth.js (Auth), util.js (pad, nowLabel)
   ========================================================== */

'use strict';

// ──────────────────────────────────────────────────────────
// CM-01 — SNB 토글
// ──────────────────────────────────────────────────────────
const SNB = {
  drawer:  document.getElementById('snbDrawer'),
  overlay: document.getElementById('snbOverlay'),

  open()   { this.drawer.classList.add('open');    this.overlay.classList.add('open'); },
  close()  { this.drawer.classList.remove('open'); this.overlay.classList.remove('open'); },
  toggle() { this.drawer.classList.contains('open') ? this.close() : this.open(); },

  init() {
    document.getElementById('hamburger')?.addEventListener('click', () => this.toggle());
    document.getElementById('snbClose') ?.addEventListener('click', () => this.close());
    this.overlay?.addEventListener('click', () => this.close());
  },
};


// ──────────────────────────────────────────────────────────
// SNB-01 — 메뉴 렌더링 & 아코디언
// ──────────────────────────────────────────────────────────
const Menu = {
  currentPath: window.location.pathname,

  iconMap: { shield: '🛡', monitor: '🖥', settings: '⚙' },

  render(menuTree) {
    const container = document.getElementById('snbMenu');
    const errDiv    = document.getElementById('snbError');

    if (!menuTree || menuTree.length === 0) { errDiv.style.display = 'block'; return; }
    errDiv.style.display = 'none';

    const ul = document.createElement('ul');
    ul.className = 'snb-depth1';

    menuTree.forEach((menu) => {
      const li          = document.createElement('li');
      li.className      = 'snb-depth1-item';
      const hasChildren = menu.children && menu.children.length > 0;
      const icon        = this.iconMap[menu.icon] || '•';

      const btn = document.createElement('button');
      btn.className = 'snb-depth1-btn';
      btn.setAttribute('data-id', menu.id);
      btn.innerHTML = `
        <span class="menu-icon">${icon}</span>
        <span class="menu-label">${menu.label}</span>
        ${hasChildren ? '<span class="menu-arrow">▶</span>' : ''}
      `;
      li.appendChild(btn);

      if (hasChildren) {
        const subUl = document.createElement('ul');
        subUl.className = 'snb-depth2';
        subUl.id        = `submenu-${menu.id}`;

        menu.children.forEach((child) => {
          const subLi = document.createElement('li');
          const isActive = this.currentPath === child.path;
          subLi.innerHTML = `<a href="${child.path}" class="${isActive ? 'active' : ''}" data-path="${child.path}">${child.label}</a>`;
          subUl.appendChild(subLi);
        });
        li.appendChild(subUl);

        btn.addEventListener('click', () => {
          const isExpanded = btn.classList.contains('expanded');
          btn.classList.toggle('expanded', !isExpanded);
          subUl.classList.toggle('open', !isExpanded);
        });

        if (menu.children.some(c => c.path === this.currentPath)) {
          btn.classList.add('expanded');
          subUl.classList.add('open');
        }

        subUl.querySelectorAll('a').forEach(a => a.addEventListener('click', () => SNB.close()));
      } else if (menu.path) {
        btn.addEventListener('click', () => { window.location.href = menu.path; SNB.close(); });
      }

      ul.appendChild(li);
    });

    container.innerHTML = '';
    container.appendChild(ul);
  },

  showError() { document.getElementById('snbError').style.display = 'block'; },
};


// ──────────────────────────────────────────────────────────
// CM-02 — 시계 / 새로고침 / 홈 / 관리자 / 로그아웃
// ──────────────────────────────────────────────────────────
const Header = {
  isRefreshing: false,
  adminUrl:     null,

  initClock() {
    const clockEl = document.getElementById('clock');
    const tick = () => {
      if (!clockEl) return;
      const now = new Date();
      clockEl.textContent =
        `${now.getFullYear()}.${pad(now.getMonth() + 1)}.${pad(now.getDate())} ` +
        `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
    };
    tick();
    setInterval(tick, 1000);
  },

  updateLastUpdated() {
    const el = document.getElementById('lastUpdate');
    if (!el) return;
    el.textContent = nowLabel();
  },

  async handleRefresh() {
    if (this.isRefreshing) return;
    this.isRefreshing = true;
    const btn = document.getElementById('btnRefresh');
    if (btn) btn.classList.add('spinning');
    try {
      const res  = await Auth.apiFetch('/api/dashboard/refresh/');
      if (res.status === 401) { Auth.redirectLogin(); return; }
      const data = await res.json();
      if (data.admin_url) {
        this.adminUrl = data.admin_url;
        const btnAdmin = document.getElementById('btnAdmin');
        if (btnAdmin) btnAdmin.style.display = '';
      }
      this.updateLastUpdated();
    } catch { /* 실패 시 수치 '-' 처리는 각 패널 담당 */ }
    finally {
      this.isRefreshing = false;
      if (btn) btn.classList.remove('spinning');
    }
  },

  handleHome() {
    if (window.location.pathname === '/') { this.handleRefresh(); }
    else { window.location.href = '/'; }
  },

  handleAdmin() { window.location.href = this.adminUrl || '/admin/'; },

  initLogout() {
    const modal         = document.getElementById('logoutModal');
    const btnLogout     = document.getElementById('btnLogout');
    const logoutConfirm = document.getElementById('logoutConfirm');
    const logoutCancel  = document.getElementById('logoutCancel');

    btnLogout    ?.addEventListener('click', () => { modal.style.display = 'flex'; });
    logoutCancel ?.addEventListener('click', () => { modal.style.display = 'none'; });
    logoutConfirm?.addEventListener('click', () => { Auth.redirectLogin(); });
  },

  renderUser(username) {
    const nameEl = document.getElementById('headerUsername');
    if (nameEl) nameEl.textContent = username ? `${username}님 환영합니다` : '-';
  },

  showAdminBtn(role) {
    if (role === 'admin' || role === 'superadmin') {
      const btn = document.getElementById('btnAdmin');
      if (btn) btn.style.display = '';
    }
  },

  init() {
    this.initClock();
    this.initLogout();
    document.getElementById('btnRefresh')?.addEventListener('click', () => this.handleRefresh());
    document.getElementById('btnHome')   ?.addEventListener('click', () => this.handleHome());
    document.getElementById('btnAdmin')  ?.addEventListener('click', () => this.handleAdmin());
  },
};
