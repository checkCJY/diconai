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
    this.overlay?.addEventListener('click', () => this.close());
  },
};


// ──────────────────────────────────────────────────────────
// SNB-01 — 메뉴 렌더링 & 아코디언
// ──────────────────────────────────────────────────────────
const Menu = {
  currentPath: window.location.pathname,

  iconMap: {
    shield:   '<svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" style="vertical-align:middle"><path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4z"/></svg>',
    monitor:  '<svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" style="vertical-align:middle"><path d="M21 3H3c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h5v2H7v2h10v-2h-1v-2h5c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 14H3V5h18v12z"/></svg>',
    settings: '<svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" style="vertical-align:middle"><path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/></svg>',
  },

  // ── API에서 받은 메뉴 트리를 SNB DOM으로 렌더링하고 아코디언을 설정한다. ─
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
      let icon = this.iconMap[menu.icon];
      if (!icon) {
        if (menu.icon) console.warn('[Menu] icon not defined:', menu.icon);
        icon = '•';
      }

      const btn = document.createElement('button');
      btn.className = 'snb-depth1-btn';
      btn.setAttribute('data-id', menu.id);
      // 사용자 데이터(menu.label)는 textContent로 안전 처리. icon은 인하우스 정의 SVG/텍스트만.
      const iconSpan = document.createElement('span');
      iconSpan.className = 'menu-icon';
      iconSpan.innerHTML = icon;
      btn.appendChild(iconSpan);
      const labelSpan = document.createElement('span');
      labelSpan.className = 'menu-label';
      labelSpan.textContent = menu.label;
      btn.appendChild(labelSpan);
      if (hasChildren) {
        const arrowSpan = document.createElement('span');
        arrowSpan.className = 'menu-arrow';
        arrowSpan.textContent = '▶';
        btn.appendChild(arrowSpan);
      }
      li.appendChild(btn);

      if (hasChildren) {
        const subUl = document.createElement('ul');
        subUl.className = 'snb-depth2';
        subUl.id        = `submenu-${menu.id}`;

        menu.children.forEach((child) => {
          const subLi = document.createElement('li');
          const isActive = this.currentPath === child.path;
          const a = document.createElement('a');
          a.href = child.path;
          if (isActive) a.classList.add('active');
          a.dataset.path = child.path;
          a.textContent = child.label;
          subLi.appendChild(a);
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
const ROLE_LABEL = Object.freeze({
  worker:         '작업자',
  facility_admin: '공장관리자',
  super_admin:    '슈퍼관리자',
  viewer:         '열람자',
});

const Header = {
  isRefreshing: false,
  adminUrl:     null,
  _refreshErrTimer: null,

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
    el.textContent = nowDateLabel();
  },

  // ── 새로고침 API 호출 후 이벤트 패널을 재조회하고 최종 갱신 시각을 업데이트한다. ─
  async handleRefresh() {
    if (this.isRefreshing) return;
    this.isRefreshing = true;
    const btn = document.getElementById('btnRefresh');
    if (btn) btn.classList.add('spinning');
    try {
      const res  = await Auth.apiFetch('/dashboard/api/refresh/');
      if (res.status === 401) { Auth.redirectLogin(); return; }
      const data = await res.json();
      if (data.admin_url) {
        this.adminUrl = data.admin_url;
        const btnAdmin = document.getElementById('btnAdmin');
        if (btnAdmin) btnAdmin.style.display = '';
      }
      this.updateLastUpdated();
      // H-2: 이벤트 패널 REST 재조회 (가스/전력/지도는 WebSocket 실시간, 작업자는 30s 폴링)
      if (typeof EventPanel !== 'undefined') EventPanel.loadEventList();
    } catch {
      // M-2: 실패 시 버튼 시각적 피드백 (timer 누적 방지)
      if (btn) {
        btn.style.color = 'var(--danger)';
        btn.title = '새로고침 실패 — 잠시 후 다시 시도하세요';
        clearTimeout(this._refreshErrTimer);
        this._refreshErrTimer = setTimeout(() => {
          btn.style.color = ''; btn.title = '새로고침';
        }, 3000);
      }
    }
    finally {
      this.isRefreshing = false;
      if (btn) btn.classList.remove('spinning');
    }
  },

  // ── 현재 페이지가 대시보드이면 새로고침, 아니면 대시보드로 이동한다. ────
  handleHome() {
    if (window.location.pathname === '/dashboard/') { this.handleRefresh(); }
    else { window.location.href = '/dashboard/'; }
  },

  handleAdmin() { window.location.href = this.adminUrl || '/admin-panel/accounts-management/'; },

  initLogout() {
    const modal           = document.getElementById('logoutModal');
    const successModal    = document.getElementById('logoutSuccessModal');
    const btnLogout       = document.getElementById('btnLogout');
    const logoutConfirm   = document.getElementById('logoutConfirm');
    const logoutCancel    = document.getElementById('logoutCancel');
    const logoutSuccessOk = document.getElementById('logoutSuccessOk');

    btnLogout    ?.addEventListener('click', () => { modal.style.display = 'flex'; });
    logoutCancel ?.addEventListener('click', () => { modal.style.display = 'none'; });
    logoutConfirm?.addEventListener('click', async () => {
      try {
        // Phase 5: refresh 토큰을 body로 동봉 → 서버가 blacklist 등록
        const refresh = Auth.getRefreshToken();
        await Auth.apiFetch('/api/auth/logout/', {
          method: 'POST',
          body: JSON.stringify(refresh ? { refresh } : {}),
        });
      } finally {
        modal.style.display = 'none';
        successModal.style.display = 'flex';
      }
    });
    logoutSuccessOk?.addEventListener('click', () => { Auth.redirectLogin(); });
    // L-2: backdrop 클릭 시 팝업 닫기
    modal?.addEventListener('click', (e) => {
      if (e.target === modal) modal.style.display = 'none';
    });
  },

  renderUser(username, role) {
    const nameEl = document.getElementById('headerUsername');
    const roleEl = document.getElementById('headerRole');
    if (nameEl) nameEl.textContent = username ? `${username}님 환영합니다` : '-';
    if (roleEl) {
      const label = ROLE_LABEL[role];
      if (!label && role) console.warn('[Header] unknown role:', role);
      roleEl.textContent = label || '-';
    }
  },

  showAdminBtn(role) {
    if (role === 'facility_admin' || role === 'super_admin') {
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


// ──────────────────────────────────────────────────────────
// CM-01 공통 초기화 — app.js(메인) / app-sub.js(서브 페이지) 공유
// 의존: Auth, Header, Menu, SNB
// 헤더·SNB 공통 초기화 — 사용자 정보 조회 후 메뉴 렌더링
// ──────────────────────────────────────────────────────────
async function initHeaderAndSNB() {
  if (!Auth.getAccessToken()) { Auth.redirectLogin(); return null; }

  const user = await Auth.getMe();
  if (!user) {
    Header.renderUser(Auth.getUsername() || '-');
    Menu.showError();
  } else {
    Header.renderUser(user.username, user.role);
    Header.showAdminBtn(user.role);
    Menu.render(user.menu_tree);
    if (user.admin_url) Header.adminUrl = user.admin_url;
    Auth.setRole(user.role);
  }

  SNB.init();
  Header.init();
  Header.updateLastUpdated();
  return user;
}
