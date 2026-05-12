/* admin/safety/vr_training.js — VR 교육 관리
 *
 * 역할: /admin-panel/safety/vr-training/ 페이지 동작 전담.
 * - facility별 단일 콘텐츠 조회
 * - 영상 교체 (multipart POST /replace/) — duration 자동 추출은 서버 ffprobe
 * - 메타만 수정 (JSON PATCH /<pk>/)
 *
 * 분기 로직: 모달 [저장] 시
 *   file 선택됨 → POST /replace/ (multipart)
 *   file 없음   → PATCH /<pk>/ (JSON)
 *
 * super_admin 전용: 상단 facility 드롭다운 노출, 다른 공장 콘텐츠 조회 가능.
 */
'use strict';

const VRTrainingAdmin = {
  facilityId: null,
  current: null, // detail or {empty:true,...}
  role: null,

  async init() {
    if (!(await AdminAccess.check())) return;
    this.role = Auth.getRole();
    this._bindEvents();
    await this._initFacilityScope();
    await this._load();
  },

  // ── super_admin 한정 facility 선택 ─────────────────────
  // facility_admin은 본인 공장으로 강제되므로 드롭다운 미노출.
  //
  // [다중 공장 운영 전까지 UI 비활성]
  // 공장 확장 정책이 확정되지 않아 super_admin에게도 드롭다운을 노출하지
  // 않는다. 템플릿·CSS·이벤트 바인딩은 그대로 살아 있고, 다중 공장 전환
  // 결정 시 본 함수의 `wrap.hidden = false;` 한 줄만 풀면 즉시 활성화된다.
  // 그동안 facilityId는 null로 유지되어 서버가 user.facility_id || default로
  // 자동 결정한다.
  async _initFacilityScope() {
    if (this.role !== 'super_admin') return;
    const wrap = document.getElementById('facilitySelectWrap');
    const sel = document.getElementById('facilitySelect');
    if (!sel || sel.options.length === 0) return;
    // wrap.hidden = false;   // 다중 공장 운영 결정 시 활성화
    this.facilityId = Number(sel.value);
    sel.addEventListener('change', async () => {
      this.facilityId = Number(sel.value);
      await this._load();
    });
  },

  _bindEvents() {
    document.getElementById('btnEditMeta').addEventListener('click', () => this._openEdit());
    document.getElementById('vrEditClose').addEventListener('click', () => this._closeEdit());
    document.getElementById('vrEditCancel').addEventListener('click', () => this._closeEdit());
    document.getElementById('btnPickVideo').addEventListener('click', () =>
      document.getElementById('videoInput').click(),
    );
    document.getElementById('videoInput').addEventListener('change', (e) =>
      this._onFilePicked(e.target.files[0]),
    );
    document.getElementById('vrEditForm').addEventListener('submit', (e) => this._onSubmitEdit(e));
  },

  // ── API ────────────────────────────────────────────────
  _qs() {
    return this.facilityId ? `?facility_id=${this.facilityId}` : '';
  },

  async _api(path, opts = {}) {
    const url = `/api/admin/training${path}`;
    const res = await Auth.apiFetch(url, opts);
    if (res.status === 401 || res.status === 403) {
      window.alert('접근 권한이 없습니다.');
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
      err.detail = payload?.detail || null;
      throw err;
    }
    if (res.status === 204) return null;
    return res.json();
  },

  async _apiUpload(path, formData) {
    const url = `/api/admin/training${path}`;
    const headers = {};
    const token = Auth.getAccessToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;
    // Content-Type은 명시하지 않는다 — fetch가 boundary와 함께 자동 설정.
    const res = await fetch(url, { method: 'POST', headers, body: formData });
    if (res.status === 401 || res.status === 403) {
      window.alert('접근 권한이 없습니다.');
      throw new Error('forbidden');
    }
    if (!res.ok) {
      let payload = null;
      try {
        payload = await res.json();
      } catch (_) {
        payload = null;
      }
      const err = new Error(`Upload failed: ${res.status}`);
      err.status = res.status;
      err.detail = payload?.detail || payload?.file?.[0] || null;
      throw err;
    }
    return res.json();
  },

  // ── 로딩 / 렌더 ────────────────────────────────────────
  async _load() {
    try {
      const data = await this._api(`/vr-training/${this._qs()}`);
      this.current = data;
      this._render();
    } catch (err) {
      console.error(err);
    }
  },

  _render() {
    const data = this.current || {};
    const isEmpty = data.empty === true || !data.id;

    document.getElementById('vrEmpty').hidden = !isEmpty;
    document.getElementById('vrSummary').hidden = isEmpty;
    document.getElementById('vrLayout').hidden = isEmpty;
    document.getElementById('btnEditMeta').disabled = isEmpty;

    if (isEmpty) return;

    document.getElementById('sumName').textContent = data.name || '-';
    document.getElementById('sumFacility').textContent = data.facility_name || '-';
    document.getElementById('sumStatus').textContent = data.is_active ? '사용' : '사용 안 함';
    document.getElementById('sumUpdatedAt').textContent = this._fmtDate(data.updated_at);

    document.getElementById('infoName').textContent = data.name || '-';
    document.getElementById('infoFacility').textContent = data.facility_name || '-';
    document.getElementById('infoStatus').textContent = data.is_active ? '사용' : '사용 안 함';
    document.getElementById('infoDuration').textContent = this._fmtDurationLong(data.duration_seconds);
    document.getElementById('infoUpdatedAt').textContent = this._fmtDate(data.updated_at);
    document.getElementById('infoDescription').textContent = data.description || '-';
    document.getElementById('infoOperationNote').textContent = data.operation_note || '-';

    document.getElementById('footerName').textContent = data.name || '';

    const video = document.getElementById('vrPreview');
    if (data.content_url) {
      video.src = data.content_url;
      video.load();
    } else {
      video.removeAttribute('src');
    }

    const badge = document.getElementById('durationBadge');
    if (data.duration_seconds) {
      badge.textContent = this._fmtDurationShort(data.duration_seconds);
    } else {
      // 서버에 duration이 없으면 클라이언트 metadata 로드 시 계산.
      badge.textContent = '--:--';
      video.addEventListener(
        'loadedmetadata',
        () => {
          if (!Number.isFinite(video.duration)) return;
          badge.textContent = this._fmtDurationShort(Math.round(video.duration));
        },
        { once: true },
      );
    }
  },

  // ── 모달 ───────────────────────────────────────────────
  // 영상 파일 선택은 모달 안의 [영상 업로드] 버튼으로 일원화한다.
  _openEdit() {
    const data = this.current || {};
    document.getElementById('editName').value = data.name || '';
    document.getElementById('editDescription').value = data.description || '';
    document.getElementById('editOperationNote').value = data.operation_note || '';
    document.getElementById('editDuration').value = data.duration_seconds
      ? this._fmtDurationLong(data.duration_seconds)
      : '업로드 후 자동 계산';
    document.getElementById('pickedName').textContent = '선택된 파일 없음';
    document.getElementById('videoInput').value = '';
    document.getElementById('vrEditModal').hidden = false;
  },

  _closeEdit() {
    document.getElementById('vrEditModal').hidden = true;
  },

  _onFilePicked(file) {
    if (!file) {
      document.getElementById('pickedName').textContent = '선택된 파일 없음';
      return;
    }
    document.getElementById('pickedName').textContent = file.name;
    document.getElementById('editDuration').value = '업로드 후 자동 계산';
  },

  async _onSubmitEdit(e) {
    e.preventDefault();
    const file = document.getElementById('videoInput').files[0];
    const name = document.getElementById('editName').value.trim();
    const description = document.getElementById('editDescription').value;
    const operationNote = document.getElementById('editOperationNote').value;
    const isEmpty = !this.current || this.current.empty;

    if (!file && isEmpty) {
      window.alert('첫 콘텐츠 등록은 영상 파일이 필요합니다.');
      return;
    }

    try {
      if (file) {
        const fd = new FormData();
        fd.append('file', file);
        if (name) fd.append('name', name);
        fd.append('description', description);
        fd.append('operation_note', operationNote);
        if (this.facilityId) fd.append('facility_id', String(this.facilityId));
        this.current = await this._apiUpload(`/vr-training/replace/${this._qs()}`, fd);
      } else {
        // 메타만 수정.
        const body = {};
        if (name) body.name = name;
        body.description = description;
        body.operation_note = operationNote;
        this.current = await this._api(`/vr-training/${this.current.id}/${this._qs()}`, {
          method: 'PATCH',
          body: JSON.stringify(body),
        });
      }
      this._render();
      this._closeEdit();
    } catch (err) {
      console.error(err);
      window.alert(err.detail || '저장에 실패했습니다.');
    }
  },

  // ── 포매터 ─────────────────────────────────────────────
  _fmtDate(s) {
    if (!s) return '-';
    try {
      const d = new Date(s);
      const pad = (n) => String(n).padStart(2, '0');
      return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    } catch (_) {
      return s;
    }
  },

  _fmtDurationShort(sec) {
    if (sec == null) return '--:--';
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  },

  _fmtDurationLong(sec) {
    if (sec == null) return '-';
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m}분 ${String(s).padStart(2, '0')}초`;
  },
};

document.addEventListener('DOMContentLoaded', () => VRTrainingAdmin.init());
