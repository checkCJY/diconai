# 팀 공유용 의사결정 통합 정리 (Phase 1~4 + 회귀 점검)

> **목적**: Phase 1~4 진행 중 내려진 모든 선택지/결정을 한 곳에 모은 팀 공유 문서.
> **형식**: 각 결정마다 [배경 → 옵션 → 채택안 + 장단점 → 미채택 옵션 분석 → 디테일/영향].
> **상태 표기**: ✅ 채택 / ⏸ 보류 / 🔄 후속 트랙
> **참조**: Phase 3 결정 33건은 [phase_3_plan.md](phase_3_plan.md) 참조 (동일 형식 단독 결정문).

---

## 📚 결정 카테고리 인덱스

- [§1. Phase 1 거시 전략 + 인프라 결정 (7건)](#1-phase-1-거시-전략--인프라-결정)
- [§2. Phase 1 모델/이넘 확장 결정 (3건)](#2-phase-1-모델이넘-확장-결정)
- [§3. Phase 2 도메인 모델 결정 (4건)](#3-phase-2-도메인-모델-결정)
- [§4. Phase 3 관계 변경 (33건, 별도 문서)](#4-phase-3-관계-변경-33건-별도-문서)
- [§5. Phase 4 서비스/뷰 결정 (4건)](#5-phase-4-서비스뷰-결정)
- [§6. 정휘훈 4차 결정 분석 대조 (6건)](#6-정휘훈-4차-결정-분석-대조)
- [§7. 회귀 점검 방식 (1건)](#7-회귀-점검-방식)

---

## §1. Phase 1 거시 전략 + 인프라 결정

### 1-1. 통합 적용 거시 전략 ✅

**배경**: ISH/CJY/imsi 3개 분석 plan + 정휘훈 결정 분석을 통합 적용 시 같은 파일/모델/이넘을 동시에 건드려 충돌 발생 위험.

**옵션**:
- **A**: **계층적 Phase 분할** — 기반 → 도메인 → 관계 → 앱 → 서비스 6단계 직렬
- **B**: **기반 통합 PR + 도메인 분리** — Cross-cutting 결정만 1개 PR에 집중, 도메인은 plan별 병렬
- **C**: **plan 단위 독립 + 사전 합의서만** — 3 plan 각자 독립 PR, 충돌 지점만 합의서 1장

**채택**: ✅ **B (기반 통합 PR + 도메인 분리)**

**B 장점**:
- Cross-cutting 결정이 첫 PR 1개에 집중 → 합의 비용 1회로 끝
- 기반 통합 후 plan별 도메인 PR 병렬 가능 → 출시 일정 단축
- 머지 충돌 위험이 가장 큰 `core/constants.py` 충돌이 1회로 해소
- 책임 경계가 도메인 단위로 명확 (notices=A, training=B …)

**B 단점**:
- 첫 통합 PR이 비대화 → 리뷰 부담 큼 (모델 6개 + 이넘 확장 + 컨벤션 결정 동시)
- 첫 PR이 막히면 모든 후속 작업 블록 → 단일 실패 지점

**미채택 분석**:
- **A 단점**: Phase 1~2 끝나기 전엔 도메인 화면 출시 불가 → 출시 일정 직렬화. plan별 작성자(또는 도메인 담당자) 분업 시 Phase 안에 여러 plan이 섞여 책임 경계가 흐려짐
- **C 단점**: 마이그레이션 순서가 PR 머지 순서에 의존 → 머지 순서 잘못되면 makemigrations 충돌·롤백 위험. `core/constants.py` 동시 수정 → rebase 충돌 거의 확정적

**디테일**: 결과적으로 Phase 1 단일 통합 PR + Phase 2~4 개별 PR로 진행. Phase 3는 위험도 별도로 3 PR 분할 (PR1=3a / PR2=3b+3d+3e / PR3=3c).

---

### 1-2. 신규 앱 신설 시점 ✅

**배경**: ISH의 운영 정책류 3개(AppLog/IntegrationLog/DataRetentionPolicy) + imsi의 공통 코드 마스터 2개(CodeGroup/CommonCode)가 core 앱에 들어가면 비대화. 정휘훈 plan은 "정책 모델 3개+ 모이면 분리" 권고.

**옵션**:
- **A**: 지금 `operations/` + `reference/` 두 앱 동시 신설 (총 6 모델 분리)
- **B**: core에 모두 흡수, 추후 분리
- **C**: core/constants/ 폴더만 분리, 모델은 그대로

**채택**: ✅ **A (operations + reference 동시 신설)**

**A 장점**:
- core 비대화 방지 (정휘훈 우려 해소)
- core import 전파 영향 최소화 (CommonCode 잦은 migration이 다른 앱 빌드/테스트에 영향 안 미침)
- 책임 분리 명확화 (core=기반·핵심분류 / reference=공통코드마스터 / operations=운영로그·정책)
- 정휘훈 분리 기준("정책 모델 3개 이상")이 이번에 충족됨 → 지금이 분리 시점

**A 단점**:
- 신규 앱 2개 동시 신설 → 보일러플레이트 부담 (apps.py × 2, INSTALLED_APPS 추가 등)
- 향후 플랜 변경 시 의존 관계 재정리 필요할 수 있음

**미채택 분석**:
- **B**: 단순하지만 core 비대화 + migration 전파 영향 잔존. 향후 분리 비용 ↑
- **C**: 모델은 그대로 두는 절충안. 비대화는 모델보다 코드 import에 더 민감하므로 효과 작음

**디테일**:
- `apps.operations`: AppLog, IntegrationLog, DataRetentionPolicy
- `apps.reference`: CodeGroup, CommonCode
- core 잔류: RiskLevelStandard (코드 이넘과 1:1 강제, 비즈니스 핵심 분류)

---

### 1-3. BaseModel 컨벤션 통일 (Equipment + SafetyCheckItem) ✅

**배경**: Phase 1 시점 BaseModel 상속 모델 2개(Company/Department) vs 직접 정의 15개+. ISH는 Equipment에 직접 `updated_by` 추가 권고, CJY는 SafetyCheckItem을 BaseModel 상속으로 변경 권고. 두 모델을 다르게 처리하면 분기 더 깊어짐.

**옵션**:
- **A**: 두 모델 모두 BaseModel 상속
- **B**: 두 모델 모두 직접 추가
- **C**: 본 작업 전 15개+ 모델 일괄 BaseModel 통일 PR 선행

**채택**: ✅ **A (두 모델 모두 BaseModel 상속)**

**A 장점**:
- CJY가 신규 모델 11개를 BaseModel 상속으로 도입 → BaseModel이 다수파가 됨, 일관성 ↑
- updated_by 자동 추적, related_name 패턴 통일
- 향후 BaseModel 일괄 통일 PR 시 본 두 모델 마이그 재실행 불필요

**A 단점**:
- Equipment/SafetyCheckItem.Meta가 명시적으로 BaseModel.Meta 상속해야 db_table/indexes 보존
- `related_name="updated_equipments"` override 필요 (자동 값은 `updated_equipment_set`)
- 일부 직접 정의 모델 15개+와 분기 잔존 (별도 PR로 정리 예정)

**미채택 분석**:
- **B**: Surgical Changes 원칙엔 부합하지만, CJY가 BaseModel 신규 모델 11개를 도입하므로 다수파 패턴이 BaseModel로 바뀜 → 본 두 모델만 직접 추가하면 일관성 더 깨짐
- **C**: 가장 깔끔하나 17개+ 모델 일괄 마이그가 부담 큼. 본 작업과 분리하는 게 surgical

**디테일**: 잔여 15개+ 모델은 별도 PR로 일괄 통일 (회귀 점검 후 트랙 §B 항목).

---

### 1-4. CI 정합성 테스트 도입 (이넘 ↔ DB 마스터) ✅

**배경**: AlarmType (이넘) ↔ HazardType (DB 모델), GasTypeChoices (이넘) ↔ CommonCode(GAS_TYPE) (DB 모델) 같이 데이터가 두 곳에 동시 존재하는 경우, 한쪽만 추가하고 다른쪽 누락하면 운영 사고 발생.

**옵션**:
- **A**: PR 단계 CI 정합성 테스트 도입 (`assert set(이넘.values) == set(DB 키)`)
- **B**: 코드 리뷰만으로 휴먼 검증
- **C**: signal로 자동 동기화 (이넘 변경 시 DB 시드 자동 갱신)

**채택**: ✅ **A (CI 정합성 테스트)**

**A 장점**:
- 누구든 한쪽만 추가하면 PR 단계에서 즉시 알게 됨
- 테스트 코드 ~10줄로 매우 가벼움
- 머지 차단 → 운영 사고 차단

**A 단점**:
- HazardType seed가 DB에 들어가 있어야 의미 있음 (Phase 2-a까지 placeholder)
- 테스트 환경에서 fixture 자동 적용 필요

**미채택 분석**:
- **B**: 휴먼 에러 가능성 ↑ — 프로덕션 배포 후에야 드러남. 비추천
- **C**: 이넘 코드는 코드 push로 변경되는데 signal이 DB 시드 어떻게 갱신할지 불명확. 과대설계

**디테일**: 도입된 정합성 테스트 4종:
1. `AlarmType` ↔ `HazardType.type_code`
2. `GasTypeChoices` ↔ `CommonCode(GAS_TYPE).code`
3. `RiskLevel` ↔ `RiskLevelStandard.code`
4. `RiskLevelStandard.event_priority` 중복 검증

---

### 1-5. AlertPolicy.target_user_types — JSON vs FK ✅

**배경**: AlertPolicy의 수신 대상(시설관리자/작업자 등)을 어떻게 저장할지. JSON 배열 vs RoleProfile M2M.

**옵션**:
- **A**: JSON 배열로 시작 (`["facility_admin", "worker"]`)
- **B**: RoleProfile M2M (`target_role_profiles`)
- **C**: UserType FK 단일 (관계 단순)

**채택**: ✅ **A (JSON으로 시작)**

**A 장점**:
- AlertPolicy를 RoleProfile과 독립적으로 출시 가능 (병렬 진행)
- 모델 단순 → 디버깅 쉬움 → 운영 초기 안정성 ↑
- 마이그레이션 1회 (필드 추가만)
- 현재 화면 요구("전체 / 시설관리자 / 작업자" 수준 선택)에 충분

**A 단점**:
- 향후 운영 중 "특정 RoleProfile의 사용자가 받는 정책 모두 조회" 같은 정밀 추적 요구 시 데이터 마이그레이션 필요
- JSON 안 검색은 느림 (LIKE 패턴 또는 PostgreSQL JSON 인덱스 별도)

**미채택 분석**:
- **B**: 정통 관계형이지만 RoleProfile 출시 의존 + CASCADE/SET_NULL 결정 필요 + M2M 조인 비용. 4종 권한 수준에서 과대설계
- **C**: UserType 단일은 다중 수신 불가능 (대부분 알림은 여러 역할이 받음)

**디테일**: 향후 정밀 추적 요구 발생 시 RoleProfile FK/M2M으로 마이그레이션. 학습 환경에선 JSON 충분.

---

### 1-6. IntegrationLog 부하 완화 ✅

**배경**: fastapi → DRF 호출 1건당 IntegrationLog 1건 추가 → DRF 호출 ~2배 우려.

**옵션**:
- **A**: fire-and-forget으로 시작 (`raise_on_error=False`)
- **B**: 1초 단위 batch flush (메모리 큐에 모았다가 한 번에 전송)
- **C**: 기록 안 함 (fastapi → DRF 호출 자체를 IntegrationLog로 추적 안 함)

**채택**: ✅ **A (fire-and-forget 시작)**

**A 장점**:
- 구현 매우 간단 — `drf_client.post_to_drf`에 `raise_on_error=False` 옵션만
- 본 흐름(센서 데이터 저장)에 영향 0 — IntegrationLog 실패해도 가스 데이터는 정상 저장
- 빠른 출시 가능

**A 단점**:
- 호출 수 자체가 ~2배 그대로 → 운영 시작 후 부하가 실제 문제가 되는지 측정 필요
- 부하가 임계점 넘으면 → batch flush로 전환 (코드 변경 필요, 마이그레이션 없음)

**미채택 분석**:
- **B**: 정밀하지만 메모리 큐 + 플러시 타이머 + fastapi 재시작 시 큐 손실 처리 필요. 첫 출시 코드 비대화
- **C**: 컨벤션 깨짐 + 피그마 요구 미충족 (운영 데이터 화면에 "수집" 카테고리 표시 불가)

**디테일**: A → B 전환은 IntegrationLog 모델 변경 없음 — 호출 코드만 변경 (마이그레이션 불필요). 운영 부하 측정 후 전환 검토 (회귀 점검 후 트랙).

---

### 1-7. RiskLevelStandard.code ↔ RiskLevel 동기화 ✅

**배경**: RiskLevel은 코드 이넘(NORMAL/WARNING/DANGER), RiskLevelStandard는 DB 모델. code 필드가 이넘 값과 1:1 일치해야 함. 운영자가 코드를 임의 변경/추가하면 시스템 깨짐.

**옵션**:
- **A**: fixture + UI readonly 병행 (이중 잠금)
- **B**: fixture만 (어드민에서 자유 수정 가능)
- **C**: UI readonly만 (fixture 없으면 row 자체 없음)

**채택**: ✅ **A (fixture + UI readonly)**

**A 장점**:
- fixture: 마이그레이션 시점에 row 3개 자동 생성 → 코드와 DB 항상 일치 시작
- UI readonly: 어드민 폼에서 code 필드 잠금 → 운영자는 메타(name/color/priority)만 수정
- 코드 일관성 + 운영자 자유도 둘 다 충족

**A 단점**:
- fixture 파일 + 어드민 폼 설정 둘 다 관리
- 향후 RiskLevel 새 단계 추가 시 fixture 동시 갱신

**미채택 분석**:
- **B**: 운영자가 code="critical" 임의 추가 → 코드(`RiskLevel.CRITICAL`)에 없으면 죽은 데이터. 더 위험: code="normal"을 "okay"로 변경 → 위험도 매칭 전부 실패
- **C**: row 자체 없으면 시스템 동작 안 함

**디테일**: `display_color`는 토큰명(green/orange/red)으로 진입 — 디자이너 hex 회신 시 마이그레이션 1회로 갱신. `event_priority`/`alert_intensity`는 운영 정책 확정값.

---

## §2. Phase 1 모델/이넘 확장 결정

### 2-1. AlarmType 10종 확정 ✅

**배경**: 기존 AlarmType 4종(GAS_THRESHOLD/POWER_OVERLOAD/GEOFENCE_INTRUSION/SENSOR_FAULT) 외 CJY 화면 요구로 추가 필요.

**옵션**:
- **A**: 단일 AlarmType 이넘 확장 (10종)
- **B**: AlarmType + EventDetail 별도 enum 분리

**채택**: ✅ **A (10종 확장)**

**A 장점**:
- 기존 `AlarmRecord.alarm_type`, `Event.event_type` 참조 코드 변경 없음
- 4차 AI 이상탐지 결과를 새 값(`AI_ANOMALY` 등) 추가만으로 파이프라인 연결
- 모든 알람 유형이 단일 진실 공급원에서 관리

**A 단점**:
- 이넘 비대화 (4종 → 10종)
- AI 이상탐지/점검 일정 등 성격이 다른 유형이 한 이넘에 섞임

**미채택 분석**:
- **B**: 도메인별 분리는 명확하나 `AlarmRecord`/`Event` 두 모델에 FK/필드 추가 마이그 + 두 enum 매핑 로직이 영구 유지비용. 4차 AI Celery 태스크가 두 enum 동시 참조 → 분기 2배

**디테일**:
```python
# 기존 4종 (키/값 변경 없음)
GAS_THRESHOLD, POWER_OVERLOAD, GEOFENCE_INTRUSION, SENSOR_FAULT
# 신규 6종
PPE_VIOLATION, VR_TRAINING_NOT_DONE, SAFETY_CHECK_PENDING,
INSPECTION_SCHEDULED, BATCH_FAILED, STORAGE_OVERDUE
```
정책 화면 노출은 9종 (`USER_FACING_ALARM_TYPES`, SENSOR_FAULT 제외).

---

### 2-2. SystemLog ActionType 17종 추가 ✅

**배경**: ISH의 지도 편집 5종 + CJY의 정책/공지/VR/체크리스트 12종 추가 필요.

**옵션**:
- **A**: 1개 PR로 17종 일괄 추가
- **B**: ISH MAP_* 5종 / CJY 12종 분리 PR

**채택**: ✅ **A (1개 PR 일괄)**

**A 장점**:
- ActionType 추가는 choices 메타만 변경 → 마이그 1회로 끝
- core/constants.py 동시 수정 충돌 회피

**A 단점**:
- 한 PR에 사용자 액션 다양 → 리뷰 시 의도 분기 분류 부담

**디테일**:
```
MAP_*  : MAP_GEOFENCE_CREATE, MAP_SENSOR_MOVE, MAP_FACILITY_UPDATE,
         MAP_POSITION_NODE_REGISTER, MAP_OBJECT_DELETE
POLICY_*  : POLICY_CREATED, POLICY_UPDATED, POLICY_DEACTIVATED
NOTICE_*  : NOTICE_CREATE, NOTICE_UPDATE, NOTICE_DELETE
VR_*  : VR_CONTENT_CREATED, VR_CONTENT_REPLACED, VR_CONTENT_TOGGLED
CHECKLIST_*  : CHECKLIST_REVISION_PUBLISHED, CHECKLIST_SECTION_CREATED,
              CHECKLIST_ITEM_DEACTIVATED
```

CHECKLIST 그룹은 일관성 위해 모두 `CHECKLIST_` prefix 통일 (원안의 prefix 없는 SECTION_CREATED/ITEM_DEACTIVATED 갱신).

---

### 2-3. RiskLevelStandard 색상 토큰 진입 ✅

**배경**: 디자이너 hex 회신 전 시드 데이터 필요.

**옵션**:
- **A**: 토큰명(green/orange/red)으로 시작, 후속 hex 갱신
- **B**: 임시 hex(#28A745 등) 가짜 시작
- **C**: 시드 보류, 디자이너 회신 후 시작

**채택**: ✅ **A (토큰명)**

**A 장점**:
- 마이그레이션 진행 가능 (시드 미존재 시 NOT NULL 전환 차단)
- hex 회신 시 마이그레이션 1회 (display_color 컬럼 update)
- 프론트는 토큰 → CSS class 매핑으로 처리 가능

**A 단점**:
- 토큰명 → CSS 매핑 코드 별도 필요

**미채택 분석**:
- **B**: 가짜 hex가 그대로 운영 노출 위험
- **C**: 디자인 회신 일정 불확실 → 마이그 차단

---

## §3. Phase 2 도메인 모델 결정

### 3-1. Phase 2 진행 단위 ✅

**옵션**:
- **A**: 단일 PR (8개 sub-step 합쳐 한 묶음)
- **B**: 2-3 PR 분할 (의존 그룹별)
- **C**: 8 sub-PR 분리

**채택**: ✅ **A (단일 PR)**

**A 장점**:
- Phase 1 패턴 일관 → 의사결정 비용 ↓
- 머지 충돌 감소 (한 번에 통과)
- Phase 단위 관리 일관성

**A 단점**:
- PR 비대 (모델 12개 + 시드 2 + 인프라 5)

**미채택 분석**:
- **B**: 의존성 분배 가능하나 Phase 단위 일관성 깨짐
- **C**: 가장 작은 단위지만 PR 8개 관리 부담 + CI 8회

---

### 3-2. Menu.code 형식 ✅

**옵션**:
- **A**: snake_case (`dashboard_main`, `equipment_management`)
- **B**: 기존 `'SNB-01'` 유지 (하이픈 + 숫자)

**채택**: ✅ **A (snake_case)**

**A 장점**:
- 다른 코드값 컨벤션과 일치 (`CodeGroup.code`, `RoleProfile.code` 모두 snake_case)
- 일관된 검색·치환 가능
- 의미 명확 (`safety_checklist` vs 'SNB-01')

**A 단점**:
- 기존 menu.py 'SNB-XX' 데이터를 매핑 변환 필요
- 외부에서 ID 참조 중이면 깨짐 (회귀 점검 항목)

**미채택 분석**:
- **B**: 기존 ID 보존이지만 다른 코드값과 컨벤션 불일치, 의미 불명확

---

### 3-3. VRTrainingContent UNIQUE 조건 ✅

**옵션**:
- **A**: 부분 UniqueConstraint (`is_active=True`일 때만 (target_type, target_facility) 1개)
- **B**: 전체 UNIQUE ((target_type, target_facility) 조합당 영구 1개)

**채택**: ✅ **A (부분 UniqueConstraint)**

**A 장점**:
- 콘텐츠 교체 시 기존 row를 `is_active=False`로 보존 → 이력 추적
- 새 row 생성 + 부분 UNIQUE로 활성 1개 강제
- VRTrainingRevision과 별개로 메인 콘텐츠도 이력 보존

**A 단점**:
- PostgreSQL 부분 인덱스 필요 (SQLite는 지원하지만 syntax 차이)

**미채택 분석**:
- **B**: 교체 이력 보존 안 됨 → VRTrainingRevision에만 의존, 메인 콘텐츠 자체 이력은 사라짐. 분리 책임 모호

---

### 3-4. Notice 첨부파일 제약 ✅

**옵션**:
- **A**: 최대 10MB, 이미지+문서 (jpg/png/gif/pdf/docx/xlsx/pptx)
- **B**: 최대 5MB, 이미지만 (jpg/png/gif)
- **C**: 제한 없음 (max_size 없이 자유)

**채택**: ✅ **A (10MB + 이미지+문서)**

**A 장점**:
- 일반적 공지 용도(이미지+문서)에 충분
- 보안 위험 차단 (실행 파일/스크립트 제외)
- validators 파일로 분리 → 향후 다른 첨부 도메인에서 재사용 가능

**A 단점**:
- 운영 자유도 제한 (예: zip 압축본 첨부 불가)
- 10MB 초과 파일 케이스 별도 처리

**미채택 분석**:
- **B**: 너무 제한적. 점검 보고서 PDF 첨부 불가
- **C**: 보안 위험 큼 (악성 실행파일 업로드 가능)

---

## §4. Phase 3 관계 변경 (33건, 별도 문서)

[phase_3_plan.md](phase_3_plan.md)에 33건 결정이 동일 형식으로 정리되어 있음.

**핵심 결정 6건만 요약**:

| ID | 결정 | 채택안 |
|---|---|---|
| 3a | WorkerPosition.received_node 책임 | 본인이 fastapi + DRF 양측 동시 갱신 (외부 펌웨어 의존 0) |
| 3a | node_id 식별자 형식 | `PositionNode.device_id` 그대로 |
| 3b | Section 모델 facility 단위 | 공장별 (facility FK PROTECT) |
| 3b | Section 삭제 정책 | PROTECT (Item 남아있으면 삭제 차단) |
| 3c | Session 식별 키 | `(worker, date, revision)` 복합 UNIQUE |
| 3c | UNIQUE 다단계 마이그 | 5단계 분할 (nullable→백필→old drop→new add→NOT NULL) |
| 3d | AlertPolicy FK on_delete | SET_NULL (Soft Delete 일관) |
| 3e | event FK CASCADE → SET_NULL | nullable + clean()에서 event/policy 둘 중 하나 필수 |
| 3e | DELAYED 상태 | 동적 판정 (PENDING + 5분 timeout) |
| 횡단 | PR 분할 | 3 PR (PR1=3a / PR2=3b+3d+3e / PR3=3c) |

상세 옵션·장단점은 [phase_3_plan.md](phase_3_plan.md) 참조.

---

## §5. Phase 4 서비스/뷰 결정

### 5-1. Phase 4 진행 단위 ✅

**옵션**:
- **A**: 단일 PR (Phase 1, 2와 동일)
- **B**: 2-3 PR 분할 (인프라/정책/배치 묶음)

**채택**: ✅ **B (3 PR 분할)**

**B 장점**:
- PR1(인프라 4abcd) — 위험도 중 (가스 알람 회귀 가능성)
- PR2(정책+템플릿 4ef) — 새 서비스 추가, 기존 영향 적음
- PR3(Celery 4g) — 단독 작업, 독립 검증
- 위험도별 격리 (실패 영향 한정), 학습 가치 큼

**B 단점**:
- PR 3개 관리 + CI 3회
- Phase 1, 2와 일관성 약화

**미채택 분석**:
- **A**: 단일 PR이면 인프라 변경(GasData.save 재작성)과 정책 매칭이 한꺼번에 들어가 회귀 위험 ↑

---

### 5-2. 캐시 백엔드 ✅

**옵션**:
- **A**: Redis (django-redis CACHES)
- **B**: 프로세스 메모리 (lru_cache)

**채택**: ✅ **A (Redis)**

**A 장점**:
- gunicorn worker 4개 + Celery worker 2개 = 총 6개 프로세스가 같은 Redis 공유 → 일관성
- 운영자가 Threshold 수정 → signal로 `cache.delete()` → 모든 worker 즉시 새 값 사용
- 디코나이가 이미 Redis 활용 중 (gas_alarm.py) → 인프라 재사용
- TTL 설정 가능 (예: 1시간 자동 갱신)

**A 단점**:
- 네트워크 호출 ~1ms 추가 (단, DB 쿼리 ~수ms보다 빠름)
- Redis 다운 시 graceful degradation 필요 (DB 직접 조회 fallback)

**미채택 분석**:
- **B (lru_cache)**:
  - 🔴 **프로세스별 독립 캐시** — gunicorn worker 4개 각자 다른 캐시. 워커 간 일관성 없음
  - 🔴 **Invalidate 불가능** — 운영자가 Threshold 수정해도 lru_cache는 모름 → 서버 재시작 전까지 옛 값 사용 (운영 사고)
  - Celery worker는 또 다른 캐시 → 같은 데이터를 7번 조회

**디테일**: 캐시 키 패턴 `threshold:{group_code}:{item}` (TTL 1시간), `menu_tree:role:{role}` (TTL 5분). signal로 자동 invalidate.

---

### 5-3. Threshold seed 본 PR 포함 여부 ✅

**옵션**:
- **A**: 본 PR(PR1)에 포함
- **B**: 별도 트랙으로 분리

**채택**: ✅ **A (포함)**

**A 장점**:
- 4b/4c/4d가 DB 조회로 전환되니 seed 없으면 알람 동작 차단
- 마이그레이션 한 번에 완료
- 운영자가 별도 작업 없이 적용

**A 단점**:
- PR1 비대화 (모델 + 시드 + 마이그)

**미채택 분석**:
- **B**: 본 PR 머지 직후 알람 판정 코드 동작 안 하는 구간 발생 → 운영 사고 위험

**디테일**:
- `gas_legal` ThresholdGroup + 가스 9종 (CO/H2S/CO2/O2/NO2/SO2/O3/NH3/VOC)
- `power_default` ThresholdGroup + power_w 1종
- 기존 `core/constants.py POWER_THRESHOLDS` + `facilities LEGAL_THRESHOLDS` 상수에서 fixture로 이전

---

### 5-4. Notification 템플릿 엔진 ✅

**옵션**:
- **A**: Python f-string + dict
- **B**: Django Template (`django.template.Template`)
- **C**: Jinja2

**채택**: ✅ **B (Django Template)**

**B 장점**:
- 조건문(`{% if %}`), 반복문(`{% for %}`), 필터(`{{ value|upper }}`) 등 풍부
- Django 내장 → 의존성 추가 0
- 디코나이 dashboard가 이미 Django Template 사용 중 → 운영자 동일 문법 사용 가능
- 변수 누락 시 빈 문자열 (silent fallback)
- 알람 태스크 4개+ 분기 로직 필요 → 사용자 결정 (Phase 4-f)

**B 단점**:
- f-string보다 느림 (파싱+렌더 단계)
- 알람 메시지에 if/for 과대설계 가능성

**미채택 분석**:
- **A (f-string)**: 단순 치환에 충분하지만 조건문 불가 ("위험도가 danger면 '🚨 긴급'" 분기 어려움). 알람 태스크 추가 가능성 고려 시 한계
- **C (Jinja2)**: 별도 라이브러리, 의존성 추가. Django Template와 거의 동일 기능 → 비추천

**디테일**:
- 예시 템플릿: `"{{ source_label }}에서 {% if level == 'danger' %}🚨 긴급{% else %}⚠️ 주의{% endif %} — {{ gas_name }} {{ value }}{{ unit }}"`
- 빈 템플릿 또는 SyntaxError → fallback (Event.summary 사용)

---

## §6. 정휘훈 4차 결정 분석 대조

정휘훈 plan과 통합 plan의 결정 비교 (6건):

| # | 정휘훈 결정 | 통합 plan 결정 | 일치 여부 |
|---|---|---|---|
| 1 | AlarmType 단일 확장 | AlarmType 10종 단일 확장 | ✅ 일치 |
| 2 | GasTypeChoices 이넘 유지 + DB 병행 | 이넘 유지 + CommonCode(GAS_TYPE) DB 병행 + CI 테스트 | ✅ 일치 (+CI 강화) |
| 3 | Threshold DB화 | Threshold 모델 + Phase 4-c GasData.save() DB 조회 전환 | ✅ 일치 |
| 4 | DataRetentionPolicy core 앱 | operations 앱 신설 (정휘훈 분리 기준 충족됨) | ⚠️ 시점 차이 |
| 5 | IntegrationLog DRF internal API | DRF 신규 internal API + fire-and-forget | ✅ 일치 |
| 6 | GasData.ch4 보류 | 보류 (센서 정의서 기준) | ✅ 일치 |

**§4 시점 차이 부연**: 정휘훈은 "정책 모델 3개 이상 모이면 분리" 권고. 본 통합 작업으로 정책 모델 3건(AppLog/IntegrationLog/DataRetentionPolicy)이 동시 신설되어 정휘훈 본인 기준이 충족됨 → 지금 분리가 맞다는 해석.

---

## §7. 회귀 점검 방식

### 7-1. Phase 1~4 완료 후 회귀 점검 진입 방식 ✅

**배경**: Phase 1~4에서 모델/필드/시그니처 30+건 변경. 단위 테스트 29건은 통과했지만 정적 분석 + 핵심 흐름 회귀 테스트로 보강 필요.

**옵션**:
- **A**: 자동 grep + 영향 분석 보고서 (Explore 에이전트 1개)
- **B**: 항목별 수동 점검 (각 행 1건씩 grep)
- **C**: 회귀 테스트 우선 (5개 흐름 단위/통합 테스트)

**채택**: ✅ **A → C 순으로 진행**

**A → C 순 장점**:
- A 먼저: 30분 내 영향 영역 정리, 깨진 호출처 명확화
- 발견된 깨진 곳 즉시 fix → 별도 PR
- C 다음: 5개 핵심 흐름 회귀 테스트 → CI 자동화

**A → C 순 단점**:
- 두 단계 분리 진행 → 사이클 2회
- B (수동 점검) 학습 가치 일부 손실

**미채택 분석**:
- **B만 단독**: 항목당 5~10분, 시간 큼 + 누락 위험. 정적 분석 자동화로 대체 가능
- **C만 단독**: 회귀 테스트는 동작 검증이지 코드 영향 분석은 못 함 → A와 함께 가야 완전

**디테일**: 다음 세션 진입 절차는 [post_phase4_regression_plan.md](post_phase4_regression_plan.md) §5/§9 참조.

---

## 📌 결정 요약 한 페이지

| § | Phase | 결정 항목 | 채택 |
|---|---|---|---|
| 1-1 | 1 | 거시 전략 | 기반 통합 PR + 도메인 분리 |
| 1-2 | 1 | 신규 앱 신설 | operations + reference 동시 |
| 1-3 | 1 | BaseModel 컨벤션 | Equipment + SafetyCheckItem 모두 상속 |
| 1-4 | 1 | CI 정합성 테스트 | 도입 (4종) |
| 1-5 | 1 | AlertPolicy.target_user_types | JSON 시작 |
| 1-6 | 1 | IntegrationLog 부하 | fire-and-forget 시작 |
| 1-7 | 1 | RiskLevelStandard 동기화 | fixture + UI readonly |
| 2-1 | 1 | AlarmType | 10종 단일 확장 |
| 2-2 | 1 | SystemLog ActionType | 17종 일괄 추가 |
| 2-3 | 1 | RiskLevelStandard 색상 | 토큰명 진입 |
| 3-1 | 2 | Phase 2 진행 단위 | 단일 PR |
| 3-2 | 2 | Menu.code 형식 | snake_case |
| 3-3 | 2 | VRTrainingContent UNIQUE | 부분 UniqueConstraint |
| 3-4 | 2 | Notice 첨부 제약 | 10MB + 이미지+문서 |
| 4 | 3 | 33건 (별도 문서) | phase_3_plan.md 참조 |
| 5-1 | 4 | Phase 4 진행 단위 | 3 PR 분할 |
| 5-2 | 4 | 캐시 백엔드 | Redis |
| 5-3 | 4 | Threshold seed | 본 PR 포함 |
| 5-4 | 4 | Notification 템플릿 | Django Template |
| 7-1 | post-4 | 회귀 점검 방식 | A(grep) → C(회귀 테스트) |

---

## 🔗 참조 문서

- [phase_1_plan.md](phase_1_plan.md) ~ [phase_1_report.md](phase_1_report.md) — Phase 1 상세
- [phase_2_plan.md](phase_2_plan.md) ~ [phase_2_report.md](phase_2_report.md) — Phase 2 상세
- [phase_3_plan.md](phase_3_plan.md) — Phase 3 단독 결정문 33건
- [phase_3_pr1_report.md](phase_3_pr1_report.md) ~ [phase_3_pr3_report.md](phase_3_pr3_report.md) — Phase 3 PR 보고서
- [phase_4_plan.md](phase_4_plan.md) — Phase 4 plan
- [phase_4_pr1_report.md](phase_4_pr1_report.md) ~ [phase_4_pr3_report.md](phase_4_pr3_report.md) — Phase 4 PR 보고서
- [post_phase4_regression_plan.md](post_phase4_regression_plan.md) — 회귀 점검 plan + 다음 세션 가이드
