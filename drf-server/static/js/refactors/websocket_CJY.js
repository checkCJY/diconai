/* ==========================================================
   websocket_CJY.js — 전력 패널 컬럼 변경 버전
   변경: 설비명 / 전력(W) / 전압(V) / 전류(A) / ON/OFF / 위험수치
   의존: util.js (levelLabel, nowLabel, pushData)
        charts.js (gasChart, powerChart)
        map-panel.js (MapPanel)
        alarm-popup.js (AlarmPopup)
   수신 페이로드 (equipment[] 변경):
     equipment[]: { name, watt, voltage, current, onoff, sensor_status, risk_level }
       - sensor_status: 'active' | 'comm_failure'
       - onoff: true(ON) | false(OFF)
       - risk_level: 'normal' | 'warning' | 'danger'
   ========================================================== */

'use strict';

// ── 전력 테이블 렌더링 상수 ─────────────────────────────────
const _riskLabel = { normal: '정상', warning: '주의', danger: '위험' };
const _riskClass = { normal: 'safe', warning: 'caution', danger: 'danger' };

// ── AI 전력 패널 채널 네비게이션 상태 ────────────────────────
let _aiPowerIdx     = 0;
let _aiPowerPreds   = [];   // [{name, eta_min, max_load_val, max_load_unit, max_load_pct, risk_level}]
const _aiPowerHist  = {};   // { idx: { labels: string[], data: number[] } }
const _HIST_MAX     = 30;

function _pushChannelHistory(idx, label, value) {
  if (value == null) return;
  if (!_aiPowerHist[idx]) _aiPowerHist[idx] = { labels: [], data: [] };
  const h = _aiPowerHist[idx];
  h.labels.push(label);
  h.data.push(value);
  if (h.labels.length > _HIST_MAX) { h.labels.shift(); h.data.shift(); }
}

function _switchPowerChart(idx) {
  if (!powerChart || !_aiPowerHist[idx]) return;
  const h = _aiPowerHist[idx];
  powerChart.data.labels            = [...h.labels];
  powerChart.data.datasets[0].data  = [...h.data];
  powerChart.update('none');
}

function _renderAIPowerNav() {
  if (_aiPowerPreds.length === 0) return;
  const pred    = _aiPowerPreds[_aiPowerIdx];
  const nameEl  = document.getElementById('aiPowerEquipName');
  const etaEl   = document.getElementById('aiPowerEta');
  const loadEl  = document.getElementById('aiPowerMaxLoad');
  const countEl = document.getElementById('aiPowerNavCount');

  if (nameEl) {
    nameEl.textContent = pred.name;
    const riskCls = pred.risk_level === 'danger' ? 'danger-text'
                  : pred.risk_level === 'warning' ? 'caution-text' : '';
    nameEl.className = `fw ai-equip-name ${riskCls}`.trim();
  }
  if (etaEl) etaEl.textContent = pred.eta_min != null ? `${pred.eta_min} 분 뒤` : '-';
  if (loadEl) {
    if (pred.max_load_val != null) {
      const unit   = pred.max_load_unit || 'kW';
      const pctStr = pred.max_load_pct != null
        ? ` <span style="font-size:11px;font-weight:400;">(정상 대비 ${pred.max_load_pct}%)</span>`
        : '';
      loadEl.innerHTML = `${pred.max_load_val.toLocaleString()} ${unit}${pctStr}`;
    } else {
      loadEl.innerHTML = '-';
    }
  }
  if (countEl) countEl.textContent = `${_aiPowerIdx + 1} / ${_aiPowerPreds.length}`;
  _switchPowerChart(_aiPowerIdx);
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('aiPowerPrev')?.addEventListener('click', () => {
    if (_aiPowerPreds.length === 0) return;
    _aiPowerIdx = (_aiPowerIdx - 1 + _aiPowerPreds.length) % _aiPowerPreds.length;
    _renderAIPowerNav();
  });
  document.getElementById('aiPowerNext')?.addEventListener('click', () => {
    if (_aiPowerPreds.length === 0) return;
    _aiPowerIdx = (_aiPowerIdx + 1) % _aiPowerPreds.length;
    _renderAIPowerNav();
  });
});

// ── 전력 패널 단건 행 렌더링 ────────────────────────────────
function _renderPowerRow(eq) {
  const isComm = eq.sensor_status === 'comm_failure';

  const watt    = isComm || eq.watt    == null ? '-' : eq.watt;
  const voltage = isComm || eq.voltage == null ? '-' : eq.voltage;
  const current = isComm || eq.current == null ? '-' : eq.current;

  const onoffBadge = (isComm || eq.onoff == null)
    ? '<span class="brisk gray">-</span>'
    : eq.onoff
      ? '<span class="brisk on">ON</span>'
      : '<span class="brisk off">OFF</span>';

  const riskBadge = isComm
    ? '<span class="brisk gray">-</span>'
    : `<span class="brisk ${_riskClass[eq.risk_level] || 'safe'}">${_riskLabel[eq.risk_level] || '-'}</span>`;

  const rowClass = isComm ? '' : ` class="risk-row risk-${_riskClass[eq.risk_level] || 'safe'}"`;

  return `<tr${rowClass}>
    <td>${eq.name}</td>
    <td>${watt}</td>
    <td>${voltage}</td>
    <td>${current}</td>
    <td>${onoffBadge}</td>
    <td>${riskBadge}</td>
  </tr>`;
}

// ── 전력 패널 오류/빈 데이터 상태 렌더링 ───────────────────
// UI_Handling.md: 통신 장애 → '-' 표시, 배지 gray, 패널 메시지 노출
function _setPowerPanelError(msg) {
  const powerTotal     = document.getElementById('powerTotal');
  const powerChangePct = document.getElementById('powerChangePct');
  const powerTableBody = document.getElementById('powerTableBody');
  const powerPanelMsg  = document.getElementById('powerPanelMsg');

  if (powerTotal)     powerTotal.textContent     = '-';
  if (powerChangePct) powerChangePct.textContent  = '-';
  if (powerChangePct) powerChangePct.className    = '';

  if (powerPanelMsg) {
    powerPanelMsg.textContent = msg;
    powerPanelMsg.style.display = 'block';
  }
  if (powerTableBody) {
    powerTableBody.innerHTML = '';
  }
}

function _clearPowerPanelMsg() {
  const powerPanelMsg = document.getElementById('powerPanelMsg');
  if (powerPanelMsg) powerPanelMsg.style.display = 'none';
}

// ──────────────────────────────────────────────────────────
// WebSocket — FastAPI ws://127.0.0.1:8001/ws/sensors/
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
      ws = new WebSocket('ws://127.0.0.1:8002/ws/sensors/');
    } catch {
      setWsStatus('● 연결 불가', 'error');
      _setPowerPanelError('데이터를 불러올 수 없습니다.');
      return;
    }

    ws.onopen = () => {
      setWsStatus('● 실시간 연결', 'connected');
      _clearPowerPanelMsg();
    };

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

      // ── 패널 14: 전력 현황 (변경) ──────────────────────
      const powerTotal     = document.getElementById('powerTotal');
      const powerChangePct = document.getElementById('powerChangePct');
      const powerTableBody = document.getElementById('powerTableBody');

      if (powerTotal && data.total_power_kw !== undefined)
        powerTotal.textContent = `${data.total_power_kw.toLocaleString()} kW`;

      if (powerChangePct && data.power_change_pct !== undefined) {
        const pct  = data.power_change_pct;
        const sign = pct >= 0 ? '▲ +' : '▼ ';
        powerChangePct.textContent = `기준 대비 ${sign}${pct}%`;
        powerChangePct.className   = pct >= 15 ? 'danger-text' : 'caution-text';
      }

      if (powerTableBody) {
        if (data.power_loading) {
          // 더미 센더 미수신 중 — 스켈레톤 유지 (에러 메시지 표시 안 함)
        } else if (!data.equipment || data.equipment.length === 0) {
          // UI_Handling.md: Empty Data → 메시지 노출
          _setPowerPanelError('데이터가 존재하지 않습니다.');
        } else {
          _clearPowerPanelMsg();
          powerTableBody.innerHTML = data.equipment.map(_renderPowerRow).join('');
        }
      }

      // ── 패널 15: AI 예측 — 전력 채널 네비게이션 ────────────
      if (!data.power_loading) {
        if (data.ai_predictions && data.ai_predictions.length > 0) {
          // 서버가 채널별 배열을 보내는 경우 (index 0 = 전체)
          _aiPowerPreds = data.ai_predictions;
        } else if (data.equipment && data.equipment.length > 0) {
          const overallRisk = data.equipment.some(e => e.risk_level === 'danger')  ? 'danger'
                            : data.equipment.some(e => e.risk_level === 'warning') ? 'warning'
                            : 'normal';
          _aiPowerPreds = [
            // index 0: 전체 사용량 (kW × 1.1)
            {
              name:          '전체 사용량',
              eta_min:       data.ai_eta_min ?? null,
              max_load_val:  data.total_power_kw != null ? Math.round(data.total_power_kw * 1.1 * 10) / 10 : null,
              max_load_unit: 'kW',
              max_load_pct:  data.power_change_pct ?? null,
              risk_level:    overallRisk,
            },
            // index 1–16: 개별 채널 (W × 1.1)
            ...data.equipment.map(eq => ({
              name:          eq.name,
              eta_min:       null,
              max_load_val:  eq.watt != null ? Math.round(eq.watt * 1.1) : null,
              max_load_unit: 'W',
              max_load_pct:  null,
              risk_level:    eq.risk_level || 'normal',
            })),
          ];
        } else if (data.ai_power_equipment) {
          _aiPowerPreds = [{
            name:          data.ai_power_equipment,
            eta_min:       data.ai_eta_min      ?? null,
            max_load_val:  data.ai_max_load_kw  ?? null,
            max_load_unit: 'kW',
            max_load_pct:  data.ai_max_load_pct ?? null,
            risk_level:    'danger',
          }];
        }
        _renderAIPowerNav();
      }

      // ── 차트 실시간 업데이트 ────────────────────────────
      const tick = nowLabel();
      if (gasChart) pushData(gasChart, tick, data.co, Math.round(data.co * 1.5));
      if (!data.power_loading) {
        // index 0: 전체 사용량 히스토리 (kW × 1.1)
        if (data.total_power_kw != null)
          _pushChannelHistory(0, tick, Math.round(data.total_power_kw * 1.1 * 10) / 10);
        // index 1–16: 개별 채널 히스토리 (W × 1.1)
        if (data.equipment) {
          data.equipment.forEach((eq, i) => {
            if (eq.watt != null) _pushChannelHistory(i + 1, tick, Math.round(eq.watt * 1.1));
          });
        }
        _switchPowerChart(_aiPowerIdx);
      }

      // ── MN-02 맵 — 가스센서 + 작업자 위치 ───────────────
      MapPanel.updateGasSensorFromWS(data);
      if (data.worker_positions && typeof MapPanel.updateWorkerPositions === 'function') {
        MapPanel.updateWorkerPositions(data.worker_positions);
      }

      // ── CM-07 — 위험 발생 시 알림 팝업 + 이벤트 패널 ───
      if (data.level === '위험') {
        const alarmData = {
          alarm_level: 'danger',
          message:     `CO: ${data.co}ppm / H₂S: ${data.h2s}ppm / O₂: ${data.o2}%`,
          sensor_name: data.device_id,
          timestamp:   data.timestamp,
        };
        AlarmPopup.show(alarmData);
        EventPanel.addItem(alarmData);
      }
    };

    // UI_Handling.md: 통신 장애 → '-' 표시, 패널 메시지, 3초 재연결(onclose에서 처리)
    ws.onerror = () => {
      setWsStatus('● 연결 오류', 'error');
      _setPowerPanelError('데이터를 불러올 수 없습니다.');
    };

    ws.onclose = () => {
      setWsStatus('● 연결 끊김', 'error');
      _setPowerPanelError('데이터를 불러올 수 없습니다.');
      setTimeout(connect, 3000);  // UI_Handling.md: 3초 주기 재연결
    };
  }

  function connectPositions() {
    let wsPos;
    try {
      wsPos = new WebSocket('ws://127.0.0.1:8001/ws/positions/');
    } catch {
      return;
    }

    wsPos.onmessage = (e) => {
      let data;
      try { data = JSON.parse(e.data); } catch { return; }
      if (data.worker_positions) {
        MapPanel.updateWorkerPositions(data.worker_positions);
      }
    };

    wsPos.onclose = () => {
      setTimeout(connectPositions, 3000);
    };
  }

  connect();
  connectPositions();
}
