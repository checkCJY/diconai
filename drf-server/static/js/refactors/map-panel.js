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
  workerMarkers: {},

  // 드로잉 관련 상태
  drawMode:     false,
  drawPoints:   [],
  drawMarkers:  [],
  drawPolyline: null,
  drawPolygon:  null,

  STATUS_COLOR: { normal: '#3fb950', caution: '#e3b341', danger: '#f85149' },
  ZONE_COLOR:   { danger: '#f85149', warning: '#e3b341', normal: '#3fb950' },

  riskColor(level)    { return [this.STATUS_COLOR.normal, this.STATUS_COLOR.caution, this.STATUS_COLOR.danger][level] ?? this.STATUS_COLOR.normal; },
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
    { id:1, name:'작업자 A', x:150, y:120, movement_status:'moving',     current_geofence:'위험구역 A', dx:4,  dy:2  },
    { id:2, name:'작업자 B', x:600, y:350, movement_status:'moving',     current_geofence:null,         dx:-3, dy:4  },
    { id:3, name:'작업자 C', x:950, y:200, movement_status:'stationary', current_geofence:'관리구역 C', dx:0,  dy:0  },
    { id:4, name:'작업자 D', x:350, y:480, movement_status:'moving',     current_geofence:null,         dx:5,  dy:-3 },
  ],

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

    await this._drawAll();
    this._initTabFilter();
    this._startWorkerAnimation();

    const role = Auth.getRole();
    if (role === 'admin') {
      document.getElementById('geofence-toolbar').style.display = 'flex';
      this._initDrawing();
    }
  },

  async _drawAll() {
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

    await this._loadGeofences();

    this.DUMMY_WORKERS.forEach(w => {
      const m = L.circleMarker([w.y, w.x], {
        radius: 8, fillColor: '#58a6ff', color: '#fff', weight: 2, fillOpacity: 1,
      }).bindPopup(this.workerPopupHtml(w), { maxWidth: 200 });
      m.addTo(this.layers.worker);
      this.workerMarkers[w.id] = { marker: m, data: w };
    });
  },

  async _loadGeofences() {
    try {
      const token = Auth.getAccessToken();
      const res = await fetch('/api/geofences/', {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const geofences = await res.json();
      this.layers.geofence.clearLayers();

      geofences.forEach(g => {
        const latlngs = g.polygon.map(([x, y]) => [y, x]);
        const color   = this.ZONE_COLOR[g.risk_level] || '#888';
        const layer   = L.polygon(latlngs, {
          color, fillColor: color, fillOpacity: 0.15, weight: 2
        });
        const popupContent = `
          <div class='popup-title'>🚧 ${g.name}</div>
          <div>위험도: ${g.risk_level}</div>
          <div>${g.description || ''}</div>
          <button
            onclick="MapPanel.deleteGeofence(${g.id})"
            style="margin-top:8px; background:#f85149; color:#fff; border:none; border-radius:4px; padding:4px 10px; cursor:pointer; font-size:12px;">
            🗑️ 삭제
          </button>
        `;
        layer.bindPopup(popupContent, { maxWidth: 220 }).addTo(this.layers.geofence);
      });

      console.log(`[MapPanel] 지오펜스 ${geofences.length}개 로드 완료`);
    } catch (err) {
      console.warn('[MapPanel] 지오펜스 로드 실패, 더미 데이터 사용:', err);
      this.DUMMY_GEOFENCES.forEach(g => {
        const latlngs = g.polygon.map(([x, y]) => [y, x]);
        const color   = this.ZONE_COLOR[g.zone_type] || '#888';
        L.polygon(latlngs, { color, fillColor: color, fillOpacity: 0.15, weight: 2 })
         .bindPopup(`<div class='popup-title'>🚧 ${g.name}</div>`)
         .addTo(this.layers.geofence);
      });
    }
  },

  async deleteGeofence(id) {
    if (!confirm('이 지오펜스를 삭제하시겠습니까?')) return;
    try {
      const token = Auth.getAccessToken();
      const res = await fetch(`/api/geofences/${id}/`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` },
      });
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
      if (this.drawPoints.length < 3) {
        alert('최소 3개 이상의 점을 찍어주세요.');
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

      if (this.drawPoints.length >= 3) {
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
        const token = Auth.getAccessToken();
        const res = await fetch('/api/geofences/', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
          },
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
