# Phase 1~4 회귀 점검 — Step 1 영향 분석 보고서

> 작업일: 2026-05-08
> 브랜치: `feature/0508_refactory`
> 부모 plan: [post_phase4_regression_plan.md](post_phase4_regression_plan.md) §4 Step 1
> 직전: [phase_4_pr3_report.md](phase_4_pr3_report.md)

---

## 1. 작업 목적

Phase 1~4에서 모델/필드/시그니처 30+건 변경된 후, 기존 호출처가 깨지지 않았는지 grep 기반 정적 분석. plan §3 영향 영역 8건 점검.

---

## 2. 점검 결과 요약

| # | 항목 | 결과 | 위험도 |
|---|---|---|---|
| 1 | Equipment `EQP-` → `FAC-` | ✅ 완전 전환 | 안전 |
| 2 | dashboard 메뉴 ID `SNB-XX` → snake_case | ✅ 완전 전환 | 안전 |
| 3 | `.deactivate(updated_by=)` 시그니처 | ✅ 영향 모델만 갱신 | 안전 |
| 4 | `mark_checked(session, note=)` 시그니처 | ✅ 호출자 갱신 완료 | 안전 |
| 5 | AlarmType 4 → 10종 | ✅ 분기 코드 없음 | 안전 |
| 6 | Notification.clean() 강화 | ✅ 정상 호출 | 안전 |
| 7 | POWER_THRESHOLDS 직접 사용 잔존 | 🟡 **회귀 가능** | DRF + FastAPI 양측 |
| 8 | gas_thresholds.py ↔ threshold_default.json | ✅ 9종 값 일치 | 안전 |

**즉시 깨짐**: 0건 / **회귀 가능**: 1건 (POWER_THRESHOLDS) / **컨벤션 불일치**: 0건

---

## 3. 위험도 재분류 (plan §9-2 A항)

### 3-1. 즉시 깨짐 (현재 import error / 마이그 미적용 / runtime crash)

**0건**. 모든 마이그레이션 적용 완료, import 그래프 정상, 단위 테스트 29건 통과.

### 3-2. 회귀 가능 (특정 흐름에서만 발현, 평소엔 모름)

**1건 — POWER_THRESHOLDS 동기화 위험 (DRF + FastAPI 양측)**

| 파일 | 라인 | 역할 |
|---|---|---|
| [drf-server/apps/core/constants.py](../../drf-server/apps/core/constants.py#L127) | 127 | `POWER_THRESHOLDS` dict 정의 (잔존) |
| [drf-server/apps/alerts/tasks.py](../../drf-server/apps/alerts/tasks.py#L296) | 296, 299 | `fire_power_alarm_task` 내 `POWER_THRESHOLDS["danger"]` 직접 사용 |
| [drf-server/apps/alerts/tasks.py](../../drf-server/apps/alerts/tasks.py#L352) | 352, 355 | `fire_power_warning_alarm_task` 내 `POWER_THRESHOLDS["caution"]` 직접 사용 |
| [drf-server/apps/monitoring/views/power_data.py](../../drf-server/apps/monitoring/views/power_data.py#L13) | 13, 45 | API endpoint가 dict 그대로 응답 |
| [fastapi-server/power/services/power_service.py](../../fastapi-server/power/services/power_service.py#L10) | 10, 108, 110 | FastAPI 위험도 분기 |
| [fastapi-server/core/power_thresholds.py](../../fastapi-server/core/power_thresholds.py) | 전체 | FastAPI 측 별도 dict 정의 (DRF와 동기화 의무) |

**현재 안전성**: fixture `threshold_default.json`의 power 임계치(2200/2860 W)가 `POWER_THRESHOLDS` 상수(caution=2200, danger=2860)와 정확히 일치 → 운영 동작 차이 없음.

**잠재 위험**: 운영자가 어드민에서 Threshold 수정해도 alerts/tasks.py / power_data.py / fastapi 측은 상수 사용 → **DB 변경이 반영 안 됨**. Phase 4-c "단일 진실 공급원" 정책 위반.

**fastapi-server / drf-server 양측 영향**: ✅ 양쪽 다 영향 (plan §9-2 C항).

### 3-3. 컨벤션 불일치 (동작은 하나 스타일/일관성 문제)

**0건**.

---

## 4. 항목별 상세

### 4-1. Equipment `EQP-` → `FAC-` (안전)

[`drf-server/apps/facilities/models/equipment.py:13`](../../drf-server/apps/facilities/models/equipment.py#L13)에 docstring 메모만 남음 (`"EQP- → FAC- 로 변경 (4차)"`). 실제 코드/템플릿/JS에서 `"EQP-"` 하드코딩 0건.

### 4-2. 메뉴 ID `SNB-XX` (안전)

[`drf-server/static/js/shared/layout.js:28`](../../drf-server/static/js/shared/layout.js#L28)에 주석(`// SNB-01 — 메뉴 렌더링 & 아코디언`)만 남음. 실제 분기 0건. `dashboard/menu.py`는 Phase 4-a에서 DB 조회로 전면 재작성, 반환 형식은 `menu.code` (snake_case).

### 4-3. `.deactivate(updated_by=)` 시그니처 (안전)

**시그니처 변경 모델 3개**:
- `Equipment.deactivate(self, updated_by=None)` — Phase 1
- `SafetyCheckItem.deactivate(self, updated_by=None)` — Phase 1
- `SafetyCheckSection.deactivate(self, updated_by=None)` — Phase 3 PR2

**시그니처 미변경 모델 (기존 `def deactivate(self):` 그대로)**:
- `SoftDeleteMixin` (`core/mixins.py:23`) — 기본
- `Facility`, `GasSensor`/`PowerDevice` (`facilities/models/devices.py`, `facility.py`), `Geofence`, `CustomUser` — 모두 기본 시그니처

**Equipment 호출처 갱신 확인**: `facilities/views/facility_admin.py:470, 498` 모두 `equipment.deactivate(updated_by=request.user)` ✅. `equipment.py:65`의 `self.power_device.deactivate()`는 PowerDevice 호출이라 시그니처 영향 없음.

**SafetyCheckItem/SafetyCheckSection.deactivate() 호출처**: grep 결과 0건 (어드민 화면 미구현 상태).

### 4-4. `mark_checked(session, note=)` 시그니처 (안전)

호출처 단 2건, 모두 키워드 인자 사용:
- [`safety/services/check_service.py:56`](../../drf-server/apps/safety/services/check_service.py#L56) — `status.mark_checked(session=session, note=note)` ✅
- [`safety/tests/test_session_migration.py:95`](../../drf-server/apps/safety/tests/test_session_migration.py#L95) — 테스트도 `mark_checked(session=...)` ✅

### 4-5. AlarmType 4 → 10종 (안전)

분기 코드 (switch/if-elif/match) 0건. 모든 사용처가 명시적 값 참조 (`AlarmType.GAS_THRESHOLD`, `AlarmType.POWER_OVERLOAD`, `AlarmType.GEOFENCE_INTRUSION`, `AlarmType.PPE_VIOLATION` 등) — 새 타입을 처리하지 않는 default 분기 없음.

### 4-6. Notification.clean() 강화 (안전)

`Notification(...)` 직접 인스턴스 생성은 [`notifications/services/notification_service.py:52~62`](../../drf-server/apps/notifications/services/notification_service.py#L52)뿐. event=None, policy=None 동시 호출 사례 0건.

**미세 주의 (보고만)**: 같은 위치에서 `bulk_create()` 사용 — Django 정책상 `clean()` 자동 호출 안 함. 현재 `event` 항상 NotNull로 진입하기에 실제 위험 없음.

### 4-7. POWER_THRESHOLDS (회귀 가능)

§3-2 참조. **권장 fix**: 4건 모두 `evaluate_power_risk(watt)` 또는 `get_threshold("power_default", "power_w")` 위임. FastAPI 측은 [`fastapi-server/core/power_thresholds.py`](../../fastapi-server/core/power_thresholds.py)와 [`drf-server/apps/core/constants.py:127`](../../drf-server/apps/core/constants.py#L127) 두 정의를 fixture 단일 진실 공급원으로 통합.

### 4-8. gas_thresholds.py ↔ threshold_default.json (안전)

가스 9종 (CO/H2S/CO2/O2/NO2/SO2/O3/NH3/VOC) `warning_min/max`, `danger_min/max` 값이 양측에서 1:1 일치. 단 `LEL`은 [`fastapi-server/core/gas_thresholds.py`](../../fastapi-server/core/gas_thresholds.py) 측에서도 임계치 미정의 — Phase 1 후속 트랙(`GasTypeChoices.LEL` dead code cleanup)과 일관.

---

## 5. 추가 확인 (plan §3 외)

| 항목 | 상태 |
|---|---|
| `_MENU_WORKER`/`_MENU_ADMIN_EXTRA` 잔존 import | ✅ 0건 (Phase 4-a 재작성 완료) |
| `event.delete()` 후 Notification 자동 정리 가정 | ✅ 0건 (Soft Delete 정책상 운영 시점 사례 미존재) |
| `GasTypeChoices.LEL` dead code | 🟢 fastapi-server까지 일관되게 미정의 → 후속 cleanup PR로 분리 |
| Equipment 검색 쿼리 `EQP-` prefix | ✅ 0건 |

---

## 6. 결정 필요 항목 (plan §8)

### 6-1. POWER_THRESHOLDS fix 범위 — 본 PR vs 별도 PR

**옵션 A: 본 회귀 점검 PR에 묶기**
- 장점: 단일 commit으로 회귀 점검 + fix + 회귀 테스트 일괄 처리. 양측 서버 동기화도 한 번에.
- 단점: 본 PR이 review/test/문서화 4건 변경 (drf-server 3 + fastapi-server 1) 포함되어 비대화. fastapi-server 측 venv 작업 필요.

**옵션 B: 별도 PR로 분리 (`fix : POWER_THRESHOLDS DB 일원화`)**
- 장점: 회귀 점검 결과와 fix를 분리 → 회귀 테스트(Step 3)가 fix 전 동작도 캡처 가능. PR 단위가 작아져 review 명확.
- 단점: 양측 서버 작업이라 Step 3와 동시 진행 시 commit history 더 길어짐.

### 6-2. Step 3 회귀 테스트 5개 — 한 PR vs 흐름별 분리

(plan §4 핵심 흐름 5개: 가스/전력/지오펜스 알람 + 안전 체크리스트 + 메뉴 트리)

**옵션 A: 한 PR에 5개 묶기** — Phase 4 PR2 (4ef) 패턴. 검증/리뷰 한 번에.
**옵션 B: 흐름별 분리 PR** — Phase 4 PR1 (4abcd)과 다름. 각 흐름이 독립이라면 합치는 게 자연스러움. 운영 트랙 우선순위 변경 필요.

### 6-3. plan §7 운영 트랙 우선순위 재조정 필요?

본 영향 분석 결과 **즉시 깨짐 0건** → 우선순위 재조정 불필요.
운영 트랙 잔여 항목(BaseModel 컨벤션, AppLog 비동기, AlertPolicy seed 등)은 별도 PR 트랙으로 진행 가능.

---

## 7. 다음 단계

§6의 결정 후 Step 2 (fix) → Step 3 (회귀 테스트 5개)로 진행. 결정 결과는 본 보고서 §8에 기록.

---

## 8. 사용자 결정 (2026-05-08)

| 결정 항목 | 채택 옵션 | 이유 |
|---|---|---|
| **6-1. POWER_THRESHOLDS fix 범위** | **별도 fix PR로 분리** | 회귀 점검 docs commit과 fix를 분리. drf-server 3 + fastapi-server 1 양측 동기화를 단일 commit (`fix : POWER_THRESHOLDS DB 일원화`) |
| **6-2. Step 3 회귀 테스트 5개 PR 단위** | **한 PR에 5개 묶기** | Phase 4 PR2 (4ef) 패턴. 5개 흐름 모두 회귀 점검 목적이라 단일 PR로 검증/리뷰 한 번에 |
| **6-3. 운영 트랙 우선순위 재조정** | 불필요 | 즉시 깨짐 0건이라 plan §7 잔여 항목 그대로 |

### 작업 commit 흐름

1. **docs**: 본 Step 1 보고서 commit (`docs : Step 1 회귀 점검 보고서`)
2. **fix**: POWER_THRESHOLDS DB 일원화 (`fix : POWER_THRESHOLDS DB 일원화`) — §9 세부 결정 적용
3. **test**: 회귀 테스트 5개 + CI 자동화 (`test : Phase 1~4 회귀 테스트 5종`)

---

## 9. Step 2 fix 세부 결정 (2026-05-08, 팀 공유용)

본 fix는 두 가지 세부 사항이 필요했음. 옵션 분석 + 채택 이유를 기록.

### 9-1. PowerThresholdView API `{caution, danger, maxY, unit}` 응답 DB 기반화

#### 배경
[`monitoring/views/power_data.py:45`](../../drf-server/apps/monitoring/views/power_data.py#L45)가 `apps.core.constants.POWER_THRESHOLDS` 상수를 그대로 응답으로 반환. DB의 `Threshold` 모델은 `warning_max=2200, danger_max=2860, unit="W"`만 있고, **차트 Y축 최대값(`maxY=3500`)은 DB에 없음**. 프론트 차트 주석 라인 + 차트 스케일링 용도.

#### 옵션 분석

| 옵션 | 구현 | 장점 | 단점 |
|---|---|---|---|
| **A. Threshold.chart_max 필드 추가** | 마이그 1개 + fixture 갱신 + view에서 `get_threshold(...)` 사용 | 완전한 단일 진실 공급원. 어드민에서 차트 스케일까지 운영자 조정 가능. 향후 가스 차트도 동일 패턴 활용 | 마이그 1개 추가 (학습 환경에선 비용 적음). 기존 9개 가스 row는 chart_max=NULL |
| B. 코드 측 `maxY` 합성 (`danger_max × 1.22`) | view에서 비율 계산 | 마이그 불필요 | "1.22"라는 디자이너 상수가 코드에 숨겨짐. 운영자가 못 바꿈. 가스 일반화 어려움. 운영 진입 시 chart_max 도입 재작업 |
| C. API 응답 형식 변경 (`warning_max/danger_max`) | view 응답 형식 변경 | DB 형식 그대로 노출 (가장 깔끔) | 프론트 호출처 깨짐. 키 변경 영향 큼. 회귀 점검 범위에 프론트 변경 포함 |

#### 채택: 옵션 A (Threshold.chart_max 필드 추가)

**채택 이유**:
- "단일 진실 공급원" 정책(Phase 4-c) 일관성 유지가 회귀 점검의 본질
- 디자이너 hex 회신 후 어드민에서 chart_max도 함께 조정할 수 있어야 함
- 학습 환경에서 마이그 1개 추가 비용은 미미 (Phase 4 PR1에서도 마이그 3개 추가)
- 옵션 B의 "1.22" 상수는 향후 가스 차트 도입 시 재작업 비용 발생 (가스마다 비율 다를 수 있음)
- 옵션 C는 프론트 영향 분석 추가 필요해 회귀 점검 범위 비대화

### 9-2. FastAPI `core/power_thresholds.py` 처리

#### 배경
[`fastapi-server/core/power_thresholds.py`](../../fastapi-server/core/power_thresholds.py)는 `core.config.settings.POWER_THRESHOLD_CAUTION/DANGER` env로 주입받음. [`fastapi-server/power/services/power_service.py:108~110`](../../fastapi-server/power/services/power_service.py#L108)의 `build_equipment()`가 채널별 risk_level 계산에 사용 — **WS 페이로드 표시용**, DB 저장 대상 아님. 실제 알람 판정 + DB 저장은 DRF `power_alarm.py`가 수행 (Phase 4-b에서 `evaluate_power_risk` DB 전환 완료).

#### 옵션 분석

| 옵션 | 구현 | 장점 | 단점 |
|---|---|---|---|
| **A. docstring 강화만** | 양 파일 docstring에 "표시용 fallback, DRF가 단일 진실 공급원" 명시 | HTTP 의존성 도입 안 함 (센서 수신 hot path 보호). 의도 명확. 학습 환경 작업량 최소 | 어드민 Threshold 변경이 fastapi 표시용 risk에 자동 반영 안 됨 (env 재배포 필요). 100% 단일 진실 공급원은 아님 |
| B. FastAPI가 DRF API 호출 캐시 | 시작 시 fetch + TTL 1시간 캐시 | 완전한 단일 진실 공급원. 어드민 수정 1시간 내 반영 | HTTP 의존성 추가. fastapi 시작 순서 의존 (DRF 먼저 떠야). 표시용 risk를 위한 인프라 부담. Phase 4 PR1 단일 진실 공급원 정책에 가스만 포함, 전력은 미포함 |
| C. 별도 트랙으로 분리 | 본 PR은 DRF만, fastapi는 추후 | fix PR 범위 작음. fastapi 정책 추후 재결정 | 양측 영향 항목이 한 번에 마무리 안 됨. docstring 미갱신 시 함정 재발 |

#### 채택: 옵션 A (docstring 강화)

**채택 이유**:
- fastapi의 risk_level은 **표시용 fallback** — 실제 알람 판정 + DB 저장은 DRF `power_alarm.py`가 수행 (Phase 4-b에서 이미 DB 전환됨)
- 가스의 경우 DRF `GasData.save()`가 단일 진실 공급원 (fastapi 페이로드 risk 무시) — 동일 패턴
- HTTP 의존성을 센서 수신 hot path에 추가하면 latency 부담 + DRF 다운 시 fallback 복잡
- 학습 환경에서는 DRF/fastapi 동일 env 사용 → 실질적 차이 없음
- 운영 진입 시점에 다시 평가 (펌웨어 합의 트랙과 묶을 수 있음)
- docstring 강화로 다음 작업자가 함정에 빠지지 않게 명시

### 9-3. 채택 조합 요약

**1A + 2A**:
- DRF 측: Threshold.chart_max 필드 추가 + 마이그 + fixture 갱신 + alerts/tasks.py + power_data.py + constants.py 정리
- FastAPI 측: docstring 강화만 (코드 수정 없음)

이 조합으로 단일 진실 공급원 정책을 DRF 측에서 100% 달성하고, fastapi 측은 표시용 fallback임을 명시. 운영 진입 시 fastapi 측 정책 재평가 여지 보존.
