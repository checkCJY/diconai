/* safety_history.js — 안전 확인 이력 월간 캘린더 */

(function () {
  // pad는 shared/util.js의 글로벌 함수 사용

  const today = new Date();
  const todayStr = `${today.getFullYear()}-${pad(today.getMonth()+1)}-${pad(today.getDate())}`;

  // ══════════════════════════════════════════════
  // 나의 안전 확인 탭
  // ══════════════════════════════════════════════
  let myYear  = today.getFullYear();
  let myMonth = today.getMonth() + 1;
  let myRecords  = {};
  let myJoined   = '';

  document.getElementById('btnPrevMonth').addEventListener('click', () => shiftMyMonth(-1));
  document.getElementById('btnNextMonth').addEventListener('click', () => shiftMyMonth(1));
  document.getElementById('btnDownload').addEventListener('click', () => downloadXlsx(myRecords, myYear, myMonth));
  document.getElementById('btnPrint').addEventListener('click', () => printCalendar('my'));

  function shiftMyMonth(delta) {
    myMonth += delta;
    if (myMonth > 12) { myMonth = 1;  myYear++; }
    if (myMonth < 1)  { myMonth = 12; myYear--; }
    loadMyMonth();
  }

  async function loadMyMonth() {
    document.getElementById('monthLabel').textContent = `${myYear}년 ${myMonth}월`;
    const monthStr = `${myYear}-${pad(myMonth)}`;
    try {
      const res = await Auth.apiFetch(`/dashboard/api/safety-history/?month=${monthStr}`);
      if (!res.ok) throw new Error();
      const data = await res.json();
      myJoined  = data.joined_date || '';
      myRecords = {};
      (data.records || []).forEach(r => { myRecords[r.date] = r; });
      if (data.worker_name) {
        document.getElementById('myWorkerName').textContent = data.worker_name;
      }
    } catch {
      myJoined  = '';
      myRecords = {};
    }
    renderCalendar(myYear, myMonth, myRecords, myJoined, 'calBody');
  }

  loadMyMonth();

  // ══════════════════════════════════════════════
  // 탭 전환
  // ══════════════════════════════════════════════
  document.querySelectorAll('.history-tab').forEach(tab => {
    tab.addEventListener('click', () => switchTab(tab.dataset.tab));
  });

  function switchTab(tabId) {
    document.querySelectorAll('.history-tab').forEach(t =>
      t.classList.toggle('active', t.dataset.tab === tabId)
    );
    document.getElementById('tabMyHistory').style.display  = tabId === 'my'  ? '' : 'none';
    document.getElementById('tabAllHistory').style.display = tabId === 'all' ? '' : 'none';
  }

  // ══════════════════════════════════════════════
  // 전체 이력 현황 탭 (관리자)
  // ══════════════════════════════════════════════
  let allYear    = today.getFullYear();
  let allMonth   = today.getMonth() + 1;
  let allRecords = {};
  let allJoined  = '';
  let selectedWorkerId   = null;
  let selectedWorkerName = '';
  let checkedWorkerIds   = new Set();
  let workerData         = [];

  // 관리자 여부 확인 후 전체 이력 탭 노출
  (async function initAdminTab() {
    try {
      const res = await Auth.apiFetch('/dashboard/api/workers-list/');
      if (!res.ok) return;  // 권한 없으면 탭 숨김 유지
      const data = await res.json();
      document.getElementById('tabAllBtn').style.display = '';
      workerData = data.workers || [];
      buildDeptDropdown(data.departments || []);
      renderWorkerTable(workerData);
      initAllTabEvents();
    } catch { /* 비관리자 — 탭 숨김 유지 */ }
  })();

  function buildDeptDropdown(depts) {
    const sel = document.getElementById('deptFilter');
    depts.forEach(d => {
      const opt = document.createElement('option');
      opt.value = d.id;
      opt.textContent = d.name;
      sel.appendChild(opt);
    });
  }

  function renderWorkerTable(workers) {
    const tbody = document.getElementById('workerTableBody');
    if (!workers.length) {
      tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;padding:20px;color:var(--text2);">작업자가 없습니다.</td></tr>';
      return;
    }
    tbody.innerHTML = workers.map(w => `
      <tr class="worker-row${selectedWorkerId === w.id ? ' selected' : ''}" data-id="${w.id}" data-name="${w.name}">
        <td><input type="checkbox" class="wlp-cb worker-cb" data-id="${w.id}" ${checkedWorkerIds.has(w.id) ? 'checked' : ''}></td>
        <td>${w.department}</td>
        <td>${w.name}</td>
        <td class="${w.is_present ? 'badge-present' : 'badge-absent'}">${w.is_present ? '● 출근' : '미출근'}</td>
      </tr>
    `).join('');

    // 행 클릭 → 우측 캘린더 로드
    tbody.querySelectorAll('.worker-row').forEach(row => {
      row.addEventListener('click', e => {
        if (e.target.type === 'checkbox') return;
        selectWorker(Number(row.dataset.id), row.dataset.name);
      });
    });

    // 체크박스
    tbody.querySelectorAll('.worker-cb').forEach(cb => {
      cb.addEventListener('change', e => {
        e.stopPropagation();
        const id = Number(cb.dataset.id);
        cb.checked ? checkedWorkerIds.add(id) : checkedWorkerIds.delete(id);
        syncAllFooterButtons();
      });
    });
  }

  function initAllTabEvents() {
    document.getElementById('btnAllPrevMonth').addEventListener('click', () => shiftAllMonth(-1));
    document.getElementById('btnAllNextMonth').addEventListener('click', () => shiftAllMonth(1));
    document.getElementById('btnAllDownload').addEventListener('click', allDownload);
    document.getElementById('btnAllPrint').addEventListener('click', allPrint);

    document.getElementById('cbSelectAll').addEventListener('change', e => {
      const checked = e.target.checked;
      checkedWorkerIds = checked ? new Set(workerData.map(w => w.id)) : new Set();
      renderWorkerTable(filteredWorkers());
      syncAllFooterButtons();
    });

    document.getElementById('deptFilter').addEventListener('change', () => {
      renderWorkerTable(filteredWorkers());
    });

    let searchTimer;
    document.getElementById('nameSearch').addEventListener('input', () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => renderWorkerTable(filteredWorkers()), 250);
    });
  }

  function filteredWorkers() {
    const deptId = Number(document.getElementById('deptFilter').value) || null;
    const nameQ  = document.getElementById('nameSearch').value.trim().toLowerCase();
    return workerData.filter(w => {
      if (deptId && w.department_id !== deptId) return false;
      if (nameQ && !w.name.toLowerCase().includes(nameQ)) return false;
      return true;
    });
  }

  function syncAllFooterButtons() {
    const hasSelected = selectedWorkerId !== null;
    document.getElementById('btnAllDownload').classList.toggle('active', hasSelected);
    document.getElementById('btnAllPrint').classList.toggle('active', hasSelected);
  }

  function shiftAllMonth(delta) {
    allMonth += delta;
    if (allMonth > 12) { allMonth = 1;  allYear++; }
    if (allMonth < 1)  { allMonth = 12; allYear--; }
    if (selectedWorkerId) loadAllCalendar(selectedWorkerId);
  }

  function selectWorker(workerId, workerName) {
    selectedWorkerId   = workerId;
    selectedWorkerName = workerName;

    // 선택 하이라이트
    document.querySelectorAll('.worker-row').forEach(r =>
      r.classList.toggle('selected', Number(r.dataset.id) === workerId)
    );

    document.getElementById('wdpWorkerName').textContent = workerName;
    document.getElementById('wdpControls').style.visibility  = 'visible';
    document.getElementById('allCalLegend').style.visibility = 'visible';

    // 안내 메시지 제거
    const placeholder = document.querySelector('#allCalBody .cal-no-selection');
    if (placeholder) placeholder.remove();

    syncAllFooterButtons();

    allYear  = today.getFullYear();
    allMonth = today.getMonth() + 1;
    loadAllCalendar(workerId);
  }

  async function loadAllCalendar(workerId) {
    document.getElementById('allMonthLabel').textContent = `${allYear}년 ${allMonth}월`;
    const monthStr = `${allYear}-${pad(allMonth)}`;
    try {
      const res = await Auth.apiFetch(`/dashboard/api/safety-history/?month=${monthStr}&worker_id=${workerId}`);
      if (!res.ok) throw new Error();
      const data = await res.json();
      allJoined  = data.joined_date || '';
      allRecords = {};
      (data.records || []).forEach(r => { allRecords[r.date] = r; });
    } catch {
      allJoined  = '';
      allRecords = {};
    }
    renderCalendar(allYear, allMonth, allRecords, allJoined, 'allCalBody');
  }

  function allDownload() {
    if (!selectedWorkerId) return;
    function doDownload() {
      const monthStr = `${allYear}-${pad(allMonth)}`;
      const rows = [['날짜', '안전 확인 체크리스트', 'VR 교육']];
      Object.keys(allRecords).sort().forEach(dateStr => {
        const r = allRecords[dateStr];
        rows.push([dateStr, r.checklist_done ? '완료' : '미완료', r.vr_done ? '완료' : '미완료']);
      });
      if (rows.length === 1) { alert('해당 월에 기록된 이력이 없습니다.'); return; }
      const wb = XLSX.utils.book_new();
      const ws = XLSX.utils.aoa_to_sheet(rows);
      ws['!cols'] = [{ wch: 14 }, { wch: 20 }, { wch: 12 }];
      XLSX.utils.book_append_sheet(wb, ws, selectedWorkerName.slice(0, 31));
      XLSX.writeFile(wb, `안전확인이력_${selectedWorkerName}_${monthStr}.xlsx`);
    }

    if (typeof XLSX !== 'undefined') { doDownload(); return; }
    const script = document.createElement('script');
    script.src = 'https://cdn.sheetjs.com/xlsx-0.20.3/package/dist/xlsx.full.min.js';
    script.onload = doDownload;
    script.onerror = () => alert('다운로드 라이브러리 로드 실패. 네트워크를 확인해주세요.');
    document.head.appendChild(script);
  }

  function allPrint() {
    if (!selectedWorkerId) return;
    printCalendar('all');
  }

  // ══════════════════════════════════════════════
  // 인쇄: 해당 탭 캘린더만 출력
  // ══════════════════════════════════════════════
  function printCalendar(tab) {
    document.body.dataset.printTab = tab;
    window.print();
    delete document.body.dataset.printTab;
  }

  // ══════════════════════════════════════════════
  // 공통 캘린더 렌더러
  // ══════════════════════════════════════════════
  function renderCalendar(year, month, records, joinedDate, bodyId) {
    const firstDow    = new Date(year, month - 1, 1).getDay();
    const daysInMonth = new Date(year, month, 0).getDate();
    const daysInPrev  = new Date(year, month - 1, 0).getDate();

    const body = document.getElementById(bodyId);
    body.innerHTML = '';

    for (let i = 0; i < firstDow; i++) {
      body.appendChild(makeCell(year, month - 1, daysInPrev - firstDow + 1 + i, true, records, joinedDate));
    }
    for (let d = 1; d <= daysInMonth; d++) {
      body.appendChild(makeCell(year, month, d, false, records, joinedDate));
    }
    const total    = firstDow + daysInMonth;
    const trailing = total % 7 === 0 ? 0 : 7 - (total % 7);
    for (let d = 1; d <= trailing; d++) {
      body.appendChild(makeCell(year, month + 1, d, true, records, joinedDate));
    }
  }

  function makeCell(year, month, day, isOther, records, joinedDate) {
    const cellDate = new Date(year, month - 1, day);
    const ry = cellDate.getFullYear(), rm = cellDate.getMonth() + 1, rd = cellDate.getDate();
    const dateStr  = `${ry}-${pad(rm)}-${pad(rd)}`;
    const dow      = cellDate.getDay();

    const cell = document.createElement('div');
    cell.className = 'cal-cell' +
      (isOther           ? ' other-month' : '') +
      (dateStr === todayStr ? ' today'     : '') +
      (dow === 0 ? ' sun' : '') +
      (dow === 6 ? ' sat' : '');

    const numEl = document.createElement('div');
    numEl.className = 'cal-day-num';
    numEl.textContent = rd;
    cell.appendChild(numEl);

    const inRange = !isOther && dateStr <= todayStr && (!joinedDate || dateStr >= joinedDate);
    if (inRange) {
      const rec = records[dateStr] || { attended: false, checklist_done: false, vr_done: false };
      cell.appendChild(makeIndicators(rec));
    }

    return cell;
  }

  function makeIndicators(rec) {
    const wrap = document.createElement('div');
    wrap.className = 'cal-indicators';
    if (!rec.attended) {
      const absent = document.createElement('div');
      absent.className = 'cal-absent';
      absent.textContent = '미출근';
      wrap.appendChild(absent);
      return wrap;
    }
    wrap.appendChild(makeIndicatorRow(rec.checklist_done, '안전 체크리스트'));
    wrap.appendChild(makeIndicatorRow(rec.vr_done,        'VR 교육'));
    return wrap;
  }

  function makeIndicatorRow(done, label) {
    const row = document.createElement('div');
    row.className = 'cal-indicator';

    const ic = document.createElement('span');
    ic.className = done ? 'ic ic-done' : 'ic ic-undone';
    ic.textContent = done ? '○' : '✕';

    const lbl = document.createElement('span');
    lbl.textContent = label;
    row.appendChild(ic);
    row.appendChild(lbl);
    return row;
  }

  // ══════════════════════════════════════════════
  // 나의 탭 다운로드
  // ══════════════════════════════════════════════
  function downloadXlsx(records, year, month) {
    function doDownload() {
      const monthStr = `${year}-${pad(month)}`;
      const rows = [['날짜', '안전 확인 체크리스트', 'VR 교육']];
      Object.keys(records).sort().forEach(dateStr => {
        const r = records[dateStr];
        rows.push([dateStr, r.checklist_done ? '완료' : '미완료', r.vr_done ? '완료' : '미완료']);
      });
      if (rows.length === 1) { alert('해당 월에 기록된 이력이 없습니다.'); return; }
      const wb = XLSX.utils.book_new();
      const ws = XLSX.utils.aoa_to_sheet(rows);
      ws['!cols'] = [{ wch: 14 }, { wch: 20 }, { wch: 12 }];
      XLSX.utils.book_append_sheet(wb, ws, '안전확인이력');
      XLSX.writeFile(wb, `안전확인이력_${monthStr}.xlsx`);
    }

    if (typeof XLSX !== 'undefined') { doDownload(); return; }
    const script = document.createElement('script');
    script.src = 'https://cdn.sheetjs.com/xlsx-0.20.3/package/dist/xlsx.full.min.js';
    script.onload = doDownload;
    script.onerror = () => alert('다운로드 라이브러리 로드 실패. 네트워크를 확인해주세요.');
    document.head.appendChild(script);
  }
})();
