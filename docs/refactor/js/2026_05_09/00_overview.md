# JS 리팩토링 — 핵심 공유 계층 함수 단위 분석 (2026-05-09)

> **목적**: drf-server/static/js/ 의 핵심 공유 계층 함수를 모두 분석하여 리팩토링 가능성 도출.
> **범위**: shared/ 9개 + auth/login.js + detail/my_profile.js (비밀번호 부분) + dashboard/app.js + detail/ui-exception.js
> **산출물**: 6개 기능 파일 + 본 overview, 총 7개

## 1. 의존성 그래프

```
                              ┌──────────────────┐
                              │ config.js        │ ← 모든 모듈의 토대
                              │ window.AppConfig │
                              └──────────────────┘
                                       ▲
                       ┌───────────────┴────────────┐
                       │                            │
                ┌──────────┐               ┌──────────────┐
                │ auth.js  │               │ ws-client.js │
                │  Auth    │ ◀────────────▶│  WSClient    │
                └──────────┘  attachToken   └──────────────┘
                  ▲   ▲                         ▲
                  │   │                         │
                  │   └────┐               ┌────┘
                  │        │               │
        ┌─────────┴─┐  ┌───┴────┐    ┌─────┴────┐  ┌───────────────┐
        │ login.js  │  │layout  │    │alarm-ws  │  │ worker-ws.js  │
        │           │  │  .js   │    │  .js     │  │               │
        └───────────┘  └────────┘    └──────────┘  └───────────────┘
                          ▲              │              │
                          │              ▼              ▼
                  ┌──────────────┐  ┌──────────────────────┐
                  │ app-sub.js   │  │   alarm-popup.js     │
                  │ initApp()    │  │  AlarmPopup +Toast   │
                  └──────────────┘  └──────────────────────┘
                          ▲
                          │
                  ┌───────────────┐  ┌─────────┐
                  │ my_profile.js │  │ util.js │ ← pad, nowLabel, levelLabel
                  │ (페이지)        │  │         │   (전역 함수)
                  └───────────────┘  └─────────┘
```

**핵심 의존 규칙**:
- 모든 모듈이 `config.js` (window.AppConfig) 의존
- API 호출은 `Auth.apiFetch` 단일 진입
- WebSocket 연결은 `WSClient.connect` 단일 진입
- 알람 렌더는 `AlarmPopup.show` / `AlarmToast.show` 단일 진입
- 페이지 진입은 `initHeaderAndSNB` (layout.js) 단일 진입

## 2. 기능 그룹 인덱스

| # | 기능 그룹 | 핵심 모듈 | 함수 수 | 리팩토링 권고 | 파일 |
|---|---|---|---|---|---|
| 01 | 인증·세션 | Auth + login + PasswordModal + Logout | ~20 | R1~R10 (상 1, 중 4, 하 5) | [01_auth_session.md](01_auth_session.md) |
| 02 | WebSocket 인프라 | WSClient + AppConfig.wsUrl | ~10 | R1~R10 (상 3, 중 3, 하 4) | [02_ws_infrastructure.md](02_ws_infrastructure.md) |
| 03 | 알람 파이프라인 | alarm-ws + AlarmPopup/Toast + worker-ws | ~12 | R1~R10 (상 2, 중 4, 하 4) | [03_alarm_pipeline.md](03_alarm_pipeline.md) |
| 04 | 레이아웃·메뉴·헤더 | SNB + Menu + Header + initHeaderAndSNB | ~15 | R1~R10 (상 2, 중 4, 하 4) | [04_layout_menu_header.md](04_layout_menu_header.md) |
| 05 | 페이지 진입 패턴 | initApp + loadMySafetyStatus + ui-exception | ~10 | R1~R10 (상 3, 중 3, 하 4) | [05_page_init.md](05_page_init.md) |
| 06 | 공통 유틸 | pad/nowLabel/pushData/MAX_POINTS/levelLabel + AppConfig | ~8 | R1~R10 (상 3, 중 3, 하 4) | [06_utils_config.md](06_utils_config.md) |

총 ~75 함수/메서드, ~13 파일. 리팩토링 권고 60건 (상 14, 중 21, 하 25).

## 3. 우선순위 Top 10 (도메인 횡단)

각 기능 그룹의 [상] 우선순위에서 가장 영향 큰 10개를 종합:

| # | 항목 | 기능 그룹 | 영향 | 시급도 | 규모 |
|---|---|---|---|---|---|
| 1 | **`AlarmPopup` 큐 silent drop 정책 재설계** (drop count + throttle/group) | 03 R2 | 산재 예방 시스템 알람 누락 | 🔴 시급 | 중 |
| 2 | **`alarm-mapper.js` 추출 — 키 변환 단일화** (3곳 분산 → 1 모듈) | 03 R1 | contract fragility 핵심 | 🔴 시급 | 소 |
| 3 | **`Auth._refresh` 동시성 가드** (싱글톤 in-flight Promise) | 01 R1 | 토큰 회전 후 강제 로그아웃 회귀 | 🔴 시급 | 소 |
| 4 | **`levelLabel` dead code/contract 정합** (백엔드 enum과 일치 또는 제거) | 06 R1 | silent UI 깨짐 | 🔴 시급 | 소 |
| 5 | **WS 인프라 메시지 catch-up** (last_event_id 기반 재연결 시 누락 복구) | 02 R3 | 알람 누락 (재연결 중) | 🟠 1주 | 중 |
| 6 | **WS 인프라 지수 백오프 + 최대 시도** (3초 영구 재시도 → 자원 절감) | 02 R1 | 서버 영구 다운 시 자원 폭주 | 🟠 1주 | 소 |
| 7 | **`Menu.render` innerHTML → createElement** (XSS 패턴 정착) | 04 R1 | 향후 XSS 위험 차단 | 🟠 1주 | 중 |
| 8 | **`initApp` 에러 핸들링** (`.catch()` + 사용자 피드백) | 05 R1 | unhandled rejection / 빈 화면 | 🟠 1주 | 소 |
| 9 | **`loadMySafetyStatus` Auth.apiFetch 사용** (직접 fetch → 인증 헤더·refresh) | 05 R2 | 인증 일관성 결여 + 백엔드 변경 회귀 | 🟠 1주 | 소 |
| 10 | **`'caution'·'safe'` vs `'warning'·'normal'` contract 정합** | 05 R3 | CSS·JS·백엔드 enum 불일치 | 🟡 sprint | 중 |

## 4. 핵심 소견 요약

### 01 인증·세션
**Auth 객체의 단일 진입 패턴은 모범 사례**. 그러나 핵심 버그: `_refresh`가 동시성 미보호 — 다중 401 시 race로 강제 로그아웃 가능. 클라/서버 검증 정책 듀얼 메인테넌스 (login.js + my_profile.js + 백엔드). PasswordModal의 strict 매개변수 패턴은 좋은 UX 디자인. 검증 라벨: ✅ 다수 / ❌ 4건 / ⚠️ ~7건 / 💡 ~10건.

### 02 WebSocket 인프라
**WSClient는 핵심 모범 코드** — 연결 캐시·자동 재연결·다중 핸들러 dispatch 모두 깔끔. 그러나 (1) 재연결 시 메시지 catch-up 부재 → 알람 누락, (2) 무한 재시도 + 고정 3초 → 서버 다운 시 자원 폭주, (3) attachToken 캐시 동작이 직관 어긋남. AppConfig·Auth 부재 silent fallback도 디버깅 어려움. 검증 라벨: ✅ 7건 / ❌ 1건 / ⚠️ ~5건 / 💡 ~6건.

### 03 알람 파이프라인
**가장 큰 fragility 도메인**. 3곳 호출자(alarm-ws, worker-ws, dashboard/websocket)가 같은 키 매핑을 각자 인라인 + AlarmPopup이 양쪽 키 fallback — 백엔드 키 변경 시 silent break 가능. `MAX_QUEUE=5 silent drop`은 산재 예방 시스템에서 알람 누락 위험. 클라이언트 timestamp 사용으로 시각 부정확. AlarmPopup의 idempotent init·textContent 사용·_POPUP_CFG fallback은 좋은 패턴. 검증 라벨: ✅ 8건 / ❌ 5건 / ⚠️ ~7건 / 💡 ~9건.

### 04 레이아웃·메뉴·헤더
**Header.handleRefresh의 try-catch-finally + debounce는 매우 잘 작성된 패턴**. SNB·Menu·Header 책임 분리도 명확. 약점: Menu.render의 innerHTML 패턴(현재 안전, 미래 XSS 위험), iconMap 인라인 SVG + silent fallback, getMe 실패 시 부분 동작 UI. SNB 모듈 로드 시점 getElementById는 layout.js 로드 위치에 따라 NPE 위험. 검증 라벨: ✅ ~10건 / ❌ 3건 / ⚠️ ~8건 / 💡 ~7건.

### 05 페이지 진입 패턴
**ui-exception.js의 헬퍼들 (DocumentFragment·data 속성·closure)은 잘 짜여진 코드**. 그러나 dashboard/app.js의 `initApp()` await 없이 즉시 호출 → unhandled rejection. `loadMySafetyStatus`가 `Auth.apiFetch` 미사용으로 인증 일관성 결여. `'caution'·'safe'` 클래스명이 백엔드 RiskLevel enum (`warning`·`normal`)과 불일치. AlarmPopup.init 중복 호출은 idempotent라 OK이지만 의도 불명확. 검증 라벨: ✅ ~7건 / ❌ 3건 / ⚠️ ~6건 / 💡 ~6건.

### 06 공통 유틸
**`pad`/`nowLabel`/`AppConfig.apiUrl` 모두 단순·정확**. 그러나 `levelLabel`은 호출자 grep 결과 없음 — dead code 또는 silent 깨짐. `pushData`의 dataset/values 길이 검증 부재로 silent NPE 위험. WS_BASE의 운영 fallback이 localhost — app_config.html 부재 시 운영에서 모든 WS 연결 실패. safety_history.js의 pad 로컬 재정의는 의도 불명확. 검증 라벨: ✅ ~7건 / ❌ 3건 / ⚠️ ~5건 / 💡 ~5건.

## 5. 단계별 통합 적용 순서 (PR 묶음)

각 기능 파일의 §6에 자세한 단계별 순서가 있음. 본 섹션은 **도메인 횡단으로 효율적인 PR 묶음**을 제안.

### PR-J1 (1일) — 정합·로깅 즉시 (소규모 변경) ⚡
- **06 R1** levelLabel grep 후 결정 (제거 또는 정합)
- **06 R2** pushData 검증 (1줄 추가)
- **06 R3** WS_BASE 운영 가드 (console.warn)
- **06 R5** safety_history.js pad 재정의 제거
- **02 R4** AppConfig·Auth 부재 console.warn
- **04 R4** iconMap console.warn
- **04 R7** roleLabel 상수화 + console.warn
- **05 R1** initApp `.catch()` 추가
- **05 R6** loadMySafetyStatus catch console.warn
- **이유**: 모두 1~5줄 변경. 디버깅·운영 가시성 즉시 향상. 회귀 위험 거의 없음.

### PR-J2 (2~3일) — 알람 contract 정합 🔧
- **03 R1** `shared/alarm-mapper.js` 추출 (alarm-ws/worker-ws/dashboard/websocket의 키 매핑 통합)
- **03 R3** 서버 timestamp 사용 (mapper에서 처리)
- **03 R4** AlarmToast 호출 일관 (worker-ws에 추가 또는 명시 주석)
- **03 R10** AlarmPopup show 분기 console.warn
- **이유**: 알람 contract fragility 차단. 한 PR에 묶어 회귀 검증 1회.

### PR-J3 (3~5일) — 인증 보안 강화 🔐
- **01 R1** Auth._refresh 싱글톤 가드
- **01 R7** Auth.getMe catch console.warn
- **05 R2** loadMySafetyStatus → Auth.apiFetch (백엔드 03 C2와 협업)
- **이유**: 인증 동시성·일관성. PR-J1의 console.warn 도입 후 진행.

### PR-J4 (5~7일) — WS 인프라 견고성 🔌
- **02 R1** 지수 백오프 + 최대 시도
- **02 R7** JSON 파싱 console.debug
- **02 R9** close() dispatch 추가
- **이유**: WS 자원 절감 + 디버깅 가시성.

### PR-J5 (7~10일) — XSS 패턴 정착 🛡
- **04 R1** Menu.render createElement
- **04 R5** menuTree·path 검증
- **이유**: 보안 패턴 정착. 향후 새 코드도 안전.

### PR-J6 (10~14일) — 알람 큐 정책 (운영 합의 후) 🚨
- **03 R2** AlarmPopup 큐 정책 (옵션 A/B/C 중 합의)
- **03 R8** _POPUP_CFG freeze
- **03 R9** 자동 close 상수화
- **이유**: 운영팀 정책 합의 필요 — 단독 PR.

### PR-J7 (다음 sprint) — WS 인증 통합 🔐
- **02 R2** attachToken 캐시 정합
- **02 R3** 메시지 catch-up (서버 협업)
- **04 R2** initHeaderAndSNB 실패 처리
- **05 R3** caution/safe contract 정합
- **이유**: 백엔드 변경 동반 또는 큰 작업. 핵심 공유 계층 안정 후.

### PR-J8 (다음 sprint) — JS 공통화 🏗
- **01 R3** 폼 에러 헬퍼 추출
- **01 R4** 비밀번호 정책 중앙화
- **04 R3** SVG sprite 분리
- **05 R5** ui-exception 인라인 style → CSS class
- **06 R6** MAX_POINTS 차트별 설정
- **이유**: 코드 재사용 + 디자인 시스템.

## 6. 다음 sprint 계획 (Phase 2 — 별도 plan)

핵심 공유 계층 분석·리팩토링 머지 후 다음 단계 (별도 plan으로 진행):

```
docs/refactor/js/2026_06_XX/  (다음 sprint)
  07_dashboard_render.md      — dashboard/(app, charts, websocket, panels)
                                ~7 파일, ~30+ 함수
  08_detail_realtime.md       — detail/(websocket_gas, websocket_power, gas_monitoring,
                                power_system, monitoring_workers)
                                ~5 파일, ~25+ 함수
  09_detail_pages.md          — detail/(event_list, event_detail, my_profile loadProfile,
                                safety_*)
                                ~7 파일, ~20+ 함수
  10_admin_list.md            — admin/(accounts, organizations, facility, gas_sensor,
                                power_system, gas_data, power_data, geofence)
                                ~8 파일, ~80+ 함수 (5+ 페이지가 동일 패턴 — base 추출 후보)
  11_admin_map_editor.md      — admin/map_editor (특수 케이스, 캔버스/SVG 좌표)
                                ~1 파일, ~20+ 함수
```

총 5개 추가 기능 그룹, ~28 파일, ~175+ 함수.

## 7. 표준 템플릿 (재확인)

각 기능 파일은 동일한 6섹션 구조:

```
## 1. 관련 파일 및 의존성
## 2. 기능 흐름 (ASCII 시퀀스)
## 3. 함수 분석 (각 파일별)
   ### 3.X 파일명
   #### 함수명
   - 시그니처 / 역할 / 단계별 동작 (코드 라인 인용)
   - 호출하는 함수 / 호출자
   - 올바름 검증 (✅⚠️❌💡)
## 4. 종합 평가 (강점/약점/중복/contract)
## 5. 리팩토링 권고 R1~R10 (왜/장점/단점/변경위치/before-after)
## 6. 단계별 적용 순서 + ⚠️ 초보자 주의사항
```

## 8. 검증 결과 통계

도메인 횡단 검증 라벨 분포:

| 기능 그룹 | ✅ 정상 | ⚠️ 위험 | ❌ 버그/문제 | 💡 개선 |
|---|---|---|---|---|
| 01 인증·세션 | 다수 | ~7 | 4 | ~10 |
| 02 WS 인프라 | 7 | ~5 | 1 | ~6 |
| 03 알람 | 8 | ~7 | 5 | ~9 |
| 04 레이아웃 | ~10 | ~8 | 3 | ~7 |
| 05 페이지 진입 | ~7 | ~6 | 3 | ~6 |
| 06 공통 유틸 | ~7 | ~5 | 3 | ~5 |
| **합계** | ~50 | ~38 | **19** | ~43 |

> ❌ 19건 중 14건이 [상] 우선순위 리팩토링 권고로 매핑됨. 나머지 5건은 [중] 우선순위.

## 9. 사용자 다음 단계 선택

이 보고서를 바탕으로 다음 중 선택:

1. **PR-J1 즉시 시작**: 1일 분량 정합·로깅 묶음. 가장 안전·작은 변경부터.
2. **Top 10 우선 처리**: 위 §3의 1~10번 순차로 PR.
3. **특정 기능 그룹 깊이**: 한 그룹의 모든 R1~R10을 한 번에 (예: 03 알람 도메인 전체 정리).
4. **Phase 2 (페이지/렌더 계층) 분석**: 다음 sprint의 07~11 진행.
5. **추가 영역**: 이 분석이 다루지 않은 영역 (예: CSS 토큰화, 빌드 도구 도입, 단위 테스트 인프라).

각 기능 파일의 §6 "단계별 적용 순서"가 자세한 작업 흐름을 제시. 선택 후 해당 PR부터 시작 가능.
