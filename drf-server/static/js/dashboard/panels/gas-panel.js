/* ==========================================================
   gas-panel.js — 유해가스 현황 테이블 초기 렌더링 (패널 12)
   출처: dashboard.js GAS_INIT_DATA + renderGasTable
   의존: util.js (levelLabel)
   ========================================================== */

'use strict';

// ──────────────────────────────────────────────────────────
// 가스 더미 데이터 초기 렌더 (패널 12 초기값)
// WebSocket 수신 후에는 websocket.js 가 tbody를 덮어씀
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
