# 알람 시스템 Phase 2 완성 + 이벤트 패널 UX 개선

작성일: 2026-05-17
브랜치: `feature/alarm-phase2-global-loading` (Phase 2 연속 작업)
선행 문서: [`alarm-system-redesign-2026-05-15.md`](alarm-system-redesign-2026-05-15.md) — Phase 1/2 진단·결정·검증
관련 문서: [`docs/codereviews/2026_05_17/alarm-phase2-flow.md`](../../../docs/codereviews/2026_05_17/alarm-phase2-flow.md) — 코드 흐름·함수 분석

---

## 개요

선행 작업(`bd729ac`) 시점의 Phase 2 잔여 항목 마무리 + 사용자 추가 요구 (이벤트 패널 UX) 처리. 본 세션 총 **7 commit** 으로 다음 두 묶음의 작업을 진행.

**시연 컨텍스트 (2026-05-17 사용자 확정):** **학습용 프로젝트**. "이런 기능을 어떻게 구현했다" 시연 가치 우선 — 본 세션의 모든 결정이 운영급 풀 기능 완성도가 아닌 **학습 자료로서의 명확성** 에 가중치를 둠. 자세한 컨텍스트는 [`memory/demo_2026_06_14_arima_roadmap.md`](/home/cjy/.claude/projects/-home-cjy-diconai/memory/demo_2026_06_14_arima_roadmap.md).

### 묶음 A — Phase 2 인프라 마무리 (인증·장애 복원력)

| commit | 작업 | plan 출처 |
|---|---|---|
| `830a769` | WSClient 토큰 만료 자동 refresh + 60s 지속 끊김 fallback 인프라 | `alarm-system-redesign.md` Phase 2 |
| `f6aa032` | 알람 팝업 WS 재연결 catch-up + fallback 폴링 구독 | `alarm-system-redesign.md` Phase 2 |

### 묶음 B — 이벤트 패널 UX 개선 (자료구조·디자인 시스템·재활용)

| commit | 작업 | 출처 |
|---|---|---|
| `a2bd68a` | 이벤트 패널 아이콘 이모지 → Lucide SVG (임시안) | 사용자 추가 요청 |
| `bc0623f` | 이벤트 패널 source 단위 그룹화 + "외 N건" 펼침 | 사용자 추가 요청 |
| `8976109` | AlarmRecord.channel + channel_meta 기반 채널 라벨 표시 | 사용자 추가 요청 |
| `56b0c1b` | 사이트 전체 스크롤바 일관화 (다크/라이트 6px) | 사용자 추가 요청 |
| `d624531` | main.html Lucide 주석 Django → HTML (스타일 정리) | 사용자 직접 변경 |

총 변경 라인 (대략):
- 묶음 A: ~135줄 (인프라 90 + 구독 31 + 헤더 docstring 갱신)
- 묶음 B: ~370줄 (아이콘 25 + 그룹화 250 + 채널 65 + 스크롤바 20 + style 2)
- 회귀 테스트: DRF 71/71 + FastAPI 80/80 통과 (기존 + 신규 영향 0)

---

## 묶음 A — Phase 2 인프라 마무리

선행 작업에서 보류된 "WS 토큰 만료 자동 처리" + "60s 지속 끊김 시 보조 폴링" 두 항목 마무리. 학습 관점에서 **인증 토큰 라이프사이클 + graceful degradation** 패턴 학습 가치.

### A.1 WSClient 토큰 만료 자동 refresh (`830a769`)

#### 문제
fastapi 측 `websocket/auth.py` 가 토큰 만료 시 `close(code=1008, reason="unauthenticated")` 송신. 브라우저 WSClient 는 단순 지수 백오프로 같은(만료된) 토큰 URL 로 재시도 — 401 close 무한 반복 후 20회 초과 시 포기.

#### 해결
WSClient onclose 안에서 close code/reason 분기:
- `code === 1008 && reason === "unauthenticated"` → `Auth._refresh()` 호출 → 새 access_token 으로 즉시 `_open()` 재진입 (백오프 우회, attempts=0)
- `reason === "forbidden"` → refresh 의미 없음, 일반 백오프 fall through

#### 부가 — `_cache` race 사전 차단 (F5 분석 결과)
기존 cache key 가 full URL(`/ws/sensors/?token=...`) 기반이라 token 갱신 후 다른 호출자가 같은 path 호출 시 cache miss → 같은 채널에 별개 instance + 두 WS 연결되는 race 가능했음.
→ cache key 를 `path + JSON.stringify(opts)` 기반으로 변경. 호출자 인터페이스 영향 0 (같은 path 호출은 같은 instance 보장).

#### 재활용 자산
- `Auth._refresh()` 의 `_refreshing` Promise 가드 — apiFetch 가 이미 사용 중. WSClient 자체 race 처리 X
- `_open()` 기존 함수 재호출 — 새 토큰으로 connect 흐름 그대로
- `attempts = 0` reset 패턴 — 정상 흐름이라 백오프 reset

### A.2 60s 지속 끊김 fallback (`830a769` + `f6aa032`)

#### 문제
WS 가 끊긴 채로 운영자가 페이지 있으면 위험 알람을 못 받음. 단순 백오프로는 fastapi 다운 시 ~10분 후 포기 — 산업 안전 시스템에서 수용 불가.

#### 해결
WSClient 에 **신규 콜백** `onFallbackStart/onFallbackEnd` 추가 + 60s 타이머:
- onclose 시 `_startFallbackTimer()` — fallbackTimer 등록 (60s 후 dispatch)
- 60s 안 onopen → `_clearFallbackState()` 으로 타이머 cleanup, fallback 시그널 안 보냄
- 60s 지속 → fallbackStartHandlers dispatch → 구독자 (AlarmPopup) 가 catch-up 폴링 시작
- 재연결 성공 시 fallbackEndHandlers dispatch → 폴링 중단

alarm-popup.js 가 onFallbackStart/End 구독 + `_runCatchUp()` 을 30s 주기로 호출 (기존 catch-up 흐름 재활용).

#### 옵션 비교 (사용자 결정 — C 옵션)

| 옵션 | 발동 타이밍 | 단점 |
|---|---|---|
| A) max_reconnect_attempts | ~8분 | 알람 누락 10분 — 산업 안전 수용 불가 |
| B) onclose 3회 연속 | ~7초 | 일시 끊김(1~3초)에도 폴링 시작/중단 빈번 |
| **C) disconnect 60s 지속** ★ | 60s | 알람 누락 최대 90s — 균형 |

이유 — 일시 끊김은 무시, 진짜 지속 끊김에만 응답. 시각 표시도 "60s 끊김 → fallback 모드" 직관적.

#### 콜백 인터페이스 결정 (F4 분석)
fallback 시그널을 `errorHandlers` 재사용 vs 신규 콜백:
- errorHandlers 재사용 시 → 3 페이지 (dashboard/websocket, websocket_gas, websocket_power) 가 fallback 을 "연결 오류" 로 오인 → UI 잘못 표시
- → **신규 콜백 `onFallbackStart/End`** 으로 인터페이스 분리. 기존 onError 구독자 무영향.

#### 재활용 자산
- `reconnectTimer` 의 setTimeout/clearTimeout 패턴 → `fallbackTimer` 동일 패턴
- `_dispatch(set, ...args)` 헬퍼 → 신규 콜백 dispatch 시 그대로
- `_addHandler(set, fn)` 헬퍼 → onFallbackStart/End 등록 시 그대로
- `_runCatchUp()` 재사용 — 폴링도 같은 함수 (since= 자동 갱신, newAlarmEvent dispatch, 패널 dedup 모두 보존)

#### 검증 (T1~T4 수동 통과)
- T1: localStorage 토큰 인위 만료 → Network 탭에 `POST /api/auth/token/refresh/` 1회 + WS 재연결 정상
- T2: `docker compose stop fastapi` 후 60s 대기 → 콘솔 "WS 60s 지속 끊김 — 폴링 시작" + 30s 마다 `GET /alerts/api/alarms/catch-up/?since=...` 호출 + 재시작 시 "폴링 중단"
- T3: fastapi 10초만 stop → 폴링 시작 메시지 안 뜸 (false positive 0)
- T4: 두 탭 동시 토큰 만료 → refresh 1회만 호출 (`_refreshing` Promise 가드 정상)

---

## 묶음 B — 이벤트 패널 UX 개선

학습 관점에서 **자료구조 재활용 + 디자인 시스템 + 모델 설계** 패턴 학습 가치.

### B.1 아이콘 이모지 → Lucide SVG (`a2bd68a`)

#### 문제
이벤트 패널의 아이콘이 이모지(🌫️ ⚡ 🤖 등) — OS 별 렌더링 차이 + 전문 시스템 톤과 불일치.

#### 결정 사항 (사용자 확정)

| 결정 | 선택 | 이유 |
|---|---|---|
| 아이콘 라이브러리 | **Lucide CDN** | 무료 ISC + 1400+ 아이콘 + currentColor 자동 적용 |
| 캡처(피그마) 톤 매칭 | **불가능 (포기)** | SVG/PNG export 불가 — 디자이너 협업 안 됨 |
| 도입 방식 | **CDN 동적 SVG (a)** | inline SVG(b) 보다 가벼움, 향후 교체 쉬움 |
| 임시 vs 정식 | **임시안 명시** | 디자이너 SVG 받으면 ICON_BY_TYPE 매핑만 갈아끼움 |

#### alarm_type → Lucide 매핑 (13종)

| alarm_type | Lucide name |
|---|---|
| gas_threshold | flame |
| gas_clear | circle-check |
| power_overload | zap |
| power_anomaly_ai | brain-circuit |
| power_clear | circle-check |
| geofence_intrusion | map-pin |
| sensor_fault | shield-alert |
| ppe_violation | hard-hat |
| vr_training_not_done | graduation-cap |
| safety_check_pending | clipboard-check |
| inspection_scheduled | wrench |
| batch_failed | circle-x |
| storage_overdue | package-x |

#### 핵심 변경
- main.html 헤더에 `<script src="https://unpkg.com/lucide@latest"></script>`
- `ICON_BY_TYPE` 매핑 갈아끼움 (이모지 → Lucide name)
- DOM 렌더 — `<span class="event-icon">${icon}</span>` → `<i data-lucide="${icon}" class="event-icon"></i>`
- addItem / `_addToClearGroup` 끝에 `lucide.createIcons()` 호출 (idempotent — 이미 SVG 인 element 무시)
- CSS `.event-icon` — font-size 기반 → SVG 기반 (16x16, currentColor, stroke-width 1.75)

### B.2 source 단위 그룹화 + "외 N건" 펼침 (`bc0623f`)

#### 문제
같은 가스 센서 / 전력 장비 / 지오펜스에서 발생한 여러 알람이 별도 줄로 나열 → 패널 길이 폭주. 캡처에서 "더미 전력장비 5건" 표시 확인.

백엔드 Event 모델이 이미 `(alarm_type + source + 60s cooldown)` 단위 자동 병합하지만, **사용자 요구는 그것보다 더 큰 단위 (source 만, alarm_type 무관)** 그룹화.

#### 결정 사항 (사용자 확정)

| 결정 | 선택 | 이유 |
|---|---|---|
| 묶음 단위 | source + 30분 윈도우 | 같은 운영 세션 의미 단위. 시간차 큰 알람은 별개 그룹 |
| 헤더 메시지 | **첫 발생 알람** 고정 | 이상 추적 출발점 — 운영자가 "어디서부터 시작했나" 확인 우선 |
| 헤더 시간 | 첫 발생 시각 | 시간 흐름 추적 시작점 |
| 헤더 위험도 색상 | **그룹 안 최고 위험도** | 색은 즉시 위험 인지용 — 메시지(첫 발생) 와 색(최고 위험) 둘 다 살림 |
| "+다른 유형 N건" 라벨 | 첫 발생과 다른 alarm_type 있을 때만 | 다양성 시그널 |
| 헤더 클릭 | 첫 발생 event 상세 | 출발점 추적 일관 |
| "외 N건" 배지 클릭 | 펼침/접힘 토글 | stopPropagation 으로 헤더 클릭 차단 |
| 펼친 안 알람 클릭 | 그 event 상세 | 시나리오 개별 확인 흐름 보존 |
| 펼침 정렬 | 시간 내림차순 | 최신이 위 |
| 적용 페이지 | 메인 대시보드만 | 시연 안전 머지 — 검증 후 monitoring_events 로 확장 |

#### 사용자가 거부한 옵션 — 학습 컨텍스트
1. **그룹화 자체 보류** (한때 검토) — "각 시나리오 개별 확인" 우려. **재고 후 "외 N건 + 펼침" 으로 결정** — 운영자 흐름이 "헤더 보고 디바이스 인식 → 펼침으로 시나리오 list 확인" 자연
2. **시각적 stripe 만** (대안) — 정보 압축 효과 ↓
3. **시간 그룹 헤더** (대안) — 디바이스 단위 묶음과 결이 다름

#### 자료구조 — 정상화 burst 패턴 재활용
기존 정상화 알람 burst 그룹화 (`_clearGroups`) 와 같은 패턴:
- `_sourceGroups: Map<key, group>` — key=`source:${source_label}:${30min_bucket}`
- 그룹 객체 — `{ itemEl, items, moreEl, moreCountEl, otherTypesEl, itemsEl, descEl, firstAlarmType, maxLevel, maxLevelColorClass }`
- 첫 도착 → 그룹 줄 생성 (외형은 일반 줄과 동일, "외 N건" hidden)
- 두 번째 도착 → `_refreshSourceGroup` — 카운트·다른 유형·위험도 색·펼침 list 갱신
- LRU 정리 — 그룹 줄 제거 시 그룹 안 모든 `event_id` 의 `_seenKeys` 도 같이 cleanup

#### 디자인 — ASCII Mockup

**접힘 (그룹 1줄)**:
```
🤖 더미 전력장비              16:29:07
   AI 이상 패턴 감지 (7925.8 W)
                ▶ 외 4건 (+다른 유형 1건)
```

**펼침 (시나리오 list)**:
```
🤖 더미 전력장비              16:29:07
   AI 이상 패턴 감지 (7925.8 W)
                ▼ 외 4건 (+다른 유형 1건)
  ├ 🤖 AI 이상 패턴 감지 (7608.1 W)  16:30:07
  ├ ⚡ 전력 임계치 초과 (15.58 W)    16:29:27
  ├ ⚡ 전력 임계치 초과 (15.42 W)    16:29:12
  └ ⚡ 전력 임계치 초과 (22.98 W)    16:29:07
```

### B.3 AlarmRecord.channel + channel_meta 라벨 (`8976109`)

#### 문제
B.2 의 펼친 list 에서 "전력 임계치 초과 (15.58 W)" 만 보임 — PowerDevice 한 대에 16채널인데 어느 채널인지 패널에서 식별 불가. 운영자가 일일이 클릭해 상세 확인 필요.

#### 결정 사항 (사용자 옵션 C 선택)

옵션 비교:
- A) `AlarmRecord.channel` 필드 추가 + `get_short_message` 에 채널 inline — 가장 단순
- B) A + serializer 노출 + 프론트 별도 표시 — 더 유연하지만 작업량 ↑
- **C) A + `channel_meta` 활용 — 운영자 등록한 이름("송풍기A") 우선, 미지정 시 "CHn" 폴백** ★

이유 — 채널 번호("CH2") 보다 사용자 정의 이름("송풍기A") 이 운영자에게 친숙. `PowerDevice.channel_meta` JSONField 가 이미 모델에 있어서 데이터 활용만 추가하면 됨.

#### 핵심 변경

**모델**:
- `AlarmRecord.channel = PositiveSmallIntegerField(null=True)` 추가 (migration 0016)
- `PowerDevice.get_channel_label(channel)` 메서드 신규 — `channel_meta[str(ch)]["name"]` 우선, 폴백 `CHn`
- 기존 `monitoring/services/power_alarm._channel_label` 의 라벨 로직을 모델 메서드로 끌어올려 단일화 (재활용 자산화)

**서비스**:
- `event_service.create_alarm_and_event` 에 `channel` 인자 추가 (2 군데 `AlarmRecord.create()` 전달)
- `tasks.fire_power_danger_task / fire_power_warning_task` — 이미 받고 있던 `channel` 을 끝까지 연결
- fastapi `power_service.forward_inference_e2e` 의 `alarm_payload` 에 `channel` 추가 (AI 이상 알람용 — `anomaly_meta.channel` 활용)

**메시지**:
```python
# get_short_message (AlarmRecord 모델 메서드)
if self.power_device_id and self.measured_value is not None:
    prefix = ""
    if self.channel is not None and self.power_device is not None:
        prefix = f"{self.power_device.get_channel_label(self.channel)} "
    if self.alarm_type == "power_anomaly_ai":
        return f"{prefix}AI 이상 패턴 감지 ({self.measured_value} W)"
    return f"{prefix}전력 임계치 초과 ({self.measured_value} W)"
```

**성능**:
- `catch_up` endpoint 의 `select_related` 에 `power_device` 추가 — `get_short_message` 의 `channel_meta` 조회 시 N+1 회피
- `AlarmRecordViewSet` 의 `select_related` 는 이미 `power_device` 포함 — 변경 없음

**프론트 영향: 0** ✅
`get_short_message` 결과가 message 필드로 inline 들어가므로 패널/팝업/토스트/이력 페이지 모두 자동 적용. alarm-mapper / event-panel / alarm-popup 변경 없음.

#### 검증 (시연 환경)
- channel_meta 미등록 시: `"CH1 전력 임계치 초과 (15.58 W)"` 폴백
- channel_meta 등록 후: `"보조 모터 1 전력 임계치 초과 (14.05 W)"` — 운영자 친화 라벨 (캡처 확인)

### B.4 사이트 전체 스크롤바 일관화 (`56b0c1b`)

#### 문제
OS 기본 스크롤바(15~17px) 가 이벤트 패널 공간을 점유. 다크 테마 시스템 톤과 불일치.

#### 결정 사항 (사용자 확정)
- 적용 범위: **사이트 전체 (Q1=A)** — 일관성 + 모든 스크롤 영역 동일
- 디자인 톤: **얇고 미니멀 (Q2=α)** — 6px, 트랙 투명, thumb 회색

#### 배치 — 신규 파일 미생성 (사용자 지적 반영)
초안 — `components/scrollbar.css` 신규 파일 + 3 base 에 link 추가
**최종** — 기존 공용 CSS 두 곳에 inline:
- `header.css` (다크 톤, var(--border) thumb) — dashboard + snb_details 공용
- `admin.css` (라이트 톤, #cbd5e1 thumb) — admin_panel 공용

두 영역의 디자인 시스템이 다른 만큼 (다크 dashboard vs 라이트 admin) 색만 분리. 신규 파일 0개.

```css
/* Webkit */
::-webkit-scrollbar      { width: 6px; height: 6px; }
::-webkit-scrollbar-track  { background: transparent; }
::-webkit-scrollbar-thumb  { background: var(--border); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--text2); }
/* Firefox */
* { scrollbar-width: thin; scrollbar-color: var(--border) transparent; }
```

---

## 사용자 요구 매트릭스 (본 세션)

| 요구 | 처리 commit | 적용 |
|---|---|---|
| 토큰 만료 자동 처리 | `830a769` | ✅ Phase 2 plan 잔여 |
| 60s 지속 끊김 보조 폴링 | `830a769` + `f6aa032` | ✅ Phase 2 plan 잔여 |
| 이벤트 패널 아이콘 변경 (피그마 시안 시도) | `a2bd68a` | ⚠️ Lucide 임시안 (SVG export 불가) |
| 같은 디바이스 알람 묶음 (외 N건) | `bc0623f` | ✅ source + 30분 윈도우 |
| 같은 디바이스 안 채널 식별 | `8976109` | ✅ channel_meta 활용 라벨 |
| 스크롤바 개선 | `56b0c1b` | ✅ 사이트 전체 6px 미니멀 |

---

## 학습 시연 가치

본 세션 commit 들이 시연 자료로 활용 가능한 학습 포인트:

| 학습 주제 | 시연 commit |
|---|---|
| **인증 토큰 라이프사이클** (JWT refresh, race 가드) | `830a769` |
| **Graceful degradation** (60s 끊김 → 폴링 보조) | `830a769` + `f6aa032` |
| **외부 라이브러리 도입 패턴** (CDN, 동적 element replace) | `a2bd68a` |
| **자료구조 재활용** (`_clearGroups` 패턴 → `_sourceGroups`) | `bc0623f` |
| **모델 설계 + JSON 활용** (channel + channel_meta) | `8976109` |
| **CSS 디자인 시스템** (테마별 변수 + 의사 요소) | `56b0c1b` |

각 commit 메시지에 의도·결정 근거·검증 시나리오 충실히 기록 — 코드 안 보고도 의도 파악 가능.

---

## 검증

### 자동
- DRF pytest: **71/71** (alerts 25 + monitoring 18 + 신규 channel 영향 검증)
- FastAPI pytest: **80/80** (anomaly_alarm_forward / push_alarm_dedup / threshold_eval 등)
- pre-commit (ruff/ruff-format): Pass

### 수동 (브라우저 시나리오)
| 시나리오 | 결과 |
|---|---|
| T1 — localStorage 토큰 인위 만료 → 자동 refresh | ✅ Network 탭 refresh 1회 + WS 재연결 |
| T2 — fastapi 60s 지속 stop → 폴링 시작/중단 | ✅ 콘솔 로그 + 30s catch-up 호출 |
| T3 — fastapi 10초만 stop → 폴링 미발동 | ✅ false positive 없음 |
| T4 — 두 탭 동시 만료 → refresh dedup | ✅ Promise 가드 1회만 |
| 이벤트 패널 그룹화 (외 N건 표시) | ✅ "외 1건 (+다른 유형 1건)" 캡처 확인 |
| 채널 라벨 표시 | ✅ "보조 모터 1 전력 임계치 초과 (14.05 W)" 캡처 확인 |
| 스크롤바 6px 미니멀 (다크·라이트) | ✅ 두 테마 모두 통일 톤 |

---

## 보류 항목 (시연 후로 정리)

학습용 시연 컨텍스트라 모두 시연 critical 0:

| 항목 | 사유 |
|---|---|
| D 옵션 본격 (60s 클라 dedup + 헤더 미확인 배지) | 운영 단계 진입 후 운영자 피드백 후 진행. 디자인 5건(D1~D5) 결정 선행 |
| 공지사항 통합 RFC | 모델 설계 + RFC 문서 선행. 시연 후 sprint |
| Phase 3 — 권한별 라우팅 + 서버측 ack 분기 | 작업자 디바이스 결정 후 |
| 작업자 화면 stub | Phase 3 에 통합 진행 |
| 가스 트랙 `gas_anomaly_ai` helper 호출 | 가스 작업자 합류 시 |
| monitoring_events / event_detail alarm_stack 전환 | 위생 작업 — 시연 후 가능 |
| monitoring_realtime websocket.js 의존성 정리 | `drf-server/docs/known-issues/` 인계, 시연 시나리오 #3 제외 |

---

## 관련 파일 (본 세션 변경분)

### 신규
- `drf-server/apps/alerts/migrations/0016_alarmrecord_channel.py`

### 모델
- `drf-server/apps/alerts/models/alarm_record.py` — `channel` 필드 + `get_short_message` 분기
- `drf-server/apps/facilities/models/devices.py` — `PowerDevice.get_channel_label` 메서드

### 서비스
- `drf-server/apps/monitoring/services/power_alarm.py` — `_channel_label` → 모델 메서드 위임
- `drf-server/apps/alerts/services/event_service.py` — `create_alarm_and_event(..., channel=)` 인자 추가
- `drf-server/apps/alerts/tasks.py` — `fire_power_*_task` 의 create_alarm_and_event 호출에 channel 전달

### Serializer / View
- `drf-server/apps/alerts/serializers/anomaly_alarm_record.py` — `channel` 필드
- `drf-server/apps/alerts/views/anomaly_alarm_record.py` — create_alarm_and_event 호출에 channel 전달
- `drf-server/apps/alerts/views/alarm_record.py` — `catch_up` endpoint `select_related` 에 `power_device` 추가

### Fastapi
- `fastapi-server/power/services/power_service.py` — `forward_inference_e2e` 의 `alarm_payload` 에 channel 추가

### Frontend — JS
- `drf-server/static/js/shared/ws-client.js` — 토큰 refresh + fallback 콜백 + cache key 변경
- `drf-server/static/js/shared/alarm-popup.js` — `_startFallbackPolling/_stopFallbackPolling` + WSClient hook
- `drf-server/static/js/dashboard/panels/event-panel.js` — `_sourceGroups` 자료구조 + Lucide 아이콘

### Frontend — CSS / HTML
- `drf-server/static/css/components/header.css` — 다크 톤 스크롤바
- `drf-server/static/css/admin.css` — 라이트 톤 스크롤바
- `drf-server/static/css/dashboard.css` — `.event-icon` SVG 기반 + `.event-source-*` 그룹 클래스
- `drf-server/templates/dashboard/main.html` — Lucide CDN 추가 (`@latest` — 시연 직전 0.x 고정 권장)

---

## 다음 작업자 가이드

본 문서를 본 시점에 이미 7 commit 머지됐다고 가정. 다음 작업자가 본 문서를 참고할 가능성 시나리오:

1. **Lucide → 디자이너 SVG 교체 시** — `ICON_BY_TYPE` 매핑 갈아끼우고 `<i data-lucide>` 를 `<img src>` 또는 inline SVG 로 변경. CDN script 제거.
2. **channel_meta 운영자 등록 UI 작업 시** — `admin_panel` 의 PowerDevice 편집 폼에 `channel_meta` JSONField 입력 UI 추가. 본 작업에서 백엔드는 이미 활용 가능.
3. **D 옵션 본격 진입 시** — 본 세션의 alarm-popup.js 가 hook 기반(WSClient.onOpen / onFallbackStart) 이라 헤더 배지 hook 추가 자연. localStorage dedup 키 prefix 는 `diconai:alarm:popup:*` 컨벤션 추천.
4. **Phase 3 작업자 라우팅 진입 시** — 본 세션의 `AlarmRecord.channel` 이 권한 라우팅에 활용 가능 (특정 channel 만 모니터링 권한 부여 등).

문의/이슈는 commit hash 기준으로 추적: `git log --oneline a2bd68a^..56b0c1b`.
