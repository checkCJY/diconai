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

// ── 전력 테이블 위험도 레이블·클래스 상수 (LevelMapper 위임 — 05 R3) ─

// ── AI 가스 네비게이션 상태 ──────────────────────────────────
const _GAS_META = [
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

let _aiGasIdx  = 0;           // 현재 선택된 가스 인덱스
let _aiGasData = {};          // 최근 수신 가스 데이터 캐시
const _aiGasHist = {};        // 가스별 차트 히스토리 { key: { labels, current, predicted } }

// 가스 히스토리에 데이터를 추가한다. 최대 _HIST_MAX개 유지.
function _pushGasHistory(key, label, currentVal) {
  if (currentVal == null) return;
  if (!_aiGasHist[key]) _aiGasHist[key] = { labels: [], current: [], predicted: [] };
  const h = _aiGasHist[key];
  h.labels.push(label);
  h.current.push(currentVal);
  h.predicted.push(parseFloat((currentVal * 1.3).toFixed(2)));
  if (h.labels.length > _HIST_MAX) { h.labels.shift(); h.current.shift(); h.predicted.shift(); }
}

// 현재 선택 가스의 차트를 히스토리 데이터로 교체 렌더링 + 가스별 SoT 임계치로 thresholdZones 업데이트.
function _switchGasChart(key) {
  if (!gasChart || !_aiGasHist[key]) return;
  const h = _aiGasHist[key];
  gasChart.data.labels              = [...h.labels];
  gasChart.data.datasets[0].data   = [...h.current];
  gasChart.data.datasets[1].data   = [...h.predicted];
  // 가스 전환 시 임계치도 함께 — DASH_GAS_THRESHOLDS[key] 의 warning/danger 라인을 표시.
  if (typeof updateGasThresholds === 'function') updateGasThresholds(key);
  gasChart.update('none');
}

// AI 가스 패널 네비게이션 UI를 현재 인덱스 기준으로 갱신한다.
function _renderAIGasNav() {
  const gas  = _GAS_META[_aiGasIdx];
  const data = _aiGasData;
  const risk = data[`${gas.key}_risk`] || 'normal';
  const val  = data[gas.key] ?? null;

  const nameEl    = document.getElementById('aiGasName');
  const countEl   = document.getElementById('aiGasNavCount');
  const currentEl = document.getElementById('aiCurrentVal');
  const maxEl     = document.getElementById('aiMaxVal');

  if (nameEl) {
    nameEl.textContent = gas.name;
    nameEl.className   = `fw ${LevelMapper.toTextClass(risk)}`.trim();
  }
  if (countEl)   countEl.textContent   = `${_aiGasIdx + 1} / ${_GAS_META.length}`;
  if (currentEl) {
    currentEl.textContent = val != null ? `${val} ${gas.unit}` : '--';
    currentEl.className   = `big ${LevelMapper.toTextClass(risk)}`.trim();
  }
  if (maxEl) maxEl.textContent = val != null ? `${(val * 1.3).toFixed(2)} ${gas.unit}` : '--';

  _switchGasChart(gas.key);
}

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
// idx 0 = "전체 사용량"(kW 단위, 채널 정격 합 × % 임계치), idx 1+ = 설비별(W 단위, 채널 정격 × % 임계치).
function _switchPowerChart(idx) {
  if (!powerChart || !_aiPowerHist[idx]) return;
  // idx 1+ 은 channel = idx (1~16). idx 0 은 전체 — channel 불필요.
  applyPowerChartUnit(idx === 0 ? 'kW' : 'W', idx);
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
    nameEl.className = `fw ai-equip-name ${LevelMapper.toTextClass(pred.risk_level)}`.trim();
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
    : `<span class="brisk ${LevelMapper.toCssClass(eq.risk_level)}">${LevelMapper.toLabel(eq.risk_level)}</span>`;

  const rowClass = isComm ? '' : ` class="risk-row risk-${LevelMapper.toCssClass(eq.risk_level)}"`;

  return `<tr${rowClass}>
    <td>${eq.name}</td>
    <td>${watt}</td>
    <td>${voltage}</td>
    <td>${current}</td>
    <td>${onoffBadge}</td>
    <td>${riskBadge}</td>
  </tr>`;
}

// 유해가스 패널을 오류/빈 상태로 전환한다.
// 총합·위험도를 '-'로 비우고 테이블을 지운 뒤 메시지를 노출한다.
function _setGasPanelError(msg) {
  const gasWorstName = document.getElementById('gasWorstName');
  const gasWorstRisk = document.getElementById('gasWorstRisk');
  const gasTableBody = document.getElementById('gasTableBody');
  const gasPanelMsg  = document.getElementById('gasPanelMsg');

  if (gasWorstName) gasWorstName.textContent = '-';
  if (gasWorstRisk) { gasWorstRisk.textContent = '-'; gasWorstRisk.className = ''; }
  if (gasPanelMsg)  { gasPanelMsg.textContent = msg; gasPanelMsg.style.display = 'block'; }
  if (gasTableBody) gasTableBody.innerHTML = '';
}

// 유해가스 패널 오류 메시지를 숨긴다.
function _clearGasPanelMsg() {
  const el = document.getElementById('gasPanelMsg');
  if (el) el.style.display = 'none';
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

  // AI 가스 화살표 버튼 이벤트 등록
  document.getElementById('aiGasPrev')?.addEventListener('click', () => {
    _aiGasIdx = (_aiGasIdx - 1 + _GAS_META.length) % _GAS_META.length;
    _renderAIGasNav();
  });
  document.getElementById('aiGasNext')?.addEventListener('click', () => {
    _aiGasIdx = (_aiGasIdx + 1) % _GAS_META.length;
    _renderAIGasNav();
  });

  // 헤더 상단 WebSocket 연결 상태 배지를 갱신한다.
  function setWsStatus(text, cls) {
    if (!wsStatusEl) return;
    wsStatusEl.textContent = text;
    wsStatusEl.className   = `ws-status${cls ? ' ' + cls : ''}`;
  }

  // /ws/sensors/ 에 연결해 1초마다 수신되는 통합 페이로드를 각 패널에 반영한다.
  // shared/ws-client.js의 WSClient를 사용해 alarm-ws.js와 동일 엔드포인트
  // 중복 연결을 방지한다.
  function connect() {
    const ws = WSClient.connect('/ws/sensors/', { attachToken: true });

    ws.onOpen(() => {
      setWsStatus('● 실시간 연결', 'connected');
      _clearPowerPanelMsg();
      MapPanel.setMarkersConnected();
    });

    ws.onMessage((data) => {

      // ── 패널 12: 유해가스 현황 테이블 (9종) ──────────────
      const gasTableBody = document.getElementById('gasTableBody');
      if (data.gas_loading) {
        // FastAPI 가스 수신 대기 중 — skeleton 상태 그대로 유지
      } else if (gasTableBody && data.co !== undefined) {
        _clearGasPanelMsg();

        // 가장 위험한 가스 계산 후 KPI 박스 갱신
        let worstGas = null, worstRisk = 'normal';
        _GAS_META.forEach(g => {
          const risk = data[`${g.key}_risk`] || 'normal';
          if (risk === 'danger' || (risk === 'warning' && worstRisk === 'normal')) {
            worstRisk = risk; worstGas = g;
          }
        });
        const gasWorstName = document.getElementById('gasWorstName');
        const gasWorstRisk = document.getElementById('gasWorstRisk');
        if (gasWorstName) gasWorstName.textContent = worstGas ? worstGas.name : '이상 없음';
        if (gasWorstRisk) {
          gasWorstRisk.textContent = LevelMapper.toLabel(worstRisk);
          gasWorstRisk.className   = `${LevelMapper.toCssClass(worstRisk)}-text`;
        }

        // 가스 리스트 테이블 갱신
        gasTableBody.innerHTML = _GAS_META.map(g => {
          const val      = data[g.key] ?? '-';
          const risk     = data[`${g.key}_risk`] || 'normal';
          const riskCls  = LevelMapper.toCssClass(risk);   // normal → safe, warning → caution
          return `<tr class="gas-row ${riskCls}">
            <td>${g.name}</td><td>${val}</td><td>${g.unit}</td>
            <td><span class="brisk ${riskCls}">${LevelMapper.toLabel(risk)}</span></td>
          </tr>`;
        }).join('');
      }

      // ── 패널 13: AI 예측 — 가스별 히스토리 누적 + 네비게이션 갱신 ──
      if (data.co !== undefined) {
        const tick = nowLabel();
        _aiGasData = data;
        _GAS_META.forEach(g => _pushGasHistory(g.key, tick, data[g.key] ?? null));
        _renderAIGasNav();
      }

      // ── 패널 14: 전력 현황 ────────────────────────────────
      const powerTotal     = document.getElementById('powerTotal');
      const powerChangePct = document.getElementById('powerChangePct');
      const powerTableBody = document.getElementById('powerTableBody');

      if (powerTotal && data.total_power_kw != null)
        powerTotal.textContent = `${data.total_power_kw.toLocaleString()} kW`;

      if (powerChangePct && data.power_change_pct != null) {
        const pct  = data.power_change_pct;
        const sign = pct >= 0 ? '▲ +' : '▼ ';
        powerChangePct.textContent = `기준 대비 ${sign}${pct}%`;
        // 증감률 임계 — 15%+ 위험, 미만은 주의로 매핑
        powerChangePct.className   = LevelMapper.toTextClass(pct >= 15 ? 'danger' : 'warning');
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

      // ── 전력 차트 — 채널별 히스토리 누적 후 현재 채널 렌더 ──
      const tick = nowLabel();
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

      // ── MN-02 맵 — 가스센서·전력장치·작업자 위치 갱신 ─────
      MapPanel.updateGasSensorFromWS(data);
      if (data.equipment) MapPanel.updatePowerDevicesFromWS(data.equipment);
      if (data.worker_positions && typeof MapPanel.updateWorkerPositions === 'function') {
        const posArray = Object.entries(data.worker_positions).map(([id, pos]) => ({
          worker_id: parseInt(id), ...pos,
        }));
        MapPanel.updateWorkerPositions(posArray);
      }

      // ── CM-07 — 알람 팝업 + 이벤트 패널 ─────────────────
      // alarms[]는 DRF가 새 Event 생성 시에만 포함되며, 병합(merge) 틱에서는 빈 배열이다.
      if (Array.isArray(data.alarms) && data.alarms.length > 0) {
        console.log('[알람 수신]', data.alarms.map(a => `${a.risk_level}(new=${a.is_new_event})`));
        data.alarms.forEach(alarm => {
          const alarmData = AlarmMapper.fromSensorsAlarm(alarm);
          // 새 이벤트(danger/warning)만 중앙 팝업 — 조치완료 전 동일 이벤트 재발화는 팝업 없음
          // 2026-05-15 알람 재설계: event_resolved_at 박힌 RESOLVED 신호도 show 로 흘려
          // _handleResolved 분기가 같은 event_id 떠있는 팝업 close + 토스트 처리.
          if (alarm.is_new_event || alarm.event_resolved_at) AlarmPopup.show(alarmData);
          // 정상화는 우하단 토스트
          if (alarm.risk_level === 'normal' && typeof AlarmToast !== 'undefined') {
            AlarmToast.show(alarmData);
          }
          if (typeof EventPanel !== 'undefined') EventPanel.addItem(alarmData);
        });
      }
    });

    // 연결 오류 시 상태 배지를 갱신한다. 재연결은 WSClient가 자동 처리.
    ws.onError(() => {
      setWsStatus('● 연결 오류', 'error');
      _setPowerPanelError('데이터를 불러올 수 없습니다.');
      _setGasPanelError('데이터를 불러올 수 없습니다.');
    });

    // 연결 끊김 시 상태 배지만 갱신. 재연결은 WSClient(3초)가 처리.
    ws.onClose(() => {
      setWsStatus('● 연결 끊김', 'error');
      _setPowerPanelError('데이터를 불러올 수 없습니다.');
      _setGasPanelError('데이터를 불러올 수 없습니다.');
    });
  }

  // /ws/positions/ 에 연결해 IoT 장비로부터 수신된 작업자 위치만 별도로 처리한다.
  // sensors 페이로드에도 worker_positions가 포함되어 있으나,
  // 이 채널은 위치 전용 고빈도 갱신을 위해 분리 운영한다.
  function connectPositions() {
    const wsPos = WSClient.connect('/ws/positions/', { attachToken: true });
    wsPos.onMessage((data) => {
      if (data.worker_positions && typeof MapPanel.updateWorkerPositions === 'function') {
        MapPanel.updateWorkerPositions(data.worker_positions);
      }
    });
  }

  connect();
  connectPositions();
}
