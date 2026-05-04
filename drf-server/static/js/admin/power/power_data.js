/**
 * static/js/admin/power/power_data.js
 * 스마트 전력 시스템 데이터 관리 어드민 페이지 — 전체 인터랙션 담당
 *
 * 주요 역할:
 *   1. 필터 값 수집 → API 호출 → 테이블 렌더링
 *   2. 빠른 날짜 버튼(오늘/어제/최근7일/이번달) → 날짜 입력 자동 채우기
 *   3. 페이지네이션 버튼 생성 및 클릭 처리
 *   4. CSV 내보내기 버튼 클릭 → export 엔드포인트로 파일 다운로드
 *   5. 페이지 진입 시 장비 드롭다운 목록 자동 로드
 *
 * API 의존:
 *   GET /api/admin/power-data/         — 목록 (PowerDataAdminListView)
 *   GET /api/admin/power-data/export/  — CSV 파일 다운로드 (PowerDataAdminExportView)
 *   GET /api/admin/power-data/devices/ — 장비 드롭다운 (PowerDataAdminDeviceListView)
 */

(function () {
  'use strict';

  // ── 상태 ──────────────────────────────────────────────────────────────
  let currentPage = 1;
  const PAGE_SIZE = 20;

  const API_BASE    = '/api/admin/power-data/';
  const API_DEVICES = '/api/admin/power-data/devices/';

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
  const elDateFrom    = document.getElementById('dateFrom');
  const elDateTo      = document.getElementById('dateTo');
  const elDevice      = document.getElementById('deviceFilter');
  const elDataType    = document.getElementById('dataTypeFilter');
  const elOrdering    = document.getElementById('orderingFilter');
  const elBtnSearch   = document.getElementById('btnSearch');
  const elBtnReset    = document.getElementById('btnReset');
  const elBtnExport   = document.getElementById('btnExport');
  const elTableBody   = document.getElementById('powerTableBody');
  const elTotalCount  = document.getElementById('totalCount');
  const elPageInfo    = document.getElementById('pageInfo');
  const elPagination  = document.getElementById('pagination');

  // ── 장비 드롭다운 로드 ────────────────────────────────────────────────
  /**
   * 페이지 진입 시 활성 전력 장비 목록을 받아 <select> 옵션을 채운다.
   * 가스 데이터와 달리 서버사이드 렌더링 대신 JS로 로드 — 장비 목록이
   * 페이지 HTML 생성 시점과 실제 조회 시점 사이에 바뀔 수 있기 때문.
   */
  function loadDevices() {
    Auth.apiFetch(API_DEVICES)
      .then(function (res) { return res.json(); })
      .then(function (devices) {
        devices.forEach(function (d) {
          const opt = document.createElement('option');
          opt.value       = d.id;
          opt.textContent = d.device_name;
          elDevice.appendChild(opt);
        });
      })
      .catch(function () {
        // 드롭다운 로드 실패는 무시 — 필터 없이도 조회 가능
      });
  }

  // ── 필터 값 수집 ──────────────────────────────────────────────────────
  /**
   * 현재 입력된 필터 값을 URLSearchParams 객체로 반환한다.
   * fetchData()와 exportCsv() 양쪽에서 호출해 항상 같은 필터를 사용한다.
   *
   * @param {number|null} page - 요청할 페이지 번호 (export는 null로 전달 → 파라미터 생략)
   */
  function buildParams(page) {
    const p = new URLSearchParams();
    if (elDateFrom.value) p.set('date_from',  elDateFrom.value);
    if (elDateTo.value)   p.set('date_to',    elDateTo.value);
    if (elDevice.value)   p.set('device',     elDevice.value);
    if (elDataType.value) p.set('data_type',  elDataType.value);
    if (elOrdering.value) p.set('ordering',   elOrdering.value);
    if (page !== null)    p.set('page',       page);
    p.set('page_size', PAGE_SIZE);
    return p;
  }

  // ── 데이터 fetch + 테이블 렌더 ────────────────────────────────────────
  function fetchData() {
    const params = buildParams(currentPage);
    elTableBody.innerHTML = '<tr><td colspan="6" class="empty-msg">불러오는 중...</td></tr>';

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
          '<tr><td colspan="6" class="empty-msg">데이터를 불러오지 못했습니다. (' + err.message + ')</td></tr>';
      });
  }

  // ── 테이블 렌더 ───────────────────────────────────────────────────────
  /**
   * API 응답의 results 배열을 받아 <tbody>를 다시 그린다.
   * 측정값이 null이면 "-"로 표시 (결측 또는 통신 오류).
   *
   * @param {Array} rows - 백엔드 _serialize_row() 결과 객체 배열
   */
  function renderTable(rows) {
    if (!rows || rows.length === 0) {
      elTableBody.innerHTML = '<tr><td colspan="6" class="empty-msg">조회된 데이터가 없습니다.</td></tr>';
      return;
    }

    const html = rows.map(function (row) {
      const value = row.value !== null && row.value !== undefined
        ? row.value
        : '-';

      const label = RISK_LABEL[row.risk_level] || row.risk_level;
      const cls   = RISK_BADGE[row.risk_level]  || 'badge badge-gray';

      return '<tr>'
        + '<td>' + row.received_at + '</td>'
        + '<td>' + row.device_name + '</td>'
        + '<td class="col-channel">ch' + row.channel + '</td>'
        + '<td>' + row.data_type_label + '</td>'
        + '<td class="col-value">' + value + '</td>'
        + '<td><span class="' + cls + '">' + label + '</span></td>'
        + '</tr>';
    }).join('');

    elTableBody.innerHTML = html;
  }

  // ── 페이지네이션 렌더 ─────────────────────────────────────────────────
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

    elPagination.querySelectorAll('button[data-page]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        currentPage = parseInt(this.dataset.page, 10);
        fetchData();
      });
    });
  }

  // ── CSV 내보내기 ──────────────────────────────────────────────────────
  function exportCsv() {
    const params = buildParams(null);
    params.delete('page');
    params.delete('page_size');

    const url = '/api/admin/power-data/export/?' + params.toString();

    // <a href> 직접 트리거는 JWT를 부착하지 못해 401. fetch + blob으로 처리.
    Auth.apiFetch(url)
      .then(function (res) {
        if (!res.ok) throw new Error('CSV 다운로드 실패 ' + res.status);
        return res.blob();
      })
      .then(function (blob) {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'power_data_export.csv';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(a.href);
      })
      .catch(function (err) { alert(err.message); });
  }

  // ── 빠른 날짜 버튼 ────────────────────────────────────────────────────
  function applyQuickDate(range) {
    const today   = new Date();
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

    loadDevices();

    elBtnSearch.addEventListener('click', function () {
      currentPage = 1;
      fetchData();
    });

    elBtnReset.addEventListener('click', function () {
      elDateFrom.value  = '';
      elDateTo.value    = '';
      elDevice.value    = '';
      elDataType.value  = '';
      elOrdering.value  = '-received_at';
      currentPage       = 1;
      fetchData();
    });

    elBtnExport.addEventListener('click', exportCsv);

    document.querySelectorAll('.quick-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        applyQuickDate(this.dataset.range);
      });
    });

    [elDateFrom, elDateTo].forEach(function (el) {
      el.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') { currentPage = 1; fetchData(); }
      });
    });

  });

})();
