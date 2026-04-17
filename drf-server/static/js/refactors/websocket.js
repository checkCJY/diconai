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
     ai_max_load_kw, ai_max_load_pct
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
