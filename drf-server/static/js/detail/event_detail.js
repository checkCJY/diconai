'use strict';

const STATUS_LABEL = { active: '발생', acknowledged: '확인', in_progress: '조치 중', resolved: '조치 완료' };
const STATUS_CLASS = { active: 'danger', acknowledged: 'warning', in_progress: 'blue', resolved: 'gray' };
const RISK_LABEL   = { danger: '위험', warning: '주의', normal: '정상' };
const RISK_CLASS   = { danger: 'danger', warning: 'warning', normal: 'normal' };

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
    ? new Date(ev.first_detected_at).toLocaleString('ko-KR') : '-';
  document.getElementById('summary-worker').textContent = ev.worker_name ?? '-';

  // 상세 내용
  document.getElementById('detail-summary').textContent = ev.summary ?? '-';
  document.getElementById('detail-source-info').innerHTML =
    `타입 : 유해가스 센서<br>대상 ID : ${ev.source_label ?? '-'} / 연관 작업자 : ${ev.worker_name ?? '-'}`;
  document.getElementById('detail-trend').textContent =
    `최근 알람 ${ev.alarm_count ?? 0}건 누적`;

  // 조치 상태 변경 버튼 표시
  updateStatusButtons(ev.status);

  // 연관 모니터링 정보
  document.getElementById('monitor-sensor').textContent =
    `유해가스 센서 : ${ev.source_label ?? '-'} / 현재 상태 ${RISK_LABEL[ev.risk_level] ?? '-'} / 연결 상태 정상`;
  document.getElementById('monitor-worker').textContent =
    `연관 작업자 : ${ev.worker_name ?? '-'} / 마지막 연결 정상`;
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
