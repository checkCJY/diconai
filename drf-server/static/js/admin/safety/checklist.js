/* admin/safety/checklist.js — 작업 전 안전 점검 체크리스트 관리
 *
 * 역할: /admin-panel/safety/checklist/ 페이지 동작 전담.
 * - 섹션/문항 CRUD (추가, 수정, 복제, 삭제, 순서 변경)
 * - [반영 저장] → SafetyChecklistRevision 스냅샷 생성
 * - [반영 이력] 모달 → 시점 선택 후 읽기 전용 스냅샷 표시
 *
 * 핵심 상태 (state machine):
 *   facilityId           — _qs()로 매 요청에 facility_id 쿼리 자동 부착
 *   currentSectionId     — 우측 편집기에 노출 중인 섹션 (좌측 클릭으로 전환)
 *   isDirty              — 마지막 publish 이후 클라이언트가 수정한 적 있는지 (UI 즉시 신호)
 *   hasUnpublishedChanges — 서버 측 timestamp 비교 결과 (state API에서 받음)
 *   "편집 중" 배지 = isDirty || hasUnpublishedChanges
 *
 * 주요 흐름:
 *   init → _loadAll(state + sections 병렬 fetch) → _render
 *      ├ 좌측: _renderSectionList (× 삭제 버튼은 hover/active 시 노출)
 *      └ 우측: _renderEditor (input change → _onSectionFieldChange/_onItemTitleChange)
 *   CRUD 요청 → _markDirty() → _loadAll 재호출
 *   [반영 저장] → POST publish/ → 200=다이얼로그 + state 리셋 / 400 no_changes=보류 안내
 *
 * 공용 컴포넌트:
 *   Dialog.prompt/confirm/alert  — 네이티브 window.* 대체. Promise 반환, ESC=취소, Enter=확인.
 *     · variant: 'danger'로 빨간 확정 버튼 (삭제 액션 전용)
 *
 * API 엔드포인트 (모두 /api/admin/safety/):
 *   GET    /checklist/state/                헤더 메타
 *   GET    /sections/                       섹션 + 문항 트리
 *   POST   /sections/                       섹션 추가
 *   PATCH  /sections/<id>/                  섹션 수정
 *   DELETE /sections/<id>/                  섹션 비활성화
 *   POST   /sections/reorder/               섹션 순서
 *   POST   /sections/<id>/items/            문항 추가
 *   PATCH  /items/<id>/                     문항 수정
 *   DELETE /items/<id>/                     문항 비활성화
 *   POST   /items/<id>/duplicate/           문항 복제
 *   POST   /items/reorder/                  문항 순서
 *   POST   /checklist/publish/              반영 저장
 *   GET    /checklist/revisions/            이력 리스트
 *   GET    /checklist/revisions/<id>/       스냅샷 상세
 */
'use strict';

const PLEDGE_TEXT = '상기 체크리스트를 모두 확인하였으며 작업 전 안전 기준을 준수하겠습니다.';

// ──────────────────────────────────────────────────────────
// 공용 다이얼로그 (window.prompt / confirm / alert 대체)
// ──────────────────────────────────────────────────────────
const Dialog = {
  _show({ title, message, type, defaultValue = '', confirmLabel = '확인', confirmVariant = 'primary' }) {
    return new Promise((resolve) => {
      const overlay = document.createElement('div');
      overlay.className = 'app-modal-overlay';
      const dialog = document.createElement('div');
      dialog.className = 'app-modal-dialog';
      dialog.setAttribute('role', 'dialog');

      const titleEl = document.createElement('h3');
      titleEl.className = 'app-modal-title';
      titleEl.textContent = title;
      dialog.appendChild(titleEl);

      if (message) {
        const msgEl = document.createElement('p');
        msgEl.className = 'app-modal-message';
        msgEl.textContent = message;
        dialog.appendChild(msgEl);
      }

      let input = null;
      if (type === 'prompt') {
        input = document.createElement('input');
        input.className = 'app-modal-input';
        input.type = 'text';
        input.value = defaultValue;
        dialog.appendChild(input);
      }

      const actions = document.createElement('div');
      actions.className = 'app-modal-actions';

      const cancelBtn = document.createElement('button');
      cancelBtn.className = 'app-modal-btn-outline';
      cancelBtn.textContent = '취소';

      const confirmBtn = document.createElement('button');
      confirmBtn.className =
        confirmVariant === 'danger' ? 'app-modal-btn-danger' : 'app-modal-btn-primary';
      confirmBtn.textContent = confirmLabel;

      if (type !== 'alert') actions.appendChild(cancelBtn);
      actions.appendChild(confirmBtn);
      dialog.appendChild(actions);
      overlay.appendChild(dialog);
      document.body.appendChild(overlay);

      const cancelValue = type === 'prompt' ? null : false;

      const close = (value) => {
        document.removeEventListener('keydown', onKey);
        overlay.remove();
        resolve(value);
      };

      const submit = () => {
        if (type === 'prompt') close(input.value.trim());
        else if (type === 'confirm') close(true);
        else close();
      };

      const onKey = (e) => {
        if (e.key === 'Escape') close(cancelValue);
        if (e.key === 'Enter') {
          if (type === 'prompt') {
            e.preventDefault();
            submit();
          } else if (type === 'alert' || type === 'confirm') {
            e.preventDefault();
            submit();
          }
        }
      };

      cancelBtn.addEventListener('click', () => close(cancelValue));
      confirmBtn.addEventListener('click', submit);
      overlay.addEventListener('click', (e) => {
        if (e.target === overlay) close(cancelValue);
      });
      document.addEventListener('keydown', onKey);

      setTimeout(() => (input ? input.focus() : confirmBtn.focus()), 0);
    });
  },

  prompt(message, opts = {}) {
    return this._show({
      title: opts.title || '입력',
      message,
      type: 'prompt',
      defaultValue: opts.defaultValue || '',
      confirmLabel: opts.confirmLabel || '확인',
    });
  },

  confirm(message, opts = {}) {
    return this._show({
      title: opts.title || '확인',
      message,
      type: 'confirm',
      confirmLabel: opts.confirmLabel || '확인',
      confirmVariant: opts.variant || 'primary',
    });
  },

  alert(message, opts = {}) {
    return this._show({
      title: opts.title || '알림',
      message,
      type: 'alert',
      confirmLabel: opts.confirmLabel || '확인',
    });
  },
};

const SafetyChecklistAdmin = {
  facilityId: null,
  sections: [],
  currentSectionId: null,
  lastPublishedAt: null,
  hasUnpublishedChanges: false,
  isDirty: false,

  // ── 초기화 ────────────────────────────────────────────
  async init() {
    this._bindEvents();
    await this._loadAll();
  },

  _bindEvents() {
    document.getElementById('btnAddSection').addEventListener('click', () => this._onAddSection());
    document.getElementById('btnAddItem').addEventListener('click', () => this._onAddItem());
    document.getElementById('btnPublish').addEventListener('click', () => this._onPublish());
    document.getElementById('btnOpenHistory').addEventListener('click', () => this._openHistory());
    document.getElementById('historyClose').addEventListener('click', () => this._closeHistory());

    document.getElementById('editSectionName').addEventListener('change', (e) =>
      this._onSectionFieldChange('name', e.target.value),
    );
    document.getElementById('editSectionDescription').addEventListener('change', (e) =>
      this._onSectionFieldChange('description', e.target.value),
    );
  },

  // ── API 헬퍼 ──────────────────────────────────────────
  _qs(extra = '') {
    if (!this.facilityId) return extra ? `?${extra}` : '';
    const base = `facility_id=${this.facilityId}`;
    return extra ? `?${base}&${extra}` : `?${base}`;
  },

  async _api(path, opts = {}) {
    const url = `/api/admin/safety${path}`;
    const res = await Auth.apiFetch(url, opts);
    if (res.status === 401 || res.status === 403) {
      await Dialog.alert('접근 권한이 없습니다. 관리자 계정으로 로그인해 주세요.');
      window.location.href = '/dashboard/';
      throw new Error('forbidden');
    }
    if (!res.ok) {
      let payload = null;
      try {
        payload = await res.json();
      } catch (_) {
        payload = null;
      }
      const err = new Error(`API ${url} failed: ${res.status}`);
      err.status = res.status;
      err.code = payload?.code || null;
      err.detail = payload?.detail || null;
      throw err;
    }
    if (res.status === 204) return null;
    return res.json();
  },

  // ── 로딩 / 렌더 ───────────────────────────────────────
  async _loadAll() {
    try {
      const [state, sections] = await Promise.all([
        this._api(`/checklist/state/${this._qs()}`),
        this._api(`/sections/${this._qs()}`),
      ]);
      this.facilityId = state.facility_id;
      this.lastPublishedAt = state.last_published_at;
      this.hasUnpublishedChanges = state.has_unpublished_changes;
      this.sections = sections;
      if (this.sections.length > 0 && !this.currentSectionId) {
        this.currentSectionId = this.sections[0].id;
      }
      this._render();
    } catch (err) {
      console.error(err);
    }
  },

  _render() {
    this._renderHeader();
    this._renderSectionList();
    this._renderEditor();
  },

  _renderHeader() {
    document.getElementById('lastPublishedAt').textContent = this._formatDate(this.lastPublishedAt);
  },

  _renderSectionList() {
    const list = document.getElementById('sectionList');
    document.getElementById('sectionTotal').textContent = this.sections.length;
    if (this.sections.length === 0) {
      list.innerHTML = '<li class="empty-state">섹션을 추가해 주세요.</li>';
      document.getElementById('sectionStatus').hidden = true;
      return;
    }
    list.innerHTML = '';
    this.sections.forEach((section) => {
      const li = document.createElement('li');
      li.className = 'section-card' + (section.id === this.currentSectionId ? ' active' : '');
      li.dataset.sectionId = section.id;
      li.innerHTML = `
        <span class="drag-handle" aria-hidden="true">⋮⋮</span>
        <span class="name"></span>
        <div class="section-card-actions">
          <span class="count">${section.item_count}개</span>
          <button class="section-delete" type="button" aria-label="섹션 삭제" title="섹션 삭제">×</button>
        </div>
      `;
      li.querySelector('.name').textContent = section.name;
      li.addEventListener('click', () => {
        this.currentSectionId = section.id;
        this._render();
      });
      li.querySelector('.section-delete').addEventListener('click', (e) => {
        e.stopPropagation();
        this._onDeleteSection(section);
      });
      li.draggable = true;
      this._bindSectionDnD(li);
      list.appendChild(li);
    });

    const status = document.getElementById('sectionStatus');
    const current = this._currentSection();
    if (current) {
      status.hidden = false;
      document.getElementById('statusCurrentName').textContent = current.name;
      document.getElementById('badgeEditing').hidden = !(this.hasUnpublishedChanges || this.isDirty);
    } else {
      status.hidden = true;
    }
  },

  _renderEditor() {
    const pane = document.getElementById('editorPane');
    const current = this._currentSection();
    if (!current) {
      pane.hidden = true;
      return;
    }
    pane.hidden = false;
    document.getElementById('editorSectionName').textContent = current.name;
    document.getElementById('editSectionName').value = current.name;
    document.getElementById('editSectionDescription').value = current.description || '';

    const idx = this.sections.findIndex((s) => s.id === current.id) + 1;
    document.getElementById('sectionIndex').textContent = `${idx}/${this.sections.length}`;
    document.getElementById('itemCount').textContent = current.items.length;

    const itemList = document.getElementById('itemList');
    if (current.items.length === 0) {
      itemList.innerHTML = '<li class="empty-state">[문항 추가] 버튼으로 문항을 등록해 주세요.</li>';
      return;
    }
    itemList.innerHTML = '';
    current.items.forEach((item, idx) => {
      const li = document.createElement('li');
      li.className = 'item-row';
      li.draggable = true;
      li.dataset.itemId = item.id;
      li.innerHTML = `
        <span class="drag-handle" aria-hidden="true">⋮⋮</span>
        <span class="item-number">${idx + 1}</span>
        <input class="item-input" type="text" maxlength="200">
        <div class="item-actions">
          <button class="btn-outline btn-sm" data-action="duplicate">복제</button>
          <button class="btn-danger btn-sm" data-action="delete">삭제</button>
        </div>
      `;
      const input = li.querySelector('.item-input');
      input.value = item.title;
      input.addEventListener('change', () => this._onItemTitleChange(item.id, input.value));
      li.querySelector('[data-action="duplicate"]').addEventListener('click', () =>
        this._onDuplicateItem(item.id),
      );
      li.querySelector('[data-action="delete"]').addEventListener('click', () =>
        this._onDeleteItem(item.id),
      );
      this._bindItemDnD(li);
      itemList.appendChild(li);
    });
  },

  _currentSection() {
    return this.sections.find((s) => s.id === this.currentSectionId) || null;
  },

  _markDirty() {
    this.isDirty = true;
    document.getElementById('badgeEditing').hidden = false;
  },

  // ── 섹션 핸들러 ───────────────────────────────────────
  async _onAddSection() {
    const name = await Dialog.prompt('새 섹션 이름을 입력하세요.', { title: '섹션 추가' });
    if (!name) return;
    await this._api(`/sections/${this._qs()}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    });
    this._markDirty();
    await this._loadAll();
  },

  async _onDeleteSection(section) {
    const itemCountText = section.item_count > 0
      ? `\n하위 문항 ${section.item_count}개도 함께 비활성화됩니다.`
      : '';
    const ok = await Dialog.confirm(
      `"${section.name}" 섹션을 삭제하시겠습니까?${itemCountText}`,
      { title: '섹션 삭제', confirmLabel: '삭제', variant: 'danger' },
    );
    if (!ok) return;
    await this._api(`/sections/${section.id}/${this._qs()}`, { method: 'DELETE' });
    // 현재 선택 섹션이 삭제됐으면 선택 초기화 — 다음 렌더에서 첫 활성 섹션으로 폴백됨
    if (this.currentSectionId === section.id) {
      this.currentSectionId = null;
    }
    this._markDirty();
    await this._loadAll();
  },

  async _onSectionFieldChange(field, value) {
    const current = this._currentSection();
    if (!current) return;
    await this._api(`/sections/${current.id}/${this._qs()}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ [field]: value }),
    });
    this._markDirty();
    await this._loadAll();
  },

  // ── 문항 핸들러 ───────────────────────────────────────
  async _onAddItem() {
    const current = this._currentSection();
    if (!current) return;
    const title = await Dialog.prompt('새 문항을 입력하세요.', { title: '문항 추가' });
    if (!title) return;
    await this._api(`/sections/${current.id}/items/${this._qs()}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    });
    this._markDirty();
    await this._loadAll();
  },

  async _onItemTitleChange(itemId, title) {
    if (!title.trim()) return;
    await this._api(`/items/${itemId}/${this._qs()}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    });
    this._markDirty();
    await this._loadAll();
  },

  async _onDuplicateItem(itemId) {
    await this._api(`/items/${itemId}/duplicate/${this._qs()}`, { method: 'POST' });
    this._markDirty();
    await this._loadAll();
  },

  async _onDeleteItem(itemId) {
    const ok = await Dialog.confirm('문항을 삭제하시겠습니까?', {
      title: '문항 삭제',
      confirmLabel: '삭제',
      variant: 'danger',
    });
    if (!ok) return;
    await this._api(`/items/${itemId}/${this._qs()}`, { method: 'DELETE' });
    this._markDirty();
    await this._loadAll();
  },

  // ── 섹션 드래그 앤 드롭 ──────────────────────────────
  _bindSectionDnD(li) {
    li.addEventListener('dragstart', (e) => {
      li.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', li.dataset.sectionId);
    });
    li.addEventListener('dragend', () => {
      li.classList.remove('dragging');
      document
        .querySelectorAll('.section-card.drop-target')
        .forEach((el) => el.classList.remove('drop-target'));
    });
    li.addEventListener('dragover', (e) => {
      e.preventDefault();
      li.classList.add('drop-target');
    });
    li.addEventListener('dragleave', () => {
      li.classList.remove('drop-target');
    });
    li.addEventListener('drop', async (e) => {
      e.preventDefault();
      li.classList.remove('drop-target');
      const draggedId = parseInt(e.dataTransfer.getData('text/plain'), 10);
      const targetId = parseInt(li.dataset.sectionId, 10);
      if (draggedId === targetId) return;
      const ids = this.sections.map((s) => s.id).filter((id) => id !== draggedId);
      const targetIdx = ids.indexOf(targetId);
      ids.splice(targetIdx, 0, draggedId);
      await this._api(`/sections/reorder/${this._qs()}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ordered_ids: ids }),
      });
      this._markDirty();
      await this._loadAll();
    });
  },

  // ── 문항 드래그 앤 드롭 ───────────────────────────────
  _bindItemDnD(li) {
    li.addEventListener('dragstart', (e) => {
      li.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', li.dataset.itemId);
    });
    li.addEventListener('dragend', () => {
      li.classList.remove('dragging');
      document
        .querySelectorAll('.item-row.drop-target')
        .forEach((el) => el.classList.remove('drop-target'));
    });
    li.addEventListener('dragover', (e) => {
      e.preventDefault();
      li.classList.add('drop-target');
    });
    li.addEventListener('dragleave', () => {
      li.classList.remove('drop-target');
    });
    li.addEventListener('drop', async (e) => {
      e.preventDefault();
      li.classList.remove('drop-target');
      const draggedId = parseInt(e.dataTransfer.getData('text/plain'), 10);
      const targetId = parseInt(li.dataset.itemId, 10);
      if (draggedId === targetId) return;
      const current = this._currentSection();
      if (!current) return;
      const ids = current.items.map((it) => it.id).filter((id) => id !== draggedId);
      const targetIdx = ids.indexOf(targetId);
      ids.splice(targetIdx, 0, draggedId);
      await this._api(`/items/reorder/${this._qs()}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ section_id: current.id, ordered_ids: ids }),
      });
      this._markDirty();
      await this._loadAll();
    });
  },

  // ── [반영 저장] ──────────────────────────────────────
  async _onPublish() {
    const ok = await Dialog.confirm(
      '현재 체크리스트를 반영하시겠습니까?\n저장 후 운영 화면에 즉시 적용됩니다.',
      { title: '반영 저장', confirmLabel: '반영' },
    );
    if (!ok) return;
    try {
      const revision = await this._api(`/checklist/publish/${this._qs()}`, { method: 'POST' });
      this.isDirty = false;
      this.hasUnpublishedChanges = false;
      this.lastPublishedAt = revision.published_at;
      await Dialog.alert(`v${revision.version} 으로 반영되었습니다.`, { title: '반영 완료' });
    } catch (err) {
      if (err.code === 'no_changes') {
        this.isDirty = false;
        this.hasUnpublishedChanges = false;
        await Dialog.alert(
          err.detail || '변경 사항이 없어 새 버전을 생성하지 않았습니다.',
          { title: '반영 보류' },
        );
      } else {
        throw err;
      }
    }
    await this._loadAll();
  },

  // ── 반영 이력 모달 ────────────────────────────────────
  async _openHistory() {
    document.getElementById('historyModal').hidden = false;
    const list = await this._api(`/checklist/revisions/${this._qs()}`);
    this._renderHistoryList(list);
    if (list.length > 0) {
      this._renderHistoryDetail(list[0].id, list);
    } else {
      document.getElementById('historyDetail').innerHTML =
        '<p class="empty-state">아직 반영된 이력이 없습니다.</p>';
    }
  },

  _closeHistory() {
    document.getElementById('historyModal').hidden = true;
  },

  _renderHistoryList(list) {
    const ul = document.getElementById('historyList');
    if (list.length === 0) {
      ul.innerHTML = '<li class="empty-state">이력이 없습니다.</li>';
      return;
    }
    ul.innerHTML = '';
    list.forEach((rev) => {
      const li = document.createElement('li');
      const { date, time } = this._splitDateTime(rev.published_at);
      li.innerHTML = `
        <div class="ts-date">${date} ${time}</div>
        <div class="ts-actor">수정자 <strong>${this._escape(rev.published_by_name || '-')}</strong></div>
      `;
      li.addEventListener('click', () => this._renderHistoryDetail(rev.id, list));
      ul.appendChild(li);
    });
  },

  async _renderHistoryDetail(revisionId, list) {
    document
      .querySelectorAll('#historyList li')
      .forEach((el) => el.classList.remove('active'));
    const idx = list.findIndex((r) => r.id === revisionId);
    const items = document.querySelectorAll('#historyList li');
    if (items[idx]) items[idx].classList.add('active');

    const detail = await this._api(`/checklist/revisions/${revisionId}/${this._qs()}`);
    const wrap = document.getElementById('historyDetail');
    const { date, time } = this._splitDateTime(detail.published_at);

    const summaryHtml = this._renderChangeSummary(detail);

    const sectionsHtml = (detail.revision_data?.sections || [])
      .map(
        (section, sIdx) => `
        <article class="hd-section">
          <header class="hd-section-header">
            <h4>섹션 ${sIdx + 1}. ${this._escape(section.name)}</h4>
            <span class="hd-section-count">문항 ${section.items?.length || 0}개</span>
          </header>
          ${
            section.description
              ? `<p class="hd-section-desc">${this._escape(section.description)}</p>`
              : ''
          }
          <ol class="hd-item-list">
            ${(section.items || [])
              .map(
                (it) => `
              <li class="hd-item">
                <span class="hd-item-text">${this._escape(it.title)}</span>
                ${it.is_required === false ? '<span class="hd-item-optional">선택</span>' : ''}
              </li>`,
              )
              .join('')}
          </ol>
        </article>`,
      )
      .join('');

    wrap.innerHTML = `
      <header class="hd-head">
        <div class="hd-head-title">
          <span class="hd-version-badge">v${detail.version}</span>
          <h4>${date} 기준 체크리스트</h4>
        </div>
        <p class="hd-muted">당시 반영된 전체 문항과 마지막 서약 문구를 보여줍니다.</p>
      </header>

      <section class="hd-meta-grid">
        <div>
          <div class="hd-field-label">기준 일시</div>
          <div class="hd-field-value">${date} ${time}</div>
        </div>
        <div>
          <div class="hd-field-label">수정자</div>
          <div class="hd-field-value">${this._escape(detail.published_by_name || '-')}</div>
        </div>
      </section>

      ${summaryHtml}

      <section class="hd-body">
        ${sectionsHtml || '<p class="empty-state">스냅샷에 포함된 섹션이 없습니다.</p>'}
      </section>

      <section class="hd-pledge">
        <h4>최종 확인 및 서약</h4>
        <label><input type="checkbox" disabled> ${this._escape(PLEDGE_TEXT)}</label>
      </section>
    `;
  },

  _renderChangeSummary(detail) {
    const s = detail.change_summary || {};
    if (s.is_initial) {
      return `
        <section class="hd-summary hd-summary-initial">
          <span class="hd-summary-icon">●</span>
          <div>
            <div class="hd-summary-title">최초 발행</div>
            <div class="hd-summary-line">이 시점에 체크리스트가 처음 반영되었습니다.</div>
          </div>
        </section>`;
    }
    const sectionParts = [];
    if (s.sections_added) sectionParts.push(`<strong>${s.sections_added}</strong>개 추가`);
    if (s.sections_modified) sectionParts.push(`<strong>${s.sections_modified}</strong>개 수정`);
    if (s.sections_removed) sectionParts.push(`<strong>${s.sections_removed}</strong>개 삭제`);
    const itemParts = [];
    if (s.items_added) itemParts.push(`<strong>${s.items_added}</strong>개 추가`);
    if (s.items_modified) itemParts.push(`<strong>${s.items_modified}</strong>개 수정`);
    if (s.items_removed) itemParts.push(`<strong>${s.items_removed}</strong>개 삭제`);

    const noChanges = sectionParts.length === 0 && itemParts.length === 0;

    return `
      <section class="hd-summary">
        <div class="hd-summary-title">변경 요약 <small>(v${s.previous_version} → v${detail.version})</small></div>
        <ul class="hd-summary-lines">
          ${
            noChanges
              ? '<li>이전 버전과 내용 변경이 없습니다.</li>'
              : `
                ${sectionParts.length ? `<li>섹션 ${sectionParts.join(', ')}</li>` : ''}
                ${itemParts.length ? `<li>문항 ${itemParts.join(', ')}</li>` : ''}
              `
          }
        </ul>
      </section>`;
  },

  // ── 유틸 ─────────────────────────────────────────────
  _formatDate(iso) {
    if (!iso) return '-';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '-';
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    return `${yyyy}-${mm}-${dd}`;
  },

  _splitDateTime(iso) {
    if (!iso) return { date: '-', time: '' };
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return { date: '-', time: '' };
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    const hh = String(d.getHours()).padStart(2, '0');
    const mi = String(d.getMinutes()).padStart(2, '0');
    return { date: `${yyyy}-${mm}-${dd}`, time: `${hh}:${mi}` };
  },

  _escape(s) {
    return String(s ?? '').replace(/[&<>"']/g, (c) => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    })[c]);
  },
};

document.addEventListener('DOMContentLoaded', () => SafetyChecklistAdmin.init());
