/* admin/alerts/policy_modal.js — 알림 정책 등록/수정 모달.
 *
 * 책임: 모달 열기·닫기 / 탭 전환 / 폼 prefill / chip 토글 / 권고 조치 동적 라인 /
 *       alarm_type 따라 위험·주의 2섹션 vs 단일 섹션 자동 분기 / 저장 (POST/PATCH).
 *
 * AlertPolicyAdmin (목록) 가 init 시 호출. 저장 성공 시 onSaved 콜백으로 목록 새로고침.
 */
'use strict';

// alarm_type 별 권고 조치 분기 — 0021 시드 데이터와 동기. 추가 type 발생 시 갱신.
const LEVEL_AWARE_TYPES = new Set([
  'gas_threshold',
  'gas_anomaly_ai',
  'power_overload',
  'power_anomaly_ai',
  'geofence_intrusion',
]);

// alarm_type 별 알림 내용 기본 템플릿 — 한글 토큰 표기 (운영자 친화).
// [발생원]·[요약] 토큰은 저장 시 Django 변수 ({{ source_label }} 등) 로 변환.
// 신규 등록 시 이벤트 상세 선택하면 textarea 비어있을 때만 prefill (편집 보호).
const DEFAULT_TEMPLATES = {
  gas_threshold:        '[발생원] 가스 위험 — [요약]',
  gas_anomaly_ai:       '[발생원] 가스 AI 이상 — [요약]',
  power_overload:       '[발생원] 전력 과부하 — [요약]',
  power_anomaly_ai:     '[발생원] 전력 AI 이상 — [요약]',
  geofence_intrusion:   '[발생원] 위험구역 진입 — [요약]',
  ppe_violation:        'PPE 미착용 감지 — [발생원]',
  safety_check_pending: '안전 점검 미완료 — [요약]',
  vr_training_not_done: 'VR 교육 미이수 — [요약]',
  inspection_scheduled: '점검 예정 — [요약]',
  storage_overdue:      '보관 주기 실패 — [요약]',
  batch_failed:         '배치 실패 — [요약]',
  sensor_fault:         '센서 통신 이상 — [발생원]',
};

// 한글 토큰 ↔ Django Template 변수 양방향 매핑.
// UI 에는 [발생원] 같은 한글만 노출, DB 저장은 Django 문법으로.
const TOKEN_TO_VAR = {
  '[발생원]': '{{ source_label }}',
  '[요약]':   '{{ summary }}',
};
const VAR_TO_TOKEN = {
  '{{ source_label }}': '[발생원]',
  '{{summary}}':         '[요약]',
  '{{ summary }}':       '[요약]',
  '{{source_label}}':    '[발생원]',
};

function tokensToVars(text) {
  let out = text || '';
  for (const [token, v] of Object.entries(TOKEN_TO_VAR)) {
    out = out.split(token).join(v);
  }
  return out;
}

function varsToTokens(text) {
  let out = text || '';
  for (const [v, token] of Object.entries(VAR_TO_TOKEN)) {
    out = out.split(v).join(token);
  }
  return out;
}

const PolicyModal = {
  mode: 'create',          // 'create' | 'edit'
  policyId: null,
  channels: new Set(),
  recipients: new Set(),
  isActive: true,
  onSaved: null,

  init(onSaved) {
    this.onSaved = onSaved;
    this._bindEvents();
  },

  open(mode, policy = null) {
    this.mode = mode;
    this.policyId = policy ? policy.id : null;
    document.getElementById('policyModalTitle').textContent =
      mode === 'create' ? '알림 정책 등록' : '알림 정책 수정';

    this._resetForm();
    if (policy) this._prefill(policy);
    this._switchTab('basic');
    document.getElementById('policyFormModal').style.display = 'flex';
    // (display 는 inline override 라 'flex' 가 .ap-modal-overlay 의 'flex' 와 일치)

    // 이벤트 상세가 채워졌으면 권고 조치 섹션 동기화 (수정 모드).
    const et = document.getElementById('policyEventType').value;
    if (et) this._syncActionSections(et, policy ? policy.recommended_actions : null);
  },

  close() {
    document.getElementById('policyFormModal').style.display = 'none';
  },

  // ── 이벤트 바인딩 (init 시 1회) ─────────────────────────

  _bindEvents() {
    document.getElementById('btnPolicyClose').addEventListener('click', () => this.close());
    document.getElementById('btnPolicyCancel').addEventListener('click', () => this.close());
    document.getElementById('btnPolicySubmit').addEventListener('click', () => this._submit());

    // 탭 전환
    document.querySelectorAll('.ap-tab').forEach(btn => {
      btn.addEventListener('click', () => this._switchTab(btn.dataset.tab));
    });

    // 이벤트 상세 변경 → 권고 조치 섹션 분기 다시 계산 + 빈 textarea 면 기본 템플릿 prefill
    document.getElementById('policyEventType').addEventListener('change', (e) => {
      this._syncActionSections(e.target.value);
      this._prefillDefaultTemplate(e.target.value);
    });

    // chip 토글
    this._bindChipGroup('policyChannelChips', this.channels);
    this._bindChipGroup('policyRecipientChips', this.recipients);

    // 사용 여부 (single-select chip)
    document.querySelectorAll('#policyActiveChips .ap-chip').forEach(c => {
      c.addEventListener('click', () => {
        document.querySelectorAll('#policyActiveChips .ap-chip').forEach(x => x.classList.remove('selected'));
        c.classList.add('selected');
        this.isActive = c.dataset.value === 'true';
      });
    });

    // 권고 조치 라인 추가
    document.querySelectorAll('.ap-action-add').forEach(btn => {
      btn.addEventListener('click', () => this._addActionRow(btn.dataset.level));
    });

    // 변수 칩 클릭 → textarea 커서 위치에 토큰 삽입
    document.querySelectorAll('.ap-var-chip').forEach(btn => {
      btn.addEventListener('click', () => this._insertAtCursor(btn.dataset.token));
    });

    // 외부 클릭으로 닫기
    document.getElementById('policyFormModal').addEventListener('click', (e) => {
      if (e.target.id === 'policyFormModal') this.close();
    });
  },

  _bindChipGroup(containerId, set) {
    document.querySelectorAll(`#${containerId} .ap-chip`).forEach(c => {
      c.addEventListener('click', () => {
        const v = c.dataset.value;
        if (set.has(v)) { set.delete(v); c.classList.remove('selected'); }
        else            { set.add(v); c.classList.add('selected'); }
      });
    });
  },

  // ── 탭 ────────────────────────────────────────────────

  _switchTab(name) {
    document.querySelectorAll('.ap-tab').forEach(b => {
      b.classList.toggle('active', b.dataset.tab === name);
    });
    document.querySelectorAll('.ap-tab-panel').forEach(p => {
      p.classList.toggle('active', p.dataset.tabPanel === name);
    });
  },

  // ── 폼 초기화 / prefill ──────────────────────────────────

  _resetForm() {
    document.getElementById('policyName').value = '';
    document.getElementById('policyEventType').value = '';
    document.getElementById('policyMessageTemplate').value = '';
    this.channels.clear();
    this.recipients.clear();
    this.isActive = true;

    document.querySelectorAll('#policyChannelChips .ap-chip, #policyRecipientChips .ap-chip')
      .forEach(c => c.classList.remove('selected'));
    document.querySelectorAll('#policyActiveChips .ap-chip').forEach(c => {
      c.classList.toggle('selected', c.dataset.value === 'true');
    });

    document.querySelectorAll('.ap-action-section').forEach(s => s.style.display = 'none');
    document.querySelectorAll('.ap-action-list').forEach(l => l.innerHTML = '');
    document.getElementById('actionsHint').style.display = 'block';
  },

  _prefill(p) {
    document.getElementById('policyName').value = p.name || '';
    document.getElementById('policyEventType').value = p.event_type || '';
    // DB 는 Django 변수 ({{ source_label }} 등) 저장 → UI 에는 [발생원] 한글 토큰으로 표시
    document.getElementById('policyMessageTemplate').value = varsToTokens(p.message_template || '');

    (p.channels || []).forEach(v => {
      this.channels.add(v);
      const c = document.querySelector(`#policyChannelChips .ap-chip[data-value="${v}"]`);
      if (c) c.classList.add('selected');
    });
    (p.target_user_types || []).forEach(v => {
      this.recipients.add(v);
      const c = document.querySelector(`#policyRecipientChips .ap-chip[data-value="${v}"]`);
      if (c) c.classList.add('selected');
    });

    this.isActive = p.is_active !== false;
    document.querySelectorAll('#policyActiveChips .ap-chip').forEach(c => {
      c.classList.toggle('selected', (c.dataset.value === 'true') === this.isActive);
    });
  },

  // textarea 가 비어있을 때만 default template 채움. 이미 운영자가 편집한
  // 내용이 있으면 덮어쓰지 않음 (편집 보호).
  _prefillDefaultTemplate(eventType) {
    const ta = document.getElementById('policyMessageTemplate');
    if (!ta || ta.value.trim() !== '') return;
    const tpl = DEFAULT_TEMPLATES[eventType];
    if (tpl) ta.value = tpl;
  },

  // textarea 커서 위치에 토큰 삽입 — 변수 칩 클릭 시 호출.
  _insertAtCursor(token) {
    const ta = document.getElementById('policyMessageTemplate');
    if (!ta) return;
    const start = ta.selectionStart ?? ta.value.length;
    const end = ta.selectionEnd ?? ta.value.length;
    const before = ta.value.slice(0, start);
    const after = ta.value.slice(end);
    ta.value = `${before}${token}${after}`;
    const pos = start + token.length;
    ta.focus();
    ta.setSelectionRange(pos, pos);
  },

  // ── alarm_type 분기 + 권고 조치 ──────────────────────────

  _syncActionSections(eventType, existingActions = null) {
    const hint = document.getElementById('actionsHint');
    const dangerSec = document.querySelector('.ap-action-section[data-level="danger"]');
    const warningSec = document.querySelector('.ap-action-section[data-level="warning"]');
    const defaultSec = document.querySelector('.ap-action-section[data-level="default"]');

    document.getElementById('actionListDanger').innerHTML = '';
    document.getElementById('actionListWarning').innerHTML = '';
    document.getElementById('actionListDefault').innerHTML = '';

    if (!eventType) {
      hint.style.display = 'block';
      dangerSec.style.display = 'none';
      warningSec.style.display = 'none';
      defaultSec.style.display = 'none';
      return;
    }

    hint.style.display = 'none';
    const levelAware = LEVEL_AWARE_TYPES.has(eventType);
    dangerSec.style.display = levelAware ? 'block' : 'none';
    warningSec.style.display = levelAware ? 'block' : 'none';
    defaultSec.style.display = levelAware ? 'none' : 'block';

    // existingActions 가 있으면 prefill, 없으면 빈 1줄 시드.
    const actions = existingActions || {};
    if (levelAware) {
      (actions.danger || ['']).forEach(s => this._addActionRow('danger', s));
      (actions.warning || ['']).forEach(s => this._addActionRow('warning', s));
    } else {
      (actions.default || ['']).forEach(s => this._addActionRow('default', s));
    }
  },

  _addActionRow(level, text = '') {
    const list = document.getElementById({
      danger: 'actionListDanger',
      warning: 'actionListWarning',
      default: 'actionListDefault',
    }[level]);
    const idx = list.children.length + 1;

    const row = document.createElement('div');
    row.className = 'ap-action-row';
    row.innerHTML = `
      <span class="ap-action-index">${idx}.</span>
      <input type="text" class="ap-action-input" placeholder="권고 조치 단계">
      <button type="button" class="ap-action-del">삭제</button>
    `;
    row.querySelector('.ap-action-input').value = text;
    row.querySelector('.ap-action-del').addEventListener('click', () => {
      row.remove();
      this._renumber(level);
    });
    list.appendChild(row);
  },

  _renumber(level) {
    const list = document.getElementById({
      danger: 'actionListDanger',
      warning: 'actionListWarning',
      default: 'actionListDefault',
    }[level]);
    [...list.children].forEach((row, i) => {
      row.querySelector('.ap-action-index').textContent = `${i + 1}.`;
    });
  },

  _collectActions() {
    const collect = (listId) =>
      [...document.querySelectorAll(`#${listId} .ap-action-input`)]
        .map(i => i.value.trim())
        .filter(Boolean);

    const eventType = document.getElementById('policyEventType').value;
    if (LEVEL_AWARE_TYPES.has(eventType)) {
      return {
        danger: collect('actionListDanger'),
        warning: collect('actionListWarning'),
      };
    }
    const def = collect('actionListDefault');
    return def.length > 0 ? { default: def } : {};
  },

  // ── 저장 ──────────────────────────────────────────────

  async _submit() {
    const payload = {
      name: document.getElementById('policyName').value.trim(),
      event_type: document.getElementById('policyEventType').value,
      channels: [...this.channels],
      target_user_types: [...this.recipients],
      is_active: this.isActive,
      // UI 의 [발생원] 한글 토큰을 Django 변수 ({{ source_label }}) 로 변환해 저장
      message_template: tokensToVars(document.getElementById('policyMessageTemplate').value),
      recommended_actions: this._collectActions(),
    };

    // 클라이언트 검증 (간단한 필수 체크 — 서버가 최종 검증).
    if (!payload.name) return this._error('정책명을 입력하세요.');
    if (!payload.event_type) return this._error('이벤트 상세를 선택하세요.');
    if (payload.channels.length === 0) return this._error('발송 채널을 1개 이상 선택하세요.');
    if (payload.target_user_types.length === 0) return this._error('수신 대상을 1개 이상 선택하세요.');

    const url = this.mode === 'create'
      ? '/api/admin/alerts/policies/'
      : `/api/admin/alerts/policies/${this.policyId}/`;
    const method = this.mode === 'create' ? 'POST' : 'PATCH';

    try {
      const res = await Auth.apiFetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        return this._error(`저장 실패: ${JSON.stringify(err)}`);
      }
      this.close();
      if (this.onSaved) await this.onSaved();
    } catch (e) {
      console.error('[PolicyModal] submit 실패:', e);
      this._error('저장 중 오류가 발생했습니다.');
    }
  },

  _error(msg) {
    alert(msg);
  },
};
