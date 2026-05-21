/**
 * 데이터 보관 정책 관리 페이지 JS
 *
 * [흐름]
 * 1. 페이지 로드 → fetchPolicies() → 테이블 렌더링
 * 2. "수정" 클릭 → openModal(id) → GET detail API → 모달 폼 채우기 + 삭제 예정 행 수 표시
 * 3. raw_retention_days 입력 변경 (debounce 600ms) → fetchPreview() → 경고 배너 업데이트
 * 4. "저장" 클릭 → PATCH API → 성공 시 테이블 갱신 + 모달 닫기
 *
 * [경고 배너 조건]
 * raw_days_reduced=true && affected_rows > 0 → 주황색 경고 배너 표시
 * "저장 시 약 N행이 삭제됩니다. 되돌릴 수 없습니다."
 */

const API_BASE = '/api/admin/retention-policies/';

// 현재 편집 중인 정책 ID + 원래 보관 기간 (기간 감소 여부 판단용)
let currentPolicyId = null;
let originalRawDays = null;
let originalHistoryDays = null;
let previewDebounceTimer = null;
// 마지막 preview API 응답 — 저장 전 확인창에서 삭제 예정 행 수 표시용
let lastPreviewResult = null;

// ── 페이지 초기화 ────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  fetchPolicies();
  bindModalEvents();
});

// ── 정책 목록 조회 ───────────────────────────────────────────────
async function fetchPolicies() {
  try {
    const res = await authedFetch(API_BASE);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    renderTable(data.results);
    document.getElementById('totalCount').textContent = data.count;
  } catch (e) {
    document.getElementById('policyTableBody').innerHTML =
      `<tr><td colspan="8" class="empty-msg">목록을 불러오지 못했습니다.</td></tr>`;
  }
}

// ── 테이블 렌더링 ────────────────────────────────────────────────
function renderTable(policies) {
  const tbody = document.getElementById('policyTableBody');
  if (!policies.length) {
    tbody.innerHTML = '<tr><td colspan="8" class="empty-msg">등록된 정책이 없습니다.</td></tr>';
    return;
  }

  tbody.innerHTML = policies.map(p => `
    <tr>
      <td>${p.device_type_display}</td>
      <td>${p.data_category_display}</td>
      <td><span class="rp-days">${p.raw_retention_days}<span>일</span></span></td>
      <td><span class="rp-days">${p.history_retention_days}<span>일</span></span></td>
      <td>${p.delete_cycle_display}</td>
      <td>
        <span class="${p.is_active ? 'rp-badge-active' : 'rp-badge-inactive'}">
          ${p.is_active ? '활성' : '비활성'}
        </span>
      </td>
      <td>${formatDate(p.updated_at)}</td>
      <td>
        <button class="btn-edit" onclick="openModal(${p.id})">수정</button>
      </td>
    </tr>
  `).join('');
}

// ── 편집 모달 열기 ───────────────────────────────────────────────
async function openModal(policyId) {
  currentPolicyId = policyId;
  clearErrors();
  showWarningBanner(false);
  setCurrentCount('불러오는 중...');

  document.getElementById('editModal').style.display = 'flex';

  try {
    const res = await authedFetch(`${API_BASE}${policyId}/`);
    if (!res.ok) throw new Error();
    const p = await res.json();

    originalRawDays = p.raw_retention_days;
    originalHistoryDays = p.history_retention_days;

    // 모달 제목 + 설명
    document.getElementById('modalTitle').textContent =
      `${p.device_type_display} — ${p.data_category_display}`;
    document.getElementById('modalDesc').textContent =
      `카테고리: ${p.data_category}`;

    // 폼 값 채우기
    document.getElementById('inputRawDays').value = p.raw_retention_days;
    document.getElementById('inputHistoryDays').value = p.history_retention_days;
    document.getElementById('inputDeleteCycle').value = p.delete_cycle;
    document.getElementById('inputIsActive').checked = p.is_active;
    document.getElementById('toggleLabel').textContent = p.is_active ? '활성' : '비활성';
    document.getElementById('inputMemo').value = p.memo || '';

    // 현재 삭제 예정 행 수 표시
    renderCurrentCount(p.affected_rows);

  } catch (e) {
    setCurrentCount('불러오기 실패');
  }
}

// ── 현재 삭제 예정 행 수 렌더링 ─────────────────────────────────
function renderCurrentCount(count) {
  const el = document.getElementById('currentCount');
  if (count === null || count === undefined) {
    el.textContent = '계산 불가';
    el.className = 'rp-info-value';
  } else if (count === 0) {
    el.textContent = '0행 (삭제 대상 없음)';
    el.className = 'rp-info-value safe';
  } else {
    el.textContent = `${count.toLocaleString()}행`;
    el.className = 'rp-info-value danger';
  }
}

function setCurrentCount(text) {
  const el = document.getElementById('currentCount');
  el.textContent = text;
  el.className = 'rp-info-value';
}

// ── 보관 기간 입력 변경 시 미리보기 (debounce) ───────────────────
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('inputRawDays').addEventListener('input', () => {
    clearTimeout(previewDebounceTimer);
    previewDebounceTimer = setTimeout(fetchPreview, 600);
  });

  document.getElementById('inputHistoryDays').addEventListener('input', () => {
    clearTimeout(previewDebounceTimer);
    previewDebounceTimer = setTimeout(fetchPreview, 600);
  });

  // 토글 라벨 연동
  document.getElementById('inputIsActive').addEventListener('change', function () {
    document.getElementById('toggleLabel').textContent = this.checked ? '활성' : '비활성';
  });
});

async function fetchPreview() {
  if (!currentPolicyId) return;
  const rawDays = parseInt(document.getElementById('inputRawDays').value);
  const historyDays = parseInt(document.getElementById('inputHistoryDays').value);
  if (isNaN(rawDays) || rawDays < 1) {
    showWarningBanner(false);
    lastPreviewResult = null;
    return;
  }

  const params = new URLSearchParams({ raw_days: rawDays });
  if (!isNaN(historyDays) && historyDays >= 1) params.append('history_days', historyDays);

  try {
    const res = await authedFetch(
      `${API_BASE}${currentPolicyId}/preview/?${params}`
    );
    if (!res.ok) return;
    const data = await res.json();
    lastPreviewResult = data;

    // 입력값 기준 삭제 예정 행 수로 count 박스 실시간 갱신
    renderCurrentCount(data.affected_rows);

    // 기간이 줄고 삭제될 행이 있을 때만 경고 배너 표시
    if (data.days_reduced && data.affected_rows > 0) {
      showWarningBanner(
        true,
        `저장 시 약 ${data.affected_rows.toLocaleString()}행이 삭제됩니다. ` +
        `이 작업은 되돌릴 수 없습니다.`
      );
    } else {
      showWarningBanner(false);
    }
  } catch (e) {
    // 미리보기 실패는 조용히 무시
  }
}

function showWarningBanner(show, text = '') {
  const banner = document.getElementById('warningBanner');
  banner.style.display = show ? 'flex' : 'none';
  if (show) document.getElementById('warningText').textContent = text;
}

// ── 저장 ─────────────────────────────────────────────────────────
async function savePolicy() {
  if (!currentPolicyId) return;
  clearErrors();

  const rawDays = parseInt(document.getElementById('inputRawDays').value);
  const historyDays = parseInt(document.getElementById('inputHistoryDays').value);
  const deleteCycle = document.getElementById('inputDeleteCycle').value;
  const isActive = document.getElementById('inputIsActive').checked;
  const memo = document.getElementById('inputMemo').value.trim();

  // 클라이언트 유효성
  let hasError = false;
  if (!rawDays || rawDays < 1) {
    document.getElementById('errRawDays').textContent = '1 이상의 숫자를 입력하세요.';
    hasError = true;
  }
  if (!historyDays || historyDays < 1) {
    document.getElementById('errHistoryDays').textContent = '1 이상의 숫자를 입력하세요.';
    hasError = true;
  }
  if (historyDays < rawDays) {
    document.getElementById('errHistoryDays').textContent =
      '이력 보관 기간은 원천 보관 기간 이상이어야 합니다.';
    hasError = true;
  }
  if (hasError) return;

  // 저장 전 확인창 — 기간이 줄고 삭제 예정 행이 있을 때
  const willReduce = lastPreviewResult?.days_reduced && lastPreviewResult?.affected_rows > 0
    || (rawDays < originalRawDays || historyDays < originalHistoryDays);
  if (willReduce) {
    const count = lastPreviewResult.affected_rows.toLocaleString();
    const confirmed = window.confirm(
      `⚠ 보관 기간을 줄이면 저장 시 약 ${count}행이 즉시 삭제됩니다.\n` +
      `이 작업은 되돌릴 수 없습니다.\n\n` +
      `정말 저장하시겠습니까?`
    );
    if (!confirmed) return;
  }

  const btnSave = document.getElementById('btnSave');
  btnSave.disabled = true;
  btnSave.textContent = '저장 중...';

  try {
    const res = await authedFetch(`${API_BASE}${currentPolicyId}/`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        raw_retention_days: rawDays,
        history_retention_days: historyDays,
        delete_cycle: deleteCycle,
        is_active: isActive,
        memo,
      }),
    });

    if (!res.ok) {
      const err = await res.json();
      const msg = err.non_field_errors?.[0] || err.detail || '저장에 실패했습니다.';
      document.getElementById('errGlobal').textContent = msg;
      return;
    }

    closeModal();
    fetchPolicies();

  } finally {
    btnSave.disabled = false;
    btnSave.textContent = '저장';
  }
}

// ── 모달 닫기 / 이벤트 바인딩 ────────────────────────────────────
function closeModal() {
  document.getElementById('editModal').style.display = 'none';
  currentPolicyId = null;
  originalRawDays = null;
  originalHistoryDays = null;
  lastPreviewResult = null;
  clearErrors();
  showWarningBanner(false);
}

function clearErrors() {
  ['errRawDays', 'errHistoryDays', 'errGlobal'].forEach(id => {
    document.getElementById(id).textContent = '';
  });
}

function bindModalEvents() {
  document.getElementById('btnModalClose').addEventListener('click', closeModal);
  document.getElementById('btnCancel').addEventListener('click', closeModal);
  document.getElementById('btnSave').addEventListener('click', savePolicy);

  // 오버레이 클릭 시 닫기
  document.getElementById('editModal').addEventListener('click', (e) => {
    if (e.target === document.getElementById('editModal')) closeModal();
  });
}

// ── 유틸 ─────────────────────────────────────────────────────────
function formatDate(isoStr) {
  if (!isoStr) return '-';
  const d = new Date(isoStr);
  return `${d.getFullYear()}년 ${d.getMonth() + 1}월 ${d.getDate()}일`;
}

/**
 * JWT 인증 포함 fetch 헬퍼.
 * 프로젝트 공통 Auth 모듈(window.Auth)에서 토큰을 가져온다.
 */
async function authedFetch(url, options = {}) {
  const token = window.Auth?.getAccessToken?.() || localStorage.getItem('access_token');
  return fetch(url, {
    ...options,
    headers: {
      ...(options.headers || {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
}
