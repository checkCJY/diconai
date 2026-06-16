'use strict';

const STATUS_LABEL = { active: '발생', acknowledged: '확인', in_progress: '조치 중', resolved: '조치 완료' };
const RISK_LABEL   = { danger: '위험', warning: '주의', normal: '정상' };
const RISK_CLASS   = { danger: 'danger', warning: 'warning', normal: 'normal' };
const STATUS_CLASS = { active: 'danger', acknowledged: 'warning', in_progress: 'blue', resolved: 'gray' };

const PAGE_SIZE = 20;

let currentStatus = 'pending';
let currentPage = 1;
let currentTotal = 0;
let allCounts = { pending: 0, in_progress: 0, resolved: 0 };

async function loadEvents(statusFilter, page = 1) {
  const tbody = document.getElementById('event-tbody');
  tbody.innerHTML = `<tr><td colspan="7" class="empty-row">불러오는 중...</td></tr>`;

  try {
    const res = await Auth.apiFetch(
      `/alerts/api/events/?status=${statusFilter}&page=${page}&page_size=${PAGE_SIZE}`
    );
    if (!res.ok) throw new Error();
    const data = await res.json();
    const list = Array.isArray(data) ? data : (data.results ?? []);
    currentTotal = (typeof data?.total === 'number') ? data.total : list.length;
    currentPage = (typeof data?.page === 'number') ? data.page : page;

    if (list.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" class="empty-row">이벤트가 없습니다.</td></tr>`;
      renderPagination();
      return;
    }

    // 페이지 내 인덱스가 아닌 전체 인덱스를 No 컬럼에 표시
    const baseIdx = (currentPage - 1) * PAGE_SIZE;
    tbody.innerHTML = list.map((ev, idx) => {
      const time = ev.first_detected_at
        ? (typeof TimeFormat !== 'undefined' ? TimeFormat.abs(ev.first_detected_at) : new Date(ev.first_detected_at).toLocaleString('ko-KR'))
        : '-';
      const rClass  = RISK_CLASS[ev.risk_level]  ?? 'normal';
      const sClass  = STATUS_CLASS[ev.status]    ?? 'gray';
      const isResolved = ev.status === 'resolved';
      return `<tr class="${isResolved ? 'resolved' : ''}" onclick="location.href='/dashboard/monitoring/events/${ev.id}/'">
        <td><span class="status-badge ${sClass}">${STATUS_LABEL[ev.status] ?? ev.status}</span></td>
        <td>${baseIdx + idx + 1}</td>
        <td><span class="status-badge ${rClass}">${RISK_LABEL[ev.risk_level] ?? ev.risk_level}</span></td>
        <td>${ev.event_type === 'gas_threshold' ? '유해가스 초과' : ev.event_type}</td>
        <td>${ev.source_label ?? '-'}</td>
        <td>${time}</td>
        <td style="max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${ev.summary ?? '-'}</td>
      </tr>`;
    }).join('');

    renderPagination();
  } catch {
    tbody.innerHTML = `<tr><td colspan="7" class="empty-row">데이터를 불러올 수 없습니다.</td></tr>`;
    renderPagination();
  }
}

function renderPagination() {
  const el = document.getElementById('pagination');
  if (!el) return;

  const totalPages = Math.max(1, Math.ceil(currentTotal / PAGE_SIZE));
  if (totalPages <= 1) {
    el.innerHTML = '';
    return;
  }

  const startPage = Math.max(1, currentPage - 2);
  const endPage = Math.min(totalPages, startPage + 4);
  const pageButtons = Array.from(
    { length: endPage - startPage + 1 },
    (_, i) => startPage + i
  ).map(p => `
    <button class="${p === currentPage ? 'active' : ''}" onclick="goToPage(${p})">${p}</button>
  `).join('');

  el.innerHTML = `
    <button onclick="goToPage(${currentPage - 1})" ${currentPage === 1 ? 'disabled' : ''}>‹</button>
    ${pageButtons}
    <button onclick="goToPage(${currentPage + 1})" ${currentPage === totalPages ? 'disabled' : ''}>›</button>
  `;
}

function goToPage(page) {
  if (page < 1) return;
  loadEvents(currentStatus, page);
}

async function loadCounts() {
  // 탭 카운트는 page_size=1 로 total 만 받아 N+1 호출 비용 최소화
  const statuses = ['pending', 'in_progress', 'resolved'];
  await Promise.all(statuses.map(async s => {
    try {
      const res = await Auth.apiFetch(`/alerts/api/events/?status=${s}&page=1&page_size=1`);
      if (!res.ok) return;
      const data = await res.json();
      allCounts[s] = (typeof data?.total === 'number')
        ? data.total
        : (Array.isArray(data) ? data.length : (data.results?.length ?? 0));
    } catch {}
  }));
  document.getElementById('cnt-pending').textContent     = allCounts.pending;
  document.getElementById('cnt-in-progress').textContent = allCounts.in_progress;
  document.getElementById('cnt-resolved').textContent    = allCounts.resolved;
}

document.addEventListener('DOMContentLoaded', () => {
  loadCounts();
  loadEvents(currentStatus, 1);

  document.querySelectorAll('.filter-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.filter-tab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentStatus = btn.dataset.status;
      loadEvents(currentStatus, 1);
    });
  });

  document.addEventListener('newAlarmEvent', () => {
    loadCounts();
    loadEvents(currentStatus, currentPage);
  });
});
