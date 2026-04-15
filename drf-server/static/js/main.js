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
