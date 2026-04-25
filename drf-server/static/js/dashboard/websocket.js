/* ==========================================================
   websocket.js — FastAPI WebSocket 실시간 데이터 수신 및 패널 업데이트

   의존: util.js (nowLabel, pushData)
        charts.js (gasChart, powerChart)
        map-panel.js (MapPanel)
        alarm-popup.js (AlarmPopup)
        event-panel.js (EventPanel)

   수신 페이로드 (fastapi-server/websocket/services/broadcast.py):
     co, h2s, co2, o2, no2, so2, o3, nh3, voc  ← 가스 측정값 9종
     {gas}_risk                                  ← 가스별 위험도 (co_risk, h2s_risk …)
     total_power_kw, power_change_pct            ← 전력 총합 및 증감률
     equipment[]                                 ← 설비별 전력 데이터
     power_loading                               ← 전력 데이터 수신 대기 중 여부
     ai_power_equipment, ai_eta_min,
     ai_max_load_kw, ai_max_load_pct            ← AI 예측 (equipment[] 없을 때 폴백)
     worker_positions{}                          ← 작업자 위치 맵
     alarms[]                                    ← 신규 알람 이벤트 목록
   ========================================================== */

'use strict';

// ── 전력 테이블 위험도 레이블·클래스 상수 ───────────────────
const _riskLabel = { normal: '정상', warning: '주의', danger: '위험' };
const _riskClass = { normal: 'safe', warning: 'caution', danger: 'danger' };

// ── AI 전력 채널 네비게이션 상태 ─────────────────────────────
let _aiPowerIdx    = 0;
let _aiPowerPreds  = [];   // 채널별 AI 예측 배열 [{ name, eta_min, max_load_val, max_load_unit, max_load_pct, risk_level }]
const _aiPowerHist = {};   // 채널별 차트 히스토리 { idx: { labels: string[], data: number[] } }
const _HIST_MAX    = 30;   // 채널당 최대 보관 포인트 수

// 채널별 히스토리에 데이터 포인트를 추가한다.
// 최대 _HIST_MAX개를 유지하며 오래된 값은 앞에서 제거된다.
function _pushChannelHistory(idx, label, value) {
  if (value == null) return;
  if (!_aiPowerHist[idx]) _aiPowerHist[idx] = { labels: [], data: [] };
  const h = _aiPowerHist[idx];
  h.labels.push(label);
  h.data.push(value);
  if (h.labels.length > _HIST_MAX) { h.labels.shift(); h.data.shift(); }
}

// 현재 선택된 채널(idx)의 히스토리 데이터로 전력 차트를 교체 렌더링한다.
function _switchPowerChart(idx) {
  if (!powerChart || !_aiPowerHist[idx]) return;
  const h = _aiPowerHist[idx];
  powerChart.data.labels           = [...h.labels];
  powerChart.data.datasets[0].data = [...h.data];
  powerChart.update('none');
}

// 현재 _aiPowerIdx 기준으로 AI 전력 예측 패널(장비명/ETA/최대부하/카운터)을 갱신한다.
function _renderAIPowerNav() {
  if (_aiPowerPreds.length === 0) return;
  const pred    = _aiPowerPreds[_aiPowerIdx];
  const nameEl  = document.getElementById('aiPowerEquipName');
  const etaEl   = document.getElementById('aiPowerEta');
  const loadEl  = document.getElementById('aiPowerMaxLoad');
  const countEl = document.getElementById('aiPowerNavCount');

  if (nameEl) {
    nameEl.textContent = pred.name;
    const riskCls = pred.risk_level === 'danger'  ? 'danger-text'
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

// DOMContentLoaded 후 AI 전력 채널 ◁▷ 버튼에 이벤트를 등록한다.
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

// 전력 설비 단건 행 HTML을 반환한다.
// comm_failure 상태면 수치를 '-'로, 배지를 gray로 표시한다.
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

// 전력 패널 전체를 오류/빈 상태로 전환한다.
// 총합·증감률을 '-'로 비우고 패널 메시지를 노출한다.
function _setPowerPanelError(msg) {
  const powerTotal     = document.getElementById('powerTotal');
  const powerChangePct = document.getElementById('powerChangePct');
  const powerTableBody = document.getElementById('powerTableBody');
  const powerPanelMsg  = document.getElementById('powerPanelMsg');

  if (powerTotal)     powerTotal.textContent    = '-';
  if (powerChangePct) powerChangePct.textContent = '-';
  if (powerChangePct) powerChangePct.className   = '';
  if (powerPanelMsg) {
    powerPanelMsg.textContent   = msg;
    powerPanelMsg.style.display = 'block';
  }
  if (powerTableBody) powerTableBody.innerHTML = '';
}

// 전력 패널 오류 메시지를 숨긴다.
function _clearPowerPanelMsg() {
  const el = document.getElementById('powerPanelMsg');
  if (el) el.style.display = 'none';
}

// ──────────────────────────────────────────────────────────
// initWebSocket — FastAPI WebSocket 연결을 초기화한다.
// /ws/sensors/ (센서 통합 페이로드)와 /ws/positions/ (작업자 위치 전용)
// 두 채널을 각각 연결하며, 연결 끊김 시 3초 후 자동 재연결한다.
// ──────────────────────────────────────────────────────────
function initWebSocket() {
  const wsStatusEl = document.getElementById('wsStatus');

  // 헤더 상단 WebSocket 연결 상태 배지를 갱신한다.
  function setWsStatus(text, cls) {
    if (!wsStatusEl) return;
    wsStatusEl.textContent = text;
    wsStatusEl.className   = `ws-status${cls ? ' ' + cls : ''}`;
  }

  // /ws/sensors/ 에 연결해 1초마다 수신되는 통합 페이로드를 각 패널에 반영한다.
  function connect() {
    let ws;
    try {
      ws = new WebSocket('ws://127.0.0.1:8001/ws/sensors/');
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

      // ── 패널 12: 유해가스 현황 테이블 (9종) ──────────────
      // {gas}_risk 필드는 FastAPI gas_service의 calculate_individual_risks()가 생성해 페이로드에 포함한다.
      const tbody = document.getElementById('gasTableBody');
      if (tbody && data.co !== undefined) {
        const GAS_META = [
          { key: 'co',  name: 'CO (일산화탄소)',        unit: 'ppm' },
          { key: 'h2s', name: 'H₂S (황화수소)',         unit: 'ppm' },
          { key: 'co2', name: 'CO₂ (이산화탄소)',       unit: 'ppm' },
          { key: 'o2',  name: 'O₂ (산소)',              unit: '%'   },
          { key: 'no2', name: 'NO₂ (이산화질소)',       unit: 'ppm' },
          { key: 'so2', name: 'SO₂ (이산화황)',         unit: 'ppm' },
          { key: 'o3',  name: 'O₃ (오존)',              unit: 'ppm' },
          { key: 'nh3', name: 'NH₃ (암모니아)',         unit: 'ppm' },
          { key: 'voc', name: 'VOC (휘발성유기화합물)', unit: 'ppm' },
        ];
        const RISK_LABEL = { danger: '위험', warning: '주의', normal: '정상', safe: '정상' };
        tbody.innerHTML = GAS_META.map(g => {
          const val  = data[g.key] ?? '-';
          const risk = data[`${g.key}_risk`] || 'normal';
          return `<tr class="gas-row ${risk}">
            <td>${g.name}</td><td>${val}</td><td>${g.unit}</td>
            <td><span class="brisk ${risk}">${RISK_LABEL[risk] || risk}</span></td>
          </tr>`;
        }).join('');
      }

      // ── 패널 13: AI 예측 — CO ─────────────────────────────
      const coRisk       = data.co > 50;
      const aiGasName    = document.getElementById('aiGasName');
      const aiCurrentVal = document.getElementById('aiCurrentVal');
      const aiMaxVal     = document.getElementById('aiMaxVal');
      if (aiGasName) aiGasName.className = coRisk ? 'danger-text fw' : 'caution-text fw';
      if (aiCurrentVal) {
        aiCurrentVal.textContent = `${data.co} ppm`;
        aiCurrentVal.className   = 'big ' + (coRisk ? 'danger-text' : 'caution-text');
      }
      if (aiMaxVal) aiMaxVal.textContent = `${Math.round(data.co * 1.5)} ppm`;

      // ── 패널 14: 전력 현황 ────────────────────────────────
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
          // FastAPI 전력 수신 대기 중 — skeleton 상태 그대로 유지
        } else if (!data.equipment || data.equipment.length === 0) {
          _setPowerPanelError('데이터가 존재하지 않습니다.');
        } else {
          _clearPowerPanelMsg();
          powerTableBody.innerHTML = data.equipment.map(_renderPowerRow).join('');
        }
      }

      // ── 패널 15: AI 예측 — 전력 채널 네비게이션 ──────────
      // equipment[]가 있으면 설비별 채널을, 없으면 페이로드의 ai_* 단일값을 폴백으로 사용한다.
      if (!data.power_loading) {
        if (data.ai_predictions && data.ai_predictions.length > 0) {
          _aiPowerPreds = data.ai_predictions;
        } else if (data.equipment && data.equipment.length > 0) {
          const overallRisk = data.equipment.some(e => e.risk_level === 'danger')  ? 'danger'
                            : data.equipment.some(e => e.risk_level === 'warning') ? 'warning'
                            : 'normal';
          _aiPowerPreds = [
            {
              name: '전체 사용량', eta_min: data.ai_eta_min ?? null,
              max_load_val:  data.total_power_kw != null ? Math.round(data.total_power_kw * 1.1 * 10) / 10 : null,
              max_load_unit: 'kW', max_load_pct: data.power_change_pct ?? null,
              risk_level: overallRisk,
            },
            ...data.equipment.map(eq => ({
              name: eq.name, eta_min: null,
              max_load_val:  eq.watt != null ? Math.round(eq.watt * 1.1) : null,
              max_load_unit: 'W', max_load_pct: null,
              risk_level: eq.risk_level || 'normal',
            })),
          ];
        } else if (data.ai_power_equipment) {
          _aiPowerPreds = [{
            name: data.ai_power_equipment, eta_min: data.ai_eta_min ?? null,
            max_load_val: data.ai_max_load_kw ?? null, max_load_unit: 'kW',
            max_load_pct: data.ai_max_load_pct ?? null, risk_level: 'danger',
          }];
        }
        _renderAIPowerNav();
      }

      // ── 가스 차트 실시간 업데이트 ─────────────────────────
      const tick = nowLabel();
      if (gasChart) pushData(gasChart, tick, data.co, Math.round(data.co * 1.5));

      // ── 전력 차트 — 채널별 히스토리 누적 후 현재 채널 렌더 ──
      if (!data.power_loading) {
        if (data.total_power_kw != null)
          _pushChannelHistory(0, tick, Math.round(data.total_power_kw * 1.1 * 10) / 10);
        if (data.equipment) {
          data.equipment.forEach((eq, i) => {
            if (eq.watt != null) _pushChannelHistory(i + 1, tick, Math.round(eq.watt * 1.1));
          });
        }
        _switchPowerChart(_aiPowerIdx);
      }

      // ── MN-02 맵 — 가스센서·작업자 위치 갱신 ─────────────
      MapPanel.updateGasSensorFromWS(data);
      if (data.worker_positions && typeof MapPanel.updateWorkerPositions === 'function') {
        const posArray = Object.entries(data.worker_positions).map(([id, pos]) => ({
          worker_id: parseInt(id), ...pos,
        }));
        MapPanel.updateWorkerPositions(posArray);
      }

      // ── CM-07 — 알람 팝업 + 이벤트 패널 ─────────────────
      // alarms[]는 DRF가 새 Event 생성 시에만 포함되며, 병합(merge) 틱에서는 빈 배열이다.
      if (Array.isArray(data.alarms) && data.alarms.length > 0) {
        data.alarms.forEach(alarm => {
          const alarmData = {
            alarm_level: alarm.risk_level,
            message:     alarm.summary,
            sensor_name: alarm.source_label,
            timestamp:   new Date().toISOString(),
            gas_type:    alarm.gas_type,
            event_id:    alarm.event_id,
          };
          AlarmPopup.show(alarmData);
          if (typeof EventPanel !== 'undefined') EventPanel.addItem(alarmData);
        });
      }
    };

    // 연결 오류 시 상태 배지를 갱신한다. 재연결은 onclose에서 처리한다.
    ws.onerror = () => {
      setWsStatus('● 연결 오류', 'error');
      _setPowerPanelError('데이터를 불러올 수 없습니다.');
    };

    // 연결 끊김 시 3초 후 재연결을 시도한다.
    ws.onclose = () => {
      setWsStatus('● 연결 끊김', 'error');
      _setPowerPanelError('데이터를 불러올 수 없습니다.');
      setTimeout(connect, 3000);
    };
  }

  // /ws/positions/ 에 연결해 IoT 장비로부터 수신된 작업자 위치만 별도로 처리한다.
  // sensors 페이로드에도 worker_positions가 포함되어 있으나,
  // 이 채널은 위치 전용 고빈도 갱신을 위해 분리 운영한다.
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
      if (data.worker_positions && typeof MapPanel.updateWorkerPositions === 'function') {
        MapPanel.updateWorkerPositions(data.worker_positions);
      }
    };

    wsPos.onclose = () => setTimeout(connectPositions, 3000);
  }

  connect();
  connectPositions();
}
