# Phase 3 단독 결정문 — 옵션 / 채택 / 장단점 / 대안

> **결정자**: 최재용 (단독)
> **전제**: 학습용 팀 프로젝트, 외부(펌웨어·디자인·인프라) 의존 없음, 운영 트래픽 없음
> **근거**: `이성현 Plan.md`, `최재용 Plan.md`, `정휘훈 Plan.md`, 통합 plan §3 의존 그래프
> **상태**: 모든 항목 본인 단독 결정 완료. 팀에 공유 후 이의 있으면 갱신.

---

## 결정 요약 (한 페이지)

| 영역 | 항목 | 채택 |
|---|---|---|
| **3a** | fastapi 페이로드 갱신 책임 | 본인 (fastapi + DRF 양측 동시 갱신) |
| **3a** | node_id 식별자 형식 | `PositionNode.device_id` 그대로 |
| **3a** | 페이로드 schema 변경 시점 | DRF FK nullable 먼저 → fastapi schema → 데이터 흐름 |
| **3a** | NULL row 처리 | 화면 "수신 노드 미상" 라벨 |
| **3a** | trial period | 학습 환경이라 즉시 진행 (trial 무관) |
| **3b** | Section 모델 필드 | name + description + order + facility FK + is_active + BaseModel |
| **3b** | 공장별 vs 전사 | **공장별** (facility FK 보유) |
| **3b** | 기본 Section 자동 생성 | 마이그 시 facility별 "기본" Section 1개 자동 + 기존 Item 백필 |
| **3b** | 기존 Item 매핑 | 위 자동 생성 Section으로 일괄 백필 |
| **3b** | Section 삭제 정책 | **PROTECT** |
| **3b** | order 정합성 | (section.order, item.order) 두 레벨 정렬 |
| **3c** | Session 식별 키 | **(worker, date, revision)** 복합 |
| **3c** | 1일 1세션 정책 | 1일 1세션 + "오늘 이미 체크" 차단 + 기존 세션 이어가기 |
| **3c** | Revision JSON 스냅샷 | Section 트리 + Item 제목·is_required·order |
| **3c** | Revision 발행 트리거 | 관리자 수동 "발행" 버튼 |
| **3c** | 기존 SafetyStatus 매핑 | 마이그 시 default Session 1개 자동 생성 → 일괄 매핑 |
| **3c** | UNIQUE 다단계 마이그 | 5단계 분할 |
| **3c** | mark_checked() 시그니처 | `mark_checked(session, note=None)` (session 필수) |
| **3c** | 무중단 vs 점검창 | 학습 환경이라 N/A — 즉시 적용 |
| **3d** | AlertPolicy FK on_delete | **SET_NULL** |
| **3d** | description 의미 | summary=한 줄(기존) / description=상세(신규). docstring |
| **3d** | status_note 위치 | **Event** (EventLog는 전환 이력 별도) |
| **3d** | 기존 Event row 처리 | nullable + default="" 자동 채움 |
| **3d** | AlertPolicy 자동 매칭 시점 | Phase 4-e policy_matcher가 채움. Phase 3은 FK만 |
| **3e** | event FK CASCADE → SET_NULL | **SET_NULL** + nullable |
| **3e** | event nullable 허용 시 clean() | event/policy 중 하나는 필수 |
| **3e** | retry_count | default 0 |
| **3e** | last_attempted_at | nullable DateTimeField + docstring |
| **3e** | DELAYED 상태 | 동적 판정 (PENDING + 5분 timeout = "지연" 라벨) |
| **3e** | AlertPolicy FK on_delete | SET_NULL |
| **3e** | Soft Delete | 도입 안 함 (Hard Delete) |
| **횡단 A** | PR 분할 | **3 PR** (3a 분리 / 3b+3d+3e / 3c 별도) |
| **횡단 B** | DB 백업 | 마이그 전 `pg_dump`(또는 SQLite 파일 복사) 1회 |
| **횡단 C** | 롤백 전략 | RunPython reverse 코드 필수 + 로컬 reverse 테스트 |
| **횡단 D** | 운영 무중단 | N/A (학습 환경) |
| **횡단 E** | 단계별 검증 | makemigrations → migrate → 시드 → 단위 → 회귀 |
| **횡단 F** | dry-run 환경 | 본인 로컬 DB 복제 |
| **횡단 G** | 외부 트랙 | N/A (팀 프로젝트) |

---

## §3a. WorkerPosition.received_node

### 3a-1. fastapi 페이로드 갱신 책임

**옵션**: (A) 본인이 fastapi + DRF 양측 갱신 / (B) 팀원에게 분배 / (C) 모의 데이터 처리만

**채택**: ✅ A — 본인 단독 양측 갱신

**이유**: 팀 프로젝트라 외부 펌웨어 의존 없음. 한 사람이 fastapi schema와 DRF serializer를 묶어서 변경하면 schema 불일치 위험 0. 회의 불가 상황에서 분배 협의도 불가능.

**A 장점**:
- schema 일관성 보장 (단일 책임)
- 외부 의존 0
- PR 1개로 두 서버 동시 변경 가능

**A 단점**:
- 본인 작업량 ↑ (단, fastapi 변경은 schema 1줄 + view 1곳)
- fastapi 측 코드 익숙하지 않으면 학습 비용

**대안 B (팀원 분배) 장점**:
- 부담 분산
- 팀원 fastapi 학습 기회

**대안 B 단점**:
- 동기화 오버헤드 (회의 불가 상황에서 비현실적)
- schema 불일치 위험 ↑

**대안 C (모의 데이터만) 장점**:
- fastapi 변경 0

**대안 C 단점**:
- 실제 페이로드 흐름 검증 안 됨
- 학습 가치 손실

---

### 3a-2. node_id 식별자 형식

**옵션**: (A) `PositionNode.device_id` 그대로 / (B) `PositionNode.pk` (int) / (C) 별도 코드 신설

**채택**: ✅ A — `device_id` 그대로 (예: "NODE-001")

**이유**: PositionNode 모델에 이미 `device_id` 필드 존재. 다른 디바이스(GasSensor 등)도 device_id 사용 컨벤션. 추가 모델 변경 0.

**A 장점**:
- 기존 모델 변경 0
- 컨벤션 일관 (모든 디바이스 device_id로 식별)
- 외부에 pk 노출 안 함 (보안)

**A 단점**:
- `device_id` 형식 변경 시 schema 양쪽 갱신 필요 (드물지만 비용)

**대안 B (pk) 장점**:
- 단순 정수 비교

**대안 B 단점**:
- DB 내부 식별자를 외부에 노출 → 비권장
- pk 변경(reseed 등) 시 모든 페이로드 의미 깨짐

**대안 C (별도 코드 신설) 장점**:
- 자유로운 코드 체계

**대안 C 단점**:
- 모델 마이그레이션 추가
- device_id와 중복 관리 (오타·동기화 부담)

---

### 3a-3. 페이로드 schema 변경 시점

**옵션**: (A) DRF nullable 먼저 → fastapi schema 갱신 / (B) fastapi 먼저 / (C) 동시 PR

**채택**: ✅ A — DRF FK nullable 추가 → fastapi schema 갱신 → 데이터 흐름 시작

**이유**: nullable로 두면 fastapi 갱신 전에도 기존 페이로드 그대로 받음. 단계별 검증 + 롤백 용이.

**A 장점**:
- 단계별 안전 (DRF 변경 후에도 기존 동작 유지)
- 각 단계 독립 검증
- 롤백 범위 작음

**A 단점**:
- 중간 기간 NULL 누적 (학습 환경이라 무시 가능)
- PR/적용 사이클 2회

**대안 B (fastapi 먼저) 장점**:
- 데이터 즉시 흐르기 시작

**대안 B 단점**:
- DRF 측 컬럼 없으면 변환 코드 임시 추가 필요
- 변환 코드 제거 후속 PR 필요

**대안 C (동시) 장점**:
- 사이클 1번

**대안 C 단점**:
- 실패 시 롤백 범위 크고 복잡
- 학습 환경에서도 두 서버 동시 변경은 디버깅 어려움

---

### 3a-4. NULL row 처리

**옵션**: (A) 화면에 "수신 노드 미상" 라벨 / (B) 화면 미노출 / (C) 데이터 삭제

**채택**: ✅ A — 화면에 "수신 노드 미상" 또는 "-" 표시

**이유**: WorkerPosition은 위치 데이터 자체가 가치. node 정보는 부가 메타. 데이터 손실 없이 명시적 표시가 가장 안전.

**A 장점**:
- 데이터 손실 0
- 마이그 전 데이터 그대로 활용

**A 단점**:
- 화면에 "미상" 라벨 처리 코드 추가

**대안 B (미노출) 장점**:
- UI 단순

**대안 B 단점**:
- 데이터 사라진 것처럼 보임 (운영 혼선)

**대안 C (삭제) 장점**:
- DB 정리

**대안 C 단점**:
- 데이터 손실 (학습 환경에서도 비추천)
- 위치 이력 추적 불가

---

### 3a-5. Trial period

**옵션**: (A) 즉시 진행 / (B) 1주 trial 후 fastapi 갱신 / (C) 단계별 분리 적용

**채택**: ✅ A — 즉시 진행

**이유**: 학습 환경이라 운영 영향 없음. trial period의 의미는 운영 환경에서 점진 검증인데 본 환경 무관.

**A 장점**: 빠른 진행, 검증 신속
**A 단점**: 없음 (개발 환경)
**대안 B/C 장점**: 운영 환경에서 안전성 ↑
**대안 B/C 단점**: 학습 환경에서 의미 작음, 진행 지연

---

## §3b. SafetyCheckSection + SafetyCheckItem.section FK

### 3b-1. Section 모델 필드

**옵션**: (A) 표준 (name + description + order + facility FK + is_active + BaseModel) / (B) 최소 (name + order만) / (C) 최대 (icon, color 등 UI 메타까지)

**채택**: ✅ A — 표준

```python
class SafetyCheckSection(BaseModel):
    name        = CharField(max_length=100)
    description = TextField(blank=True, default="")
    order       = PositiveIntegerField(default=0)
    facility    = ForeignKey("facilities.Facility", on_delete=PROTECT,
                             related_name="safety_check_sections")
    is_active   = BooleanField(default=True)
    deactivated_at = DateTimeField(null=True, blank=True)
```

**이유**: 화면 명세 요구 충족 + 다른 모델과 BaseModel 패턴 일관 + Soft Delete 패턴 통일.

**A 장점**: 표준 설계, 정렬·필터 즉시 활용, 향후 확장 여지
**A 단점**: 필드 6개로 약간 비대 (학습 환경 무시 가능)
**대안 B (최소) 장점**: 단순. **단점**: 운영 시 필드 추가 마이그 불가피
**대안 C (최대) 장점**: 모든 UI 요구 사전 대응. **단점**: YAGNI 위반, 미사용 필드

---

### 3b-2. 공장별 vs 전사 Section

**옵션**: (A) 공장별 (facility FK 필수) / (B) 전사 공유 (facility FK 없음) / (C) 둘 다 (facility nullable)

**채택**: ✅ A — 공장별

**이유**: 다른 도메인 모델(SafetyCheckItem, GasSensor, PowerDevice 등)이 모두 facility 단위 운영. 권한 격리(시설관리자가 본인 시설만 접근)와 일관. CJY plan §1.2 권한 정책과 정합.

**A 장점**:
- 권한 격리 일관 (시설관리자 = 본인 facility만)
- 공장별 커스터마이즈 (A공장 "가스 점검" ≠ B공장 "가스 점검")
- 다른 모델 패턴과 일관

**A 단점**:
- 같은 이름의 Section이 공장 5개에 5번 중복 생성 (운영자 부담)
- 전사 공통 정책 적용 어려움

**대안 B (전사 공유) 장점**:
- 단일 진실 공급원
- 공장 추가 시 자동 적용

**대안 B 단점**:
- 권한 격리 충돌 (어느 공장 관리자가 수정?)
- 공장별 차별화 불가
- 다른 모델과 일관성 깨짐

**대안 C (nullable) 장점**:
- 유연 (전사 + 공장별 혼용)

**대안 C 단점**:
- 정책 복잡 (NULL = 전사라는 암묵적 규칙)
- 권한 처리 코드 if/else 분기

---

### 3b-3. 기본 Section 자동 생성 정책

**옵션**: (A) 마이그 시 facility별 "기본" Section 1개 자동 + 기존 Item 백필 / (B) 자동 생성 안 함, NULL 허용 영구 / (C) 자동 생성 안 함, 운영자 수동

**채택**: ✅ A — facility별 "기본" Section 자동 생성 + 백필

**이유**: 데이터 손실 0, NOT NULL 전환 가능, 즉시 운영 가능 상태.

**A 장점**:
- 무중단 마이그
- 기존 SafetyCheckItem 손실 0
- NOT NULL 전환 즉시 가능
- 운영자 추가 작업 0

**A 단점**:
- "기본" Section이 자동 노출 → 운영자가 적절 Section으로 재분류 필요
- 자동 생성 코드 (data migration RunPython) 작성 부담

**대안 B (NULL 영구) 장점**:
- 가장 단순한 마이그

**대안 B 단점**:
- Section 트리 의미 흐려짐 (Section 없는 Item)
- NOT NULL 전환 불가
- 화면에서 "Section 없음" 케이스 분기 필요

**대안 C (수동) 장점**:
- 운영자가 의미 있는 Section 직접 생성

**대안 C 단점**:
- 마이그 직후 NOT NULL 전환 차단
- 운영자 작업 전까지 데이터 사용 불가

---

### 3b-4. 기존 SafetyCheckItem 매핑

**옵션**: (A) 자동 생성된 facility별 "기본" Section으로 일괄 / (B) 항목별 수동 매핑 / (C) NULL 유지

**채택**: ✅ A — 일괄 백필

**이유**: 3b-3과 연결. 데이터 손실 0 + 운영 즉시 가능.

**A 장점/단점**: 3b-3과 동일
**대안 B 장점**: 의미 있는 분류. **단점**: 항목 수만큼 작업, 학습 환경 시간 낭비
**대안 C 장점**: 마이그 단순. **단점**: 3b-3 대안 B 단점 동일

---

### 3b-5. Section 삭제 정책

**옵션**: (A) PROTECT / (B) CASCADE / (C) SET_NULL / (D) Soft Delete (is_active=False만 사용)

**채택**: ✅ A — PROTECT (Item 남아있으면 삭제 차단)

**이유**: CASCADE는 데이터 손실 위험, SET_NULL은 고아 Item 발생, Soft Delete는 모델 패턴 불일치(Section만 다른 패턴이면 코드 혼선). PROTECT가 가장 안전.

**A (PROTECT) 장점**:
- 데이터 보호 (SafetyCheckItem 의도치 않은 손실 0)
- 운영자에게 명시적 정리 강제 ("Item 옮기고 Section 삭제하세요")

**A 단점**:
- 운영자가 Item 모두 옮겨야 Section 삭제 가능 (UX 약간 불편)
- bulk delete 시 PROTECT 에러 처리 코드 필요

**대안 B (CASCADE) 장점**:
- 단순, 자동 정리

**대안 B 단점**:
- 데이터 손실 위험 (실수 클릭 한 번에 Item 수십 개 사라짐)
- SafetyStatus까지 cascade 영향

**대안 C (SET_NULL) 장점**:
- Section만 사라짐, Item 보존

**대안 C 단점**:
- 고아 Item 발생 (Section 없는 Item)
- 화면에서 NULL 처리 분기 필요
- 3b-2의 NOT NULL 정책과 충돌

**대안 D (Soft Delete) 장점**:
- 복구 가능
- 데이터 보존

**대안 D 단점**:
- BaseModel은 hard delete 가능 패턴 → Section만 다르면 패턴 혼선
- 비활성 Section을 어떻게 표시할지 화면 정책 추가

---

### 3b-6. order 필드 정합성

**옵션**: (A) Section.order + Item.order 두 레벨 / (B) Flat order (Section + Item 같은 공간) / (C) 자동 계산 (id 또는 created_at 기반)

**채택**: ✅ A — 두 레벨 정렬, ORDER BY (section.order, item.order)

**이유**: 트리 구조의 자연스러운 표현. 운영자가 Section 단위 + Item 단위 따로 정렬 변경 가능.

**A 장점**:
- 트리 구조 명시적
- Section/Item 독립 정렬
- UI에서 즉시 활용 (drag-drop)

**A 단점**:
- 같은 order 값 충돌 시 처리 정책 별도 필요 (created_at 보조 정렬 권장)
- 정렬 변경 시 다수 row UPDATE

**대안 B (flat) 장점**:
- 정렬 단순 (단일 ORDER BY)

**대안 B 단점**:
- Section 추가/이동 시 모든 Item order 재계산
- 트리 구조 표현 어색

**대안 C (자동 계산) 장점**:
- order 필드 불필요

**대안 C 단점**:
- 운영자가 순서 변경 불가
- created_at 기반은 운영 의도와 무관한 정렬

---

## §3c. Session + Revision + UNIQUE 변경

### 3c-1. Session 식별 키

**옵션**: (A) (worker, date) / (B) (worker, revision) / (C) (worker, date, revision) 복합

**채택**: ✅ C — (worker, date, revision) 복합 UNIQUE

**이유**: 같은 날 개정 발행 시 worker별로 개정 전후 세션 충돌 방지 + 일자 추적 보존. 양쪽 케이스 모두 안전.

**C 장점**:
- 같은 worker가 같은 날 개정 전/후 모두 작업 가능
- "5/8 작업분" 일자 기준 조회 가능
- "v2 개정 적용분" 개정 기준 조회 가능

**C 단점**:
- UNIQUE 인덱스 3컬럼 (성능 미세 영향, 학습 환경 무시)

**대안 A (worker, date) 장점**:
- 단순, 인덱스 작음

**대안 A 단점**:
- 같은 날 개정 발행 시 충돌 (worker가 v1 시작 → 발행 → v2로 마저 작업하면 같은 (worker, date) 키 충돌)

**대안 B (worker, revision) 장점**:
- 개정별 명확

**대안 B 단점**:
- 일자 추적 손실 ("5/8 작업" 조회 어려움)
- 같은 revision에서 며칠에 걸쳐 작업하면 의미 불명확

---

### 3c-2. 1일 1세션 정책

**옵션**: (A) 1일 1세션 + 차단 + 기존 세션 이어가기 / (B) 1일 1세션 + reset / (C) 무제한 다회

**채택**: ✅ A — "오늘 이미 체크함" 차단, 기존 세션 이어가기 (incomplete 상태면 재개)

**이유**: UNIQUE(worker, date, revision)가 자연스럽게 강제. 데이터 일관성 + 명확한 정책.

**A 장점**:
- 데이터 일관 (1일 = 1 세션 = 1 결과)
- 우발적 중복 방지
- 화면 명세 자연스러움

**A 단점**:
- 같은 날 두 번 작업 케이스 차단 (오전/오후 분리 작업 시)
- 단, "1일 = 24시간 = 1번"이 안전 점검 일반 정책

**대안 B (reset) 장점**:
- 자유로운 재시작

**대안 B 단점**:
- 기존 데이터 덮어씀 → 추적 손실
- 감사 요구 충족 어려움

**대안 C (무제한) 장점**:
- 가장 자유

**대안 C 단점**:
- UNIQUE 제약 깨짐 (3c-1 결정 무효화)
- "오늘의 결과"가 무엇인지 불명확
- 점검 통계 산출 어려움

---

### 3c-3. Revision JSON 스냅샷 필드

**옵션**: (A) Section 트리 + Item 메타 / (B) Item ID만 / (C) 전체 모델 직렬화

**채택**: ✅ A

```python
revision_data = {
    "sections": [
        {"id": 1, "name": "가스 점검", "order": 1, "items": [
            {"id": 10, "title": "CO 농도 확인", "is_required": True, "order": 1},
            {"id": 11, "title": "...", "is_required": False, "order": 2},
        ]},
        ...
    ]
}
```

**이유**: 발행 후 SafetyCheckItem 변경/삭제에도 과거 Revision 불변. 감사 요구 충족.

**A 장점**:
- 발행 시점 동결 (Item 변경 시에도 과거 데이터 보존)
- JSON 크기 적당 (수백 Item 기준 ~수십 KB)
- 화면 렌더에 즉시 사용

**A 단점**:
- JSON 비대화 가능성 (수천 Item 시 MB 단위, 학습 환경 무관)
- Item 모델 필드 추가 시 스냅샷 누락 위험

**대안 B (ID만) 장점**:
- JSON 작음

**대안 B 단점**:
- Item 변경/삭제 시 의미 손실 (예: "Item #10이 뭐였더라?")
- 과거 Revision 조회 시 매번 Item join

**대안 C (전체 직렬화) 장점**:
- 완벽 보존

**대안 C 단점**:
- JSON 매우 비대 (불필요 필드까지 포함)
- 모델 변경 시 스냅샷 schema 충돌 위험

---

### 3c-4. Revision 발행 트리거

**옵션**: (A) 관리자 수동 "발행" 버튼 / (B) 자동 (Item 변경 시) / (C) 일정 기반 (월 1회 등)

**채택**: ✅ A — 관리자 수동 "발행"

**이유**: 자동 발행은 사소한 변경에도 새 Revision 발행 → 노이즈. 일정 기반은 변경 없는데도 발행. 수동이 가장 통제 가능.

**A 장점**:
- 발행 시점 명확 (관리자 의도)
- 사소한 변경 시 발행 안 함
- SystemLog 기록 명확 (`CHECKLIST_REVISION_PUBLISHED` action)

**A 단점**:
- 운영자 수동 작업 필요
- 발행 깜빡할 시 변경된 Item이 active Revision에 반영 안 됨

**대안 B (자동) 장점**:
- 자동화, 발행 누락 0

**대안 B 단점**:
- 사소한 변경(오타 수정 등)에도 새 Revision
- Revision 누적 ↑ (DB 비대화)
- "어떤 변경이 트리거인가" 정의 모호 (제목? order? required?)

**대안 C (일정) 장점**:
- 정기 발행, 예측 가능

**대안 C 단점**:
- 변경 없는데도 발행 (의미 없는 Revision)
- 긴급 변경 시 다음 발행까지 대기

---

### 3c-5. ActionType (CHECKLIST_REVISION_PUBLISHED 등)

**채택**: ✅ Phase 1에서 이미 결정됨 (`보류결정사항_확정안_3건.md` §2.2-(5) 참고). 본 plan에서 재논의 없음.

---

### 3c-6. 기존 SafetyStatus 매핑

**옵션**: (A) default Session 1개 자동 생성 → 일괄 매핑 / (B) worker별 자동 분류 / (C) 데이터 삭제

**채택**: ✅ A — default Session 1개 + 일괄 매핑

**이유**: 데이터 손실 0, 마이그 단순.

**A 장점**:
- 무중단 마이그
- 기존 데이터 보존

**A 단점**:
- default Session에 모든 row 몰림 (의미상 부정확)
- 화면에서 "마이그 이전 데이터"로 표시 정책 필요

**대안 B (worker별 분류) 장점**:
- 의미 있는 매핑 (worker별 1세션)

**대안 B 단점**:
- 마이그 RunPython 복잡
- 같은 worker의 여러 날짜 row를 어떻게 묶을지 정책 추가

**대안 C (삭제) 장점**:
- DB 정리

**대안 C 단점**:
- 데이터 손실
- 학습 환경에서도 회귀 테스트용 데이터 손실은 비추천

---

### 3c-7. UNIQUE 다단계 마이그

**옵션**: (A) 5단계 분할 / (B) 단일 마이그 / (C) 3단계 압축

**채택**: ✅ A — 5단계

```
(a) session FK nullable 추가         # 0001_add_session_fk.py
(b) default session 매핑 백필        # 0002_backfill_session_data.py (RunPython)
(c) UNIQUE(worker, check_item) 제거   # 0003_drop_old_unique.py
(d) UNIQUE(session, check_item) 추가  # 0004_add_new_unique.py
(e) session NOT NULL 전환            # 0005_session_not_null.py
```

**이유**: 학습 가치(다단계 마이그 학습) + 안전(각 단계 검증·롤백 가능).

**A 장점**:
- 각 단계 독립 검증
- 실패 시 어느 단계인지 명확
- reverse 마이그 단계별 검증 가능

**A 단점**:
- 마이그 파일 5개 (관리 약간 부담)

**대안 B (단일) 장점**:
- 마이그 파일 1개로 단순

**대안 B 단점**:
- 실패 시 어디서 막혔는지 진단 어려움
- reverse 마이그 작성 어려움
- 학습 가치 손실

**대안 C (3단계 압축) 장점**:
- 단계 약간 축소

**대안 C 단점**:
- (c)+(d) UNIQUE 제거+추가를 한 마이그에 넣으면 PostgreSQL이 lock 잡는 시점 길어짐 (운영 환경 위험, 학습 환경 무관하지만 학습 가치 작음)

---

### 3c-8. mark_checked() 시그니처

**옵션**: (A) `mark_checked(session, note=None)` (session 필수) / (B) `mark_checked(note, session=None)` (자동 추론) / (C) `mark_checked(note)` (호출자 변경 0)

**채택**: ✅ A — session 필수 키워드 인자

**이유**: session 도입 후 명시적 전달이 안전. 자동 추론은 silent error 위험.

**A 장점**:
- 명시적, 타입 안전
- IDE/타입 체커가 누락 호출 검출
- 의도 명확

**A 단점**:
- 모든 호출자 갱신 필요 (학습 환경에서 호출 위치 적음, 부담 작음)

**대안 B (자동 추론) 장점**:
- 호출자 변경 0

**대안 B 단점**:
- 추론 실패(worker의 오늘 세션 없음 등) 시 silent error 또는 자동 생성
- 의도 불명확 (호출 코드만 봐서는 어떤 session인지 모름)

**대안 C (변경 0) 장점**:
- 가장 단순

**대안 C 단점**:
- session 정보 어디서 오는지 불명확
- 시그널/middleware로 주입하면 디버깅 어려움

---

### 3c-9. 운영 무중단 vs 점검창

**채택**: ✅ N/A — 학습 환경이라 점검창 무관, 즉시 적용

**이유**: 운영 트래픽 없음. UNIQUE 변경 lock 자체는 발생하지만 동시 INSERT 없으므로 무관.

**대안 (운영 환경 가정 시 권장)**: (c)+(d) UNIQUE 제거·추가 단계는 점검창 또는 PostgreSQL `CONCURRENTLY` 옵션 활용 필요. 본 환경 무관.

---

## §3d. Event 확장

### 3d-1. AlertPolicy FK on_delete

**옵션**: (A) SET_NULL / (B) CASCADE / (C) PROTECT

**채택**: ✅ A — SET_NULL

**이유**: Soft Delete 컨벤션 일관 (AlertPolicy는 deactivate 패턴). 정책 삭제 시에도 Event 이력 보존.

**A 장점**:
- Event 이력 보존 (정책 변경/삭제와 무관)
- Soft Delete 컨벤션 일관
- 감사 요구 충족 (과거 Event는 어떤 정책으로 트리거됐는지 NULL이어도 자체 정보 보존)

**A 단점**:
- AlertPolicy 비활성 후 NULL 처리 코드 필요
- 정책-Event 정합성 검증 약화

**대안 B (CASCADE) 장점**:
- 정합성 강제 (정책 삭제 = 이벤트 자동 정리)

**대안 B 단점**:
- 정책 삭제 시 Event 다수 일괄 삭제 위험
- 감사 이력 손실
- AlertPolicy는 Soft Delete인데 Event는 Hard Delete? → 패턴 불일치

**대안 C (PROTECT) 장점**:
- 안전

**대안 C 단점**:
- 정책 삭제 어려움 (Event 다수 정리해야 함)
- AlertPolicy Soft Delete 컨벤션과 충돌 (PROTECT는 hard delete 가정)

---

### 3d-2. description 의미

**옵션**: (A) summary=한 줄(기존), description=상세(신규) / (B) summary 확장 (max_length 증가) / (C) description으로 통합 (summary 제거)

**채택**: ✅ A — 두 필드 공존, docstring 명시

```python
summary     = CharField(max_length=200, ...)  # 기존: 한 줄 요약
description = TextField(blank=True, default="")  # 신규: 상세 본문
```

**이유**: 기존 데이터 호환 + 화면 요구(상세 본문) 충족.

**A 장점**:
- 기존 데이터 영향 0
- 화면 컬럼 분리 가능 (목록=summary, 상세=description)
- 의미 분리 명확

**A 단점**:
- 두 필드 의미 차이 docstring 의존 (개발자 학습 비용)
- summary와 description 중복 입력 가능 (정책으로 방지)

**대안 B (summary 확장) 장점**:
- 필드 1개

**대안 B 단점**:
- "한 줄 요약"의 의미 손실
- 목록 화면에서 길이 제한 코드 추가

**대안 C (통합) 장점**:
- 필드 1개, 단순

**대안 C 단점**:
- 기존 summary 데이터 description으로 마이그 부담
- 기존 화면(목록 컬럼) 영향

---

### 3d-3. status_note 위치

**옵션**: (A) Event에 두기 / (B) EventLog에 두기 / (C) 두 곳 모두 (이력 + 현재)

**채택**: ✅ A — Event

**이유**: EventLog는 이미 status 전환 이력 기록 중. status_note는 "현재 상태에 대한 처리자 메모"라 Event 본체에 두는 게 자연스러움.

**A 장점**:
- 현재 상태 메모 조회 단순 (Event 직접 조회)
- 화면 상세 팝업에서 즉시 표시

**A 단점**:
- 상태 전환 시 status_note 갱신해야 함 (이전 메모는 EventLog에 별도 보관 필요할 수 있음)
- 메모 이력 보존하려면 추가 코드

**대안 B (EventLog) 장점**:
- 상태 전환 이력과 함께 메모 보존
- 감사 요구 충족

**대안 B 단점**:
- 현재 상태 메모 조회가 EventLog의 최신 row 조회 필요 (join 1회)
- 화면 응답 약간 복잡

**대안 C (둘 다) 장점**:
- 현재 + 이력 모두 보존

**대안 C 단점**:
- 두 곳 동기화 부담
- 데이터 중복

---

### 3d-4. 기존 Event row 처리

**채택**: ✅ description: nullable + default="", status_note: nullable + default=""

**이유**: 기존 데이터 영향 0. 마이그 시 자동 채움.

**장점**: 무중단, 데이터 손실 0
**단점**: 기존 row의 description/status_note 비어있음 (자연스러움, 운영자가 필요 시 입력)

---

### 3d-5. AlertPolicy 자동 매칭 시점

**옵션**: (A) Phase 4-e policy_matcher가 채움 / (B) Phase 3에 policy_matcher도 포함 / (C) 본 PR에서 모든 기존 Event에 policy 일괄 매핑

**채택**: ✅ A — Phase 4-e에서 채움

**이유**: Phase 3은 모델 추가 단계, Phase 4-e는 서비스 로직 단계. 단계 분리 명확.

**A 장점**:
- 단계별 분리 (모델 vs 서비스)
- Phase 3 PR 범위 작음
- AlertPolicy는 Phase 2에서 도입되므로 Phase 3 시점에 매칭 가능

**A 단점**:
- Phase 3 ~ Phase 4 사이 NULL 일시 누적
- 두 PR 머지 후에야 정상 동작

**대안 B (Phase 3에 포함) 장점**:
- 1 PR로 완성

**대안 B 단점**:
- PR 범위 비대화
- policy_matcher 로직은 Phase 4 전체와 묶여야 자연스러움 (template_renderer 등)

**대안 C (일괄 매핑) 장점**:
- 마이그 후 즉시 정상 동작

**대안 C 단점**:
- 마이그 RunPython 비대 (모든 Event 순회)
- AlertPolicy 매칭 로직이 마이그에 박힘 → 향후 변경 시 마이그 수정?

---

## §3e. Notification 확장

### 3e-1. event FK CASCADE → SET_NULL

**옵션**: (A) SET_NULL + nullable / (B) CASCADE 유지 + 더미 Event / (C) 두 모델 분리 (EventNotification + Standalone)

**채택**: ✅ A — SET_NULL + nullable

**이유**: 비-Event 알림(점검 일정 사전 알림, 배치 실패 알림 등) 모델링 자연스러움. Soft Delete 컨벤션 일관.

**A 장점**:
- 비-Event 알림 자연스럽게 모델링
- Event 삭제 시에도 알림 이력 보존
- AlertPolicy 트리거 알림은 `notification.policy` FK로 추적 가능

**A 단점**:
- v3 의도(Event 삭제 시 알림 자동 정리) 상실
- Event 삭제 후 NULL 알림이 어느 출처인지 불명확 (단, policy/source 정보로 추적 가능)

**대안 B (CASCADE + 더미 Event) 장점**:
- 모든 알림에 Event 강제 → 정합성 ↑

**대안 B 단점**:
- 점검·배치 알림용 더미 Event 다수 생성 (Event 의미 희석)
- Event 테이블 비대화

**대안 C (두 모델 분리) 장점**:
- 도메인 책임 명확

**대안 C 단점**:
- 모델 2종 운영 (코드 중복, 화면 분기)
- 발송 로직 두 곳에 작성

---

### 3e-2. event nullable 허용 시 clean()

**옵션**: (A) event/policy 중 하나는 필수 / (B) 무제약 / (C) 둘 다 nullable + 출처 필드(source) 강제

**채택**: ✅ A — clean()에서 event 또는 policy 중 하나 필수

```python
def clean(self):
    if not self.event and not self.policy:
        raise ValidationError("Notification은 event 또는 policy 중 하나는 필수")
```

**이유**: 출처 없는 알림 차단. 의미 있는 알림만 허용.

**A 장점**:
- 무의미한 알림 방지
- 출처 추적 보장 (event 또는 policy 중 하나)

**A 단점**:
- clean() 추가 코드
- bulk_create 시 clean() 호출 안 되는 점 주의

**대안 B (무제약) 장점**:
- 단순

**대안 B 단점**:
- 출처 없는 알림 가능 ("어디서 온 거지?")
- 디버깅 어려움

**대안 C (source 강제) 장점**:
- 모든 알림에 출처 명시

**대안 C 단점**:
- source 필드 enum 정의 추가
- event/policy와 별도 관리 → 중복

---

### 3e-3. retry_count

**채택**: ✅ default 0

**이유**: 발송 시도 0회가 자연스러운 초기값. 운영 후 시도 시 +1.

**장점**: 명시적, 필수 필드
**단점**: 없음
**대안**: nullable — 0과 NULL 의미 차이 모호 → 비추천

---

### 3e-4. last_attempted_at

**채택**: ✅ nullable DateTimeField + docstring으로 created_at과 의미 분리

```python
created_at         = DateTimeField(auto_now_add=True)  # Notification 생성 시점
last_attempted_at  = DateTimeField(null=True, blank=True)  # 최근 발송 시도 시점
```

**이유**: 발송 시도 전에는 NULL, 시도 후 갱신.

**장점**: 의미 명확, retry 로직 활용 가능
**단점**: NULL 처리 추가
**대안 (created_at 재사용)**: 장점 — 필드 1개. 단점 — 의미 충돌 (생성 ≠ 시도)

---

### 3e-5. DELAYED 동적 판정

**옵션**: (A) 동적 판정 (PENDING + timeout) / (B) DELAYED 상태 추가 + 자동 전환 / (C) 미도입 (DELIVERED 4종 유지)

**채택**: ✅ A — 동적 판정, 임계 5분

```python
# 화면 직렬화에서
def get_status_display(self, obj):
    if obj.delivery_status == "PENDING" and obj.last_attempted_at:
        if (now - obj.last_attempted_at) > timedelta(minutes=5):
            return "지연"
    return obj.get_delivery_status_display()
```

**이유**: enum 비대화 방지 + 자동 전환 코드(Celery 등) 불필요. 임계 조정 자유.

**A 장점**:
- enum 단순 유지 (4종)
- 임계 조정이 코드 1줄
- 자동 전환 워커 불필요

**A 단점**:
- 화면 로직 약간 복잡 (직렬화에서 분기)
- DB 쿼리로 "지연 알림" 필터링 시 raw SQL 또는 annotation 필요

**대안 B (DELAYED 상태 + 자동 전환) 장점**:
- DB 쿼리 단순 (`status="DELAYED"` 필터)
- 명시적

**대안 B 단점**:
- enum 5종 비대화
- 자동 전환 워커(Celery beat) 필요
- DELIVERED와 의미 충돌 가능 (DELIVERED 후에도 DELAYED 표시?)

**대안 C (미도입) 장점**:
- 가장 단순

**대안 C 단점**:
- 화면 명세 "지연" 라벨 미충족
- 운영자가 timeout 케이스 식별 불가

---

### 3e-6. AlertPolicy FK on_delete (Notification)

**채택**: ✅ SET_NULL (3d-1과 동일 패턴)

**이유**: 정책 삭제 시 알림 이력 보존.

**장점/단점**: 3d-1과 동일

---

### 3e-7. Soft Delete (Notification)

**옵션**: (A) Hard Delete (Soft Delete 미도입) / (B) Soft Delete (deactivated_at) / (C) 보관 기간 설정 (created_at 기준 N일 후 자동 삭제)

**채택**: ✅ A — Hard Delete

**이유**: Notification은 발송 이력. AlertPolicy(사용자 자산)와 다름. 보존 가치 < 인덱스 비용.

**A 장점**:
- 모델 단순 (deactivated_at 필드 불필요)
- DB 인덱스 비대화 방지 (Notification은 누적량 큼)
- 발송 후 일정 기간 후 정리 가능

**A 단점**:
- 실수 삭제 시 복구 불가 (학습 환경에서 OK)
- 감사 요구 시 별도 보존 정책 필요

**대안 B (Soft Delete) 장점**:
- 복구 가능
- 감사 이력 보존

**대안 B 단점**:
- Notification 누적량 큼 → 인덱스/저장 부담
- 화면에서 active만 노출 코드 추가
- 보관 정책(N일 후 hard delete) 별도 필요

**대안 C (보관 기간) 장점**:
- 자동 정리

**대안 C 단점**:
- 보관 기간 정책 결정 부담
- DataRetentionPolicy 모델 의존 (이성현 Plan에서 제안된 모델)
- 본 단계에서는 과대설계

---

## 횡단 결정

### A. PR 분할 vs 단일 PR

**옵션**: (A) 3 PR (3a 분리 / 3b+3d+3e / 3c) / (B) 단일 PR (5개 sub-step 합침) / (C) 5 PR (sub-step별)

**채택**: ✅ A — 3 PR

| PR | 포함 | 위험도 | 사유 |
|---|---|---|---|
| PR1 | 3a (WorkerPosition.received_node) | 중 | fastapi schema 동시 변경 필요, 분리 |
| PR2 | 3b + 3d + 3e (Section + Event 확장 + Notification 확장) | 저 | 저위험·독립적 변경, 함께 진입 |
| PR3 | 3c (Session + Revision + UNIQUE 5단계) | 고 | 다단계 마이그, 별도 PR로 격리 |

**A 장점**:
- 위험도별 격리 (실패 영향 한정)
- 검증 명확 (각 PR 단위)
- 학습 가치 (다양한 마이그 패턴)

**A 단점**:
- PR 3개 관리
- 의존성 명시 필요

**대안 B (단일) 장점**:
- 사이클 1번

**대안 B 단점**:
- 위험 누적
- 롤백 범위 큼
- 리뷰 어려움

**대안 C (5 PR) 장점**:
- 가장 작은 단위

**대안 C 단점**:
- 의존성 관리 부담 (3a → 3c 순서 등)
- PR 5개 = CI 5번
- 학습 환경에서 오버엔지니어링

---

### B. DB 백업 정책

**채택**: ✅ 마이그 전 `pg_dump` 또는 SQLite 파일 복사 1회

```bash
# PostgreSQL
pg_dump -U user diconai > backup_$(date +%Y%m%d_%H%M%S).sql

# SQLite
cp db.sqlite3 db.sqlite3.backup_$(date +%Y%m%d)
```

**이유**: 학습 환경이라도 마이그 실패 시 복구 위해 1회 덤프 권장.

**장점**: 안전망, 학습 가치
**단점**: 디스크 약간 차지 (학습 환경 무시)

---

### C. 롤백 전략

**채택**: ✅ RunPython 마이그는 reverse 코드 필수 + 본인 로컬에서 reverse 테스트 통과 후 PR 머지

```python
def forward(apps, schema_editor):
    # 마이그 로직
    ...

def reverse(apps, schema_editor):
    # 역방향 로직 (필수)
    ...

class Migration(migrations.Migration):
    operations = [migrations.RunPython(forward, reverse)]
```

**이유**: 학습 환경이라 rollback 실험 자체가 학습 가치.

**장점**: 안전, 학습 가치, 운영 환경 패턴 학습
**단점**: reverse 코드 작성 부담
**대안 (reverse 생략)**: 장점 — 작성 부담 0. 단점 — 학습 가치 손실, `migrate appname zero` 등 동작 검증 불가

---

### D. 운영 무중단 vs 점검창

**채택**: ✅ N/A (학습 환경)

---

### E. 단계별 검증 시점

**채택**: ✅ 본인이 PR 전 자체 검증

```
1. python manage.py makemigrations --dry-run    # 마이그 누락 확인
2. python manage.py makemigrations
3. python manage.py migrate                      # 적용
4. fixture 시드 검증                              # default Section/Session 자동 생성 확인
5. python manage.py test apps.safety.tests       # 단위 테스트
6. 회귀 테스트 (기존 알람 흐름)                    # 알람 → Event → Notification 흐름
7. python manage.py migrate apps.safety zero     # reverse 검증
8. python manage.py migrate apps.safety          # 다시 적용
```

**이유**: 학습 환경에서도 검증 절차 표준화.

---

### F. 데이터 마이그 dry-run 환경

**채택**: ✅ 본인 로컬 DB 복제로 dry-run

```bash
# PostgreSQL
createdb diconai_dryrun
pg_restore -d diconai_dryrun backup.sql
DATABASE_URL=postgres://.../diconai_dryrun python manage.py migrate

# SQLite
cp db.sqlite3 db.sqlite3.dryrun
DATABASE_URL=sqlite:///db.sqlite3.dryrun python manage.py migrate
```

**이유**: 학습 환경이라 별도 인프라 불필요.

---

### G. 외부 트랙 (펌웨어 / 디자인)

**채택**: ✅ N/A — 팀 프로젝트, 외부 의존 없음. fastapi schema도 본인이 갱신 (3a-1).

---

## PR 분할 최종안 (실행 순서)

### PR1 — 3a: WorkerPosition.received_node (먼저)

```
1. (DRF) WorkerPosition.received_node FK nullable 추가 마이그
2. (fastapi) position_router schema에 node_id 추가
3. (DRF) WorkerPositionReceiveView serializer에 node_id 처리 + PositionNode lookup
4. 화면 직렬화에서 received_node NULL 시 "수신 노드 미상" 라벨
5. 단위 테스트 + reverse 검증
```

**의존**: 없음. 단독 진입 가능.

---

### PR2 — 3b + 3d + 3e: Section + Event 확장 + Notification 확장 (저위험 묶음)

```
1. SafetyCheckSection 모델 신규 (3b)
2. SafetyCheckItem.section FK nullable 추가 (3b, 1단계)
3. data migration: facility별 "기본" Section 자동 생성 + 기존 Item 백필 (3b, 2단계)
4. SafetyCheckItem.section NOT NULL 전환 (3b, 3단계)
5. Event 확장: policy/description/status_note (3d)
6. Notification 확장: policy/retry_count/last_attempted_at + event SET_NULL (3e)
7. clean() 갱신: event/policy 둘 중 하나 필수 (3e-2)
8. 단위 테스트 + reverse 검증
```

**의존**: AlertPolicy 모델이 Phase 2에서 들어와 있어야 함 (이미 진입 가정).

---

### PR3 — 3c: Session + Revision + UNIQUE 5단계 (별도, 가장 위험)

```
1. SafetyChecklistRevision 모델 신규
2. SafetyCheckSession 모델 신규
3. SafetyStatus.session FK nullable 추가 (3c, 1단계)
4. data migration: default Session 자동 생성 + 기존 SafetyStatus 백필 (3c, 2단계)
5. UNIQUE(worker, check_item) 제거 (3c, 3단계)
6. UNIQUE(session, check_item) 추가 (3c, 4단계)
7. SafetyStatus.session NOT NULL 전환 (3c, 5단계)
8. mark_checked() 시그니처 갱신 (3c-8)
9. SafetyCheckSession.unique_together = (worker, date, revision) (3c-1)
10. 단위 테스트 + reverse 검증 (5단계 모두)
```

**의존**: PR2 머지 후 진입 (SafetyCheckItem.section이 활성 상태).

---

## 다음 단계

1. **본 결정문 검토** → 자체 review (의문점 메모)
2. **PR1 (3a) 작성** → 본인 로컬 검증 → 머지
3. **PR2 (3b+3d+3e) 작성** → 본인 로컬 검증 → 머지
4. **PR3 (3c) 작성** → 5단계 마이그 + reverse 검증 → 머지
5. **Phase 4 진입** (서비스 로직: policy_matcher, template_renderer)

각 PR 머지 후 본 결정문에 ✅ 마킹. 새로운 결정 필요 시 본 문서 추가.

---

**작성일**: 2026-05-08
**작성자**: 최재용 (단독 결정)
**근거**: 이성현 Plan / 최재용 Plan / 정휘훈 Plan + 통합 plan §3 의존 그래프
