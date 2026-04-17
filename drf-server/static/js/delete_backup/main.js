/* ==========================================================
   main.js — CM-01 / CM-02 / SNB-01
   산재 예방 통합 관제 시스템 대시보드
   ========================================================== */

'use strict';

// ──────────────────────────────────────────────────────────
// AUTH 모듈 — JWT 토큰 관리
// ──────────────────────────────────────────────────────────
const Auth = {
  getAccessToken() { return localStorage.getItem('access_token'); },
  getRole()        { return localStorage.getItem('role'); },
  getUsername()    { return localStorage.getItem('username'); },

  clear() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('username');
    localStorage.removeItem('role');
  },

  // Bearer 헤더 포함 fetch
  async apiFetch(url, opts = {}) {
    const token = this.getAccessToken();
    const headers = Object.assign({ 'Content-Type': 'application/json' }, opts.headers || {});
    if (token) headers['Authorization'] = `Bearer ${token}`;
    return fetch(url, { ...opts, headers });
  },

  // 현재 사용자 정보 조회 (401이면 로그인 페이지로)
  async getMe() {
    try {
      const res = await this.apiFetch('/api/auth/me/');
      if (res.status === 401) { this.redirectLogin(); return null; }
      if (!res.ok)            { return null; }
      return await res.json();
    } catch {
      return null;
    }
  },

  redirectLogin() {
    this.clear();
    window.location.href = '/login/';
  },
};


// ──────────────────────────────────────────────────────────
// CM-01 — SNB 토글
// ──────────────────────────────────────────────────────────
const SNB = {
  drawer:  document.getElementById('snbDrawer'),
  overlay: document.getElementById('snbOverlay'),

  open() {
    this.drawer.classList.add('open');
    this.overlay.classList.add('open');
  },
  close() {
    this.drawer.classList.remove('open');
    this.overlay.classList.remove('open');
  },
  toggle() {
    this.drawer.classList.contains('open') ? this.close() : this.open();
  },
  init() {
    document.getElementById('hamburger')
      ?.addEventListener('click', () => this.toggle());
    document.getElementById('snbClose')
      ?.addEventListener('click', () => this.close());
    this.overlay
      ?.addEventListener('click', () => this.close());
  },
};


// ──────────────────────────────────────────────────────────
// SNB-01 — 메뉴 렌더링 & 아코디언
// ──────────────────────────────────────────────────────────
const Menu = {
  currentPath: window.location.pathname,

  // 아이콘 매핑
  iconMap: {
    shield:   '🛡',
    monitor:  '🖥',
    settings: '⚙',
  },

  render(menuTree) {
    const container = document.getElementById('snbMenu');
    const errDiv    = document.getElementById('snbError');

    if (!menuTree || menuTree.length === 0) {
      errDiv.style.display = 'block';
      return;
    }
    errDiv.style.display = 'none';

    const ul = document.createElement('ul');
    ul.className = 'snb-depth1';

    menuTree.forEach((menu) => {
      const li = document.createElement('li');
      li.className = 'snb-depth1-item';

      const hasChildren = menu.children && menu.children.length > 0;
      const icon = this.iconMap[menu.icon] || '•';

      // Depth1 버튼
      const btn = document.createElement('button');
      btn.className = 'snb-depth1-btn';
      btn.setAttribute('data-id', menu.id);
      btn.innerHTML = `
        <span class="menu-icon">${icon}</span>
        <span class="menu-label">${menu.label}</span>
        ${hasChildren ? '<span class="menu-arrow">▶</span>' : ''}
      `;

      li.appendChild(btn);

      // Depth2 목록
      if (hasChildren) {
        const subUl = document.createElement('ul');
        subUl.className = 'snb-depth2';
        subUl.id = `submenu-${menu.id}`;

        menu.children.forEach((child) => {
          const subLi = document.createElement('li');
          const isActive = this.currentPath === child.path;
          subLi.innerHTML = `
            <a href="${child.path}" class="${isActive ? 'active' : ''}"
               data-path="${child.path}">${child.label}</a>
          `;
          subUl.appendChild(subLi);
        });

        li.appendChild(subUl);

        // 아코디언 토글
        btn.addEventListener('click', () => {
          const isExpanded = btn.classList.contains('expanded');
          // 열려있으면 닫기, 아니면 열기
          btn.classList.toggle('expanded', !isExpanded);
          subUl.classList.toggle('open', !isExpanded);
        });

        // 현재 경로가 하위에 있으면 기본 펼침
        const hasActivePath = menu.children.some(c => c.path === this.currentPath);
        if (hasActivePath) {
          btn.classList.add('expanded');
          subUl.classList.add('open');
        }

        // Depth2 클릭 시 SNB 닫기 (페이지 이동)
        subUl.querySelectorAll('a').forEach(a => {
          a.addEventListener('click', () => SNB.close());
        });
      } else {
        // 하위 없는 Depth1은 바로 이동
        if (menu.path) {
          btn.addEventListener('click', () => {
            window.location.href = menu.path;
            SNB.close();
          });
        }
      }

      ul.appendChild(li);
    });

    container.innerHTML = '';
    container.appendChild(ul);
  },

  showError() {
    document.getElementById('snbError').style.display = 'block';
  },
};


// ──────────────────────────────────────────────────────────
// CM-02 — 시계 / 새로고침 / 홈 / 관리자 / 로그아웃
// ──────────────────────────────────────────────────────────
const Header = {
  isRefreshing: false,
  adminUrl:     null,

  // ── 현재 시간 1초 갱신 ──────────────────────────────
  initClock() {
    const clockEl = document.getElementById('clock');
    function tick() {
      if (!clockEl) return;
      const now = new Date();
      const pad = n => String(n).padStart(2, '0');
      clockEl.textContent =
        `${now.getFullYear()}.${pad(now.getMonth()+1)}.${pad(now.getDate())} ` +
        `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
    }
    tick();
    setInterval(tick, 1000);
  },

  // ── 마지막 갱신 시간 업데이트 ───────────────────────
  updateLastUpdated() {
    const el = document.getElementById('lastUpdate');
    if (!el) return;
    const now = new Date();
    const pad = n => String(n).padStart(2, '0');
    el.textContent =
      `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
  },

  // ── 새로고침 버튼 ────────────────────────────────────
  async handleRefresh() {
    if (this.isRefreshing) return;       // 중복 요청 방지
    this.isRefreshing = true;

    const btn = document.getElementById('btnRefresh');
    if (btn) btn.classList.add('spinning');

    try {
      const res  = await Auth.apiFetch('/api/dashboard/refresh/');
      if (res.status === 401) { Auth.redirectLogin(); return; }
      const data = await res.json();

      // 관리자 URL 캐싱
      if (data.admin_url) {
        this.adminUrl = data.admin_url;
        const btnAdmin = document.getElementById('btnAdmin');
        if (btnAdmin) btnAdmin.style.display = '';
      }

      this.updateLastUpdated();
    } catch {
      // 새로고침 실패 → 수치 `-` 처리는 각 패널 담당
    } finally {
      this.isRefreshing = false;
      if (btn) btn.classList.remove('spinning');
    }
  },

  // ── 홈 버튼 ─────────────────────────────────────────
  handleHome() {
    if (window.location.pathname === '/') {
      this.handleRefresh();             // 메인이면 재조회로 대체
    } else {
      window.location.href = '/';
    }
  },

  // ── 관리자 메뉴 버튼 ─────────────────────────────────
  handleAdmin() {
    const url = this.adminUrl || '/admin/';
    window.location.href = url;
  },

  // ── 로그아웃 모달 ────────────────────────────────────
  initLogout() {
    const modal         = document.getElementById('logoutModal');
    const btnLogout     = document.getElementById('btnLogout');
    const logoutConfirm = document.getElementById('logoutConfirm');
    const logoutCancel  = document.getElementById('logoutCancel');

    btnLogout?.addEventListener('click', () => {
      modal.style.display = 'flex';
    });
    logoutCancel?.addEventListener('click', () => {
      modal.style.display = 'none';
    });
    logoutConfirm?.addEventListener('click', () => {
      Auth.redirectLogin();
    });
  },

  // ── 헤더에 사용자 정보 렌더링 (CM-01) ───────────────
  renderUser(username) {
    const nameEl = document.getElementById('headerUsername');
    const roleEl = document.getElementById('headerRole');
    if (nameEl) nameEl.textContent = username ? `${username}님` : '-';
    if (roleEl) roleEl.textContent = '환영합니다.';
  },

  // ── 관리자 버튼 노출 여부 ───────────────────────────
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


// ──────────────────────────────────────────────────────────
// 앱 초기화
// ──────────────────────────────────────────────────────────
async function initApp() {
  // 토큰 없으면 즉시 리다이렉트
  if (!Auth.getAccessToken()) {
    Auth.redirectLogin();
    return;
  }

  // 사용자 정보 조회
  const user = await Auth.getMe();
  if (!user) {
    // getMe 내부에서 401 처리하므로 여기선 graceful fallback
    const cachedName = Auth.getUsername();
    const cachedRole = Auth.getRole();
    Header.renderUser(cachedName || '-', cachedRole || '-');
    Menu.showError();
  } else {
    Header.renderUser(user.username, user.role);
    Header.showAdminBtn(user.role);
    Menu.render(user.menu_tree);
  }

  SNB.init();
  Header.init();
  Header.updateLastUpdated();

  // 차트/WebSocket 초기화
  initCharts();
  initWebSocket();
}


// ──────────────────────────────────────────────────────────
// 맵 탭
// ──────────────────────────────────────────────────────────
document.querySelectorAll('.map-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.map-tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
  });
});


// ──────────────────────────────────────────────────────────
// 가스 더미 데이터 (초기 렌더)
// ──────────────────────────────────────────────────────────
const gasData = [
  { name: 'O2(산소)',             value: 20,   unit: '%',   level: 'danger'  },
  { name: 'CO(일산화탄소)',        value: 890,  unit: 'ppm', level: 'danger'  },
  { name: 'CO2(이산화탄소)',       value: 9480, unit: 'ppm', level: 'danger'  },
  { name: 'H2S(황화수소)',         value: 78,   unit: 'ppm', level: 'caution' },
  { name: 'NO2(이산화질소)',       value: 3.2,  unit: 'ppm', level: 'caution' },
  { name: 'SO2(이산화황)',         value: 1.5,  unit: 'ppm', level: 'safe'    },
  { name: 'O3(오존)',              value: 0.05, unit: 'ppm', level: 'safe'    },
  { name: 'NH3(암모니아)',         value: 22,   unit: 'ppm', level: 'safe'    },
  { name: 'VOC(휘발성유기화합물)', value: 0.4,  unit: 'ppm', level: 'safe'    },
];
const levelLabel = { danger: '위험', caution: '주의', safe: '정상' };

(function renderGasTable() {
  const tbody = document.getElementById('gasTableBody');
  if (!tbody) return;
  gasData.forEach(g => {
    const tr = document.createElement('tr');
    tr.className = `gas-row ${g.level}`;
    tr.innerHTML = `<td>${g.name}</td><td>${g.value}</td><td>${g.unit}</td>
      <td><span class="brisk ${g.level}">${levelLabel[g.level]}</span></td>`;
    tbody.appendChild(tr);
  });
})();


// ──────────────────────────────────────────────────────────
// Chart.js 실시간 차트
// ──────────────────────────────────────────────────────────
const MAX_POINTS = 30;

function nowLabel() {
  const d = new Date(), pad = n => String(n).padStart(2, '0');
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function pushData(chart, label, ...values) {
  chart.data.labels.push(label);
  values.forEach((v, i) => chart.data.datasets[i].data.push(v));
  if (chart.data.labels.length > MAX_POINTS) {
    chart.data.labels.shift();
    chart.data.datasets.forEach(ds => ds.data.shift());
  }
  chart.update('none');
}

const CHART_DEFAULTS = {
  animation: false, responsive: true, maintainAspectRatio: true,
  plugins: { legend: { labels: { color: '#aaa', font: { size: 10 }, boxWidth: 12 } } },
  scales: {
    x: { ticks: { color: '#666', maxTicksLimit: 6, font: { size: 9 } }, grid: { color: '#2a2a2a' } },
    y: { ticks: { color: '#666', font: { size: 9 } },                   grid: { color: '#2a2a2a' } },
  },
};

let gasChart   = null;
let powerChart = null;

function initCharts() {
  const ctxGas = document.getElementById('chartGas');
  gasChart = ctxGas ? new Chart(ctxGas, {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        { label: '현재 농도 (ppm)',   data: [], borderColor: '#f59e0b', backgroundColor: 'rgba(245,158,11,0.12)', tension: 0.4, pointRadius: 2, fill: true  },
        { label: '예측 최대 농도 (ppm)', data: [], borderColor: '#ef4444', backgroundColor: 'transparent', borderDash: [5,3], tension: 0.4, pointRadius: 2, fill: false },
      ],
    },
    options: CHART_DEFAULTS,
  }) : null;

  const ctxPower = document.getElementById('chartPower');
  powerChart = ctxPower ? new Chart(ctxPower, {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        { label: '예상 최대 부하 (kW)', data: [], borderColor: '#ef4444', backgroundColor: 'rgba(239,68,68,0.12)', tension: 0.4, pointRadius: 2, fill: true },
      ],
    },
    options: CHART_DEFAULTS,
  }) : null;

  initYScaleControls();
}


// Y축 스케일 조절
const scaleState = { gas: null, power: null };

function adjustYScale(key, chart, direction) {
  if (!chart) return;
  const labelEl = document.getElementById(key + 'ScaleVal');
  if (direction === 0) {
    scaleState[key] = null;
    chart.options.scales.y.max = undefined;
    chart.options.scales.y.min = undefined;
    if (labelEl) labelEl.textContent = '자동';
  } else {
    const current = scaleState[key] ?? chart.scales.y.max;
    const factor  = direction > 0 ? 0.75 : 1.35;
    scaleState[key] = Math.max(1, Math.round(current * factor));
    chart.options.scales.y.max = scaleState[key];
    if (labelEl) labelEl.textContent = scaleState[key].toLocaleString();
  }
  chart.update('none');
}

function initYScaleControls() {
  document.getElementById('gasZoomIn')  ?.addEventListener('click', () => adjustYScale('gas',   gasChart,   +1));
  document.getElementById('gasZoomOut') ?.addEventListener('click', () => adjustYScale('gas',   gasChart,   -1));
  document.getElementById('gasReset')   ?.addEventListener('click', () => adjustYScale('gas',   gasChart,    0));
  document.getElementById('powerZoomIn') ?.addEventListener('click', () => adjustYScale('power', powerChart, +1));
  document.getElementById('powerZoomOut')?.addEventListener('click', () => adjustYScale('power', powerChart, -1));
  document.getElementById('powerReset')  ?.addEventListener('click', () => adjustYScale('power', powerChart,  0));
}


// ──────────────────────────────────────────────────────────
// WebSocket — 실시간 센서 데이터
// ──────────────────────────────────────────────────────────
function initWebSocket() {
  let ws;
  try {
    ws = new WebSocket('ws://localhost:8001/ws/sensors/');
  } catch {
    return;
  }

ws.onopen = () => { if(statusDiv) statusDiv.innerText = "🟢 연결됨 (데이터 수신 중...)"; };
ws.onclose = () => {
    if(statusDiv) statusDiv.innerText = "🔴 연결 끊김";
    if(statusDiv) statusDiv.style.color = "red";
};

    // Panel 12: 유해가스 테이블
    const tbody = document.getElementById('gasTableBody');
    if (tbody && data.co !== undefined) {
      const gases = [
        { name: 'CO (일산화탄소)', value: data.co,  unit: 'ppm', level: data.co  > 50   ? 'danger' : 'safe' },
        { name: 'H₂S (황화수소)',  value: data.h2s, unit: 'ppm', level: data.h2s > 10   ? 'danger' : 'safe' },
        { name: 'O₂ (산소)',       value: data.o2,  unit: '%',   level: data.o2  < 19.5 ? 'danger' : 'safe' },
      ];
      tbody.innerHTML = gases.map(g =>
        `<tr><td>${g.name}</td><td>${g.value}</td><td>${g.unit}</td>
         <td><span class="brisk ${g.level}">${g.level === 'danger' ? '위험' : '정상'}</span></td></tr>`
      ).join('');
    }

    // Panel 13: AI 예측 — CO
    const coRisk = data.co > 50;
    const aiGasName    = document.getElementById('aiGasName');
    const aiCurrentVal = document.getElementById('aiCurrentVal');
    const aiMaxVal     = document.getElementById('aiMaxVal');
    if (aiGasName)    aiGasName.className   = coRisk ? 'danger-text fw' : 'caution-text fw';
    if (aiCurrentVal) { aiCurrentVal.textContent = data.co + ' ppm'; aiCurrentVal.className = 'big ' + (coRisk ? 'danger-text' : 'caution-text'); }
    if (aiMaxVal)     aiMaxVal.textContent  = Math.round(data.co * 1.5) + ' ppm';

    // Panel 14: 전력 현황
    const powerTotal    = document.getElementById('powerTotal');
    const powerChangePct = document.getElementById('powerChangePct');
    const powerTableBody = document.getElementById('powerTableBody');
    if (powerTotal && data.total_power_mw !== undefined)
      powerTotal.textContent = data.total_power_mw.toLocaleString() + ' MW';
    if (powerChangePct && data.power_change_pct !== undefined) {
      const pct  = data.power_change_pct;
      const sign = pct >= 0 ? '▲ +' : '▼ ';
      powerChangePct.textContent = `기준 대비 ${sign}${pct}%`;
      powerChangePct.className   = pct >= 15 ? 'danger-text' : 'caution-text';
      powerChangePct.style.cssText = 'font-size:11px;margin-bottom:4px;';
    }
    if (powerTableBody && data.equipment) {
      powerTableBody.innerHTML = data.equipment.map(eq =>
        `<tr><td>${eq.name}</td><td>${eq.mwh} MWh</td><td>${eq.temp}°C</td>
         <td><span class="brisk ${eq.level}">${levelLabel[eq.level]}</span></td></tr>`
      ).join('');
    }

    // Panel 15: AI 예측 — 전력
    const aiPowerEquipName = document.getElementById('aiPowerEquipName');
    const aiPowerEta       = document.getElementById('aiPowerEta');
    const aiPowerMaxLoad   = document.getElementById('aiPowerMaxLoad');
    if (aiPowerEquipName && data.ai_power_equipment) aiPowerEquipName.textContent = data.ai_power_equipment;
    if (aiPowerEta       && data.ai_eta_min !== undefined) aiPowerEta.textContent = data.ai_eta_min + ' 분 뒤';
    if (aiPowerMaxLoad   && data.ai_max_load_kw !== undefined)
      aiPowerMaxLoad.innerHTML = `${data.ai_max_load_kw.toLocaleString()} kW <span style="font-size:11px;font-weight:400;">(정상 대비 ${data.ai_max_load_pct}%)</span>`;

    // 차트 실시간 업데이트
    const tick = nowLabel();
    if (gasChart)   pushData(gasChart,   tick, data.co, Math.round(data.co * 1.5));
    if (powerChart) pushData(powerChart, tick, data.ai_max_load_kw);
  };
}


// ──────────────────────────────────────────────────────────
// 실행
// ──────────────────────────────────────────────────────────
initApp();
