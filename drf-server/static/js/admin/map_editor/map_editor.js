'use strict';
/* ==========================================================
   map_editor.js — 지도 편집 관리 인터랙티브 에디터
   의존: Leaflet, auth.js
   ========================================================== */

// ── 상수 ────────────────────────────────────────────────────
const MAP_BOUNDS   = [[0, 0], [600, 1300]];
const API_OBJECTS  = '/api/map-editor/objects/';
const API_SAVE     = '/api/map-editor/save/';
const RISK_COLOR   = { danger: '#f85149', warning: '#e3b341', normal: '#3fb950' };
const TYPE_LABEL   = {
  facility: '설비', gas_sensor: '유해가스 센서',
  power_device: '스마트 전력 시스템', position_node: '위치 노드', geofence: '위험 구역',
};

// ── 전역 상태 ────────────────────────────────────────────────
let _map, _layers;
let _allObjects   = [];          // 전체 객체 원본
let _dirtySet     = new Set();   // 변경된 객체 id 추적 (type:id)
let _pendingGeofences = [];      // 신규/수정 지오펜스
let _deletedGeofences = new Set();

// 이성현 작업
// 설비 크기 조정 핸들 상태
let _resizeHandles     = [];
let _resizeMapHandlers = null;
// 이성현 작업 — 삭제: pane 방식 제거 (공장 이미지 위에 렌더링 불가 문제)
// let _geofenceRenderer = null;

// 이성현 작업
// 객체 선택 상태 (불투명화용)
let _selectedKey = null;

// 이성현 작업 — 위험구역 편집 핸들/이벤트 상태
let _geofenceEditHandles    = [];
let _geofenceEditMapHandlers = null;
let _pendingDeleteGeofenceId = null;

// 그리기 상태
let _drawMode     = null;        // null | { shape, risk, name }
let _drawPoints   = [];
let _drawMarkers  = [];
let _drawPolyline = null;
let _drawPolygon  = null;
let _drawCircle   = null;
let _drawCenter   = null;

// 레이어 맵 (type:id → L.layer)
let _layerMap     = {};

// 필터 상태
let _tabFilter    = 'all';       // all | placed | unplaced
let _typeFilter   = 'all';
let _searchQuery  = '';

// ── 초기화 ────────────────────────────────────────────────────
let _accessGranted = false;
document.addEventListener('DOMContentLoaded', async () => {
  if (!await AdminAccess.check()) return;
  _accessGranted = true;
  _initMap();
  _initControls();
  _loadObjects();
});

function _initMap() {
  _map = L.map('meMap', {
    crs: L.CRS.Simple, minZoom: -3, maxZoom: 3,
    zoomControl: false, doubleClickZoom: false,
  });

  const mapUrl = window.FACTORY_MAP_URL || '';
  if (mapUrl) L.imageOverlay(mapUrl, MAP_BOUNDS).addTo(_map);
  _map.fitBounds(MAP_BOUNDS);

  // 이성현 작업 — pane 방식 제거: 지오펜스를 geofences 레이어그룹에 먼저 추가해 SVG 스택 바닥에 배치
  // (지오펜스 먼저 addTo → 센서/설비가 위에 쌓여 클릭 이벤트 자연히 센서가 잡힘)
  _layers = {
    geofence:      L.layerGroup().addTo(_map),
    facility:      L.layerGroup().addTo(_map),
    gas_sensor:    L.layerGroup().addTo(_map),
    power_device:  L.layerGroup().addTo(_map),
    position_node: L.layerGroup().addTo(_map),
  };

  // 지도 클릭 → 그리기 모드 처리
  _map.on('click', _onMapClick);
  _map.on('mousemove', _onMapMouseMove);
}

// ── 컨트롤 이벤트 바인딩 ────────────────────────────────────
function _initControls() {
  // 저장/되돌리기
  document.getElementById('btnSaveAll').addEventListener('click', () => _showModal('saveConfirmModal'));
  document.getElementById('btnSaveConfirm').addEventListener('click', _saveAll);
  document.getElementById('btnSaveCancel').addEventListener('click', () => _hideModal('saveConfirmModal'));
  document.getElementById('btnResetAll').addEventListener('click', () => _showModal('resetConfirmModal'));
  document.getElementById('btnResetConfirm').addEventListener('click', _resetAll);
  document.getElementById('btnResetCancel').addEventListener('click', () => _hideModal('resetConfirmModal'));
  // 이성현 작업
  document.getElementById('btnSaveCompleteConfirm').addEventListener('click', () => { _hideModal('saveCompleteModal'); _loadObjects(); });
  // 이성현 작업 — 위험구역 삭제 확인 모달
  document.getElementById('btnGeofenceDeleteCancel').addEventListener('click', () => { _pendingDeleteGeofenceId = null; _hideModal('geofenceDeleteModal'); });
  document.getElementById('btnGeofenceDeleteConfirm').addEventListener('click', () => MapEditor.doDeleteGeofence());

  // 위험구역 추가
  document.getElementById('btnAddGeofence').addEventListener('click', _openGeofenceModal);
  document.getElementById('btnGeofenceModalCancel').addEventListener('click', _closeGeofenceModal);
  document.getElementById('btnStartDraw').addEventListener('click', _startDraw);
  document.getElementById('btnCancelDraw').addEventListener('click', _cancelDraw);
  document.getElementById('btnFinishDraw').addEventListener('click', () => {
    if (_drawPoints.length < 3) { alert('최소 3개 이상의 꼭짓점이 필요합니다.'); return; }
    _finishPolygonDraw();
  });

  // 위험구역 모달 토글
  document.querySelectorAll('[data-risk]').forEach(btn => {
    btn.addEventListener('click', function() {
      document.querySelectorAll('[data-risk]').forEach(b => b.classList.remove('active'));
      this.classList.add('active');
    });
  });
  document.querySelectorAll('[data-shape]').forEach(btn => {
    btn.addEventListener('click', function() {
      document.querySelectorAll('[data-shape]').forEach(b => b.classList.remove('active'));
      this.classList.add('active');
    });
  });

  // 줌 컨트롤
  document.getElementById('btnZoomIn').addEventListener('click', () => _map.zoomIn());
  document.getElementById('btnZoomOut').addEventListener('click', () => _map.zoomOut());
  document.getElementById('btnFitAll').addEventListener('click', () => _map.fitBounds(MAP_BOUNDS));

  // 사이드바 접기
  document.getElementById('btnCollapseSidebar').addEventListener('click', () => {
    const sb = document.getElementById('meSidebar');
    sb.classList.toggle('collapsed');
    document.getElementById('btnCollapseSidebar').textContent = sb.classList.contains('collapsed') ? '〉' : '〈';
  });

  // 검색
  document.getElementById('btnSearch').addEventListener('click', _applyFilter);
  document.getElementById('searchInput').addEventListener('keydown', e => { if (e.key === 'Enter') _applyFilter(); });

  // 공장 필터
  document.getElementById('facilitySelect').addEventListener('change', _applyFilter);

  // 배치 상태 탭
  document.querySelectorAll('.me-tab').forEach(btn => {
    btn.addEventListener('click', function() {
      document.querySelectorAll('.me-tab').forEach(b => b.classList.remove('active'));
      this.classList.add('active');
      _tabFilter = this.dataset.tab;
      _renderList();
    });
  });

  // 타입 탭
  document.querySelectorAll('.me-type').forEach(btn => {
    btn.addEventListener('click', function() {
      document.querySelectorAll('.me-type').forEach(b => b.classList.remove('active'));
      this.classList.add('active');
      _typeFilter = this.dataset.type;
      _renderList();
    });
  });

  // 지도 레이어 탭
  document.querySelectorAll('.me-map-tab').forEach(btn => {
    btn.addEventListener('click', function() {
      document.querySelectorAll('.me-map-tab').forEach(b => b.classList.remove('active'));
      this.classList.add('active');
      const layer = this.dataset.layer;
      Object.entries(_layers).forEach(([name, lg]) => {
        if (layer === 'all' || name === layer) _map.addLayer(lg);
        else _map.removeLayer(lg);
      });
    });
  });
}

// ── 데이터 로드 ──────────────────────────────────────────────
async function _loadObjects() {
  const facilityId = document.getElementById('facilitySelect').value;
  const url = API_OBJECTS + (facilityId ? `?facility_id=${facilityId}` : '');

  try {
    const res = await Auth.apiFetch(url);
    const data = await res.json();

    // 이성현 작업 — geofences 먼저: SVG 렌더링 순서상 바닥에 깔려 센서/설비가 위에서 클릭됨
    _allObjects = [
      ...data.geofences.map(o => ({ ...o, _objType: 'geofence' })),
      ...data.facilities.map(o => ({ ...o, _objType: 'facility' })),
      ...data.gas_sensors.map(o => ({ ...o, _objType: 'gas_sensor' })),
      ...data.power_devices.map(o => ({ ...o, _objType: 'power_device' })),
      ...data.position_nodes.map(o => ({ ...o, _objType: 'position_node' })),
    ];

    _populateFacilitySelect(data.facilities);
    _renderAll();
  } catch (e) {
    console.error('[MapEditor] 객체 로드 실패', e);
  }
}

// 이성현 작업
function _populateFacilitySelect(facilities) {
  const sel = document.getElementById('facilitySelect');
  const prevValue = sel.value;
  sel.innerHTML = '';
  facilities.forEach(f => {
    const opt = document.createElement('option');
    opt.value = f.id;
    opt.textContent = f.name || f.code;
    sel.appendChild(opt);
  });
  if (prevValue) sel.value = prevValue;
}

// ── 렌더링 ───────────────────────────────────────────────────
function _renderAll() {
  _clearLayers();
  _allObjects.forEach(obj => _renderObject(obj));
  _renderList();
}

function _clearLayers() {
  Object.values(_layers).forEach(lg => lg.clearLayers());
  _layerMap = {};
}

function _renderObject(obj) {
  const type = obj._objType || obj.type;
  switch (type) {
    case 'facility':      _renderFacility(obj); break;
    case 'gas_sensor':    _renderDevice(obj, '#f85149', '가스'); break;
    case 'power_device':  _renderDevice(obj, '#e3b341', '전력'); break;
    case 'position_node': _renderDevice(obj, '#3fb950', '노드'); break;
    case 'geofence':      _renderGeofence(obj); break;
  }
}

function _renderFacility(obj) {
  if (obj.map_x == null) return;
  const x = obj.map_x, y = obj.map_y;
  const w = obj.map_width || 200, h = obj.map_height || 120;
  const bounds = [[y, x], [y + h, x + w]];
  const rect = L.rectangle(bounds, {
    color: '#58a6ff', fillColor: '#58a6ff', fillOpacity: 0.08, weight: 2,
    dashArray: null,
  });
  rect.bindPopup(_facilityPopupHtml(obj));
  rect.addTo(_layers.facility);
  // 이성현 작업 — 클릭이 맵으로 전파되면 _clearSelection 즉시 호출되므로 차단
  rect.on('click', (e) => { L.DomEvent.stopPropagation(e); _selectObject(obj); });
  // 드래그
  _makeDraggableRect(rect, obj);
  _layerMap[`facility:${obj.id}`] = rect;
}

// 이성현 작업
function _renderDevice(obj, color, _label) {
  if (!obj.placed) return;
  const x = obj.x ?? 0, y = obj.y ?? 0;
  const marker = L.circleMarker([y, x], {
    radius: 8, fillColor: color, color: '#fff',
    weight: 2, fillOpacity: 0.9,
  });
  marker.bindPopup(_devicePopupHtml(obj));
  marker.addTo(_layers[obj._objType]);
  // 이성현 작업 — 클릭 전파 차단
  marker.on('click', (e) => { L.DomEvent.stopPropagation(e); _selectObject(obj); });
  _makeDraggableMarker(marker, obj);
  _layerMap[`${obj._objType}:${obj.id}`] = marker;
}

function _renderGeofence(obj) {
  let layer;
  // 이성현 작업 — pane 제거: 기본 렌더러 사용, _allObjects에서 geofences를 먼저 처리하므로 SVG 바닥에 배치됨
  const geofenceStyle = {
    color: RISK_COLOR[obj.risk_level] || '#888',
    fillColor: RISK_COLOR[obj.risk_level] || '#888',
    fillOpacity: 0.15, weight: 2,
  };
  if (obj.shape_type === 'circle' && obj.circle_cx != null) {
    layer = L.circle([obj.circle_cy, obj.circle_cx], {
      radius: obj.circle_radius, ...geofenceStyle,
    });
  } else {
    const latlngs = (obj.polygon || []).map(([px, py]) => [py, px]);
    if (latlngs.length < 3) return;
    layer = L.polygon(latlngs, geofenceStyle);
  }
  layer.bindPopup(_geofencePopupHtml(obj));
  layer.addTo(_layers.geofence);
  // 이성현 작업 — 클릭 전파 차단
  layer.on('click', (e) => { L.DomEvent.stopPropagation(e); _selectObject(obj); });
  // 이성현 작업 — 위험구역 위치 이동 드래그
  _makeGeofenceDraggable(layer, obj);
  _layerMap[`geofence:${obj.id}`] = layer;
}

// ── 팝업 HTML ────────────────────────────────────────────────
function _facilityPopupHtml(obj) {
  const code = obj.code || `FAC-${obj.id}`;
  const x = obj.map_x?.toFixed(0) ?? '?', y = obj.map_y?.toFixed(0) ?? '?';
  const w = obj.map_width?.toFixed(0) ?? '?', h = obj.map_height?.toFixed(0) ?? '?';
  return `<div class="me-popup-title">설비 ${code}</div>
    <div class="me-popup-row">현재 좌표: X ${x} / Y ${y}</div>
    <div class="me-popup-row">가로 ${w}px / 세로 ${h}px</div>
    <div class="me-popup-actions">
      <button class="btn-popup-edit" onclick="MapEditor.startEditFacility(${obj.id})">편집</button>
    </div>`;
}

function _devicePopupHtml(obj) {
  const code = obj.code || obj.device_name;
  const x = (obj.x ?? 0).toFixed(0), y = (obj.y ?? 0).toFixed(0);
  const typeLabel = TYPE_LABEL[obj._objType] || obj._objType;
  return `<div class="me-popup-title">${typeLabel} ${code}</div>
    <div class="me-popup-row">${obj.device_name || ''}</div>
    <div class="me-popup-row">현재 좌표: X ${x} / Y ${y}</div>
    <div class="me-popup-actions">
      <button class="btn-popup-cancel" onclick="">드래그로 이동</button>
    </div>`;
}

// 이성현 작업
function _geofencePopupHtml(obj) {
  const riskLabel = { danger: '위험', warning: '주의', normal: '정상' }[obj.risk_level] || obj.risk_level;
  const shape = obj.shape_type === 'circle' ? '원형' : '폴리곤';
  const editLabel = obj.shape_type === 'circle' ? '크기 편집' : '편집';
  return `<div class="me-popup-title">위험구역 ${obj.name}</div>
    <div class="me-popup-row">위험도: ${riskLabel} | ${shape}</div>
    <div class="me-popup-actions">
      <button class="btn-popup-edit" onclick="MapEditor.editGeofence(${obj.id})">${editLabel}</button>
      <button class="btn-popup-delete" onclick="MapEditor.confirmDeleteGeofence(${obj.id})">삭제</button>
    </div>`;
}

// 이성현 작업 — 꼭짓점/반경 편집 중 팝업
function _geofenceEditingPopupHtml(obj) {
  return `<div class="me-popup-title">위험구역 편집 중</div>
    <div class="me-popup-actions">
      <button class="btn-popup-edit" onclick="MapEditor.finishGeofenceEdit(${obj.id})">완료</button>
    </div>`;
}

// ── 드래그 처리 ──────────────────────────────────────────────
function _makeDraggableMarker(marker, obj) {
  let dragging = false, startLatlng, startPos;

  marker.on('mousedown', (e) => {
    dragging = true;
    startLatlng = e.latlng;
    startPos = { x: obj.x, y: obj.y };
    _map.dragging.disable();
    L.DomEvent.stop(e);
  });

  _map.on('mousemove', (e) => {
    if (!dragging) return;
    const dx = e.latlng.lng - startLatlng.lng;
    const dy = e.latlng.lat - startLatlng.lat;
    const nx = Math.max(0, Math.min(1290, startPos.x + dx));
    const ny = Math.max(0, Math.min(590,  startPos.y + dy));
    marker.setLatLng([ny, nx]);
    obj.x = nx; obj.y = ny;
  });

  _map.on('mouseup', () => {
    if (!dragging) return;
    dragging = false;
    _map.dragging.enable();
    _markDirty(obj._objType, obj.id);
    marker.setPopupContent(_devicePopupHtml(obj));
  });
}

function _makeDraggableRect(rect, obj) {
  let dragging = false, startLatlng, startPos;

  rect.on('mousedown', (e) => {
    dragging = true;
    startLatlng = e.latlng;
    startPos = { x: obj.map_x, y: obj.map_y };
    _map.dragging.disable();
    L.DomEvent.stop(e);
  });

  _map.on('mousemove', (e) => {
    if (!dragging) return;
    const dx = e.latlng.lng - startLatlng.lng;
    const dy = e.latlng.lat - startLatlng.lat;
    const nx = Math.max(0, startPos.x + dx);
    const ny = Math.max(0, startPos.y + dy);
    const w = obj.map_width || 200, h = obj.map_height || 120;
    rect.setBounds([[ny, nx], [ny + h, nx + w]]);
    obj.map_x = nx; obj.map_y = ny;
    // 이성현 작업 — 리사이즈 핸들 위치 동기화
    if (_resizeHandles.length) {
      [[ny, nx], [ny, nx + w], [ny + h, nx], [ny + h, nx + w]]
        .forEach((pos, i) => _resizeHandles[i].setLatLng(pos));
    }
  });

  _map.on('mouseup', () => {
    if (!dragging) return;
    dragging = false;
    _map.dragging.enable();
    _markDirty('facility', obj.id);
    rect.setPopupContent(_facilityPopupHtml(obj));
  });
}

// 이성현 작업 — 위험구역 편집 핸들 정리
function _clearGeofenceEditHandles() {
  _geofenceEditHandles.forEach(h => _map.removeLayer(h));
  _geofenceEditHandles = [];
  if (_geofenceEditMapHandlers) {
    _map.off('mousemove', _geofenceEditMapHandlers.move);
    _map.off('mouseup',   _geofenceEditMapHandlers.up);
    _geofenceEditMapHandlers = null;
  }
}

// 이성현 작업 — 위험구역 전체 이동 드래그
function _makeGeofenceDraggable(layer, obj) {
  let dragging = false, startLatlng, startCx, startCy, startPoly;

  layer.on('mousedown', (e) => {
    if (_geofenceEditHandles.length) return; // 꼭짓점 편집 중엔 이동 불가
    dragging = true;
    startLatlng = e.latlng;
    if (obj.shape_type === 'circle') {
      startCx = obj.circle_cx; startCy = obj.circle_cy;
    } else {
      startPoly = obj.polygon.map(([x, y]) => [x, y]);
    }
    _map.dragging.disable();
    L.DomEvent.stop(e);
  });

  _map.on('mousemove', (e) => {
    if (!dragging) return;
    const dx = e.latlng.lng - startLatlng.lng;
    const dy = e.latlng.lat - startLatlng.lat;
    if (obj.shape_type === 'circle') {
      obj.circle_cx = startCx + dx;
      obj.circle_cy = startCy + dy;
      layer.setLatLng([obj.circle_cy, obj.circle_cx]);
    } else {
      obj.polygon = startPoly.map(([x, y]) => [x + dx, y + dy]);
      layer.setLatLngs(obj.polygon.map(([x, y]) => [y, x]));
    }
  });

  _map.on('mouseup', () => {
    if (!dragging) return;
    dragging = false;
    _map.dragging.enable();
    if (obj.id) _markDirty('geofence', obj.id);
  });
}

// 이성현 작업 — 원형 위험구역 반경 핸들 편집
function _startResizeGeofenceCircle(obj) {
  _clearGeofenceEditHandles();
  const layer = _layerMap[`geofence:${obj.id}`];
  if (!layer) return;

  const handle = L.circleMarker(
    [obj.circle_cy, obj.circle_cx + obj.circle_radius],
    { radius: 7, fillColor: '#fff', color: RISK_COLOR[obj.risk_level] || '#888', weight: 2, fillOpacity: 1 }
  ).addTo(_map);
  _geofenceEditHandles.push(handle);

  let resizing = false;
  handle.on('mousedown', (e) => { resizing = true; _map.dragging.disable(); L.DomEvent.stop(e); });
  handle.on('click', (e) => { L.DomEvent.stopPropagation(e); }); // 이성현 작업 — 지도 click 전파 차단

  const onMove = (e) => {
    if (!resizing) return;
    const dx = e.latlng.lng - obj.circle_cx;
    const dy = e.latlng.lat - obj.circle_cy;
    obj.circle_radius = Math.max(10, Math.sqrt(dx * dx + dy * dy));
    layer.setRadius(obj.circle_radius);
    handle.setLatLng([e.latlng.lat, e.latlng.lng]);
  };
  const onUp = () => {
    if (!resizing) return;
    resizing = false;
    _map.dragging.enable();
    if (obj.id) _markDirty('geofence', obj.id);
  };
  _map.on('mousemove', onMove);
  _map.on('mouseup', onUp);
  _geofenceEditMapHandlers = { move: onMove, up: onUp };

  layer.setPopupContent(_geofenceEditingPopupHtml(obj));
}

// 이성현 작업 — 폴리곤 위험구역 꼭짓점 핸들 편집
function _startEditGeofencePolygon(obj) {
  _clearGeofenceEditHandles();
  const layer = _layerMap[`geofence:${obj.id}`];
  if (!layer) return;

  let activeIdx = null;

  obj.polygon.forEach(([px, py], idx) => {
    const h = L.circleMarker([py, px], {
      radius: 7, fillColor: '#fff', color: RISK_COLOR[obj.risk_level] || '#888', weight: 2, fillOpacity: 1,
    }).addTo(_map);
    h.on('mousedown', (e) => { activeIdx = idx; _map.dragging.disable(); L.DomEvent.stop(e); });
    h.on('click', (e) => { L.DomEvent.stopPropagation(e); }); // 이성현 작업 — 지도 click 전파 차단
    // 더블클릭으로 꼭짓점 삭제 (최소 3개 유지)
    h.on('dblclick', (e) => {
      L.DomEvent.stop(e);
      if (obj.polygon.length <= 3) return;
      obj.polygon.splice(idx, 1);
      layer.setLatLngs(obj.polygon.map(([x, y]) => [y, x]));
      if (obj.id) _markDirty('geofence', obj.id);
      _startEditGeofencePolygon(obj); // 핸들 재생성
    });
    _geofenceEditHandles.push(h);
  });

  const onMove = (e) => {
    if (activeIdx === null) return;
    obj.polygon[activeIdx] = [e.latlng.lng, e.latlng.lat];
    _geofenceEditHandles[activeIdx].setLatLng([e.latlng.lat, e.latlng.lng]);
    layer.setLatLngs(obj.polygon.map(([x, y]) => [y, x]));
  };
  const onUp = () => {
    if (activeIdx === null) return;
    activeIdx = null;
    _map.dragging.enable();
    if (obj.id) _markDirty('geofence', obj.id);
  };
  _map.on('mousemove', onMove);
  _map.on('mouseup', onUp);
  _geofenceEditMapHandlers = { move: onMove, up: onUp };

  layer.setPopupContent(_geofenceEditingPopupHtml(obj));
}

// 이성현 작업
// ── 설비 크기 조정 핸들 ──────────────────────────────────────
function _clearResizeHandles() {
  _resizeHandles.forEach(h => _map.removeLayer(h));
  _resizeHandles = [];
  if (_resizeMapHandlers) {
    _map.off('mousemove', _resizeMapHandlers.move);
    _map.off('mouseup',   _resizeMapHandlers.up);
    _resizeMapHandlers = null;
  }
}

function _startResizeFacility(obj) {
  _clearResizeHandles();
  const rect = _layerMap[`facility:${obj.id}`];
  if (!rect) return;

  // 인덱스 순서: 0=SW 1=SE 2=NW 3=NE, 각 모서리의 반대쪽 인덱스
  const OPPOSITE = [3, 2, 1, 0];
  let activeIdx = null;

  function cornerPositions() {
    const b = rect.getBounds();
    return [
      { lat: b.getSouth(), lng: b.getWest() },
      { lat: b.getSouth(), lng: b.getEast() },
      { lat: b.getNorth(), lng: b.getWest() },
      { lat: b.getNorth(), lng: b.getEast() },
    ];
  }

  cornerPositions().forEach((pos, i) => {
    const h = L.circleMarker([pos.lat, pos.lng], {
      radius: 6, fillColor: '#fff', color: '#58a6ff', weight: 2, fillOpacity: 1,
    }).addTo(_map);
    h.on('mousedown', (e) => {
      activeIdx = i;
      _map.dragging.disable();
      L.DomEvent.stop(e);
    });
    _resizeHandles.push(h);
  });

  const onMove = (e) => {
    if (activeIdx === null) return;
    const opp = cornerPositions()[OPPOSITE[activeIdx]];
    const minLat = Math.min(opp.lat, e.latlng.lat);
    const maxLat = Math.max(opp.lat, e.latlng.lat);
    const minLng = Math.min(opp.lng, e.latlng.lng);
    const maxLng = Math.max(opp.lng, e.latlng.lng);
    rect.setBounds([[minLat, minLng], [maxLat, maxLng]]);
    obj.map_x = minLng; obj.map_y = minLat;
    obj.map_width  = maxLng - minLng;
    obj.map_height = maxLat - minLat;
    cornerPositions().forEach((p, i) => _resizeHandles[i].setLatLng([p.lat, p.lng]));
  };

  const onUp = () => {
    if (activeIdx === null) return;
    activeIdx = null;
    _map.dragging.enable();
    _markDirty('facility', obj.id);
    rect.setPopupContent(_facilityResizePopupHtml(obj));
  };

  _map.on('mousemove', onMove);
  _map.on('mouseup',   onUp);
  _resizeMapHandlers = { move: onMove, up: onUp };

  rect.setPopupContent(_facilityResizePopupHtml(obj));
  rect.openPopup();
}

function _facilityResizePopupHtml(obj) {
  const code = obj.code || `FAC-${obj.id}`;
  const x = (obj.map_x ?? 0).toFixed(0), y = (obj.map_y ?? 0).toFixed(0);
  const w = (obj.map_width ?? 0).toFixed(0), h = (obj.map_height ?? 0).toFixed(0);
  return `<div class="me-popup-title">설비 ${code}</div>
    <div class="me-popup-row">현재 좌표: X ${x} / Y ${y}</div>
    <div class="me-popup-row">가로 ${w}px / 세로 ${h}px</div>
    <div class="me-popup-actions">
      <button class="btn-popup-edit" onclick="MapEditor.finishResizeFacility(${obj.id})">완료</button>
    </div>`;
}

// ── 지오펜스 그리기 ──────────────────────────────────────────
function _openGeofenceModal() {
  document.getElementById('newGeofenceName').value = '';
  _showModal('geofenceCreateModal');
}
function _closeGeofenceModal() { _hideModal('geofenceCreateModal'); }

function _startDraw() {
  const risk  = document.querySelector('[data-risk].active')?.dataset.risk || 'warning';
  const shape = document.querySelector('[data-shape].active')?.dataset.shape || 'polygon';
  const name  = document.getElementById('newGeofenceName').value.trim() || '신규 위험 구역';

  _drawMode = { risk, shape, name };
  _drawPoints = [];
  _drawMarkers = [];
  _closeGeofenceModal();

  const banner = document.getElementById('drawBanner');
  banner.style.display = 'flex';
  document.getElementById('drawBannerText').textContent =
    shape === 'circle' ? '중심점을 클릭 후 드래그해 반경을 설정하세요' : '꼭짓점 클릭 → 완료 버튼 (또는 더블클릭)';
  document.getElementById('btnFinishDraw').style.display = shape === 'polygon' ? 'inline-block' : 'none';

  _map.getContainer().style.cursor = 'crosshair';
  _map.doubleClickZoom.disable();
}

function _cancelDraw() {
  _drawMode = null;
  _drawPoints = [];
  _drawMarkers.forEach(m => _map.removeLayer(m));
  _drawMarkers = [];
  if (_drawPolyline) { _map.removeLayer(_drawPolyline); _drawPolyline = null; }
  if (_drawPolygon)  { _map.removeLayer(_drawPolygon);  _drawPolygon  = null; }
  if (_drawCircle)   { _map.removeLayer(_drawCircle);   _drawCircle   = null; }
  _drawCenter = null;
  document.getElementById('drawBanner').style.display = 'none';
  document.getElementById('btnFinishDraw').style.display = 'none';
  _map.getContainer().style.cursor = '';
  _map.doubleClickZoom.enable();
}

function _onMapClick(e) {
  // 이성현 작업 — 빈 곳 클릭 시 선택 해제 (지오펜스 편집 핸들 활성 중엔 제외)
  if (!_drawMode) { if (!_geofenceEditHandles.length) _clearSelection(); return; }
  const { lat, lng } = e.latlng;

  if (_drawMode.shape === 'circle') {
    if (!_drawCenter) {
      _drawCenter = { x: lng, y: lat };
      const dot = L.circleMarker([lat, lng], { radius: 5, fillColor: '#e3b341', color: '#fff', weight: 1.5, fillOpacity: 1 }).addTo(_map);
      _drawMarkers.push(dot);
    }
    return;
  }

  // 폴리곤 모드
  _drawPoints.push([lng, lat]);
  const dot = L.circleMarker([lat, lng], { radius: 5, fillColor: '#1f6feb', color: '#fff', weight: 1.5, fillOpacity: 1 }).addTo(_map);
  _drawMarkers.push(dot);

  if (_drawPolyline) _map.removeLayer(_drawPolyline);
  _drawPolyline = L.polyline(_drawPoints.map(([x, y]) => [y, x]), { color: '#1f6feb', weight: 2, dashArray: '5 5' }).addTo(_map);

  if (_drawPoints.length >= 3) {
    if (_drawPolygon) _map.removeLayer(_drawPolygon);
    _drawPolygon = L.polygon(_drawPoints.map(([x, y]) => [y, x]), {
      color: RISK_COLOR[_drawMode.risk] || '#e3b341',
      fillColor: RISK_COLOR[_drawMode.risk] || '#e3b341',
      fillOpacity: 0.2, weight: 2,
    }).addTo(_map);
  }
}

function _onMapMouseMove(e) {
  if (!_drawMode) return;
  const { lat, lng } = e.latlng;
  document.getElementById('drawCoordText').textContent = `X ${lng.toFixed(0)} / Y ${lat.toFixed(0)}`;

  if (_drawMode.shape === 'circle' && _drawCenter) {
    const r = Math.hypot(lng - _drawCenter.x, lat - _drawCenter.y);
    if (_drawCircle) _map.removeLayer(_drawCircle);
    _drawCircle = L.circle([_drawCenter.y, _drawCenter.x], {
      radius: r,
      color: RISK_COLOR[_drawMode.risk] || '#e3b341',
      fillColor: RISK_COLOR[_drawMode.risk] || '#e3b341',
      fillOpacity: 0.2, weight: 2,
    }).addTo(_map);
  }
}

// mouseup on circle draw
document.addEventListener('mouseup', (e) => {
  if (!_drawMode || _drawMode.shape !== 'circle' || !_drawCenter || !_drawCircle) return;
  const r = _drawCircle.getRadius();
  if (r < 5) { _cancelDraw(); return; }
  _finishCircleDraw(r);
});

function _finishPolygonDraw() {
  const newFence = {
    id: null,
    name: _drawMode.name,
    risk_level: _drawMode.risk,
    shape_type: 'polygon',
    polygon: _drawPoints.slice(),
    facility_id: parseInt(document.getElementById('facilitySelect').value) || 1,
    placed: true,
    _objType: 'geofence',
    _isNew: true,
    _tmpId: `new_${Date.now()}`,
  };
  _pendingGeofences.push(newFence);
  _allObjects.push(newFence);

  _cancelDraw();
  _renderGeofence(newFence);
  _renderList();
}

function _finishCircleDraw(radius) {
  const newFence = {
    id: null,
    name: _drawMode.name,
    risk_level: _drawMode.risk,
    shape_type: 'circle',
    polygon: [],
    circle_cx: _drawCenter.x,
    circle_cy: _drawCenter.y,
    circle_radius: radius,
    facility_id: parseInt(document.getElementById('facilitySelect').value) || 1,
    placed: true,
    _objType: 'geofence',
    _isNew: true,
    _tmpId: `new_${Date.now()}`,
  };
  _pendingGeofences.push(newFence);
  _allObjects.push(newFence);

  _cancelDraw();
  _renderGeofence(newFence);
  _renderList();
}

// 이성현 작업
// ── 체크박스로 미배치 객체 지도에 추가 ─────────────────────
function _onObjectCheck(obj, checked) {
  if (obj._objType === 'geofence') return;
  if (!checked) {
    const key = `${obj._objType}:${obj.id}`;
    const layer = _layerMap[key];
    if (layer) {
      _layers[obj._objType].removeLayer(layer);
      delete _layerMap[key];
    }
    if (obj._objType === 'facility') { obj.map_x = null; obj.map_y = null; }
    else {
      obj._savedX = obj.x; obj._savedY = obj.y;
      obj.x = 0; obj.y = 0;
    }
    obj.placed = false;
    _markDirty(obj._objType, obj.id);
    return;
  }
  const center = _map.getBounds().getCenter();
  if (obj._objType === 'facility') {
    obj.map_x = center.lng - 100;
    obj.map_y = center.lat - 60;
    obj.map_width = 200;
    obj.map_height = 120;
    obj.placed = true;
  } else {
    const hasSaved = obj._savedX != null && (obj._savedX !== 0 || obj._savedY !== 0);
    obj.x = hasSaved ? obj._savedX : center.lng;
    obj.y = hasSaved ? obj._savedY : center.lat;
    delete obj._savedX; delete obj._savedY;
    obj.placed = true;
  }
  _renderObject(obj);
  _markDirty(obj._objType, obj.id);
}

// ── 사이드바 리스트 렌더 ─────────────────────────────────────
function _applyFilter() {
  _searchQuery = document.getElementById('searchInput').value.trim().toLowerCase();
  _renderList();
}

function _renderList() {
  const list = document.getElementById('objectList');
  const filtered = _allObjects.filter(obj => {
    // 타입 필터
    if (_typeFilter !== 'all' && obj._objType !== _typeFilter) return false;
    // 배치 상태
    if (_tabFilter === 'placed'   && !obj.placed) return false;
    if (_tabFilter === 'unplaced' &&  obj.placed) return false;
    // 검색
    if (_searchQuery) {
      const code = (obj.code || obj.device_id || '').toLowerCase();
      const name = (obj.name || obj.device_name || '').toLowerCase();
      if (!code.includes(_searchQuery) && !name.includes(_searchQuery)) return false;
    }
    return true;
  });

  // 카운트 업데이트
  document.getElementById('cntAll').textContent     = _allObjects.length;
  document.getElementById('cntPlaced').textContent   = _allObjects.filter(o => o.placed).length;
  document.getElementById('cntUnplaced').textContent = _allObjects.filter(o => !o.placed).length;

  list.innerHTML = '';
  if (filtered.length === 0) {
    list.innerHTML = '<div style="padding:20px;text-align:center;color:#6e7681;font-size:12px;">해당 객체가 없습니다.</div>';
    return;
  }

  filtered.forEach(obj => {
    const item = document.createElement('div');
    item.className = 'me-object-item';

    const displayName = obj.name || obj.device_name || '';
    const code = obj.code || obj.device_id || '';
    const badgeClass = `me-object-badge badge-${obj._objType}`;
    const typeLabel = TYPE_LABEL[obj._objType] || obj._objType;

    let checkHtml = '';
    if (obj._objType !== 'geofence') {
      checkHtml = `<input type="checkbox" ${obj.placed ? 'checked' : ''}>`;
    }

    item.innerHTML = `
      ${checkHtml}
      <span class="me-object-name" title="${displayName}">${code} ${displayName}</span>
      <span class="${badgeClass}">${typeLabel}</span>
      ${!obj.placed ? '<span class="me-object-unplaced">미배치</span>' : ''}
    `;

    // 이성현 작업 — 체크박스
    const cb = item.querySelector('input[type=checkbox]');
    if (cb) {
      cb.addEventListener('click', e => e.stopPropagation());
      cb.addEventListener('change', e => {
        e.stopPropagation();
        _onObjectCheck(obj, e.target.checked);
        _renderList();
      });
    }

    // 클릭 → 지도 이동
    item.addEventListener('click', () => {
      if (obj._objType === 'facility' && obj.map_x != null) {
        _map.fitBounds([[obj.map_y, obj.map_x], [obj.map_y + (obj.map_height||120), obj.map_x + (obj.map_width||200)]]);
      } else if (obj.x != null) {
        _map.setView([obj.y, obj.x], _map.getZoom());
      }
    });

    list.appendChild(item);
  });
}

// ── 더티 추적 ────────────────────────────────────────────────
function _markDirty(type, id) {
  _dirtySet.add(`${type}:${id}`);
}

// 이성현 작업
function _selectObject(obj) {
  const key = `${obj._objType}:${obj.id}`;
  _selectedKey = key;
  Object.entries(_layerMap).forEach(([k, layer]) => {
    _setLayerDim(layer, k.split(':')[0], k !== key);
  });
}

function _clearSelection() {
  if (!_selectedKey && !_geofenceEditHandles.length) return;
  _selectedKey = null;
  // 이성현 작업 — 지오펜스 편집 핸들도 함께 해제
  _clearGeofenceEditHandles();
  Object.entries(_layerMap).forEach(([k, layer]) => {
    _setLayerDim(layer, k.split(':')[0], false);
  });
}

function _setLayerDim(layer, type, dimmed) {
  if (type === 'geofence') return;  // 이성현 작업 — 지오펜스는 dim 효과 제외
  if (type === 'facility') {
    layer.setStyle({ fillOpacity: dimmed ? 0.03 : 0.08, opacity: dimmed ? 0.2 : 1 });
  } else {
    layer.setStyle({ fillOpacity: dimmed ? 0.1 : 0.9, opacity: dimmed ? 0.2 : 1 });
  }
}

// ── 저장 ─────────────────────────────────────────────────────
async function _saveAll() {
  _hideModal('saveConfirmModal');

  // 폴리곤 그리기 중에 저장 시 자동 완료
  if (_drawMode) {
    if (_drawMode.shape === 'polygon' && _drawPoints.length >= 3) {
      _finishPolygonDraw();
    } else {
      _cancelDraw();
    }
  }

  const payload = {
    facilities:     [],
    gas_sensors:    [],
    power_devices:  [],
    position_nodes: [],
    geofences:      [],
  };

  _dirtySet.forEach(key => {
    const [type, idStr] = key.split(':');
    const id = parseInt(idStr);
    const obj = _allObjects.find(o => o._objType === type && o.id === id);
    if (!obj) return;

    switch (type) {
      case 'facility':
        payload.facilities.push({ id, map_x: obj.map_x, map_y: obj.map_y, map_width: obj.map_width, map_height: obj.map_height });
        break;
      case 'gas_sensor':
        payload.gas_sensors.push({ id, x: obj.x, y: obj.y });
        break;
      case 'power_device':
        payload.power_devices.push({ id, x: obj.x, y: obj.y });
        break;
      case 'position_node':
        payload.position_nodes.push({ id, x: obj.x, y: obj.y });
        break;
      // 이성현 작업 — 기존 위험구역 이동/크기 변경 저장
      case 'geofence':
        payload.geofences.push({
          id, name: obj.name, risk_level: obj.risk_level,
          shape_type: obj.shape_type,
          polygon: obj.polygon || [],
          circle_cx: obj.circle_cx ?? null,
          circle_cy: obj.circle_cy ?? null,
          circle_radius: obj.circle_radius ?? null,
          facility_id: obj.facility_id || 1,
          deleted: false,
        });
        break;
    }
  });

  // 신규/수정 지오펜스
  _pendingGeofences.forEach(fence => {
    payload.geofences.push({
      id: fence.id || null,
      name: fence.name,
      risk_level: fence.risk_level,
      shape_type: fence.shape_type,
      polygon: fence.polygon || [],
      circle_cx: fence.circle_cx || null,
      circle_cy: fence.circle_cy || null,
      circle_radius: fence.circle_radius || null,
      facility_id: fence.facility_id || 1,
      deleted: false,
    });
  });

  // 삭제 지오펜스
  _deletedGeofences.forEach(id => {
    const obj = _allObjects.find(o => o._objType === 'geofence' && o.id === id);
    payload.geofences.push({
      id,
      name: obj?.name || '',
      risk_level: obj?.risk_level || 'normal',
      shape_type: obj?.shape_type || 'polygon',
      polygon: obj?.polygon || [],
      facility_id: obj?.facility_id || 1,
      deleted: true,
    });
  });

  try {
    const res = await Auth.apiFetch(API_SAVE, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    // 이성현 작업
    if (res.ok) {
      _dirtySet.clear();
      _pendingGeofences = [];
      _deletedGeofences.clear();
      _showModal('saveCompleteModal');
    } else {
      const err = await res.json();
      console.error('[MapEditor] 저장 실패', err);
      alert('저장에 실패했습니다.');
    }
  } catch (e) {
    console.error('[MapEditor] 저장 오류', e);
    alert('저장 중 오류가 발생했습니다.');
  }
}

// ── 되돌리기 ─────────────────────────────────────────────────
function _resetAll() {
  _hideModal('resetConfirmModal');
  _dirtySet.clear();
  _pendingGeofences = [];
  _deletedGeofences.clear();
  _cancelDraw();
  _loadObjects();
}

// 이성현 작업 ── 지오펜스 팝업 액션
window.MapEditor = {
  // 이성현 작업 — 위험구역 편집 (반경/꼭짓점 핸들 활성화)
  editGeofence(id) {
    const obj = _allObjects.find(o => o._objType === 'geofence' && o.id === id);
    if (!obj) return;
    _map.closePopup();
    if (obj.shape_type === 'circle') {
      _startResizeGeofenceCircle(obj);
    } else {
      _startEditGeofencePolygon(obj);
    }
  },
  // 이성현 작업 — 위험구역 삭제 모달 열기
  confirmDeleteGeofence(id) {
    _pendingDeleteGeofenceId = id;
    _map.closePopup();
    _showModal('geofenceDeleteModal');
  },
  // 이성현 작업 — 위험구역 삭제 실행 (모달 확인 버튼)
  doDeleteGeofence() {
    const id = _pendingDeleteGeofenceId;
    _pendingDeleteGeofenceId = null;
    _hideModal('geofenceDeleteModal');
    const obj = _allObjects.find(o => o._objType === 'geofence' && o.id === id);
    if (!obj) return;
    if (id !== null && id !== undefined) _deletedGeofences.add(id);
    const key = `geofence:${id}`;
    const layer = _layerMap[key];
    if (layer) _layers.geofence.removeLayer(layer);
    delete _layerMap[key];
    _allObjects = _allObjects.filter(o => o !== obj);
    _pendingGeofences = _pendingGeofences.filter(o => o !== obj);
    _clearGeofenceEditHandles();
    _renderList();
  },
  // 이성현 작업 — 위험구역 편집 완료
  finishGeofenceEdit(id) {
    _clearGeofenceEditHandles();
    _map.closePopup();
    const obj = _allObjects.find(o => o._objType === 'geofence' && o.id === id);
    if (obj) {
      const layer = _layerMap[`geofence:${id}`];
      if (layer) layer.setPopupContent(_geofencePopupHtml(obj));
    }
  },
  startEditFacility(id) {
    _map.closePopup();
    const obj = _allObjects.find(o => o._objType === 'facility' && o.id === id);
    if (obj) _startResizeFacility(obj);
  },
  finishResizeFacility(id) {
    _clearResizeHandles();
    _map.closePopup();
    const obj = _allObjects.find(o => o._objType === 'facility' && o.id === id);
    if (obj) {
      const rect = _layerMap[`facility:${obj.id}`];
      if (rect) rect.setPopupContent(_facilityPopupHtml(obj));
    }
  },
};

// ── 모달 헬퍼 ────────────────────────────────────────────────
function _showModal(id) { document.getElementById(id).style.display = 'flex'; }
function _hideModal(id) { document.getElementById(id).style.display = 'none'; }

// ── 지도 더블클릭 이벤트 연결 (init 이후) ──────────────────
document.addEventListener('DOMContentLoaded', () => {
  setTimeout(() => {
    if (!_accessGranted) return;
    _map.on('dblclick', (e) => {
      if (!_drawMode || _drawMode.shape !== 'polygon') return;
      L.DomEvent.stop(e);
      if (_drawPoints.length < 3) { alert('최소 3개 이상의 꼭짓점이 필요합니다.'); return; }
      _finishPolygonDraw();
    });
  }, 100);
});
