/* ==========================================================
   dashboard.js — 산재 예방 통합 관제 시스템
   통합 출처:
     main.js     (Auth / SNB / Menu / Header / Chart / WebSocket)
     CJY.js      (MN-04 작업자 현황 패널)
     dashboard_sh.html 인라인 스크립트 (Leaflet 실시간 모니터링 맵)

   ※ 공통 유틸(pad / nowLabel / pushData / MAX_POINTS / levelLabel)은
      util.js 에 정의되어 있습니다. 반드시 util.js 를 먼저 로드하세요.
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

  async apiFetch(url, opts = {}) {
    const token   = this.getAccessToken();
    const headers = Object.assign({ 'Content-Type': 'application/json' }, opts.headers || {});
    if (token) headers['Authorization'] = `Bearer ${token}`;
    return fetch(url, { ...opts, headers });
  },

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


// ──────────────────────────────────────────────────────────
// MN-02 — Leaflet 실시간 모니터링 맵
// 출처: dashboard_sh.html 인라인 스크립트
// 지도 SVG URL은 템플릿이 window.FACTORY_MAP_URL 로 주입
// ──────────────────────────────────────────────────────────
const MapPanel = {
  map:         null,
  layers:      {},
  gasMarkers:    {},
  workerMarkers: {},

  STATUS_COLOR: { normal: '#3fb950', caution: '#e3b341', danger: '#f85149' },
  ZONE_COLOR:   { danger:  '#f85149', warning: '#e3b341', normal:  '#3fb950' },

  riskColor(level)    { return [this.STATUS_COLOR.normal, this.STATUS_COLOR.caution, this.STATUS_COLOR.danger][level] ?? this.STATUS_COLOR.normal; },
  levelToStatus(level){ return ['normal', 'caution', 'danger'][level] ?? 'normal'; },

  // ── 더미 데이터 ─────────────────────────────────────────
  DUMMY_GAS_SENSORS: [
    { id:1, name:'가스센서 A', device_id:'sensor_01', x:150,  y:80,  risk_level:2, co:230, h2s:4,  o2:20.8 },
    { id:2, name:'가스센서 B', device_id:'sensor_02', x:600,  y:200, risk_level:1, co:20,  h2s:12, o2:19.5 },
    { id:3, name:'가스센서 C', device_id:'sensor_03', x:1000, y:100, risk_level:0, co:10,  h2s:2,  o2:21.0 },
    { id:4, name:'가스센서 D', device_id:'sensor_04', x:900,  y:450, risk_level:1, co:35,  h2s:8,  o2:20.1 },
    { id:5, name:'가스센서 E', device_id:'sensor_05', x:300,  y:400, risk_level:0, co:8,   h2s:1,  o2:21.0 },
  ],

  DUMMY_POWER_DEVICES: [
    { id:1, name:'스마트파워 A', device_id:'power_01', x:400,  y:150, risk_level:1 },
    { id:2, name:'스마트파워 B', device_id:'power_02', x:800,  y:300, risk_level:0 },
    { id:3, name:'스마트파워 C', device_id:'power_03', x:200,  y:500, risk_level:2 },
    { id:4, name:'스마트파워 D', device_id:'power_04', x:1100, y:400, risk_level:0 },
  ],

  DUMMY_GEOFENCES: [
    { id:1, name:'위험구역 A', zone_type:'danger',  polygon:[[80,50],[280,50],[280,200],[80,200]] },
    { id:2, name:'주의구역 B', zone_type:'warning', polygon:[[500,300],[750,300],[750,520],[500,520]] },
    { id:3, name:'관리구역 C', zone_type:'normal',  polygon:[[850,100],[1150,100],[1150,350],[850,350]] },
  ],

  DUMMY_WORKERS: [
    { id:1, name:'작업자 A', x:150, y:120, movement_status:'moving',     current_geofence:'위험구역 A', dx:4,  dy:2  },
    { id:2, name:'작업자 B', x:600, y:350, movement_status:'moving',     current_geofence:null,         dx:-3, dy:4  },
    { id:3, name:'작업자 C', x:950, y:200, movement_status:'stationary', current_geofence:'관리구역 C', dx:0,  dy:0  },
    { id:4, name:'작업자 D', x:350, y:480, movement_status:'moving',     current_geofence:null,         dx:5,  dy:-3 },
  ],

  // ── 팝업 HTML ─────────────────────────────────────────
  gasPopupHtml(s) {
    const st    = this.levelToStatus(s.risk_level);
    const label = { normal:'정상', caution:'주의', danger:'위험' }[st];
    return `<div class='popup-title'>📡 ${s.name}</div>
      <div>ID: ${s.device_id}</div>
      <div>상태: <span class='popup-status-${st}'>${label}</span></div>
      <div>CO: ${s.co} ppm &nbsp; H2S: ${s.h2s} ppm &nbsp; O2: ${s.o2}%</div>`;
  },
  powerPopupHtml(d) {
    const st    = this.levelToStatus(d.risk_level);
    const label = { normal:'정상', caution:'주의', danger:'위험' }[st];
    return `<div class='popup-title'>⚡ ${d.name}</div>
      <div>ID: ${d.device_id}</div>
      <div>상태: <span class='popup-status-${st}'>${label}</span></div>`;
  },
  workerPopupHtml(w) {
    const statusLabel = { moving:'이동 중', stationary:'정지', idle:'대기' };
    return `<div class='popup-title'>👷 ${w.name}</div>
      <div>현재 구역: ${w.current_geofence || '구역 밖'}</div>
      <div>상태: ${statusLabel[w.movement_status] || w.movement_status}</div>
      <div>위치: x:${w.x}, y:${w.y}</div>`;
  },

  // ── Leaflet 초기화 ────────────────────────────────────
  init() {
    if (!window.L || !document.getElementById('map')) return;

    this.map = L.map('map', {
      crs: L.CRS.Simple, minZoom: -2, maxZoom: 2,
      zoomControl: false, dragging: false,
      scrollWheelZoom: false, doubleClickZoom: false, touchZoom: false,
    });

    const bounds = [[0, 0], [600, 1300]];
    // FACTORY_MAP_URL은 main_dashboard.html 에서 window 전역으로 주입
    const mapUrl = window.FACTORY_MAP_URL || '';
    if (mapUrl) L.imageOverlay(mapUrl, bounds).addTo(this.map);
    this.map.fitBounds(bounds);

    this.layers = {
      gas:      L.layerGroup().addTo(this.map),
      power:    L.layerGroup().addTo(this.map),
      geofence: L.layerGroup().addTo(this.map),
      worker:   L.layerGroup().addTo(this.map),
    };

    this._drawAll();
    this._initTabFilter();
    this._startWorkerAnimation();
  },

  _drawAll() {
    this.DUMMY_GAS_SENSORS.forEach(s => {
      const m = L.circleMarker([s.y, s.x], {
        radius: 9, fillColor: this.riskColor(s.risk_level),
        color: '#fff', weight: 1.5, fillOpacity: 0.9,
      }).bindPopup(this.gasPopupHtml(s), { maxWidth: 220 });
      m.addTo(this.layers.gas);
      this.gasMarkers[s.device_id] = { marker: m, data: s };
    });

    this.DUMMY_POWER_DEVICES.forEach(d => {
      L.circleMarker([d.y, d.x], {
        radius: 9, fillColor: this.riskColor(d.risk_level),
        color: '#e3b341', weight: 2, fillOpacity: 0.85, dashArray: '4 2',
      }).bindPopup(this.powerPopupHtml(d), { maxWidth: 220 }).addTo(this.layers.power);
    });

    this.DUMMY_GEOFENCES.forEach(g => {
      const latlngs = g.polygon.map(([x, y]) => [y, x]);
      const color   = this.ZONE_COLOR[g.zone_type] || '#888';
      L.polygon(latlngs, { color, fillColor: color, fillOpacity: 0.15, weight: 2 })
       .bindPopup(`<div class='popup-title'>🚧 ${g.name}</div><div>유형: ${g.zone_type}</div>`)
       .addTo(this.layers.geofence);
    });

    this.DUMMY_WORKERS.forEach(w => {
      const m = L.circleMarker([w.y, w.x], {
        radius: 8, fillColor: '#58a6ff', color: '#fff', weight: 2, fillOpacity: 1,
      }).bindPopup(this.workerPopupHtml(w), { maxWidth: 200 });
      m.addTo(this.layers.worker);
      this.workerMarkers[w.id] = { marker: m, data: w };
    });
  },

  _initTabFilter() {
    const TAB_LAYER_MAP = {
      all:      ['gas', 'power', 'geofence', 'worker'],
      worker:   ['worker'],
      geofence: ['geofence'],
      gas:      ['gas'],
      facility: ['power'],
      power:    ['power'],
      location: [],
    };
    document.querySelectorAll('.map-tab').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.map-tab').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const visible = TAB_LAYER_MAP[btn.dataset.layer] || [];
        Object.entries(this.layers).forEach(([name, layer]) => {
          visible.includes(name) ? this.map.addLayer(layer) : this.map.removeLayer(layer);
        });
      });
    });
  },

  _startWorkerAnimation() {
    setInterval(() => {
      Object.values(this.workerMarkers).forEach(({ marker, data }) => {
        if (data.movement_status !== 'moving') return;
        const cur = marker.getLatLng();
        let nx = cur.lng + data.dx + (Math.random() - 0.5) * 3;
        let ny = cur.lat + data.dy + (Math.random() - 0.5) * 3;
        if (nx <= 0 || nx >= 1290) data.dx *= -1;
        if (ny <= 0 || ny >= 590)  data.dy *= -1;
        nx = Math.max(0, Math.min(1290, nx));
        ny = Math.max(0, Math.min(590,  ny));
        marker.setLatLng([ny, nx]);
        data.x = Math.round(nx);
        data.y = Math.round(ny);
        if (marker.isPopupOpen()) marker.setPopupContent(this.workerPopupHtml(data));
      });
    }, 1000);
  },

  // WebSocket 에서 가스센서 실시간 반영 (sensor_01 기준)
  updateGasSensorFromWS(wsData) {
    const entry = this.gasMarkers['sensor_01'];
    if (!entry) return;
    const level = wsData.level === '위험' ? 2 : 0;
    entry.marker.setStyle({ fillColor: this.riskColor(level) });
    entry.data.risk_level = level;
    entry.data.co  = wsData.co;
    entry.data.h2s = wsData.h2s;
    entry.data.o2  = wsData.o2;
    if (entry.marker.isPopupOpen()) entry.marker.setPopupContent(this.gasPopupHtml(entry.data));
  },
};


// ──────────────────────────────────────────────────────────
// 가스 더미 데이터 초기 렌더 (패널 12 초기값)
// ──────────────────────────────────────────────────────────
const GAS_INIT_DATA = [
  { name: 'O2(산소)',              value: 20,   unit: '%',   level: 'danger'  },
  { name: 'CO(일산화탄소)',         value: 890,  unit: 'ppm', level: 'danger'  },
  { name: 'CO2(이산화탄소)',        value: 9480, unit: 'ppm', level: 'danger'  },
  { name: 'H2S(황화수소)',          value: 78,   unit: 'ppm', level: 'caution' },
  { name: 'NO2(이산화질소)',        value: 3.2,  unit: 'ppm', level: 'caution' },
  { name: 'SO2(이산화황)',          value: 1.5,  unit: 'ppm', level: 'safe'    },
  { name: 'O3(오존)',               value: 0.05, unit: 'ppm', level: 'safe'    },
  { name: 'NH3(암모니아)',          value: 22,   unit: 'ppm', level: 'safe'    },
  { name: 'VOC(휘발성유기화합물)',  value: 0.4,  unit: 'ppm', level: 'safe'    },
];
(function renderGasTable() {
  const tbody = document.getElementById('gasTableBody');
  if (!tbody) return;
  GAS_INIT_DATA.forEach(g => {
    const tr = document.createElement('tr');
    tr.className = `gas-row ${g.level}`;
    tr.innerHTML = `<td>${g.name}</td><td>${g.value}</td><td>${g.unit}</td>
      <td><span class="brisk ${g.level}">${levelLabel[g.level]}</span></td>`;
    tbody.appendChild(tr);
  });
})();


// ──────────────────────────────────────────────────────────
// Chart.js 실시간 차트 (패널 13, 15)
// ──────────────────────────────────────────────────────────
// MAX_POINTS / nowLabel / pushData → util.js 참조

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
        { label: '현재 농도 (ppm)',      data: [], borderColor: '#f59e0b', backgroundColor: 'rgba(245,158,11,0.12)', tension: 0.4, pointRadius: 2, fill: true  },
        { label: '예측 최대 농도 (ppm)', data: [], borderColor: '#ef4444', backgroundColor: 'transparent', borderDash: [5, 3], tension: 0.4, pointRadius: 2, fill: false },
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
    const current     = scaleState[key] ?? chart.scales.y.max;
    const factor      = direction > 0 ? 0.75 : 1.35;
    scaleState[key]   = Math.max(1, Math.round(current * factor));
    chart.options.scales.y.max = scaleState[key];
    if (labelEl) labelEl.textContent = scaleState[key].toLocaleString();
  }
  chart.update('none');
}

function initYScaleControls() {
  document.getElementById('gasZoomIn')   ?.addEventListener('click', () => adjustYScale('gas',   gasChart,    +1));
  document.getElementById('gasZoomOut')  ?.addEventListener('click', () => adjustYScale('gas',   gasChart,    -1));
  document.getElementById('gasReset')    ?.addEventListener('click', () => adjustYScale('gas',   gasChart,     0));
  document.getElementById('powerZoomIn') ?.addEventListener('click', () => adjustYScale('power', powerChart, +1));
  document.getElementById('powerZoomOut')?.addEventListener('click', () => adjustYScale('power', powerChart, -1));
  document.getElementById('powerReset')  ?.addEventListener('click', () => adjustYScale('power', powerChart,  0));
}


// ──────────────────────────────────────────────────────────
// WebSocket — FastAPI ws://127.0.0.1:8001/ws/sensors/
// 수신 페이로드 (fastapi-server/websocket.py 기준):
//   co, h2s, o2, level, total_power_mw, power_change_pct,
//   equipment[], ai_power_equipment, ai_eta_min,
//   ai_max_load_kw, ai_max_load_pct
// ──────────────────────────────────────────────────────────
function initWebSocket() {
  const wsStatusEl = document.getElementById('wsStatus');

  function setWsStatus(text, cls) {
    if (!wsStatusEl) return;
    wsStatusEl.textContent = text;
    wsStatusEl.className   = `ws-status${cls ? ' ' + cls : ''}`;
  }

  function connect() {
    let ws;
    try {
      ws = new WebSocket('ws://127.0.0.1:8001/ws/sensors/');
    } catch {
      setWsStatus('● 연결 불가', 'error');
      return;
    }

    ws.onopen = () => setWsStatus('● 실시간 연결', 'connected');

    ws.onmessage = (e) => {
      let data;
      try { data = JSON.parse(e.data); } catch { return; }

      // ── 패널 12: 유해가스 현황 테이블 ──────────────────
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

      // ── 패널 13: AI 예측 — CO ───────────────────────────
      const coRisk = data.co > 50;
      const aiGasName    = document.getElementById('aiGasName');
      const aiCurrentVal = document.getElementById('aiCurrentVal');
      const aiMaxVal     = document.getElementById('aiMaxVal');
      if (aiGasName)    aiGasName.className   = coRisk ? 'danger-text fw' : 'caution-text fw';
      if (aiCurrentVal) { aiCurrentVal.textContent = `${data.co} ppm`; aiCurrentVal.className = 'big ' + (coRisk ? 'danger-text' : 'caution-text'); }
      if (aiMaxVal)     aiMaxVal.textContent   = `${Math.round(data.co * 1.5)} ppm`;

      // ── 패널 14: 전력 현황 ──────────────────────────────
      const powerTotal     = document.getElementById('powerTotal');
      const powerChangePct = document.getElementById('powerChangePct');
      const powerTableBody = document.getElementById('powerTableBody');
      if (powerTotal && data.total_power_mw !== undefined)
        powerTotal.textContent = `${data.total_power_mw.toLocaleString()} MW`;
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

      // ── 패널 15: AI 예측 — 전력 ────────────────────────
      const aiPowerEquipName = document.getElementById('aiPowerEquipName');
      const aiPowerEta       = document.getElementById('aiPowerEta');
      const aiPowerMaxLoad   = document.getElementById('aiPowerMaxLoad');
      if (aiPowerEquipName && data.ai_power_equipment) aiPowerEquipName.textContent = data.ai_power_equipment;
      if (aiPowerEta       && data.ai_eta_min !== undefined) aiPowerEta.textContent = `${data.ai_eta_min} 분 뒤`;
      if (aiPowerMaxLoad   && data.ai_max_load_kw !== undefined)
        aiPowerMaxLoad.innerHTML = `${data.ai_max_load_kw.toLocaleString()} kW <span style="font-size:11px;font-weight:400;">(정상 대비 ${data.ai_max_load_pct}%)</span>`;

      // ── 차트 실시간 업데이트 ────────────────────────────
      const tick = nowLabel();
      if (gasChart)   pushData(gasChart,   tick, data.co, Math.round(data.co * 1.5));
      if (powerChart) pushData(powerChart, tick, data.ai_max_load_kw);

      // ── MN-02 맵 — 가스센서 A 실시간 반영 ──────────────
      MapPanel.updateGasSensorFromWS(data);

      // ── CM-07 — 위험 발생 시 알림 팝업 ─────────────────
      if (data.level === '위험') {
        AlarmPopup.show({
          alarm_level: 'danger',
          message:     `CO: ${data.co}ppm / H₂S: ${data.h2s}ppm / O₂: ${data.o2}%`,
          sensor_name: data.device_id,
          timestamp:   data.timestamp,
        });
      }
    };

    ws.onerror = () => setWsStatus('● 연결 오류', 'error');

    ws.onclose = () => {
      setWsStatus('● 연결 끊김', 'error');
      setTimeout(connect, 5000);   // 5초 후 재연결
    };
  }

  connect();
}


// ──────────────────────────────────────────────────────────
// CM-07 — 실시간 알림 팝업
// 출처: alarm_panel.html 인라인 스크립트
// WebSocket 수신 시 level === '위험' 이면 팝업 큐에 추가
// ──────────────────────────────────────────────────────────
const AlarmPopup = {
  queue:  [],
  isOpen: false,

  show(data) {
    this.queue.push(data);
    if (!this.isOpen) this._process();
  },

  _process() {
    if (this.queue.length === 0) { this.isOpen = false; return; }
    this.isOpen    = true;
    const data     = this.queue.shift();
    const isDanger = data.alarm_level === 'danger';
    const popup    = document.getElementById('alarm-popup');
    if (!popup) { this.isOpen = false; return; }

    const levelEl   = document.getElementById('alarm-popup-level');
    const msgEl     = document.getElementById('alarm-popup-message');
    const metaEl    = document.getElementById('alarm-popup-meta');

    levelEl.textContent  = isDanger ? '🔴 위험' : '🟡 주의';
    levelEl.style.color  = isDanger ? 'var(--danger)' : 'var(--caution)';
    popup.style.borderLeftColor = isDanger ? 'var(--danger)' : 'var(--caution)';
    msgEl.textContent    = data.message || '위험 이벤트가 발생했습니다.';

    const parts = [];
    if (data.sensor_name) parts.push(data.sensor_name);
    if (data.worker_name) parts.push(data.worker_name);
    if (data.timestamp)   parts.push(new Date(data.timestamp).toLocaleTimeString());
    metaEl.textContent = parts.join(' | ');

    popup.style.display = 'block';
    this._autoCloseTimer = setTimeout(() => this.close(), 10000);
  },

  close() {
    clearTimeout(this._autoCloseTimer);
    const popup = document.getElementById('alarm-popup');
    if (popup) popup.style.display = 'none';
    setTimeout(() => this._process(), 500);
  },

  init() {
    document.getElementById('alarm-popup-close')  ?.addEventListener('click', () => this.close());
    document.getElementById('alarm-popup-confirm') ?.addEventListener('click', () => this.close());
  },
};


// ──────────────────────────────────────────────────────────
// MN-04 — 작업자 현황 패널
// 출처: CJY.js
// user_type: 'admin' → D View(KPI 카드), 그 외 → B View(상태 바)
// ──────────────────────────────────────────────────────────
(function initMN04() {
  const POLL_MS            = 30_000;
  const API_MY_STATUS      = '/api/alarms/my-status/';
  const API_WORKER_SUMMARY = '/api/alarms/worker-summary/';

  const STATUS_CONFIG = {
    normal:  { left: '16%', color: '#2d9e75', label: '정상' },
    warning: { left: '50%', color: '#ef9f27', label: '경고' },
    danger:  { left: '84%', color: '#e24b4a', label: '위험' },
  };

  const viewWorker = document.getElementById('mn04-view-worker');
  const viewAdmin  = document.getElementById('mn04-view-admin');
  const elMarker      = document.getElementById('mn04-marker');
  const elStatusText  = document.getElementById('mn04-status-text');
  const elWorkerErr   = document.getElementById('mn04-worker-error');
  const elTotal       = document.getElementById('mn04-kpi-total');
  const elNormal      = document.getElementById('mn04-kpi-normal');
  const elWarning     = document.getElementById('mn04-kpi-warning');
  const elDanger      = document.getElementById('mn04-kpi-danger');
  const elRatioBar    = document.getElementById('mn04-ratio-bar');
  const elRatioNormal = document.getElementById('mn04-ratio-normal');
  const elRatioWarn   = document.getElementById('mn04-ratio-warning');
  const elRatioDanger = document.getElementById('mn04-ratio-danger');
  const elAdminErr    = document.getElementById('mn04-admin-error');

  function showErr(el, msg) { if (!el) return; el.textContent = msg; el.style.display = 'block'; }
  function clearErr(el)     { if (!el) return; el.textContent = '';  el.style.display = 'none'; }
  function setKpi(el, v)    { if (el) el.textContent = v; }

  function renderWorkerStatus(data) {
    clearErr(elWorkerErr);
    const cfg = STATUS_CONFIG[data.status || 'normal'] || STATUS_CONFIG.normal;
    if (elMarker)     { elMarker.style.left = cfg.left; elMarker.style.color = cfg.color; elMarker.style.display = 'block'; }
    if (elStatusText) { elStatusText.textContent = cfg.label; elStatusText.style.color = cfg.color; }
  }
  function renderWorkerError(msg) {
    if (elMarker) elMarker.style.display = 'none';
    if (elStatusText) elStatusText.textContent = '-';
    showErr(elWorkerErr, msg);
  }

  function renderAdminSummary(data) {
    clearErr(elAdminErr);
    const total = data.total_count ?? 0, normal = data.normal_count ?? 0,
          warning = data.warning_count ?? 0, danger = data.danger_count ?? 0;
    setKpi(elTotal, total); setKpi(elNormal, normal);
    setKpi(elWarning, warning); setKpi(elDanger, danger);
    if (!elRatioBar) return;
    if (total === 0) { elRatioBar.style.display = 'none'; return; }
    elRatioBar.style.display = 'flex';
    if (elRatioNormal) elRatioNormal.style.flex = normal;
    if (elRatioWarn)   elRatioWarn.style.flex   = warning;
    if (elRatioDanger) elRatioDanger.style.flex = danger;
  }
  function renderAdminError(msg) {
    setKpi(elTotal, '-'); setKpi(elNormal, '-'); setKpi(elWarning, '-'); setKpi(elDanger, '-');
    if (elRatioBar) elRatioBar.style.display = 'none';
    showErr(elAdminErr, msg);
  }

  async function fetchWorkerStatus() {
    try {
      const res = await fetch(API_MY_STATUS, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      renderWorkerStatus((await res.json()).data);
    } catch { renderWorkerError('데이터를 불러오지 못했습니다.'); }
  }

  async function fetchWorkerSummary() {
    try {
      const res = await fetch(API_WORKER_SUMMARY, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
      if (res.status === 403) { renderAdminError('접근 권한이 없습니다.'); return; }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      renderAdminSummary((await res.json()).data);
    } catch { renderAdminError('데이터를 불러오지 못했습니다.'); }
  }

  document.getElementById('mn04-btn-detail')?.addEventListener('click', () => { window.location.href = '/snb-09/'; });

  function init() {
    const isAdmin = (localStorage.getItem('user_type') || 'worker') === 'admin';
    if (isAdmin) {
      if (viewWorker) viewWorker.style.display = 'none';
      if (viewAdmin)  viewAdmin.style.display  = 'flex';
      fetchWorkerSummary();
      setInterval(fetchWorkerSummary, POLL_MS);
    } else {
      if (viewAdmin)  viewAdmin.style.display  = 'none';
      if (viewWorker) viewWorker.style.display = 'flex';
      fetchWorkerStatus();
      setInterval(fetchWorkerStatus, POLL_MS);
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();


// ──────────────────────────────────────────────────────────
// 앱 초기화
// ──────────────────────────────────────────────────────────
async function initApp() {
  if (!Auth.getAccessToken()) { Auth.redirectLogin(); return; }

  const user = await Auth.getMe();
  if (!user) {
    Header.renderUser(Auth.getUsername() || '-');
    Menu.showError();
  } else {
    Header.renderUser(user.username);
    Header.showAdminBtn(user.role);
    Menu.render(user.menu_tree);
  }

  SNB.init();
  Header.init();
  Header.updateLastUpdated();

  initCharts();
  MapPanel.init();
  initWebSocket();
  AlarmPopup.init();
}

initApp();
