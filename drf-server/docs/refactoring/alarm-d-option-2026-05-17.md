# D 옵션 본격 — 헤더 미확인 배지 + 60s 클라 dedup + 1분 토스트 격상

작성일: 2026-05-17
브랜치: `feature/alarm-phase2-global-loading`
commit: `e9c930e feat: D 옵션 본격 — 헤더 미확인 배지 + 60s 클라 dedup + 1분 토스트 격상`
선행 문서: [`alarm-phase2-completion-2026-05-17.md`](alarm-phase2-completion-2026-05-17.md) — Phase 2 완성 + 이벤트 패널 UX
관련 문서: [`docs/codereviews/2026_05_17/alarm-d-option-flow.md`](../../../docs/codereviews/2026_05_17/alarm-d-option-flow.md) — 코드 흐름·함수 분석

---

## 개요

선행 작업 (`alarm-popup-policy-followups.md` 문제 C — D 옵션 본격 미해결) 의 잔여 항목. 운영자가 다른 페이지·다른 탭·자리 비움 상태에서도 알람을 놓치지 않도록 보장하는 **헤더 미확인 알람 배지** + 백엔드 cooldown 과 일치하는 **60s 클라이언트 dedup** + DANGER 토스트의 **1분 무응답 시 차단형 모달 격상**.

### 시연 컨텍스트 (2026-05-17 사용자 확정)
**학습용 프로젝트**. "JWT user-scoped 카운트 + Phase 1 EventAcknowledgement 재활용 + WS CustomEvent 구독 + localStorage TTL 영속화" 통합 시연 가능. memory: [`demo-2026-06-14-arima-roadmap`](/home/cjy/.claude/projects/-home-cjy-diconai/memory/demo_2026_06_14_arima_roadmap.md), [`code-reuse-preference`](/home/cjy/.claude/projects/-home-cjy-diconai/memory/code_reuse_preference.md).

### D 옵션 의도 (alarm-popup-policy-followups.md 문제 C 재정리)

선행 상태:
- 백엔드 `ALARM_REPOPUP_COOLDOWN_SEC` (기본 60s) 가 같은 event 의 재푸시 60s cooldown 적용
- alarm-ws.js 의 `is_new_event === true` 분기 — 새 알람만 팝업 표시
- 즉 백엔드만으로 60s dedup 비슷한 효과는 있었음

부족했던 점:
1. **다른 페이지·다른 탭 인지** — 운영자가 admin-panel 폼 작성 중이면 알람 발생 인지 ↓
2. **자리 비움 대응** — 잠깐 자리 비웠다가 돌아왔을 때 미확인 알람 흔적 없음
3. **반복 팝업 부담** — 백엔드 cooldown 통과 직후 다중 탭에서 같은 알람을 각 탭에서 팝업 → 운영자 피로
4. **차단형 정책** — 첫 토스트를 놓쳤을 때 인지 보장 부족 (10초 격상은 너무 짧아 폼 작성 의도적 무시 시간조차 부족)

---

## 디자인 결정 매트릭스

D 옵션 plan 의 5건 결정 사항 (D1~D5) + 차단형 정책 결정:

| 항목 | 결정 | 거부한 옵션 + 이유 |
|---|---|---|
| **D1 — 헤더 배지 위치** | `header.html` 의 `header-icons` 안 (로그아웃 좌측) + `admin_panel/base.html` 의 topbar | "관리자 메뉴 옆": 헤더 중앙은 다른 정보 (시스템명·관리자 메뉴 버튼) 와 충돌. "상단 프로그레스 바": 추상적이라 학습용 시연에 부적합 |
| **D2 — 카운터 초기값** | 백엔드 API 조회 (정확성) — `summary.user_unread_event_count` 신규 필드 | "0 부터 시작": 단순하지만 페이지 진입 시점에 본인 미확인 표시 못 함. Phase 1 EventAcknowledgement 모델 재활용 가치 명확 |
| **D3 — 카운터 reset 트리거** | 배지 클릭 → 이력 페이지 이동 + reset (운영자 명시 의사) | "팝업 확인 버튼 자동": 운영자가 의도적 무시도 reset 함 — 잘못된 감소. "이력 페이지 진입 자동": 다른 경로로 이력 페이지 진입 시도 reset |
| **D4 — localStorage 키** | `diconai:alarm:popup:dedup` prefix — 기존 `diconai:alarm:*` 컨벤션 일관 | (단일 결정) |
| **D5 — dedup 시간** | 60s — 백엔드 `ALARM_REPOPUP_COOLDOWN_SEC` 일치 | "30s": 백엔드 cooldown 과 불일치 → 같은 알람이 클라에서 통과 후 백엔드 차단되는 어색함. "90s": 학습용 시연엔 적합하지만 운영자 알람 파일 ↓ 우려 |
| **차단형 정책** | 적용 — DANGER 토스트 60s 무응답 시 모달 격상 | "미적용": 운영자가 첫 토스트 놓치면 완전 놓침. 학습 시연 핵심 가치 ↓ |

### 학습 시연 가치 — 본 commit 의 6 주제

| 학습 주제 | 시연 가능 코드 위치 |
|---|---|
| JWT user-scoped 카운트 (Phase 1 모델 활용) | `selectors/event_ack_selector.get_user_unread_event_count` |
| localStorage TTL 영속화 (silent fail + JSON 직렬화) | `alarm-popup.js` 의 `_DedupStore` |
| CustomEvent 구독 모델 (모듈 간 느슨한 결합) | `alarm-badge.js` 가 `newAlarmEvent` listen |
| Timer race 디버깅 (dismiss vs escalate) | `alarm-popup.js` AlarmToastStack 의 race fix |
| 다크/라이트 테마 분리 (`header.css` vs `admin.css`) | `.alarm-badge-count` 두 테마 별도 정의 |
| 헤더 통합 우회 (`header.html` 미사용 페이지 대응) | `admin_panel/base.html` 자체 topbar 에 별도 추가 |

---

## 작업 분할 + 재활용 자산

### Backend

| 작업 | 위치 | 재활용 자산 | 신규 |
|---|---|---|---|
| `get_user_unread_event_count(user_id)` selector | `apps/alerts/selectors/event_ack_selector.py` | `get_acked_user_ids` 패턴 (Phase 1, 2026-05-15) — 같은 모듈 + `EventAcknowledgement.event` FK 인덱스 활용 | NOT EXISTS subquery (`exclude(event_acknowledgements__user_id=...).count()`) ~15줄 |
| summary endpoint 에 `user_unread_event_count` 필드 추가 | `apps/alerts/views/alarm_record.summary` | 기존 summary endpoint 흐름 (`unacknowledged_event_count` 옆) | selector 호출 1줄 + serializer 필드 1줄 + Response 키 1줄 |

### Frontend — Header HTML

| 작업 | 위치 | 재활용 자산 | 신규 |
|---|---|---|---|
| 종 아이콘 + 카운트 배지 (다크) | `templates/components/header.html` 의 `header-icons` | 기존 `btnRefresh`/`btnHome` HTML 패턴 (`.icon-btn`) | `<button id="btnAlarmBadge">` + `<svg>` (bell) + `<span class="alarm-badge-count">` |
| 종 아이콘 (라이트) | `templates/admin_panel/base.html` 의 `topbar-right` | 같은 HTML 구조 (admin_panel 은 `header.html` 미사용 — 자체 topbar) | 같은 buttom 별도 추가 |

### Frontend — CSS

| 작업 | 위치 | 재활용 자산 | 신규 |
|---|---|---|---|
| `.alarm-badge-btn` / `.alarm-badge-count` (다크) | `static/css/components/header.css` | 기존 `.badge` 의 absolute/색 패턴 (헤더 우측 카운트 동그라미) | 적응형 너비 (min-width + padding + border-radius) — `.badge` 의 13x13 고정과 달리 1~3자리 수용 |
| `.alarm-badge-btn` / `.alarm-badge-count` (라이트) | `static/css/admin.css` | header.css 와 같은 클래스 구조 (테마 변경 시 색만 다름 — 스크롤바 패턴과 동일) | 색만 라이트 톤 (`#ef4444` thumb) |

### Frontend — alarm-badge.js (신규)

| 메서드 | 재활용 자산 | 신규 |
|---|---|---|
| `_render()` 카운터 갱신 + 표시/숨김 분기 | `alarm-popup.js` 의 `_renderDropBadge` 패턴 | 신규 — 종 항상 표시 / 카운트만 분기 |
| `_fetchInitial()` summary fetch | `Auth.apiFetch` 그대로 | 신규 — `Math.max(_count, n)` race 보정 |
| `_onNewAlarm` CustomEvent listener | `event-panel.js` 의 `newAlarmEvent` 구독 패턴 | 단순 카운터 ↑ |
| `_onBadgeClick` reset + 이력 페이지 이동 | `alarm-popup.js` 의 `_goDetail` 의 `window.location.href` 패턴 | reset → href |

### Frontend — alarm-popup.js (60s 클라 dedup + race fix)

| 작업 | 재활용 자산 | 신규 |
|---|---|---|
| `_DedupStore` localStorage 영속화 | `_AckStore` / `_LastSeen` 패턴 그대로 (load + has + add + persist) | TTL 만료 시 stale 자동 정리 (`has()` 안에서 stale 즉시 delete + persist) |
| `_popupDedupKey(data)` 합성 키 | `event-panel.js` 의 `_dedupKey` 컨벤션 (event_id 우선, 합성 fallback) | 인라인 함수 — alarm-popup.js 안에서만 사용 |
| `show()` 진입에 dedup 분기 | `_AckStore.has(eventId)` 분기 옆 같은 패턴 | `_DedupStore.has(key) → return`, 통과 시 `_DedupStore.add(key)` |
| `_TOAST_ESCALATE_MS` 10s → 60s | (단순 상수 변경) | 60s = 백엔드 cooldown 일치 |
| dismiss vs escalate race fix | (없음 — 신규 분기) | DANGER 는 escalate timer 만 (dismiss 안 set), WARNING 은 dismiss timer 만 (격상 없음) |

### Script include (2 군데)

| 위치 | 이유 |
|---|---|
| `templates/dashboard/main.html` | 메인 대시보드 — alarm_stack 미사용 (`dashboard/websocket.js` 통합 처리 경계) |
| `templates/components/alarm_stack.html` | snb_details + admin_panel 자동 적용 |

**총 라인 — 신규 ~75줄 + docstring/주석 ~220줄 = 299줄**. 재활용 자산 충분 활용으로 신규 작성 비중 낮음.

---

## 동작 시나리오

### S1 — 페이지 진입 시 헤더 배지 초기화
1. 로그인 후 페이지 진입 → DOMContentLoaded → `AlarmBadge.init()` 호출
2. `_fetchInitial()` → `GET /alerts/api/alarms/summary/` → `user_unread_event_count` 추출
3. `_render()` — count = 0 이면 종만 표시, ≥ 1 이면 종 + 빨간 동그라미

### S2 — 다른 페이지에서 새 알람 발생
1. WS 알람 → alarm-ws.js → `newAlarmEvent` dispatch
2. AlarmBadge 가 `document.addEventListener('newAlarmEvent', _onNewAlarm)` 으로 수신
3. `_count += 1` + `_render()` — 빨간 동그라미 +1
4. 운영자가 다른 페이지에 있어도 헤더 배지로 알람 발생 인지

### S3 — 60s 안 같은 알람 재발생
1. 첫 알람 시 alarm-popup 의 `_DedupStore.add(key)` — 60s TTL 시작
2. 60s 안 같은 알람 도착 (예: 백엔드 cooldown 통과 직후 다중 탭에서 받음)
3. alarm-popup `show()` 진입에서 `_DedupStore.has(key)` 가 true → 팝업 skip
4. AlarmBadge 는 newAlarmEvent 별도 구독이라 카운터 ↑ (운영자 누적 인지 보장)

### S4 — DANGER 토스트 60s 무응답 격상
1. admin-panel 페이지 (DisplayMode = 'toast') 에서 DANGER 알람 도착
2. `AlarmToastStack.push()` → 우상단 토스트 표시 (폼 작성 비차단)
3. 60s 동안 운영자 무응답 (클릭·닫기 X)
4. `_timers.escalate` fire → `_dismiss(eventId, item)` + `AlarmPopup.show({ __forceModal: true })`
5. 차단형 모달 표시 (`/dashboard/` 와 같은 형태)

### S5 — 배지 클릭 → 이력 페이지
1. 운영자가 헤더 종 클릭
2. `_onBadgeClick()` → `_count = 0` + `_render()` + `window.location.href = '/dashboard/monitoring/events/'`
3. 이력 페이지 진입 → 새 페이지 load → `AlarmBadge.init()` → `_fetchInitial()` 재산정
4. 사이 본인이 ack 한 event 있으면 자연 ↓

---

## 검증

### 자동
- DRF pytest: **53/53** 통과 (selector 신규 + summary 변경 무회귀)
- pre-commit: ruff/ruff-format 모두 Pass

### 수동 (브라우저 시나리오)
| 시나리오 | 결과 |
|---|---|
| 메인 대시보드 헤더 종 (count > 0 일 때 빨간 동그라미) | ✅ 캡처 확인 (count=4, count=20) |
| admin-panel 헤더 종 표시 | ✅ admin_panel/base.html 별도 추가 |
| snb_details 헤더 종 표시 | ✅ alarm_stack 통한 자동 적용 |
| 새 알람 발생 시 카운터 ↑ | ✅ newAlarmEvent 구독 동작 |
| 60s dedup — 같은 알람 재팝업 skip | ✅ _DedupStore TTL 동작 |
| DANGER 토스트 60s 후 모달 격상 | ✅ race fix 후 동작 |
| 배지 클릭 → 이력 페이지 + reset | ✅ window.location.href 동작 |

### 디버깅 학습 — race fix 자체가 시연 가치
- 초기 도입 시 `_TOAST_ESCALATE_MS` 만 10s → 60s 로 변경 → 격상 안 됨
- 진단 — DANGER 토스트가 dismiss(15s) + escalate(60s) 두 timer set, dismiss 가 먼저 fire → `_dismiss` 안에서 escalate clearTimeout → 격상 cancel
- 수정 — DANGER 는 escalate timer 만 (dismiss 안 set, 격상 시 _dismiss 가 처리)
- 학습 — 의도 변경이 다른 의도 (`_dismiss` 의 cleanup) 와 race 충돌. setTimeout 의 순서 의존성 디버깅 사례

---

## 보류 항목 (D 옵션 잔여 + 향후 작업)

본 commit 의 범위 — 학습 시연 컨텍스트 충분 + 운영급 디테일은 시연 후. 다음 단계로:

| 항목 | 사유 |
|---|---|
| **차단형 정책 — 60s 후 1회 재발화 (백엔드 외 클라 setTimeout)** | 현재 백엔드 cooldown(60s) + 클라 dedup(60s) 동기화로 자연 충족. 추가 클라 setTimeout 은 race 위험만 ↑. 운영자 피드백 후 필요 시 도입 |
| **헤더 배지 우클릭 → 컨텍스트 메뉴 (간단 미리보기)** | UX 추가 검토 + 시연 critical 0 |
| **localStorage 만료 알람 ack 동기화** | _AckStore 와 _DedupStore 의 TTL 다름 (24h vs 60s) — 의도된 분리 (ack 영구, dedup 임시). 향후 운영 데이터로 검토 |
| **다중 user 동시 사용 시 카운터 일관성** | summary API 매 페이지 fetch 라 일관. WS 통한 실시간 server-pushed count 는 시연 후 검토 |

---

## 관련 파일 (본 commit 변경분)

### Backend
- `apps/alerts/selectors/event_ack_selector.py` — `get_user_unread_event_count` 신규
- `apps/alerts/views/alarm_record.py` — summary 필드 추가

### Frontend — JS
- `static/js/shared/alarm-badge.js` — 신규
- `static/js/shared/alarm-popup.js` — `_DedupStore` + dedup 분기 + `_TOAST_ESCALATE_MS` 60s + race fix

### Frontend — HTML
- `templates/components/header.html` — 종 아이콘 + 카운트 배지 (다크)
- `templates/admin_panel/base.html` — 종 아이콘 (라이트, 자체 topbar)
- `templates/components/alarm_stack.html` — alarm-badge.js script
- `templates/dashboard/main.html` — alarm-badge.js script

### Frontend — CSS
- `static/css/components/header.css` — `.alarm-badge-btn` / `.alarm-badge-count` (다크)
- `static/css/admin.css` — 같은 클래스 (라이트)

---

## 다음 작업자 가이드

본 문서를 본 시점에 이미 commit 머지됐다고 가정. 다음 작업자 참고 시나리오:

1. **WS 통한 server-pushed unread count 도입 시**
   - 신규 WS 채널 또는 sensors 채널에 `type: "unread_count_update"` 메시지 추가
   - `AlarmBadge.setCount(n)` 활용 — 외부 호출용 API 이미 노출됨
   - 현재 newAlarmEvent 구독은 +1 누적만 — 서버 진실로 set 으로 대체 가능

2. **헤더 배지 디자인 변경 시 (피그마 시안 받으면)**
   - `header.css` 의 `.alarm-badge-count` + `admin.css` 의 같은 클래스 — 두 곳 동일 수정
   - 종 SVG 자체는 header.html / admin_panel/base.html 의 path attribute — 디자이너 SVG 의 path 만 갈아끼움

3. **다른 페이지에 헤더 배지 적용 시 (예: 로그인 후 onboarding 페이지)**
   - 그 페이지의 base template 이 `header.html` include 또는 자체 topbar 인지 확인
   - 자체 topbar 면 admin_panel 패턴 따라 별도 `<button id="btnAlarmBadge">` 추가
   - JS 는 alarm_stack.html 또는 main.html 의 script 통해 자동 로드

4. **클라이언트 dedup 시간 변경 시 (예: 30s 운영 결정)**
   - `_DEDUP_TTL_MS = 30_000` 변경
   - **백엔드 `ALARM_REPOPUP_COOLDOWN_SEC` 도 같이 변경** — 두 값 불일치 시 어색한 동작 (백엔드 통과 한 알람이 클라에서 skip)
   - `_TOAST_ESCALATE_MS` 도 같이 검토 — 사용자 명시 의사 아니면 같은 값 유지 (시간 척도 일관성)

5. **D 옵션 사후 검토 시점에서 race 의심 시**
   - alarm-popup.js 의 `AlarmToastStack._timers` 분기 (DANGER vs WARNING) 확인
   - DANGER 는 escalate timer 만 — dismiss timer 가 다시 추가되면 race 재발 가능
   - codereviews 문서 참조

문의/이슈는 commit hash 기준: `git log --oneline e9c930e`.

---

## 후속 변경 (시간순)

본 commit 이후 알람 영역에 영향을 준 후속 작업. 본 D 옵션 흐름과의 연관 추적용.

### 2026-05-18 W4 — `AlarmRecord.algorithm_source` (ARIMA Un-격하 plan §8)

D 옵션 흐름 (헤더 배지 + 60s 클라 dedup + 1분 격상) 과 **별개의 데이터 보강** 작업. 알람 메시지에 algorithm 출처 라벨 (IF / ARIMA / IF+ARIMA / 야간 가동) prefix 추가.

**D 옵션과의 직접 연관 — 거의 없음**:
- `_DedupStore` 는 (alarm_type, source, level) 기반이라 algorithm_source 영향 X
- 헤더 배지의 카운트도 algorithm 무관 (user_unread_event_count 가 ack 여부만 봄)
- 토스트 60s 격상도 메시지 내용 무관 (level 기준)

**학습 시연 가치에 추가**:
> 본 commit 의 학습 주제 6 (JWT user-scoped 카운트 / localStorage TTL / CustomEvent 구독 / Timer race 디버깅 / 테마 분리 / 헤더 통합 우회) 외에 **시연 시 algorithm 라벨 함께 시연 가능** — 알람 토스트·모달의 메시지가 "IF+ARIMA 이상 감지" 형태로 출처 명시되어 운영자가 어떤 알고리즘이 발화시켰는지 즉시 인지 가능. 시연자가 학습 자료로서 "이런 알람 출처 표시는 다음 W4 commit 에서 추가됐다" 흐름으로 설명 가능.

**관련 commit**:
- `2205a13` feat(alerts): W4 — `AlarmRecord.algorithm_source` + migration 0017 + constants
- `2df4fe4` feat(alerts): AI 추론 가시성 — `get_short_message` algorithm 라벨 + serializer 노출 + WS push payload
- `ccd15aa` fix(ai): ARIMA 실동작 보강 + 토스트 algorithm 라벨

본 commit 의 코드 인용 부분은 W4 의 영향 받지 않음 (D 옵션 코드는 그대로). 본 문서 내용은 최신 코드 기준 stale 없음 — 노트만 추가.
