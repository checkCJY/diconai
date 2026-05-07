/**
 * static/js/admin/gas/gas_data.js
 * 유해가스 센서 데이터 관리 어드민 페이지 — 전체 인터랙션 담당
 *
 * 주요 역할:
 *   1. 필터 값 수집 → API 호출 → 테이블 렌더링
 *   2. 빠른 날짜 버튼(오늘/어제/최근7일/이번달) → 날짜 입력 자동 채우기
 *   3. 페이지네이션 버튼 생성 및 클릭 처리
 *   4. CSV 내보내기 버튼 클릭 → export 엔드포인트로 파일 다운로드
 *
 * API 의존:
 *   GET /api/admin/gas-data/         — 목록 (GasDataAdminListView)
 *   GET /api/admin/gas-data/export/  — CSV 파일 다운로드 (GasDataAdminExportView)
 *   GET /api/admin/gas-data/sensors/ — 센서 드롭다운 옵션 (GasDataAdminSensorListView)
 */

(function () {
  'use strict';

  // ── 상태 ──────────────────────────────────────────────────────────────
  // 현재 적용된 필터와 페이지 상태를 모듈 스코프 변수로 관리한다.
  // 버튼 클릭, 페이지 이동 모두 이 상태를 변경 후 fetchData()를 호출한다.
  let currentPage = 1;
  const PAGE_SIZE = 20;

  // API 베이스 경로
  const API_BASE = '/api/admin/gas-data/';

  // 가스 컬럼 순서 — 백엔드 gas_data_admin.py GAS_COLS와 반드시 일치해야 한다
  const GAS_COLS = ['co', 'h2s', 'co2', 'o2', 'no2', 'so2', 'o3', 'nh3', 'voc'];

  // 위험도 → 뱃지 CSS 클래스 매핑
  const RISK_BADGE = {
    danger:  'badge badge-orange',
    warning: 'badge badge-purple',
    normal:  'badge badge-green',
  };

  const RISK_LABEL = {
    danger:  '위험',
    warning: '주의',
    normal:  '정상',
  };

  // ── DOM 참조 ──────────────────────────────────────────────────────────
  const elDateFrom   = document.getElementById('dateFrom');
  const elDateTo     = document.getElementById('dateTo');
  const elSensor     = document.getElementById('sensorFilter');
  const elOrdering   = document.getElementById('orderingFilter');
  const elBtnSearch  = document.getElementById('btnSearch');
  const elBtnReset   = document.getElementById('btnReset');
  const elBtnExport  = document.getElementById('btnExport');
  const elTableBody  = document.getElementById('gasTableBody');
  const elTotalCount = document.getElementById('totalCount');
  const elPageInfo   = document.getElementById('pageInfo');
  const elPagination = document.getElementById('pagination');

  // ── 필터 값 수집 ──────────────────────────────────────────────────────
  /**
   * 현재 입력된 필터 값을 URLSearchParams 객체로 반환한다.
   * fetchData()와 exportCsv() 양쪽에서 호출해 항상 같은 필터를 사용한다.
   * → 화면에서 보이는 데이터와 CSV 내용이 항상 일치하는 것을 보장하는 핵심 함수.
   *
   * @param {number|null} page - 요청할 페이지 번호 (export는 null로 전달 → 파라미터 생략)
   */
  function buildParams(page) {
    const p = new URLSearchParams();
    if (elDateFrom.value) p.set('date_from', elDateFrom.value);
    if (elDateTo.value)   p.set('date_to',   elDateTo.value);
    if (elSensor.value)   p.set('sensor',    elSensor.value);
    if (elOrdering.value) p.set('ordering',  elOrdering.value);
    if (page !== null)    p.set('page',      page);
    p.set('page_size', PAGE_SIZE);
    return p;
  }

  // ── 데이터 fetch + 테이블 렌더 ────────────────────────────────────────
  /**
   * 현재 필터 상태로 API를 호출하고 테이블과 페이지네이션을 갱신한다.
   *
   * 흐름:
   *   buildParams(currentPage)
   *     → fetch GET /api/admin/gas-data/?date_from=...&page=...
   *     → renderTable(data.results)
   *     → renderPagination(data.total, data.page, data.page_size)
   *
   * 에러 발생 시 테이블에 에러 메시지 행을 표시하고 종료한다.
   */
  function fetchData() {
    const params = buildParams(currentPage);
    elTableBody.innerHTML = '<tr><td colspan="12" class="empty-msg">불러오는 중...</td></tr>';

    Auth.apiFetch(API_BASE + '?' + params.toString())
      .then(function (res) {
        if (!res.ok) throw new Error('서버 오류 ' + res.status);
        return res.json();
      })
      .then(function (data) {
        renderTable(data.results);
        renderPagination(data.total, data.page, data.page_size);
        elTotalCount.textContent = data.total.toLocaleString();
      })
      .catch(function (err) {
        elTableBody.innerHTML =
          '<tr><td colspan="12" class="empty-msg">데이터를 불러오지 못했습니다. (' + err.message + ')</td></tr>';
      });
  }

  // ── 테이블 렌더 ───────────────────────────────────────────────────────
  /**
   * API 응답의 results 배열을 받아 <tbody>를 다시 그린다.
   *
   * 가스 값이 null이면 "-"로 표시 (결측 또는 미측정).
   * 최고 위험도는 RISK_BADGE/RISK_LABEL 매핑으로 뱃지 스타일을 적용한다.
   *
   * @param {Array} rows - 백엔드 _serialize_row() 결과 객체 배열
   */
  function renderTable(rows) {
    if (!rows || rows.length === 0) {
      elTableBody.innerHTML = '<tr><td colspan="12" class="empty-msg">조회된 데이터가 없습니다.</td></tr>';
      return;
    }

    const html = rows.map(function (row) {
      const gasCells = GAS_COLS.map(function (col) {
        const val = row[col];
        return '<td>' + (val !== null && val !== undefined ? val : '-') + '</td>';
      }).join('');

      const label = RISK_LABEL[row.max_risk_level] || row.max_risk_level;
      const cls   = RISK_BADGE[row.max_risk_level] || 'badge badge-gray';

      return '<tr>'
        + '<td>' + row.received_at + '</td>'
        + '<td>' + row.sensor_name + '</td>'
        + gasCells
        + '<td><span class="' + cls + '">' + label + '</span></td>'
        + '</tr>';
    }).join('');

    elTableBody.innerHTML = html;
  }

  // ── 페이지네이션 렌더 ─────────────────────────────────────────────────
  /**
   * 총 건수·현재 페이지·페이지 크기를 받아 페이지 버튼 목록을 생성한다.
   *
   * 최대 5개 페이지 버튼을 보여주며 현재 페이지 기준으로 앞뒤 2페이지를 표시한다.
   * 버튼 클릭 시 currentPage를 갱신하고 fetchData()를 재호출한다.
   *
   * @param {number} total     - 전체 건수
   * @param {number} page      - 현재 페이지
   * @param {number} pageSize  - 페이지당 건수
   */
  function renderPagination(total, page, pageSize) {
    const totalPages = Math.ceil(total / pageSize);
    elPageInfo.textContent = page + ' / ' + totalPages + ' 페이지';

    if (totalPages <= 1) {
      elPagination.innerHTML = '';
      return;
    }

    let start = Math.max(1, page - 2);
    let end   = Math.min(totalPages, start + 4);
    start     = Math.max(1, end - 4);

    let html = '';
    html += '<button ' + (page <= 1 ? 'disabled' : '') + ' data-page="' + (page - 1) + '">‹</button>';
    for (let i = start; i <= end; i++) {
      html += '<button class="' + (i === page ? 'active' : '') + '" data-page="' + i + '">' + i + '</button>';
    }
    html += '<button ' + (page >= totalPages ? 'disabled' : '') + ' data-page="' + (page + 1) + '">›</button>';

    elPagination.innerHTML = html;

    // 이벤트 위임 대신 개별 등록 (페이지 수가 최대 5개여서 오버헤드 없음)
    elPagination.querySelectorAll('button[data-page]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        currentPage = parseInt(this.dataset.page, 10);
        fetchData();
      });
    });
  }

  // ── CSV 내보내기 ──────────────────────────────────────────────────────
  /**
   * "로그 내보내기" 버튼 클릭 시 호출된다.
   *
   * 원리:
   *   buildParams(null)로 현재 필터를 그대로 사용하되 page/page_size는 제거한다.
   *   → 백엔드 GasDataAdminExportView가 페이지네이션 없이 전체를 CSV로 반환한다.
   *
   *   <a> 태그를 동적으로 생성해 click()을 트리거하면 브라우저가 직접 파일을 다운로드한다.
   *   fetch()를 사용하지 않으므로 백엔드의 스트리밍 응답(iterator 500건씩)을
   *   브라우저가 그대로 처리해 대용량도 메모리 문제 없이 받을 수 있다.
   */
  function exportCsv() {
    const params = buildParams(null);
    params.delete('page');
    params.delete('page_size');

    const url = '/api/admin/gas-data/export/?' + params.toString();

    // <a href> 직접 트리거는 JWT를 부착하지 못해 401. fetch + blob으로 처리.
    Auth.apiFetch(url)
      .then(function (res) {
        if (!res.ok) throw new Error('CSV 다운로드 실패 ' + res.status);
        return res.blob();
      })
      .then(function (blob) {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'gas_data_export.csv';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(a.href);
      })
      .catch(function (err) { alert(err.message); });
  }

  // ── 빠른 날짜 버튼 ────────────────────────────────────────────────────
  /**
   * 오늘/어제/최근7일/이번달 버튼 클릭 시 dateFrom/dateTo 입력을 자동으로 채운다.
   *
   * data-range 속성값에 따라 날짜를 계산한다.
   * YYYY-MM-DD 포맷은 <input type="date"> value 형식이다.
   *
   * @param {string} range - 'today' | 'yesterday' | '7days' | 'month'
   */
  function applyQuickDate(range) {
    const today = new Date();
    const fmtDate = function (d) {
      const y  = d.getFullYear();
      const m  = String(d.getMonth() + 1).padStart(2, '0');
      const dd = String(d.getDate()).padStart(2, '0');
      return y + '-' + m + '-' + dd;
    };
    const startOf = function (d) { return fmtDate(d) + 'T00:00'; };
    const endOf   = function (d) { return fmtDate(d) + 'T23:59'; };

    let from, to;
    if (range === 'today') {
      from = startOf(today);
      to   = endOf(today);
    } else if (range === 'yesterday') {
      const y = new Date(today);
      y.setDate(y.getDate() - 1);
      from = startOf(y);
      to   = endOf(y);
    } else if (range === '7days') {
      const s = new Date(today);
      s.setDate(s.getDate() - 6);
      from = startOf(s);
      to   = endOf(today);
    } else if (range === 'month') {
      from = startOf(new Date(today.getFullYear(), today.getMonth(), 1));
      to   = endOf(today);
    }

    if (from) elDateFrom.value = from;
    if (to)   elDateTo.value   = to;
  }


  // ── 이벤트 바인딩 ─────────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', function () {

    // 검색 버튼 — 페이지를 1로 초기화하고 fetchData 실행
    elBtnSearch.addEventListener('click', function () {
      currentPage = 1;
      fetchData();
    });

    // 초기화 버튼 — 모든 필터 값을 기본값으로 되돌리고 재조회
    elBtnReset.addEventListener('click', function () {
      elDateFrom.value = '';
      elDateTo.value   = '';
      elSensor.value   = '';
      elOrdering.value = '-received_at';
      currentPage      = 1;
      fetchData();
    });

    // CSV 내보내기 버튼 — 현재 필터 그대로 백엔드에서 파일 생성 후 다운로드
    elBtnExport.addEventListener('click', exportCsv);

    // 빠른 날짜 버튼 — data-range 속성으로 범위 구분
    document.querySelectorAll('.quick-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        applyQuickDate(this.dataset.range);
      });
    });

    // Enter 키로도 검색 가능
    [elDateFrom, elDateTo].forEach(function (el) {
      el.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') { currentPage = 1; fetchData(); }
      });
    });

  });

})();
