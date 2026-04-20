/* ==========================================================
   map-panel.js — MN-02 Leaflet 실시간 모니터링 맵
   출처: dashboard.js MapPanel 모듈
   의존: Leaflet (window.L), window.FACTORY_MAP_URL (템플릿 주입)
   ========================================================== */

'use strict';

// ──────────────────────────────────────────────────────────
// MN-02 — Leaflet 실시간 모니터링 맵
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

  // ── Leaflet 초기화 ──────────────────────────────────── (변경점  4/20)
async init() {
  if (!window.L || !document.getElementById('map')) return;

  this.map = L.map('map', {
    crs: L.CRS.Simple, minZoom: -2, maxZoom: 2,
    zoomControl: false, dragging: false,
    scrollWheelZoom: false, doubleClickZoom: false, touchZoom: false,
  });

  const bounds = [[0, 0], [600, 1300]];
  const mapUrl = window.FACTORY_MAP_URL || '';
  if (mapUrl) L.imageOverlay(mapUrl, bounds).addTo(this.map);
  this.map.fitBounds(bounds);

  this.layers = {
    gas:      L.layerGroup().addTo(this.map),
    power:    L.layerGroup().addTo(this.map),
    geofence: L.layerGroup().addTo(this.map),
    worker:   L.layerGroup().addTo(this.map),
  };

  await this._drawAll();       // ← await 추가
  this._initTabFilter();
  this._startWorkerAnimation();
},

async _drawAll() {
  // 가스센서 — 더미 유지 (변경점 4/20)
  this.DUMMY_GAS_SENSORS.forEach(s => {
    const m = L.circleMarker([s.y, s.x], {
      radius: 9, fillColor: this.riskColor(s.risk_level),
      color: '#fff', weight: 1.5, fillOpacity: 0.9,
    }).bindPopup(this.gasPopupHtml(s), { maxWidth: 220 });
    m.addTo(this.layers.gas);
    this.gasMarkers[s.device_id] = { marker: m, data: s };
  });

  // 전력 — 더미 유지
  this.DUMMY_POWER_DEVICES.forEach(d => {
    L.circleMarker([d.y, d.x], {
      radius: 9, fillColor: this.riskColor(d.risk_level),
      color: '#e3b341', weight: 2, fillOpacity: 0.85, dashArray: '4 2',
    }).bindPopup(this.powerPopupHtml(d), { maxWidth: 220 }).addTo(this.layers.power);
  });

  // 지오펜스 — API 연동으로 교체
  await this._loadGeofences();

  // 작업자 — 더미 유지
  this.DUMMY_WORKERS.forEach(w => {
    const m = L.circleMarker([w.y, w.x], {
      radius: 8, fillColor: '#58a6ff', color: '#fff', weight: 2, fillOpacity: 1,
    }).bindPopup(this.workerPopupHtml(w), { maxWidth: 200 });
    m.addTo(this.layers.worker);
    this.workerMarkers[w.id] = { marker: m, data: w };
  });
},

async _loadGeofences() { //변경점 (4/20)
  try {
    const token = Auth.getAccessToken();
    const res = await fetch('/api/geofences/', {
      headers: { 'Authorization': `Bearer ${token}` }
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const geofences = await res.json();

    // 기존 레이어 초기화
    this.layers.geofence.clearLayers();

    geofences.forEach(g => {
      const latlngs = g.polygon.map(([x, y]) => [y, x]);
      const color   = this.ZONE_COLOR[g.risk_level] || '#888';
      L.polygon(latlngs, {
        color, fillColor: color, fillOpacity: 0.15, weight: 2
      })
      .bindPopup(`
        <div class='popup-title'>🚧 ${g.name}</div>
        <div>위험도: ${g.risk_level}</div>
        <div>${g.description || ''}</div>
      `)
      .addTo(this.layers.geofence);
    });

    console.log(`[MapPanel] 지오펜스 ${geofences.length}개 로드 완료`);
  } catch (err) {
    console.warn('[MapPanel] 지오펜스 로드 실패, 더미 데이터 사용:', err);
    // API 실패 시 더미 데이터로 폴백
    this.DUMMY_GEOFENCES.forEach(g => {
      const latlngs = g.polygon.map(([x, y]) => [y, x]);
      const color   = this.ZONE_COLOR[g.zone_type] || '#888';
      L.polygon(latlngs, { color, fillColor: color, fillOpacity: 0.15, weight: 2 })
       .bindPopup(`<div class='popup-title'>🚧 ${g.name}</div>`)
       .addTo(this.layers.geofence);
    });
  }
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
