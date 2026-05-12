# UI/UX 개선 Phase 2 — 변경 요약

> **요약 한 줄**: 색상·시각·연결상태·알람팝업의 가시성과 일관성을 4개 sprint(P1·P2·P3·P5)로 정리. P4·P6·P7은 의도적 보류.

**브랜치**: `feature/alarm_refactory` (Phase 1과 연속) · **커밋**: 7개 (P1·P2·P2확장·P2피드백·WARNING·P3·P5) · **상세 plan**: [skill/plan/ui-refactor-phase2.md](../../skill/plan/ui-refactor-phase2.md) (gitignore 영역)

---

## 왜 이 작업을 했나

Phase 1(알람 신뢰성) 머지 후, 사용자가 운영 화면에서 직접 본 UX 결함과 P1·P2 분석에서 식별된 프론트엔드 일관성 문제를 사용자 체감 임팩트 순으로 정리.

| 운영 피드백 (스크린샷 기반) | 코드 결함 |
|---|---|
| 알람 팝업 텍스트 가독성 부족 | JS·HTML 11곳에 `caution-text`/`danger-text` 하드코딩 분산 |
| 좌측 6px 테두리만 강조, 4면 비대칭 | LevelMapper와 인라인 삼항 매핑 공존 |
| 위험·주의 배지 작아서 시선 안 끔 | 4개 페이지에서 시간 표시 `toLocaleString`/`toLocaleTimeString` 혼용 |
| 알람음 부재 | 비대시보드 페이지 WS 연결 상태 표시 부재 |
| WARNING 알람이 거의 발화 안 됨 | 큐 풀 시 silent drop |

---

## 단계별 변경 (P1·P2·P3·P5)

각 sprint는 단독 커밋이라 단계 단위 롤백 가능.

### P1 — 색상 매핑 LevelMapper 전역화 ([2ad2f22](#))

**무엇**
- 신규: [level-mapper.js](../../drf-server/static/js/shared/level-mapper.js)에 `toTextClass(level)` 헬퍼 추가 (`danger-text`/`caution-text`/`''` 반환)
- 수정: JS 인라인 삼항 6곳 → `LevelMapper.toTextClass()` / `LevelMapper.toCssClass()` 호출
  - `dashboard/websocket.js` AI 가스·전력·증감률 4곳
  - `dashboard/panels/event-panel.js` `addItem`
  - `shared/alarm-popup.js` `_LEVELS.warning.actionClass`에서 caution-text 분리 후 사용 시점에 결합
- 수정: `gas_panel.html` JS 즉시 갱신 placeholder 2곳에서 무의미한 초기 색상 제거

**왜**
- 신규 페이지 추가 시 색상 불일치 구조적 차단
- 백엔드 enum(`danger/warning/normal`) ↔ CSS 클래스(`danger/caution/safe`) 매핑이 한 모듈에만 존재

**남긴 정적 클래스 (의도된 라벨)**: `event_panel.html` "위험 N건"·"주의 N건"·gas_panel.html `aiMaxVal` 상시 빨간 강조 — 디자인 의도라 유지.

---

### P2 — 알람 팝업 가시성·UX 운영 피드백 종합 ([812150d](#) + [e34e1b3](#) + [a101b8a](#))

여러 커밋에 걸쳐 누적된 알람 팝업 개선 — 핵심 12개:

| # | 변경 | 효과 |
|---|---|---|
| 1 | 그룹 카운트 빨간 원형 뱃지 (우상단, ×10+ 펄스) | 폭주 즉시 인지 |
| 2 | 자동닫힘 위험도별 차등 (danger 15s / warning 10s) | 운영자 확인 시간 확보 |
| 3 | 큐 풀 "+N건 누락" 헤더 배지 (클릭 → 이력 페이지) | silent drop 종식 |
| 4 | 폭 확장 340px → 440px | 메시지 줄바꿈 감소 |
| 5 | 4면 균등 2px border + 글로우 펄스 | 시선 강제 (좌측 6px → 4면 균등으로 여백 균형) |
| 6 | 알람 사운드 (Web Audio API 합성, 외부 mp3 없음) | 화면 외 작업 중에도 인지 |
| 7 | 그룹핑 5초 window + groupCount 누적 | 동일 위험 폭주 시 한 팝업으로 |
| 8 | 메시지 구조화 — sensor 굵은 한 줄 + 본문 별도 행 | 가독성 향상 |
| 9 | 위험·주의 배지 13px·padding 키움·letter-spacing | 운영자 시선에서 명확 |
| 10 | 메시지 색상 `text2(어두움)` → `text(밝음)` | 명도 대비 확보 |
| 11 | 임계값 컨텍스트 — `위험 기준 5.0 초과 (측정 9.82)` | 정상/위험 기준 즉시 비교 |
| 12 | 버튼 라벨 — "상세 확인"·"확인" → "상세 보기"·"확인 완료" | 동사 분리, 무의식 클릭 방지 |

**알람 사운드 상세**
- danger: 880Hz × 3펄스 (0.22s 간격, 볼륨 0.32)
- warning: 660Hz × 2펄스 (0.28s 간격, 볼륨 0.22)
- 브라우저 자동재생 정책: AudioContext는 user gesture 후에만 시작 → 첫 클릭 전 알람은 silent fallback

**임계값 컨텍스트 매핑**: 백엔드 페이로드의 `measured_value`/`threshold_value`가 이미 있었으나 [alarm-mapper.js](../../drf-server/static/js/shared/alarm-mapper.js)에서 매핑 누락 → 추가 후 활용.

**XSS 안전**: 메시지 구조화에서 innerHTML 대신 `replaceChildren()` + `createElement()` 사용.

---

### P2 부수 — WARNING 트리거 시간 단축 ([cff5d5f](#))

[apps/alerts/tasks.py](../../drf-server/apps/alerts/tasks.py)의 `WARNING_DURATION_SEC` **10초 → 3초**.

**왜**: 더미 시나리오가 빠르게 NORMAL→WARNING→DANGER로 진행해 10초 카운트다운을 못 채우고 `_revoke`로 취소되어 WARNING 알람이 거의 발화되지 않던 문제. 3초로 단축해 발화율 확보, noise filtering 의도는 유지.

**부수 효과**: summary 텍스트의 "주의 수준 N초 지속"이 "3초 지속"으로 자동 갱신.

---

### P3 — WebSocket 연결 상태 배너 공용화 ([0da12ee](#))

**무엇**
- 신규: [templates/components/ws_conn_banner.html](../../drf-server/templates/components/ws_conn_banner.html) — include용 공용 HTML
- 신규: [shared/ws-conn-banner.js](../../drf-server/static/js/shared/ws-conn-banner.js) — `WsConnBanner.attach(ws)` 헬퍼
  - `ws.onOpen` → 숨김
  - `ws.onClose` → "연결 끊김 — 재연결 중..."
  - `ws.onError(max_reconnect_attempts)` → "연결 실패 — 페이지 새로고침이 필요합니다"
- CSS: `.ws-conn-banner` / `.ws-conn-msg` / `.conn-spinner` fallback ([dashboard.css](../../drf-server/static/css/dashboard.css))
- 적용: `monitoring_power.html` + `websocket_power.js`, `monitoring_workers.html` + `monitoring_workers.js`

**왜**: 기존 `monitoring_gas.html`에만 #gas-conn-banner가 있어 다른 페이지에선 WS 끊김을 사용자가 모름.

**제외**
- `monitoring_realtime`: 이미 `#wsStatus` 별도 표시기 있음 (중복 회피)
- `monitoring_events`: WS 없음 (polling 기반)
- `monitoring_gas`: 기존 `#gas-conn-banner` 유지

**후속 일관성 sprint** (별도 plan): gas/realtime/dashboard 메인을 `#ws-conn-banner`로 마이그레이션 + `.conn-spinner` 중복 정의 통합. 0.5일 추정.

---

### P5 — 시각 표시 형식 TimeFormat 헬퍼 ([d13729c](#))

**무엇**
- 신규: [shared/time-format.js](../../drf-server/static/js/shared/time-format.js)
  - `TimeFormat.abs(input)` → `"2026-05-12 14:30:45 KST"` (전체 시각)
  - `TimeFormat.short(input)` → `"14:30:45"` (대시보드 컴팩트)
  - `TimeFormat.rel(input)` → `"3분 전"` (상대, 호출처 후속에 추가)
- 입력 호환: ISO 문자열·Date·epoch ms 모두 허용, invalid는 `'-'` 반환
- 호출처 교체 4곳: `alarm-popup.js`·`event_list.js`·`event_detail.js`·`event-panel.js`
- Script include 4곳: `dashboard/main.html`·`snb_details/{monitoring_events, event_detail, monitoring_realtime}.html`

**왜**
- 페이지마다 `toLocaleString('ko-KR')` / `toLocaleString('ko-KR', {hour12:false})` / `toLocaleTimeString()` 혼용 → 운영자가 시각 비교 시 혼란
- KST 라벨 부재 → 타임존 모호

**호환성**: `typeof TimeFormat !== 'undefined'` 가드로 script 로드 실패 시 옛 동작 폴백.

---

## 보류·제외 항목

| sprint | 상태 | 사유 |
|---|---|---|
| **P4** Prometheus 알람 큐 메트릭 | 제외 | 다른 작업자가 진행 예정 |
| **P6** 모바일 반응형 | 보류 | 운영 환경이 관제실 PC 중심이라 현 단계 불필요. 향후 현장 폰/태블릿 시나리오 확정 시 별도 sprint |
| **P7** WS 페이로드 type 분리 | 보류 | 호환 모드 유지가 최소 공수. IF §2 시점에 통합 검토 — anomaly도 `alarm_type` 필드만 추가하면 충분, WS 구조 변경 불필요 |

---

## 누적 효과

| 항목 | Phase 2 이전 | Phase 2 이후 |
|---|---|---|
| 색상 매핑 출처 | JS·HTML 11곳에 분산 | LevelMapper 단일 모듈 |
| 알람 팝업 가시성 | 좌측 4px만 강조 | 4면 테두리 + 글로우 펄스 + 비프음 |
| 알람 메시지 가독성 | sensor + 본문 한 덩어리 | 굵은 sensor + 본문 + 임계값 컨텍스트 3행 |
| 그룹 카운트 표시 | 작은 ` (×N)` 텍스트 | 우상단 빨간 원형 뱃지, ×10+ 펄스 |
| 자동닫힘 | 10초 고정 | danger 15s / warning 10s |
| 큐 풀 사용자 인지 | 콘솔 경고만 | 헤더 배지 + 이력 페이지 링크 |
| WARNING 발화율 | 거의 0건 (10초 못 채움) | 3초 트리거로 정상 발화 |
| WS 연결 끊김 인지 | gas 페이지만 | power·workers 추가 |
| 시각 표시 형식 | 4가지 혼용 | TimeFormat 단일 헬퍼 (KST 명시) |
| 알람 사운드 | 없음 | Web Audio API 합성 (위험도별 차등) |
| 버튼 라벨 동사 | "상세 확인"·"확인" 혼동 | "상세 보기"·"확인 완료" 분리 |

---

## 머지 후 운영 관찰 가이드

### 콘솔에서 빠른 검증

```javascript
// 알람 팝업 디자인·사운드·자동닫힘
AlarmPopup.queue = []; AlarmPopup.isOpen = false;
const p = document.getElementById('alarm-popup');
if (p) { p.style.display = 'none'; p.classList.remove('level-danger','level-warning'); }
AlarmPopup.show({
  alarm_level: 'danger',
  sensor_name: '더미 가스센서',
  message: '[긴급] NO₂ (이산화질소) 위험 수준 초과 — 즉시 대피하고 관리자에게 보고하세요.',
  measured_value: 9.82,
  threshold_value: 5.0,
  alarm_type: 'gas_threshold',
  timestamp: new Date().toISOString(),
});
// 기대: 빨간 4면 테두리·펄스·880Hz 비프·임계값 컨텍스트·15초 자동닫힘
```

### Celery worker 로그에서 WARNING 발화 확인

```bash
docker compose logs --since 5m celery-worker 2>&1 | grep -ciE "WARNING 알람"
# 기대: 1건 이상 (3초 트리거 이후 발화율 회복)
```

### 회귀 체크리스트

- [ ] 색상 매핑 인라인 매핑 0건 (grep `caution-text\|danger-text` JS 영역)
- [ ] LevelMapper 호출 13건 이상
- [ ] TimeFormat 호출 4건
- [ ] power·workers 페이지 WS 끊김 시 배너 표시
- [ ] 알람 사운드 user gesture 후 작동
- [ ] danger 알람 15초·warning 10초 자동닫힘
- [ ] 임계값 컨텍스트 줄 표시 (`measured_value`/`threshold_value` 있을 때만)
- [ ] 버튼 라벨 "상세 보기" / "확인 완료"

---

## 후속 sprint 예정

[skill/plan/ui-refactor-phase2.md](../../skill/plan/ui-refactor-phase2.md) "다음 단계" 섹션 참조:

| sprint | 추정 | 트리거 |
|---|---|---|
| WS 연결 표시기 일관성 마이그레이션 (gas·realtime·dashboard 메인 통일) | 0.5일 | 우선순위 결정 시 |
| 이벤트 현황 페이지 개편 (페이지네이션·필터·일괄 토글·카드 동기화·라벨 일관성) | 1~2일 | 운영 피드백 누적 시 |
| Phase 2b — W·A·V 3축 표시 | 0.5일 | 전력 §2-4 머지 후 |
| Phase 2b — anomaly_score 표시 + 자연어 메시지 | 1일 | IF §2 머지 후 |
| Phase 2b — AlarmType.ANOMALY UI 처리 | 0.5일 | IF §2-3 머지 후 |

---

## 코드 참조 일람

| sprint | 파일 | 변경 |
|---|---|---|
| P1 | [shared/level-mapper.js](../../drf-server/static/js/shared/level-mapper.js) | toTextClass 추가 |
| P1 | [shared/alarm-popup.js](../../drf-server/static/js/shared/alarm-popup.js) | _LEVELS 정리 + 사용 시점 결합 |
| P1 | [dashboard/websocket.js](../../drf-server/static/js/dashboard/websocket.js) | 4곳 LevelMapper 적용 |
| P1 | [dashboard/panels/event-panel.js](../../drf-server/static/js/dashboard/panels/event-panel.js) | LevelMapper 적용 |
| P1 | [dashboard/panels/gas_panel.html](../../drf-server/templates/dashboard/panels/gas_panel.html) | placeholder 색상 제거 |
| P2 | [templates/components/alarm_popup.html](../../drf-server/templates/components/alarm_popup.html) | 카운트 뱃지·누락 배지·버튼 라벨 |
| P2 | [shared/alarm-popup.js](../../drf-server/static/js/shared/alarm-popup.js) | 자동닫힘 차등·뱃지·사운드·메시지 구조화·임계값 |
| P2 | [shared/alarm-mapper.js](../../drf-server/static/js/shared/alarm-mapper.js) | measured/threshold 매핑 |
| P2 | [static/css/dashboard.css](../../drf-server/static/css/dashboard.css) | 외경 강조·펄스·배지·메시지 분리·여백 |
| P2 | [apps/alerts/tasks.py](../../drf-server/apps/alerts/tasks.py) | WARNING_DURATION_SEC 3초 |
| P3 | [templates/components/ws_conn_banner.html](../../drf-server/templates/components/ws_conn_banner.html) | 신규 |
| P3 | [shared/ws-conn-banner.js](../../drf-server/static/js/shared/ws-conn-banner.js) | 신규 |
| P3 | [snb_details/monitoring_power.html](../../drf-server/templates/snb_details/monitoring_power.html) | include + script |
| P3 | [snb_details/monitoring_workers.html](../../drf-server/templates/snb_details/monitoring_workers.html) | include + script |
| P3 | [detail/websocket_power.js](../../drf-server/static/js/detail/websocket_power.js) | attach 호출 |
| P3 | [detail/monitoring_workers.js](../../drf-server/static/js/detail/monitoring_workers.js) | attach 호출 |
| P5 | [shared/time-format.js](../../drf-server/static/js/shared/time-format.js) | 신규 |
| P5 | [shared/alarm-popup.js](../../drf-server/static/js/shared/alarm-popup.js) | TimeFormat.abs |
| P5 | [detail/event_list.js](../../drf-server/static/js/detail/event_list.js) | TimeFormat.abs |
| P5 | [detail/event_detail.js](../../drf-server/static/js/detail/event_detail.js) | TimeFormat.abs |
| P5 | [dashboard/panels/event-panel.js](../../drf-server/static/js/dashboard/panels/event-panel.js) | TimeFormat.short |
| P5 | dashboard/main.html · snb_details/{monitoring_events, event_detail, monitoring_realtime}.html | time-format.js include |

총 신규 4 + 수정 14 = 18 파일.
