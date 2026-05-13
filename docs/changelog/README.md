# docs/changelog — 변경 이력 인덱스

> PR·머지 단위로 작성된 변경 요약 문서들. 작업 트랙별로 서브폴더에 정리되어 있습니다.
> 새 changelog를 추가할 땐 아래 ["새 changelog 작성 가이드"](#-새-changelog-작성-가이드)를 참고하세요.

---

## 디렉토리 구조

```
docs/changelog/
├─ README.md                            (이 문서 — 인덱스 + 리다이렉션 매핑)
├─ 00_pr_verification_checklist.md      (PR 머지 전 일반 체크리스트, 메타)
│
├─ early_2026-04/                       (2026-04 초기 리팩토링)
│  ├─ drf_0421_모델변경사항.md
│  ├─ drf_refactoring_phase4.md
│  └─ fastapi_refactoring_phase3.md
│
├─ phase1-5_refactoring/                (2026-05-07 백엔드 Phase 1-5 시리즈)
│  ├─ phase1_config_centralization.md
│  ├─ phase2_admin_security_pagination.md
│  ├─ phase3_frontend_http_ws_unification.md
│  ├─ phase4_drf_layer_exceptions_swagger.md
│  └─ phase5_fastapi_cleanup.md
│
├─ single_features/                     (2026-05-07 단일 기능 PR)
│  ├─ dashboard_admin_ui_cleanup.md
│  └─ realtime_map_dynamic_geofence.md
│
├─ alarm_reliability/                   (2026-05-12 알람 신뢰성 트랙)
│  ├─ alarm_reliability_phase1.md
│  └─ ui_refactor_phase2.md
│
├─ power_phase1_2/                      (2026-05-13 전력 임계치 트랙)
│  ├─ power_phase1_2.md
│  ├─ power_phase1_2_verification.md
│  └─ power_phase3.md                   (Phase 3 — IF 학습 데이터 인프라)
│
└─ ml/                                  (2026-05-13 ML 이상탐지 트랙 — 전력·가스 공유)
   └─ ml_step1_infra.md                 (STEP 1 — IF 학습·추론 인프라)
```

---

## 트랙별 요약

| 트랙 | 시기 | 주요 변경 | 폴더 |
|---|---|---|---|
| 초기 리팩토링 | 2026-04 | 모델 변경 + DRF/FastAPI Phase 3·4 | [`early_2026-04/`](early_2026-04/) |
| 백엔드 Phase 1-5 | 2026-05-07 | 설정 중앙화·인증·HTTP/WS 통합·예외·FastAPI 정리 | [`phase1-5_refactoring/`](phase1-5_refactoring/) |
| 단일 기능 | 2026-05-07 | 대시보드 어드민 UI · 실시간 지도 지오펜스 | [`single_features/`](single_features/) |
| 알람 신뢰성 | 2026-05-12 | dedupe 원자화·SQLite WAL·Redis 큐 + 알람 UI/UX | [`alarm_reliability/`](alarm_reliability/) |
| 전력 임계치 | 2026-05-13 | W·A·V 3축 정격 % 평가 + channel_meta DB 이관 + Phase 3 IF 학습 데이터 인프라 | [`power_phase1_2/`](power_phase1_2/) |
| ML 이상탐지 | 2026-05-13 | apps/ml/ + sklearn IsolationForest 학습·추론 인프라 (전력·가스 공유) | [`ml/`](ml/) |

---

## 이전 경로 → 새 경로 매핑 (리다이렉션)

머지된 PR description·외부 문서에서 평면 경로(`docs/changelog/*.md`)를 참조하고 있다면 아래 매핑으로 새 위치를 찾을 수 있습니다.

| 이전 경로 (deprecated) | 새 경로 |
|---|---|
| `docs/changelog/drf_0421_모델변경사항.md` | [`early_2026-04/drf_0421_모델변경사항.md`](early_2026-04/drf_0421_모델변경사항.md) |
| `docs/changelog/drf_refactoring_phase4.md` | [`early_2026-04/drf_refactoring_phase4.md`](early_2026-04/drf_refactoring_phase4.md) |
| `docs/changelog/fastapi_refactoring_phase3.md` | [`early_2026-04/fastapi_refactoring_phase3.md`](early_2026-04/fastapi_refactoring_phase3.md) |
| `docs/changelog/phase1_config_centralization.md` | [`phase1-5_refactoring/phase1_config_centralization.md`](phase1-5_refactoring/phase1_config_centralization.md) |
| `docs/changelog/phase2_admin_security_pagination.md` | [`phase1-5_refactoring/phase2_admin_security_pagination.md`](phase1-5_refactoring/phase2_admin_security_pagination.md) |
| `docs/changelog/phase3_frontend_http_ws_unification.md` | [`phase1-5_refactoring/phase3_frontend_http_ws_unification.md`](phase1-5_refactoring/phase3_frontend_http_ws_unification.md) |
| `docs/changelog/phase4_drf_layer_exceptions_swagger.md` | [`phase1-5_refactoring/phase4_drf_layer_exceptions_swagger.md`](phase1-5_refactoring/phase4_drf_layer_exceptions_swagger.md) |
| `docs/changelog/phase5_fastapi_cleanup.md` | [`phase1-5_refactoring/phase5_fastapi_cleanup.md`](phase1-5_refactoring/phase5_fastapi_cleanup.md) |
| `docs/changelog/dashboard_admin_ui_cleanup.md` | [`single_features/dashboard_admin_ui_cleanup.md`](single_features/dashboard_admin_ui_cleanup.md) |
| `docs/changelog/realtime_map_dynamic_geofence.md` | [`single_features/realtime_map_dynamic_geofence.md`](single_features/realtime_map_dynamic_geofence.md) |
| `docs/changelog/alarm_reliability_phase1.md` | [`alarm_reliability/alarm_reliability_phase1.md`](alarm_reliability/alarm_reliability_phase1.md) |
| `docs/changelog/ui_refactor_phase2.md` | [`alarm_reliability/ui_refactor_phase2.md`](alarm_reliability/ui_refactor_phase2.md) |
| `docs/changelog/power_phase1_2.md` | [`power_phase1_2/power_phase1_2.md`](power_phase1_2/power_phase1_2.md) |
| `docs/changelog/power_phase1_2_verification.md` | [`power_phase1_2/power_phase1_2_verification.md`](power_phase1_2/power_phase1_2_verification.md) |

> `git mv`로 이동했으므로 git history(`git log --follow <new_path>`)는 그대로 추적 가능합니다.

---

## 📝 새 changelog 작성 가이드

### 어디에 두나
- **연속 시리즈가 있는 작업** (예: Phase 1·2·3…): 동일 폴더에 모두 둠. 폴더가 없으면 신규 생성.
- **단일 작업이지만 검증·운영 가이드 등 부속 문서가 따라붙는 작업**: 작업명 폴더 생성 후 묶음 (예: `power_phase1_2/`)
- **단일 작업 + 부속 문서 없음**: `single_features/`에 추가
- **메타 문서** (전사 체크리스트 등): 루트에 `00_*.md` prefix로 추가

### 파일명 규칙
- `snake_case.md` (기존 컨벤션 유지)
- 작업 시리즈는 `<주제>_phase<N>.md` 형식 권장 (예: `power_phase1_2.md`, `alarm_reliability_phase1.md`)
- 검증·부속 문서는 `_verification.md`, `_operations_guide.md` 등 명시적 suffix

### 폴더명 규칙
- `snake_case` (kebab-case 아님 — 기존 파일명 컨벤션과 통일)
- 시리즈: `<주제>_phaseN-M_<설명>` (예: `phase1-5_refactoring`)
- 단일 트랙 + 부속 문서: `<주제>` (예: `power_phase1_2`, `alarm_reliability`)

### 내부 상대 경로
서브폴더 한 단계 깊어졌으므로 코드 파일 참조 시 **`../../../`로 시작** (이전엔 `../../`).
- ✅ `[evaluate_power_risk](../../../drf-server/apps/facilities/services/threshold_service.py)`
- ❌ `[evaluate_power_risk](../../drf-server/...)`
- 같은 폴더 내 파일은 prefix 없이 직접: `[verification](power_phase1_2_verification.md)`
