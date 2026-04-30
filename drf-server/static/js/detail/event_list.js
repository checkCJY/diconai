'use strict';

const STATUS_LABEL = { active: '발생', acknowledged: '확인', in_progress: '조치 중', resolved: '조치 완료' };
const RISK_LABEL   = { danger: '위험', warning: '주의', normal: '정상' };
const RISK_CLASS   = { danger: 'danger', warning: 'warning', normal: 'normal' };
const STATUS_CLASS = { active: 'danger', acknowledged: 'warning', in_progress: 'blue', resolved: 'gray' };

let currentStatus = 'pending';
let allCounts = { pending: 0, in_progress: 0, resolved: 0 };

async function loadEvents(statusFilter) {
  const tbody = document.getElementById('event-tbody');
  tbody.innerHTML = `<tr><td colspan="7" class="empty-row">불러오는 중...</td></tr>`;

  try {
    const res  = await Auth.apiFetch(`/alerts/api/events/?status=${statusFilter}`);
    if (!res.ok) throw new Error();
    const data = await res.json();
    const list = Array.isArray(data) ? data : (data.results ?? []);

    if (list.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" class="empty-row">이벤트가 없습니다.</td></tr>`;
      return;
    }

    tbody.innerHTML = list.map((ev, idx) => {
      const time = ev.first_detected_at
        ? new Date(ev.first_detected_at).toLocaleString('ko-KR')
        : '-';
      const rClass  = RISK_CLASS[ev.risk_level]  ?? 'normal';
      const sClass  = STATUS_CLASS[ev.status]    ?? 'gray';
      const isResolved = ev.status === 'resolved';
      return `<tr class="${isResolved ? 'resolved' : ''}" onclick="location.href='/dashboard/monitoring/events/${ev.id}/'">
        <td><span class="status-badge ${sClass}">${STATUS_LABEL[ev.status] ?? ev.status}</span></td>
        <td>${idx + 1}</td>
        <td><span class="status-badge ${rClass}">${RISK_LABEL[ev.risk_level] ?? ev.risk_level}</span></td>
        <td>${ev.event_type === 'gas_threshold' ? '유해가스 초과' : ev.event_type}</td>
        <td>${ev.source_label ?? '-'}</td>
        <td>${time}</td>
        <td style="max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${ev.summary ?? '-'}</td>
      </tr>`;
    }).join('');

  } catch {
    tbody.innerHTML = `<tr><td colspan="7" class="empty-row">데이터를 불러올 수 없습니다.</td></tr>`;
  }
}

async function loadCounts() {
  const statuses = ['pending', 'in_progress', 'resolved'];
  await Promise.all(statuses.map(async s => {
    try {
      const res  = await Auth.apiFetch(`/alerts/api/events/?status=${s}`);
      if (!res.ok) return;
      const data = await res.json();
      const list = Array.isArray(data) ? data : (data.results ?? []);
      allCounts[s] = list.length;
    } catch {}
  }));
  document.getElementById('cnt-pending').textContent     = allCounts.pending;
  document.getElementById('cnt-in-progress').textContent = allCounts.in_progress;
  document.getElementById('cnt-resolved').textContent    = allCounts.resolved;
}

document.addEventListener('DOMContentLoaded', () => {
  loadCounts();
  loadEvents(currentStatus);

  document.querySelectorAll('.filter-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.filter-tab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentStatus = btn.dataset.status;
      loadEvents(currentStatus);
    });
  });

  document.addEventListener('newAlarmEvent', () => {
    loadCounts();
    loadEvents(currentStatus);
  });
});
