'use strict';

/* ── 상태 뱃지 색상 매핑 ── */
const STATUS_CLASS = {
  active:       'badge-danger',
  acknowledged: 'badge-warning',
  in_progress:  'badge-info',
  resolved:     'badge-success',
};

const PAGE_SIZE = 20;
let currentPage = 1;
let currentSort = 'desc'; // desc=최신순, asc=오래된순

/* ── 날짜 포맷 헬퍼 ── */
function fmtDatetime(iso) {
  if (!iso) return '-';
  // TimeFormat 유틸이 있으면 사용, 없으면 브라우저 기본 포맷
  if (typeof TimeFormat !== 'undefined') return TimeFormat.abs(iso);
  return new Date(iso).toLocaleString('ko-KR');
}

/* ── API 호출 및 테이블 렌더 ── */
async function loadEvents(page = 1) {
  currentPage = page;

  const date      = document.getElementById('filterDate').value;
  const eventType = document.getElementById('filterEventType').value;
  const status    = document.getElementById('filterStatus').value;

  // 정렬: desc → -first_detected_at (기본), asc → first_detected_at
  const ordering = currentSort === 'asc' ? 'first_detected_at' : '-first_detected_at';

  const params = new URLSearchParams({ page, page_size: PAGE_SIZE, ordering });
  if (date)      params.set('date', date);
  if (eventType) params.set('event_type', eventType);
  if (status)    params.set('status', status);

  const tbody = document.getElementById('eventTableBody');
  tbody.innerHTML = '<tr><td colspan="6" class="empty-state">불러오는 중...</td></tr>';

  try {
    const res = await Auth.apiFetch(`/api/admin/alerts/events/?${params}`);
    if (!res.ok) throw new Error();
    const data = await res.json();

    document.getElementById('totalCount').textContent = data.count ?? 0;
    renderTable(data.results ?? []);
    renderPagination(data.count ?? 0, page);
    updatePageInfo(data.count ?? 0, page);
  } catch {
    tbody.innerHTML = '<tr><td colspan="6" class="empty-state">데이터를 불러올 수 없습니다.</td></tr>';
  }
}

/* ── 테이블 행 렌더 ── */
function renderTable(items) {
  const tbody = document.getElementById('eventTableBody');

  if (!items.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="empty-state">조회된 이벤트가 없습니다.</td></tr>';
    return;
  }

  tbody.replaceChildren(
    ...items.map(ev => {
      const tr = document.createElement('tr');
      tr.style.cursor = 'pointer';

      // 이벤트 상태 뱃지
      const badgeCls = STATUS_CLASS[ev.status] ?? 'badge-info';

      tr.innerHTML = `
        <td>${fmtDatetime(ev.first_detected_at)}</td>
        <td>${ev.event_type_display ?? ev.event_type}</td>
        <td>${ev.source_label ?? '-'}</td>
        <td>${ev.policy_name ?? '-'}</td>
        <td><span class="badge ${badgeCls}">${ev.status_display ?? ev.status}</span></td>
        <td class="summary-cell">${ev.summary ?? '-'}</td>
      `;

      // 행 클릭 → 상세 팝업
      tr.addEventListener('click', () => showDetail(ev));
      return tr;
    })
  );
}

/* ── 페이지네이션 렌더 ── */
function renderPagination(total, page) {
  const totalPages = Math.ceil(total / PAGE_SIZE);
  const container  = document.getElementById('pagination');
  container.replaceChildren();

  if (totalPages <= 1) return;

  // 이전 버튼
  const prev = document.createElement('button');
  prev.textContent = '‹';
  prev.disabled = page <= 1;
  prev.addEventListener('click', () => loadEvents(page - 1));
  container.appendChild(prev);

  // 페이지 번호 — 최대 5개 노출
  const start = Math.max(1, page - 2);
  const end   = Math.min(totalPages, start + 4);
  for (let i = start; i <= end; i++) {
    const btn = document.createElement('button');
    btn.textContent = i;
    if (i === page) btn.classList.add('active');
    btn.addEventListener('click', () => loadEvents(i));
    container.appendChild(btn);
  }

  // 다음 버튼
  const next = document.createElement('button');
  next.textContent = '›';
  next.disabled = page >= totalPages;
  next.addEventListener('click', () => loadEvents(page + 1));
  container.appendChild(next);
}

/* ── 페이지 정보 텍스트 갱신 ── */
function updatePageInfo(total, page) {
  const from = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const to   = Math.min(page * PAGE_SIZE, total);
  document.getElementById('pageInfo').textContent = `${from} - ${to} / ${total}`;
}

/* ── 상세 팝업 표시 ── */
function showDetail(ev) {
  // 기본 정보 채우기
  document.getElementById('detailEventType').textContent    = ev.event_type_display ?? ev.event_type;
  document.getElementById('detailSourceLabel').textContent  = ev.source_label ?? '-';
  document.getElementById('detailPolicyName').textContent   = ev.policy_name ?? '-';
  document.getElementById('detailFirstDetected').textContent = fmtDatetime(ev.first_detected_at);
  document.getElementById('detailResolvedAt').textContent   = ev.resolved_at ? fmtDatetime(ev.resolved_at) : '-';

  // 이벤트 상태 — 뱃지로 표시
  const statusEl  = document.getElementById('detailStatus');
  const badgeCls  = STATUS_CLASS[ev.status] ?? 'badge-info';
  statusEl.innerHTML = `<span class="badge ${badgeCls}">${ev.status_display ?? ev.status}</span>`;

  // 발생 내용·상태 메모 (XSS 방어 — textContent 사용)
  document.getElementById('detailDescription').textContent = ev.description || '-';
  document.getElementById('detailStatusNote').textContent  = ev.status_note  || '-';

  document.getElementById('detailOverlay').style.display = 'flex';
}

function closeDetail() {
  document.getElementById('detailOverlay').style.display = 'none';
}

/* ── 이벤트 리스너 ── */
document.addEventListener('DOMContentLoaded', () => {
  // 오늘 날짜를 기본값으로 설정
  const today = new Date().toISOString().split('T')[0];
  document.getElementById('filterDate').value = today;

  // 초기 로드
  loadEvents(1);

  document.getElementById('btnSearch').addEventListener('click', () => loadEvents(1));

  document.getElementById('btnReset').addEventListener('click', () => {
    document.getElementById('filterDate').value      = today;
    document.getElementById('filterEventType').value = '';
    document.getElementById('filterStatus').value    = '';
    document.getElementById('sortSelect').value      = 'desc';
    currentSort = 'desc';
    loadEvents(1);
  });

  document.getElementById('sortSelect').addEventListener('change', (e) => {
    currentSort = e.target.value;
    loadEvents(1);
  });

  // 팝업 닫기 버튼 두 개 (헤더 × 버튼, 하단 닫기 버튼)
  document.getElementById('btnDetailClose').addEventListener('click',  closeDetail);
  document.getElementById('btnDetailClose2').addEventListener('click', closeDetail);

  // 팝업 오버레이 클릭으로도 닫기
  document.getElementById('detailOverlay').addEventListener('click', (e) => {
    if (e.target === e.currentTarget) closeDetail();
  });
});
