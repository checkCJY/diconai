# Phase 3 PR1 — WorkerPosition.received_node 보고서

> 작업일: 2026-05-08
> 브랜치: `feature/0508_refactory`
> 부모 plan: [.claude/plans/swirling-mixing-torvalds.md](../../.claude/plans/swirling-mixing-torvalds.md)
> 결정문: [phase_3_plan.md](phase_3_plan.md) §3a
> 직전 Phase: [phase_2_report.md](phase_2_report.md)

---

## 1. 작업 목적

부모 plan §3 의존 그래프 [Phase 3 — PR1] 단독 진입. 작업자 위치 데이터에 **수신 노드 정보** 추적 추가:

- **무엇:** WorkerPosition에 `received_node` FK 추가, 어떤 PositionNode가 본 좌표를 측정·전송했는지 기록
- **왜:** 운영 데이터 화면(피그마 명세 "장비명 NODE-001 기준 조회") 충족 + 사고 조사·감사 시 수신 노드 추적 가능
- **학습 환경 전제:** 외부 펌웨어 의존 0. 본인이 fastapi schema + DRF + 더미 스크립트 양측 동시 갱신 (결정문 3a-1).

---

## 2. 검증 결과

| 항목 | 명령 | 결과 |
|---|---|---|
| Django 시스템 검사 | `python manage.py check` | ✅ 통과 |
| 마이그레이션 일관성 | `python manage.py makemigrations --dry-run --check` | ✅ "No changes detected" |
| 마이그레이션 적용 | `python manage.py migrate` | ✅ `positioning.0002_workerposition_received_node` |
| **마이그레이션 reverse 검증** | `migrate positioning 0001` → `migrate positioning` | ✅ Unapply + Re-apply 모두 OK |
| CI 정합성 테스트 회귀 | `python manage.py test apps.reference.tests... apps.core.tests... apps.alerts.tests.test_alarm_type_consistency` | ✅ 4 tests OK |
| ruff lint + format | `pre-commit run --files <변경파일>` | ✅ Passed |

### 변경된 데이터 흐름

```
[더미 스크립트]                    [FastAPI]                   [DRF]
position_dummy.py  ──HTTP POST──>  /api/positioning/receive ──HTTP POST──> /api/positioning/receive/
  + node_id="NODE-001"               (WorkerPositionSchema           (WorkerPositionReceiveSerializer
                                      .node_id: str|None)              .node_id: CharField optional)
                                     │                                   │
                                     ▼                                   ▼
                                  save_positions_to_drf            handle_position_receive(node_id=...)
                                  payload: node_id 포함              ├─ PositionNode.objects.filter(device_id=...).first()
                                                                    └─ WorkerPosition.objects.create(received_node=...)
```

NULL 허용 정책: `node_id=None` 또는 lookup 실패 시 `received_node=None`으로 저장 (데이터 손실 회피).

---

## 3. 변경 파일 — 신규 (1개)

| 파일 | 역할 |
|---|---|
| [drf-server/apps/positioning/migrations/0002_workerposition_received_node.py](../../../drf-server/apps/positioning/migrations/0002_workerposition_received_node.py) | WorkerPosition에 `received_node` FK 컬럼 추가 (nullable, SET_NULL) |

---

## 4. 변경 파일 — 기존 수정 (7개)

### 4-1. DRF 측 (4개)

| 파일 | 변경 내용 |
|---|---|
| [drf-server/apps/positioning/models/worker_position.py](../../../drf-server/apps/positioning/models/worker_position.py) | `received_node = ForeignKey("facilities.PositionNode", SET_NULL, null=True, blank=True, related_name="received_positions")` 추가 |
| [drf-server/apps/positioning/serializers/serializers.py](../../../drf-server/apps/positioning/serializers/serializers.py) | `WorkerPositionReceiveSerializer.node_id` (CharField, required=False, allow_null/blank) 추가 |
| [drf-server/apps/positioning/services/position_service.py](../../../drf-server/apps/positioning/services/position_service.py) | `handle_position_receive()` 시그니처에 `node_id: str \| None = None` 추가. PositionNode lookup (`device_id=node_id, is_active=True`) 후 `WorkerPosition.objects.create(received_node=...)` 전달 |
| [drf-server/apps/positioning/views/position_views.py](../../../drf-server/apps/positioning/views/position_views.py) | `handle_position_receive()` 호출에 `node_id=item.get("node_id") or None` 전달 |

### 4-2. FastAPI 측 (2개)

| 파일 | 변경 내용 |
|---|---|
| [fastapi-server/positioning/schemas/position.py](../../../fastapi-server/positioning/schemas/position.py) | `WorkerPositionSchema.node_id: str \| None = None` 추가. docstring에 Phase 3-a 명시 |
| [fastapi-server/positioning/services/position_service.py](../../../fastapi-server/positioning/services/position_service.py) | `save_positions_to_drf()` payload에 `"node_id": p.node_id` 포함 |

### 4-3. 더미 스크립트 (1개)

| 파일 | 변경 내용 |
|---|---|
| [fastapi-server/dummies/position_dummy.py](../../../fastapi-server/dummies/position_dummy.py) | `DUMMY_WORKERS` 4명 모두 `node_id="NODE-001"` 추가. `generate_positions()` payload에 `"node_id": w.get("node_id")` 포함. 학습 환경에서 모의 데이터 흐름 검증용 |

---

## 5. 사용자 결정 사항 (결정문 §3a 반영)

| 항목 | 결정 | 본 PR 반영 |
|---|---|---|
| 3a-1. 책임 | 본인이 fastapi + DRF 양측 동시 갱신 | ✅ DRF 4개 + FastAPI 2개 + 더미 1개 단일 PR |
| 3a-2. node_id 형식 | `PositionNode.device_id` 그대로 (예: "NODE-001") | ✅ CharField + lookup `device_id=node_id` |
| 3a-3. schema 변경 시점 | DRF nullable 먼저 → fastapi schema 갱신 → 데이터 흐름 | ✅ FK nullable 정책 + Optional pydantic 필드 |
| 3a-4. NULL row 처리 | 화면 "수신 노드 미상" 라벨 (운영 데이터 화면 구현 시) | 모델/마이그/serializer 단계 완료. 화면 라벨은 운영 데이터 화면 구현 시 (Phase 4 외 별도 트랙) |
| 3a-5. trial period | 학습 환경이라 즉시 진행 | ✅ |

§4-6 진행 중 명확화 항목 ⓐ (더미 스크립트 갱신 PR1 포함) — ✅ 반영.

---

## 6. 발견 사항 / 부수 작업

### 6-1. PositionNode lookup 정책

`PositionNode.objects.filter(device_id=node_id, is_active=True).first()` — 비활성 노드는 매칭 안 함. 미존재/비활성 시 `received_node=None`으로 저장 (silent fallback).

→ 화면에서 NULL 케이스 표시 정책 + 운영 시 비활성 노드로부터 데이터 들어오면 로그 출력 권장 (현재 silent → Phase 4-a 운영 데이터 화면 구현 시 보강).

### 6-2. WorkerPositionSchema 비-WS 호환

`WorkerPositionSchema`는 [fastapi-server/positioning/routers/position_router.py](../../../fastapi-server/positioning/routers/position_router.py)의 `receive_positions()` 입력 + `ws_state.worker_positions[]` 캐시에 모두 사용됨. WS 전송 시 `node_id` 포함되지만 브라우저 측 처리 코드 변경 없음 (모르는 필드 무시).

### 6-3. 마이그레이션 reverse 검증

5단계 마이그(PR3)를 위한 reverse 패턴 학습 차원. 본 PR1은 단순 FK 추가라 reverse도 자동 (Django ORM이 컬럼 drop). 단계별 검증 흐름은 다음과 같음:

```bash
.venv/bin/python manage.py migrate positioning 0001  # reverse
.venv/bin/python manage.py migrate positioning       # re-apply
```

PR3에서는 RunPython 마이그가 들어가므로 reverse 코드 명시 필수.

---

## 7. 외부 / Phase 3 후속

- 본 PR1은 단독 진입 가능 (의존 없음). 머지 후 PR2 (3b + 3d + 3e) 진입.
- 화면 "수신 노드 미상" 라벨은 운영 데이터 화면 구현(Phase 4 외 별도 트랙) 시.
- 결정문 §4-6 ⓑ~ⓔ는 PR2/PR3 작성 시 결정.

---

## 8. 다음 단계

PR2 — Section + Event/Notification 확장 (저위험 묶음, 결정문 §3b + §3d + §3e)
- SafetyCheckSection 신설 + facility별 "기본" 자동 + Item 일괄 백필
- Event 확장 (policy FK SET_NULL + description + status_note)
- Notification 확장 (policy FK + retry_count + last_attempted_at + event SET_NULL)
- DELAYED 5분 timeout settings 상수화
