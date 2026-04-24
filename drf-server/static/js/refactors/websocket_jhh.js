/* ==========================================================
   websocket.js — FastAPI WebSocket 실시간 데이터 수신 및 패널 업데이트
   출처: dashboard.js initWebSocket
   의존: util.js (levelLabel, nowLabel, pushData)
          charts.js (gasChart, powerChart)
          map-panel.js (MapPanel)
          alarm-popup.js (AlarmPopup)
   수신 페이로드 (fastapi-server/websocket.py 기준):
     co, h2s, o2, level, total_power_mw, power_change_pct,
     equipment[], ai_power_equipment, ai_eta_min,
     ai_max_load_kw, ai_max_load_pct,
     worker_positions{}  ← [추가] IoT 위치 수신 시 갱신되는 작업자 좌표 맵
   ========================================================== */

'use strict';

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
      return;
    }

    ws.onopen = () => setWsStatus('● 실시간 연결', 'connected');

    ws.onmessage = (e) => {
      let data;
      try { data = JSON.parse(e.data); } catch { return; }

      // ── 패널 12: 유해가스 현황 테이블 (9종) ────────────
      const tbody = document.getElementById('gasTableBody');
      if (tbody && data.co !== undefined) {
        const GAS_META = [
          { key: 'co',  name: 'CO (일산화탄소)',       unit: 'ppm' },
          { key: 'h2s', name: 'H₂S (황화수소)',        unit: 'ppm' },
          { key: 'co2', name: 'CO₂ (이산화탄소)',      unit: 'ppm' },
          { key: 'o2',  name: 'O₂ (산소)',             unit: '%'   },
          { key: 'no2', name: 'NO₂ (이산화질소)',      unit: 'ppm' },
          { key: 'so2', name: 'SO₂ (이산화황)',        unit: 'ppm' },
          { key: 'o3',  name: 'O₃ (오존)',             unit: 'ppm' },
          { key: 'nh3', name: 'NH₃ (암모니아)',        unit: 'ppm' },
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

      // ── [추가] MN-02 맵 — 작업자 위치 실시간 반영 ───────
      // worker_positions: { "worker_id": { x, y, facility_id, updated_at } }
      // websocket.py의 /ws/position/ 수신 시 공유 상태가 갱신되어 포함됨
      if (data.worker_positions && typeof MapPanel.updateWorkerPositions === 'function') {
        const posArray = Object.entries(data.worker_positions).map(([id, pos]) => ({
          worker_id: parseInt(id), ...pos
        }));
        MapPanel.updateWorkerPositions(posArray);
      }

      // ── CM-07 — 가스 알람 이벤트 팝업 + 이벤트 패널 추가 ─
      // data.alarms: DRF가 새 Event 생성 시만 포함 (병합이면 빈 배열)
      if (Array.isArray(data.alarms) && data.alarms.length > 0) {
        data.alarms.forEach(alarm => {
          const alarmData = {
            alarm_level: alarm.risk_level,   // 'warning' | 'danger'
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

    ws.onerror = () => setWsStatus('● 연결 오류', 'error');

    ws.onclose = () => {
      setWsStatus('● 연결 끊김', 'error');
      setTimeout(connect, 5000);   // 5초 후 재연결
    };
  }
  function connectPositions() {
    let wsPos;
    try {
      wsPos = new WebSocket('ws://127.0.0.1:8002/ws/positions/');
    } catch {
      return;
    }

    wsPos.onmessage = (e) => {
      let data;
      try { data = JSON.parse(e.data); } catch { return; }

      // 작업자 위치 실시간 업데이트
      if (data.worker_positions) {
        MapPanel.updateWorkerPositions(data.worker_positions);
      }
    };

    wsPos.onclose = () => {
      setTimeout(connectPositions, 5000); // 5초 후 재연결
    };
  }

  connect();
  connectPositions();
}
