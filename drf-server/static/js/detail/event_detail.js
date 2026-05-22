'use strict';

const STATUS_LABEL = { active: '발생', acknowledged: '확인', in_progress: '조치 중', resolved: '조치 완료' };
const STATUS_CLASS = { active: 'danger', acknowledged: 'warning', in_progress: 'blue', resolved: 'gray' };
const RISK_LABEL   = { danger: '위험', warning: '주의', normal: '정상' };
const RISK_CLASS   = { danger: 'danger', warning: 'warning', normal: 'normal' };

// T2+T6 (2026-05-20) — alarm_type × level 매트릭스 권고 조치 (4 단계 절차).
// 모달의 _ACTION_TEXT (alarm-popup.js, 한 줄) 의 상세 버전. 미정의 type 은 default
// fallback. 사용자 확정 워딩 (2026-05-20) — "AI 추론 디테일 확인" → "센서/설비
// 상세 점검" 운영자 친화 표현.
const RECOMMENDED_ACTIONS = {
  gas_threshold: {
    danger: [
      '작업자 앱 긴급 알림 발송',
      '현장 작업 중지 및 대피 안내',
      '환기 설비 가동',
      '가스 농도 정상 복귀 후 조치 상태 갱신',
    ],
    warning: [
      '작업 중단 + 환기',
      '농도 추이 모니터링',
      '책임자 통보',
      '정상화 후 조치 상태 갱신',
    ],
  },
  gas_anomaly_ai: {
    danger: [
      '해당 구역 작업자 대피',
      '누출 의심 센서 위치 확인',
      '환기 설비 가동',
      '센서/설비 상세 점검',
    ],
    warning: [
      '해당 센서 농도 모니터링',
      '이상 지속 시 점검',
      '센서/설비 상세 점검',
    ],
  },
  power_overload: {
    danger: [
      '해당 설비 즉시 정지',
      '부하·발열 점검',
      '책임자 통보',
      '정상화 후 가동 재개',
    ],
    warning: [
      '설비 부하·온도 확인',
      '부하 추이 모니터링',
      '이상 지속 시 정지',
    ],
  },
  power_anomaly_ai: {
    danger: [
      '설비 정지',
      'AI 이상 패턴 확인 후 센서/설비 상세 점검',
      '정밀 점검 후 책임자 보고',
      '정상화 후 가동 재개',
    ],
    warning: [
      '부하·발열 추이 확인',
      '센서/설비 상세 점검',
      '이상 지속 시 정지',
    ],
  },
  geofence_intrusion: {
    danger: [
      '해당 작업자에게 즉시 이탈 지시',
      '작업자 위치·안전 확인',
      '책임자 통보',
    ],
    warning: [
      '작업자 위치 확인',
      '구역 이탈 안내',
      '책임자 통보',
    ],
  },
  ppe_violation: [
    '작업자에게 PPE 착용 지시',
    'PPE 종류 확인',
    '작업 진행 전 재확인',
  ],
  sensor_fault: [
    '센서 통신 상태 확인',
    '펌웨어·전원 점검',
    '지속 시 설비팀 연락',
  ],
  batch_failed: [
    '배치 로그 확인',
    '원인 분석',
    '재실행',
  ],
  storage_overdue: [
    '보관 주기 도래 항목 확인',
    '점검·갱신',
    '상태 갱신',
  ],
};
const RECOMMENDED_DEFAULT = ['알람 종류 확인', '관리자에게 보고', '조치 후 상태 갱신'];

// T2+T6 — alarm_type 별 "연관 대상 정보" 표시 분기.
// 발생원 모델 + 추가 정보 (worker 등). 기존 "유해가스 센서" 하드코딩 → 도메인별.
const SOURCE_TYPE_LABEL = {
  gas_threshold:      { type: '유해가스 센서', showWorker: false },
  gas_anomaly_ai:     { type: '유해가스 센서', showWorker: false },
  power_overload:     { type: '전력 설비', showWorker: false },
  power_anomaly_ai:   { type: '전력 설비', showWorker: false },
  geofence_intrusion: { type: '위험 구역', showWorker: true },
  ppe_violation:      { type: '작업자', showWorker: true },
  sensor_fault:       { type: '센서', showWorker: false },
  batch_failed:       { type: '시스템 배치', showWorker: false },
  storage_overdue:    { type: '보관 항목', showWorker: false },
};
const SOURCE_TYPE_DEFAULT = { type: '발생원', showWorker: true };

let currentEvent   = null;
let selectedTarget = null;

async function loadEventDetail() {
  try {
    const res = await Auth.apiFetch(`/alerts/api/events/${EVENT_ID}/`);
    if (!res.ok) throw new Error();
    currentEvent = await res.json();
    renderDetail(currentEvent);
  } catch {
    alert('이벤트 정보를 불러올 수 없습니다.');
  }
}

function renderDetail(ev) {
  // 요약 카드
  const rClass = RISK_CLASS[ev.risk_level] ?? 'normal';
  const sClass = STATUS_CLASS[ev.status]   ?? 'gray';
  document.getElementById('summary-risk').textContent   = RISK_LABEL[ev.risk_level] ?? ev.risk_level;
  document.getElementById('summary-risk').className     = `status-badge ${rClass}`;
  document.getElementById('summary-status').textContent = STATUS_LABEL[ev.status] ?? ev.status;
  document.getElementById('summary-status').className   = `status-badge ${sClass}`;
  document.getElementById('summary-source').textContent = ev.source_label ?? '-';
  document.getElementById('summary-time').textContent   = ev.first_detected_at
    ? (typeof TimeFormat !== 'undefined' ? TimeFormat.abs(ev.first_detected_at) : new Date(ev.first_detected_at).toLocaleString('ko-KR'))
    : '-';
  document.getElementById('summary-worker').textContent = ev.worker_name ?? '-';

  // 상세 내용
  document.getElementById('detail-summary').textContent = ev.summary ?? '-';

  // T2+T6 — alarm_type × level 권고 조치 분기. 기존 가스 디폴트 4 단계 (template
  // 정적 HTML) → JS 가 RECOMMENDED_ACTIONS dict lookup 후 동적 렌더.
  renderRecommendation(ev.event_type, ev.risk_level);

  // T2+T6 — 연관 대상 정보 alarm_type 별 분기. 기존 "유해가스 센서" 하드코딩 →
  // SOURCE_TYPE_LABEL dict 의 도메인별 라벨 + 작업자 표시 여부.
  const srcMeta = SOURCE_TYPE_LABEL[ev.event_type] || SOURCE_TYPE_DEFAULT;
  const workerLine = srcMeta.showWorker
    ? ` / 연관 작업자 : ${ev.worker_name ?? '-'}`
    : '';
  document.getElementById('detail-source-info').innerHTML =
    `타입 : ${srcMeta.type}<br>대상 ID : ${ev.source_label ?? '-'}${workerLine}`;

  document.getElementById('detail-trend').textContent =
    `최근 알람 ${ev.alarm_count ?? 0}건 누적`;

  // 조치 상태 변경 버튼 표시
  updateStatusButtons(ev.status);

  // 연관 모니터링 정보 — 같은 SOURCE_TYPE_LABEL 분기 적용.
  document.getElementById('monitor-sensor').textContent =
    `${srcMeta.type} : ${ev.source_label ?? '-'} / 현재 상태 ${RISK_LABEL[ev.risk_level] ?? '-'} / 연결 상태 정상`;
  document.getElementById('monitor-worker').textContent =
    `연관 작업자 : ${ev.worker_name ?? '-'} / 마지막 연결 정상`;
}

// T2+T6 — alarm_type × level 권고 조치 렌더. dict 구조 두 가지 — alarm_type 별
// {danger: [], warning: []} (level 분기) 또는 [...] (level 무관, ppe/sensor_fault 등).
function renderRecommendation(alarmType, level) {
  const el = document.getElementById('detail-recommendation');
  if (!el) return;
  const entry = RECOMMENDED_ACTIONS[alarmType];
  let steps;
  if (Array.isArray(entry)) {
    // level 무관 (ppe_violation / sensor_fault 등)
    steps = entry;
  } else if (entry && entry[level]) {
    steps = entry[level];
  } else {
    steps = RECOMMENDED_DEFAULT;
  }
  // 1. ... <br> 2. ... 형식. innerHTML 사용 — 본 dict 의 값은 정적 (사용자 입력 X)
  // 이라 XSS 위험 없음. event_detail.js 의 기존 innerHTML 패턴과 통일.
  el.innerHTML = steps.map((s, i) => `${i + 1}. ${s}`).join('<br>');
}

function updateStatusButtons(currentStatus) {
  const btnInProgress = document.getElementById('btn-in-progress');
  const btnResolved   = document.getElementById('btn-resolved');
  const changeBtn     = document.getElementById('btn-change');

  // resolved면 버튼 비활성화
  if (currentStatus === 'resolved') {
    btnInProgress.disabled = true;
    btnResolved.disabled   = true;
    changeBtn.disabled     = true;
    document.getElementById('status-change-desc').textContent = '조치 완료된 이벤트입니다.';
    return;
  }

  // 현재 상태에 따라 선택 가능한 버튼 표시
  btnInProgress.classList.remove('selected');
  btnResolved.classList.remove('selected');
  selectedTarget = null;

  document.getElementById('status-change-desc').textContent =
    `현재 상태 : ${STATUS_LABEL[currentStatus] ?? currentStatus} → 변경 예정 : -`;

  btnInProgress.addEventListener('click', () => selectTarget('in_progress'));
  btnResolved.addEventListener('click',   () => selectTarget('resolved'));
}

function selectTarget(target) {
  selectedTarget = target;
  document.getElementById('btn-in-progress').classList.toggle('selected', target === 'in_progress');
  document.getElementById('btn-resolved').classList.toggle('selected',   target === 'resolved');
  document.getElementById('status-change-desc').textContent =
    `현재 상태 : ${STATUS_LABEL[currentEvent.status]} → 변경 예정 : ${STATUS_LABEL[target]}`;
}

// 변경 버튼 클릭 → 모달 표시
document.getElementById('btn-change')?.addEventListener('click', () => {
  if (!selectedTarget) { alert('변경할 상태를 선택해주세요.'); return; }
  const body = document.getElementById('modal-body');
  body.innerHTML = `이벤트 조치 상태를<br><strong>${STATUS_LABEL[selectedTarget]}</strong>으로 변경하고<br>알림을 발송하시겠습니까?`;
  document.getElementById('modal-overlay').style.display = 'flex';
});

document.getElementById('modal-cancel')?.addEventListener('click', () => {
  document.getElementById('modal-overlay').style.display = 'none';
});

document.getElementById('modal-confirm')?.addEventListener('click', async () => {
  document.getElementById('modal-overlay').style.display = 'none';
  try {
    const res = await Auth.apiFetch(`/alerts/api/events/${EVENT_ID}/update_status/`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: selectedTarget }),
    });
    if (!res.ok) {
      const err = await res.json();
      alert(err.error ?? '상태 변경에 실패했습니다.');
      return;
    }
    currentEvent = await res.json();
    renderDetail(currentEvent);
  } catch {
    alert('상태 변경에 실패했습니다.');
  }
});

document.addEventListener('DOMContentLoaded', loadEventDetail);
