/* ==========================================================
   map-panel.js — MN-02 Leaflet 실시간 모니터링 맵
   출처: dashboard.js MapPanel 모듈
   의존: Leaflet (window.L), window.FACTORY_MAP_URL (템플릿 주입)
   ========================================================== */

'use strict';

const MapPanel = {
  map:         null,
  layers:      {},
  gasMarkers:    {},
  powerMarkers:  {},
  workerMarkers: {},

  SVG_BOUNDS:  [[0, 0], [600, 1300]],
  FIT_PADDING: [20, 20],
  // 지오펜스 경계 톨러런스 (SVG 좌표 단위) — 폴리곤 변에서 이 거리 이내의 센서도 inside로 인식
  GEOFENCE_TOLERANCE: 12,

  recenter() {
    if (this.map) this.map.fitBounds(this.SVG_BOUNDS, { padding: this.FIT_PADDING });
  },

  // 드로잉 관련 상태
  drawMode:     false,
  drawPoints:   [],
  drawMarkers:  [],
  drawPolyline: null,
  drawPolygon:  null,

  STATUS_COLOR: { normal: '#3fb950', caution: '#e3b341', danger: '#f85149' },
  ZONE_COLOR:   { danger: '#f85149', warning: '#e3b341', normal: '#3fb950' },

  // ── 위험도 레벨(0 정상·1 주의·2 위험)을 색상 코드로 변환한다. ──────
  riskColor(level)    { return [this.STATUS_COLOR.normal, this.STATUS_COLOR.caution, this.STATUS_COLOR.danger][level] ?? this.STATUS_COLOR.normal; },

  // SVG 커스텀 아이콘 생성
_createWorkerIcon(color) {
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="28" height="34" viewBox="0 0 28 34">
      <!-- 핀 모양 배경 -->
      <path d="M14 0 C6.268 0 0 6.268 0 14 C0 24.5 14 34 14 34 C14 34 28 24.5 28 14 C28 6.268 21.732 0 14 0Z"
            fill="${color}" stroke="#fff" stroke-width="1.5"/>
      <!-- 사람 아이콘 -->
      <circle cx="14" cy="10" r="4" fill="#fff"/>
      <path d="M6 24 C6 18 22 18 22 24" fill="#fff"/>
    </svg>`;
  return L.divIcon({
    html: svg,
    className: '',
    iconSize: [28, 34],
    iconAnchor: [14, 34],
    popupAnchor: [0, -34],
  });
},

_createGasIcon(color) {
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="30" height="30" viewBox="0 0 30 30">
      <!-- 육각형 배경 -->
      <polygon points="15,2 27,8.5 27,21.5 15,28 3,21.5 3,8.5"
               fill="${color}" stroke="#fff" stroke-width="1.5"/>
      <!-- 센서 물결 -->
      <path d="M9 15 Q12 11 15 15 Q18 19 21 15" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round"/>
      <circle cx="15" cy="15" r="2" fill="#fff"/>
    </svg>`;
  return L.divIcon({
    html: svg,
    className: '',
    iconSize: [30, 30],
    iconAnchor: [15, 15],
    popupAnchor: [0, -15],
  });
},

_createPowerIcon(color) {
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="30" height="30" viewBox="0 0 30 30">
      <!-- 다이아몬드 배경 -->
      <rect x="3" y="3" width="24" height="24" rx="4"
            fill="${color}" stroke="#fff" stroke-width="1.5"/>
      <!-- 번개 모양 -->
      <path d="M17 4 L10 16 L15 16 L13 26 L20 14 L15 14 Z"
            fill="#fff"/>
    </svg>`;
  return L.divIcon({
    html: svg,
    className: '',
    iconSize: [30, 30],
    iconAnchor: [15, 15],
    popupAnchor: [0, -15],
  });
},

  // ── 위험도 레벨(0·1·2)을 상태 문자열(normal·caution·danger)로 변환한다. ─
  levelToStatus(level){ return ['normal', 'caution', 'danger'][level] ?? 'normal'; },

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
  { id:1, name:'작업자 A', x:150, y:120, movement_status:'moving', current_geofence:null },
  { id:2, name:'작업자 B', x:600, y:350, movement_status:'moving', current_geofence:null },
  { id:3, name:'작업자 C', x:950, y:200, movement_status:'stationary', current_geofence:null },
  { id:4, name:'작업자 D', x:350, y:480, movement_status:'moving', current_geofence:null },
  ],

  gasPopupHtml(s) {
    const st    = this.levelToStatus(s.risk_level);
    const label = { normal:'정상', caution:'주의', danger:'위험' }[st];
    return `<div class='popup-title'>📡 ${s.name}</div>
      <div>ID: ${s.device_id}</div>
      <div>상태: <span class='popup-status-${st}'>${label}</span></div>
      <div>CO: ${s.co} ppm &nbsp; H2S: ${s.h2s} ppm &nbsp; O2: ${s.o2}%</div>`;
  },

  // 좌표가 polygon 내부인지 판별 (Ray Casting + 옵션 톨러런스)
  // tolerance > 0 이면 폴리곤 변에서 그 거리 이내도 inside로 인식 (경계 흔들림 방지)
  // 작업자 인식은 strict 유지 위해 tolerance 미지정 호출 (기본 0)
_pointInPolygon(x, y, polygon, tolerance = 0) {
  let inside = false;
  const n = polygon.length;
  let j = n - 1;
  for (let i = 0; i < n; i++) {
    const [xi, yi] = polygon[i];
    const [xj, yj] = polygon[j];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) {
      inside = !inside;
    }
    j = i;
  }
  if (inside) return true;
  if (tolerance <= 0) return false;
  for (let i = 0, k = n - 1; i < n; k = i, i++) {
    if (this._distanceToSegment(x, y, polygon[k][0], polygon[k][1], polygon[i][0], polygon[i][1]) <= tolerance) {
      return true;
    }
  }
  return false;
},

// 점(px,py)에서 선분(x1,y1)-(x2,y2)까지의 최단 거리
_distanceToSegment(px, py, x1, y1, x2, y2) {
  const dx = x2 - x1, dy = y2 - y1;
  if (dx === 0 && dy === 0) return Math.hypot(px - x1, py - y1);
  const t = Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)));
  return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
},

// 현재 로드된 지오펜스 목록 (저장용)
_geofences: [],
// id → Leaflet polygon layer 매핑 (지오펜스 색상 동적 갱신용)
_geofenceLayers: {},

// 데이터 흐름: 센서/장치 → 지오펜스 색상.
// 각 지오펜스에 대해 내부(톨러런스 포함) 장치를 모아 그 최댓값 위험도로 색상 결정.
// 내부에 장치가 하나도 없으면 어드민이 설정한 risk_level 베이스라인 유지.
_applyDeviceRiskToGeofences() {
  const allDevices = [
    ...Object.values(this.gasMarkers).map(({ data }) => data),
    ...Object.values(this.powerMarkers).map(({ data }) => data),
  ];

  this._geofences.forEach(g => {
    let maxRisk = -1;
    for (const d of allDevices) {
      if (this._pointInPolygon(d.x, d.y, g.polygon, this.GEOFENCE_TOLERANCE)) {
        const r = d.risk_level || 0;
        if (r > maxRisk) maxRisk = r;
      }
    }

    let color, effectiveRisk;
    if (maxRisk >= 0) {
      // 내부 장치 존재 → 최댓값 위험도로 색상 결정 (ZONE 키 체계: warning 사용)
      effectiveRisk = ['normal', 'warning', 'danger'][maxRisk];
      color = this.ZONE_COLOR[effectiveRisk] || this.STATUS_COLOR.normal;
    } else {
      // 내부 장치 없음 → 어드민 베이스라인
      effectiveRisk = g.risk_level;
      color = this.ZONE_COLOR[g.risk_level] || '#888';
    }

    const layer = this._geofenceLayers[g.id];
    if (layer && layer._currentColor !== color) {
      layer.setStyle({ color, fillColor: color });
      layer._currentColor = color;
    }
    // 작업자 색상/상태 산출에서 참조 — 동적 위험도 캐싱
    if (layer) layer._currentRiskLevel = effectiveRisk;
  });
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

  // ── Leaflet 지도를 초기화하고 마커·레이어·탭 필터·드로잉 기능을 등록한다. ─
  async init() {
    if (!window.L || !document.getElementById('map')) return;

    // minZoom을 임시로 넓게 풀어 fitBounds가 음수 줌까지 계산 가능하게 함
    // (CRS.Simple 기본 minZoom=0이라 컨테이너 < SVG일 때 fitBounds가 잠겨버림)
    // zoomSnap: 0 — 분수 줌을 허용해 fit이 정수로 스냅되며 과도하게 축소되는 것을 방지
    this.map = L.map('map', {
      crs: L.CRS.Simple, minZoom: -4, maxZoom: 2,
      zoomControl: false, dragging: true,
      scrollWheelZoom: true, doubleClickZoom: false, touchZoom: false,
      maxBoundsViscosity: 1.0, zoomSnap: 0,
    });

    const mapUrl = window.FACTORY_MAP_URL || '';
    if (mapUrl) L.imageOverlay(mapUrl, this.SVG_BOUNDS).addTo(this.map);

    // 컨테이너에 SVG를 패딩만큼 띄워 채우고, 그 줌 레벨을 minZoom으로 잠궈 빈 여백 노출 차단
    this.recenter();
    this.map.setMinZoom(this.map.getZoom());
    this.map.setMaxBounds(this.SVG_BOUNDS);

    this.layers = {
      gas:      L.layerGroup().addTo(this.map),
      power:    L.layerGroup().addTo(this.map),
      geofence: L.layerGroup().addTo(this.map),
      worker:   L.layerGroup().addTo(this.map),
    };

    await this._drawAll();
    this.setMarkersDisconnected();
    this._initTabFilter();
    this._startWorkerAnimation();

    const role = Auth.getRole();
    if (role === 'super_admin' || role === 'facility_admin') {
      document.getElementById('geofence-toolbar').style.display = 'flex';
      this._initDrawing();
    }
  },

  // ── 가스센서·전력설비·지오펜스·작업자 마커를 지도에 일괄 그린다. ──────
  async _drawAll() {
    await this._loadDevices();
    await this._loadGeofences();

    this.DUMMY_WORKERS.forEach(w => {
      const m = L.marker([w.y, w.x], {
        icon: this._createWorkerIcon('#58a6ff')
      }).bindPopup(this.workerPopupHtml(w), { maxWidth: 200 });
      m.addTo(this.layers.worker);
      this.workerMarkers[w.id] = { marker: m, data: w };
    });
  },

  // ── 가스센서·전력장치 위치를 DB API에서 로드한다. ─────────────────────
  async _loadDevices() {
    try {
      const res = await Auth.apiFetch('/api/map-editor/objects/');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      data.gas_sensors.forEach(s => {
        const sensorData = {
          id: s.id, name: s.device_name, device_id: s.code,
          x: s.x, y: s.y, risk_level: 0, co: 0, h2s: 0, o2: 0,
        };
        const m = L.marker([s.y, s.x], {
          icon: this._createGasIcon(this.riskColor(0)),
        }).bindPopup(this.gasPopupHtml(sensorData), { maxWidth: 220 });
        m.addTo(this.layers.gas);
        this.gasMarkers[s.code] = { marker: m, data: sensorData };
      });

      data.power_devices.forEach(d => {
        const deviceData = {
          id: d.id, name: d.device_name, device_id: d.code,
          x: d.x, y: d.y, risk_level: 0,
        };
        const m = L.marker([d.y, d.x], {
          icon: this._createPowerIcon(this.riskColor(0)),
        }).bindPopup(this.powerPopupHtml(deviceData), { maxWidth: 220 });
        m.addTo(this.layers.power);
        this.powerMarkers[d.code] = { marker: m, data: deviceData };
      });

      console.log(`[MapPanel] 가스센서 ${data.gas_sensors.length}개, 전력장치 ${data.power_devices.length}개 로드`);
    } catch (err) {
      console.warn('[MapPanel] 장치 API 실패, 더미 데이터 사용:', err);
      this._drawDummyDevices();
    }
  },

  // ── API 실패 시 더미 데이터로 폴백 ───────────────────────────────────
  _drawDummyDevices() {
    this.DUMMY_GAS_SENSORS.forEach(s => {
      const m = L.marker([s.y, s.x], {
        icon: this._createGasIcon(this.riskColor(s.risk_level)),
      }).bindPopup(this.gasPopupHtml(s), { maxWidth: 220 });
      m.addTo(this.layers.gas);
      this.gasMarkers[s.device_id] = { marker: m, data: s };
    });
    this.DUMMY_POWER_DEVICES.forEach(d => {
      const m = L.marker([d.y, d.x], {
        icon: this._createPowerIcon(this.riskColor(d.risk_level)),
      }).bindPopup(this.powerPopupHtml(d), { maxWidth: 220 });
      m.addTo(this.layers.power);
      this.powerMarkers[d.device_id] = { marker: m, data: d };
    });
  },

  async _loadGeofences() {
    try {
      const res = await Auth.apiFetch('/api/geofences/');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const geofences = await res.json();
      this._geofences = geofences;
      this._geofenceLayers = {};
      this.layers.geofence.clearLayers();

      const role    = Auth.getRole();
      const isAdmin = role === 'super_admin' || role === 'facility_admin';

      geofences.forEach(g => {
        const latlngs = g.polygon.map(([x, y]) => [y, x]);
        const color   = this.ZONE_COLOR[g.risk_level] || '#888';
        const layer   = L.polygon(latlngs, {
          color, fillColor: color, fillOpacity: 0.15, weight: 2
        });
        layer._currentColor = color;
        const deleteBtn = isAdmin ? `
          <button
            onclick="MapPanel.deleteGeofence(${g.id})"
            style="margin-top:8px; background:#f85149; color:#fff; border:none; border-radius:4px; padding:4px 10px; cursor:pointer; font-size:12px;">
            🗑️ 삭제
          </button>` : '';
        const popupContent = `
          <div class='popup-title'>🚧 ${g.name}</div>
          <div>위험도: ${g.risk_level}</div>
          <div>${g.description || ''}</div>
          ${deleteBtn}
        `;
        layer.bindPopup(popupContent, { maxWidth: 220 }).addTo(this.layers.geofence);
        this._geofenceLayers[g.id] = layer;
      });

      console.log(`[MapPanel] 지오펜스 ${geofences.length}개 로드 완료`);
    } catch (err) {
      console.warn('[MapPanel] 지오펜스 로드 실패, 더미 데이터 사용:', err);
      this._geofences = this.DUMMY_GEOFENCES.map((g, i) => ({
        id: `dummy-${i}`, ...g, risk_level: g.zone_type,
      }));
      this._geofenceLayers = {};
      this._geofences.forEach(g => {
        const latlngs = g.polygon.map(([x, y]) => [y, x]);
        const color   = this.ZONE_COLOR[g.risk_level] || '#888';
        const layer = L.polygon(latlngs, { color, fillColor: color, fillOpacity: 0.15, weight: 2 })
          .bindPopup(`<div class='popup-title'>🚧 ${g.name}</div>`);
        layer._currentColor = color;
        layer.addTo(this.layers.geofence);
        this._geofenceLayers[g.id] = layer;
      });
    }
    this._applyDeviceRiskToGeofences();
  },

  async deleteGeofence(id) {
    if (!confirm('이 지오펜스를 삭제하시겠습니까?')) return;
    try {
      const res = await Auth.apiFetch(`/api/geofences/${id}/`, { method: 'DELETE' });
      if (res.status === 204) {
        this.map.closePopup();
        await this._loadGeofences();
        console.log(`[MapPanel] 지오펜스 ${id} 삭제 완료`);
      } else {
        alert('삭제에 실패했습니다.');
      }
    } catch (err) {
      console.error('[MapPanel] 삭제 실패:', err);
      alert('삭제에 실패했습니다.');
    }
  },

  _initDrawing() {
    const btnDraw    = document.getElementById('btn-draw-geofence');
    const btnDone    = document.getElementById('btn-draw-done');
    const btnCancel  = document.getElementById('btn-draw-cancel');
    const btnSave    = document.getElementById('btn-geofence-save');
    const btnDiscard = document.getElementById('btn-geofence-discard');

    btnDraw.addEventListener('click', () => {
      this.drawMode   = true;
      this.drawPoints = [];
      btnDraw.style.display   = 'none';
      btnDone.style.display   = 'block';
      btnCancel.style.display = 'block';
      this.map.getContainer().style.cursor = 'crosshair';
    });

    btnDone.addEventListener('click', () => {
      if (this.drawPoints.length < 4) {
        alert('최소 4개 이상의 점을 찍어주세요 (사각형 이상).');
        return;
      }
      document.getElementById('geofence-modal').style.display = 'flex';
    });

    btnCancel.addEventListener('click', () => {
      this._resetDraw();
    });

    this.map.on('click', (e) => {
      if (!this.drawMode) return;
      const { lat, lng } = e.latlng;
      this.drawPoints.push([lng, lat]);

      const marker = L.circleMarker([lat, lng], {
        radius: 5, fillColor: '#1f6feb',
        color: '#fff', weight: 1.5, fillOpacity: 1,
      }).addTo(this.map);
      this.drawMarkers.push(marker);

      if (this.drawPolyline) this.map.removeLayer(this.drawPolyline);
      const latlngs = this.drawPoints.map(([x, y]) => [y, x]);
      this.drawPolyline = L.polyline(latlngs, {
        color: '#1f6feb', weight: 2, dashArray: '5 5'
      }).addTo(this.map);

      if (this.drawPoints.length >= 4) {
        if (this.drawPolygon) this.map.removeLayer(this.drawPolygon);
        this.drawPolygon = L.polygon(latlngs, {
          color: '#1f6feb', fillColor: '#1f6feb', fillOpacity: 0.1, weight: 2
        }).addTo(this.map);
      }
    });

    btnSave.addEventListener('click', async () => {
      const name      = document.getElementById('geofence-name').value.trim();
      const riskLevel = document.getElementById('geofence-risk').value;
      const desc      = document.getElementById('geofence-desc').value.trim();

      if (!name) { alert('구역 이름을 입력해주세요.'); return; }

      try {
        const res = await Auth.apiFetch('/api/geofences/', {
          method: 'POST',
          body: JSON.stringify({
            facility: 1,
            name,
            polygon: this.drawPoints,
            risk_level: riskLevel,
            description: desc,
          }),
        });

        if (!res.ok) throw new Error(`HTTP ${res.status}`);

        document.getElementById('geofence-modal').style.display = 'none';
        this._resetDraw();
        await this._loadGeofences();
        console.log('[MapPanel] 지오펜스 저장 완료');

      } catch (err) {
        console.error('[MapPanel] 저장 실패:', err);
        alert('저장에 실패했습니다.');
      }
    });

    btnDiscard.addEventListener('click', () => {
      document.getElementById('geofence-modal').style.display = 'none';
      this._resetDraw();
    });
  },

  _resetDraw() {
    this.drawMode   = false;
    this.drawPoints = [];

    this.drawMarkers.forEach(m => this.map.removeLayer(m));
    this.drawMarkers = [];
    if (this.drawPolyline) { this.map.removeLayer(this.drawPolyline); this.drawPolyline = null; }
    if (this.drawPolygon)  { this.map.removeLayer(this.drawPolygon);  this.drawPolygon  = null; }

    document.getElementById('btn-draw-geofence').style.display = 'block';
    document.getElementById('btn-draw-done').style.display     = 'none';
    document.getElementById('btn-draw-cancel').style.display   = 'none';
    this.map.getContainer().style.cursor = '';

    document.getElementById('geofence-name').value = '';
    document.getElementById('geofence-risk').value = 'danger';
    document.getElementById('geofence-desc').value = '';
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

  _startWorkerAnimation() {},

  // 통신 장애 시 모든 작업자·가스 마커를 반투명으로 전환한다.
  setMarkersDisconnected() {
    Object.values(this.workerMarkers).forEach(({ marker }) => marker.setOpacity(0.5));
    Object.values(this.gasMarkers).forEach(({ marker }) => marker.setOpacity(0.5));
  },

  // 연결 복구 시 마커 투명도를 원래대로 복원한다.
  setMarkersConnected() {
    Object.values(this.workerMarkers).forEach(({ marker }) => marker.setOpacity(1));
    Object.values(this.gasMarkers).forEach(({ marker }) => marker.setOpacity(1));
  },

  // 가스 9종(co, h2s, co2, o2, no2, so2, o3, nh3, voc) 중 최댓값 위험도를 산출 후
  // 모든 가스 마커에 동일하게 적용한다 (WS 페이로드는 사이트 전체 합산 1세트).
  updateGasSensorFromWS(wsData) {
    let worstLevel = 0;
    Object.keys(wsData).forEach(k => {
      if (!k.endsWith('_risk')) return;
      const r = wsData[k];
      if (r === 'danger')       worstLevel = Math.max(worstLevel, 2);
      else if (r === 'warning') worstLevel = Math.max(worstLevel, 1);
    });

    let changed = false;
    Object.values(this.gasMarkers).forEach(({ marker, data }) => {
      if (data.risk_level !== worstLevel) {
        marker.setIcon(this._createGasIcon(this.riskColor(worstLevel)));
        data.risk_level = worstLevel;
        changed = true;
      }
      data.co  = wsData.co;
      data.h2s = wsData.h2s;
      data.o2  = wsData.o2;
      if (marker.isPopupOpen()) marker.setPopupContent(this.gasPopupHtml(data));
    });
    if (changed) this._applyDeviceRiskToGeofences();
  },

  // WS equipment 배열의 risk_level('normal'/'warning'/'danger')을 매핑해 전력 마커 색상 갱신.
  // 이름 매칭이 되면 개별 설비 위험도 사용, 안 되면 전체 설비 최댓값을 폴백으로 모든 마커에 적용
  // (지도 위 전력 마커명과 WS 설비명이 다를 수 있어 폴백 필요 — 가스 패턴과 동일).
  updatePowerDevicesFromWS(equipment) {
    if (!equipment || !equipment.length) return;
    const RISK_TO_LEVEL = { normal: 0, warning: 1, danger: 2 };

    let worstLevel = 0;
    equipment.forEach(eq => {
      worstLevel = Math.max(worstLevel, RISK_TO_LEVEL[eq.risk_level] ?? 0);
    });

    let changed = false;
    Object.values(this.powerMarkers).forEach(({ marker, data }) => {
      const eq = equipment.find(e => e.name === data.name);
      const newLevel = eq ? (RISK_TO_LEVEL[eq.risk_level] ?? 0) : worstLevel;

      if (data.risk_level !== newLevel) {
        marker.setIcon(this._createPowerIcon(this.riskColor(newLevel)));
        data.risk_level = newLevel;
        changed = true;
      }
      if (marker.isPopupOpen()) marker.setPopupContent(this.powerPopupHtml(data));
    });
    if (changed) this._applyDeviceRiskToGeofences();
  },

  updateWorkerPositions(positions) {
    // Array와 {worker_id: {...}} 객체 모두 허용
    const posArray = Array.isArray(positions)
      ? positions
      : Object.entries(positions).map(([id, p]) => ({ worker_id: parseInt(id), ...p }));

    const statuses = {};
    posArray.forEach(w => {
      // 지오펜스 판정 — 마커 유무와 무관하게 모든 작업자에 대해 실행
      let inGeofence = null;
      for (const g of this._geofences) {
        if (this._pointInPolygon(w.x, w.y, g.polygon)) {
          inGeofence = g;
          break;
        }
      }
      // 지오펜스의 동적 효과 위험도(센서 반영)를 우선, 없으면 어드민 베이스라인
      const layer = inGeofence ? this._geofenceLayers[inGeofence.id] : null;
      const effectiveRisk = layer?._currentRiskLevel || inGeofence?.risk_level || 'normal';

      statuses[w.worker_id] = {
        status: inGeofence ? effectiveRisk : 'normal',
        geofence_name: inGeofence ? inGeofence.name : null,
        worker_name: w.worker_name || String(w.worker_id),
      };

      // 맵 마커 갱신 (마커가 있는 작업자만)
      const entry = this.workerMarkers[w.worker_id];
      if (!entry) return;

      entry.marker.setLatLng([w.y, w.x]);
      entry.data.x = w.x;
      entry.data.y = w.y;
      entry.data.movement_status = w.movement_status;

      const newColor = inGeofence
        ? (this.ZONE_COLOR[effectiveRisk] || '#f85149')
        : '#58a6ff';
      // 색이 바뀔 때만 setIcon
      if (entry.data._iconColor !== newColor) {
        entry.marker.setIcon(this._createWorkerIcon(newColor));
        entry.data._iconColor = newColor;
      }
      entry.data.current_geofence = inGeofence ? inGeofence.name : null;

      if (entry.marker.isPopupOpen()) {
        entry.marker.setPopupContent(this.workerPopupHtml(entry.data));
      }
    });

    // 작업자 현황 패널에 지오펜스 기반 실시간 상태 전달
    document.dispatchEvent(new CustomEvent('workerStatusComputed', { detail: statuses }));
  },
};
