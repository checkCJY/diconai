// 시계
function updateClock() {
  const now = new Date();
  const pad = n => String(n).padStart(2, '0');
  const str = `${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
  document.getElementById('clock').textContent = str;
  document.getElementById('lastUpdate').textContent = str;
}
updateClock();
setInterval(updateClock, 1000);

// 맵 탭
document.querySelectorAll('.map-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.map-tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
  });
});

// 가스 더미 데이터
const gasData = [
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

const label = { danger: '위험', caution: '주의', safe: '정상' };

const tbody = document.getElementById('gasTableBody');
gasData.forEach(g => {
  const tr = document.createElement('tr');
  tr.className = `gas-row ${g.level}`;
  tr.innerHTML = `<td>${g.name}</td><td>${g.value}</td><td>${g.unit}</td><td><span class="brisk ${g.level}">${label[g.level]}</span></td>`;
  tbody.appendChild(tr);
});

// API 연결 시 여기 교체
// async function fetchGasData() {
//   const res = await fetch('/api/gas/measurements/');
//   const data = await res.json();
// }


// ── Chart.js 실시간 차트 ────────────────────────────────
const MAX_POINTS = 30; // 슬라이딩 윈도우 (초)

function nowLabel() {
    const d = new Date();
    const pad = n => String(n).padStart(2, '0');
    return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function pushData(chart, label, ...values) {
    chart.data.labels.push(label);
    values.forEach((v, i) => chart.data.datasets[i].data.push(v));
    if (chart.data.labels.length > MAX_POINTS) {
        chart.data.labels.shift();
        chart.data.datasets.forEach(ds => ds.data.shift());
    }
    chart.update('none');
}

const CHART_DEFAULTS = {
    animation: false,
    responsive: true,
    maintainAspectRatio: true,
    plugins: { legend: { labels: { color: '#aaa', font: { size: 10 }, boxWidth: 12 } } },
    scales: {
        x: { ticks: { color: '#666', maxTicksLimit: 6, font: { size: 9 } }, grid: { color: '#2a2a2a' } },
        y: { ticks: { color: '#666', font: { size: 9 } },                   grid: { color: '#2a2a2a' } },
    },
};

// 13번 — 유해가스 AI 예측 차트
const ctxGas = document.getElementById('chartGas');
const gasChart = ctxGas ? new Chart(ctxGas, {
    type: 'line',
    data: {
        labels: [],
        datasets: [
            {
                label: '현재 농도 (ppm)',
                data: [],
                borderColor: '#f59e0b',
                backgroundColor: 'rgba(245,158,11,0.12)',
                tension: 0.4, pointRadius: 2, fill: true,
            },
            {
                label: '예측 최대 농도 (ppm)',
                data: [],
                borderColor: '#ef4444',
                backgroundColor: 'transparent',
                borderDash: [5, 3],
                tension: 0.4, pointRadius: 2, fill: false,
            },
        ],
    },
    options: CHART_DEFAULTS,
}) : null;

// 15번 — 전력 AI 예측 차트
const ctxPower = document.getElementById('chartPower');
const powerChart = ctxPower ? new Chart(ctxPower, {
    type: 'line',
    data: {
        labels: [],
        datasets: [
            {
                label: '예상 최대 부하 (kW)',
                data: [],
                borderColor: '#ef4444',
                backgroundColor: 'rgba(239,68,68,0.12)',
                tension: 0.4, pointRadius: 2, fill: true,
            },
        ],
    },
    options: CHART_DEFAULTS,
}) : null;

// ── Y축 스케일 조절 ─────────────────────────────────────
const scaleState = { gas: null, power: null };

function adjustYScale(key, chart, direction) {
    if (!chart) return;
    const labelEl = document.getElementById(key + 'ScaleVal');
    // direction: +1 = 범위 축소(확대), -1 = 범위 확대(축소), 0 = 자동 리셋
    if (direction === 0) {
        scaleState[key] = null;
        chart.options.scales.y.max = undefined;
        chart.options.scales.y.min = undefined;
        if (labelEl) labelEl.textContent = '자동';
    } else {
        const current = scaleState[key] ?? chart.scales.y.max;
        const factor  = direction > 0 ? 0.75 : 1.35;
        scaleState[key] = Math.max(1, Math.round(current * factor));
        chart.options.scales.y.max = scaleState[key];
        if (labelEl) labelEl.textContent = scaleState[key].toLocaleString();
    }
    chart.update('none');
}

// 버튼 이벤트 등록
document.getElementById('gasZoomIn') ?.addEventListener('click', () => adjustYScale('gas',   gasChart,   +1));
document.getElementById('gasZoomOut')?.addEventListener('click', () => adjustYScale('gas',   gasChart,   -1));
document.getElementById('gasReset')  ?.addEventListener('click', () => adjustYScale('gas',   gasChart,    0));

document.getElementById('powerZoomIn') ?.addEventListener('click', () => adjustYScale('power', powerChart, +1));
document.getElementById('powerZoomOut')?.addEventListener('click', () => adjustYScale('power', powerChart, -1));
document.getElementById('powerReset')  ?.addEventListener('click', () => adjustYScale('power', powerChart,  0));

const ws = new WebSocket("ws://localhost:8001/ws/sensors/");
const statusDiv = document.getElementById("status");
const outputPre = document.getElementById("output");

ws.onopen = () => statusDiv.innerText = "🟢 연결됨 (데이터 수신 중...)";
ws.onclose = () => {
    statusDiv.innerText = "🔴 연결 끊김";
    statusDiv.style.color = "red";
};

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);

    // Panel 12: 유해가스 현황 테이블
    const gases = [
        { name: "CO (일산화탄소)", value: data.co,  unit: "ppm", risk: data.co  > 50   ? "위험" : "정상" },
        { name: "H₂S (황화수소)",  value: data.h2s, unit: "ppm", risk: data.h2s > 10   ? "위험" : "정상" },
        { name: "O₂ (산소)",       value: data.o2,  unit: "%",   risk: data.o2  < 19.5 ? "위험" : "정상" },
    ];
    const tbody = document.getElementById("gasTableBody");
    if (tbody) {
        tbody.innerHTML = gases.map(g =>
            `<tr>
                <td>${g.name}</td>
                <td>${g.value}</td>
                <td>${g.unit}</td>
                <td><span class="brisk ${g.risk === "위험" ? "danger" : "safe"}">${g.risk}</span></td>
            </tr>`
        ).join("");
    }

    // Panel 13: AI 예측 — CO 현재 농도 업데이트 (12시간 예측은 현재값 × 1.5 시뮬레이션)
    const coRisk = data.co > 50;
    const aiGasName   = document.getElementById("aiGasName");
    const aiCurrentVal = document.getElementById("aiCurrentVal");
    const aiMaxVal     = document.getElementById("aiMaxVal");
    if (aiGasName) {
        aiGasName.className = coRisk ? "danger-text fw" : "caution-text fw";
    }
    if (aiCurrentVal) {
        aiCurrentVal.textContent = data.co + " ppm";
        aiCurrentVal.className = "big " + (coRisk ? "danger-text" : "caution-text");
    }
    if (aiMaxVal) {
        aiMaxVal.textContent = Math.round(data.co * 1.5) + " ppm";
    }

    // Panel 14: 스마트 전력 시스템 위험 현황
    const powerTotal = document.getElementById("powerTotal");
    const powerChangePct = document.getElementById("powerChangePct");
    const powerTableBody = document.getElementById("powerTableBody");

    if (powerTotal && data.total_power_mw !== undefined) {
        powerTotal.textContent = data.total_power_mw.toLocaleString() + " MW";
    }
    if (powerChangePct && data.power_change_pct !== undefined) {
        const pct = data.power_change_pct;
        const sign = pct >= 0 ? "▲ +" : "▼ ";
        powerChangePct.textContent = `기준 대비 ${sign}${pct}%`;
        powerChangePct.className = pct >= 15 ? "danger-text" : "caution-text";
        powerChangePct.style.cssText = "font-size:11px;margin-bottom:4px;";
    }
    if (powerTableBody && data.equipment) {
        const levelLabel = { danger: "위험", caution: "주의", safe: "정상" };
        powerTableBody.innerHTML = data.equipment.map(eq =>
            `<tr>
                <td>${eq.name}</td>
                <td>${eq.mwh} MWh</td>
                <td>${eq.temp}°C</td>
                <td><span class="brisk ${eq.level}">${levelLabel[eq.level]}</span></td>
            </tr>`
        ).join("");
    }

    // Panel 15: AI 예측 — 스마트 전력 시스템 위험
    const aiPowerEquipName = document.getElementById("aiPowerEquipName");
    const aiPowerEta       = document.getElementById("aiPowerEta");
    const aiPowerMaxLoad   = document.getElementById("aiPowerMaxLoad");

    if (aiPowerEquipName && data.ai_power_equipment) {
        aiPowerEquipName.textContent = data.ai_power_equipment;
    }
    if (aiPowerEta && data.ai_eta_min !== undefined) {
        aiPowerEta.textContent = data.ai_eta_min + " 분 뒤";
    }
    if (aiPowerMaxLoad && data.ai_max_load_kw !== undefined) {
        aiPowerMaxLoad.innerHTML =
            `${data.ai_max_load_kw.toLocaleString()} kW ` +
            `<span style="font-size:11px;font-weight:400;">(정상 대비 ${data.ai_max_load_pct}%)</span>`;
    }

    // 차트 실시간 업데이트
    const tick = nowLabel();
    if (gasChart)   pushData(gasChart,   tick, data.co, Math.round(data.co * 1.5));
    if (powerChart) pushData(powerChart, tick, data.ai_max_load_kw);
};
