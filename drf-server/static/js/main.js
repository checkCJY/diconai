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
};
