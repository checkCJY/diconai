# devleop 머지 충돌 트러블슈팅 (2026-05-20)

작성일: 2026-05-20
브랜치: `feature/0519_alarm_business_logic`
대상 머지 commit: `c1eed97 Merge branch 'devleop' into feature/0519_alarm_business_logic`
상대 브랜치 tip: `7d19a88 feat(monitoring): 전력 AI 5축 모니터링 메트릭 추가 및 대시보드 분리 (#69)`

대상 독자: 팀원 — 같은 패턴 재발 방지 + 학습 공유.

---

## §1. 요약 (3줄)

- **무슨 일**: `devleop` 머지 시 `power_service.py` 충돌 영역에 우리 브랜치 architecture (T4 `decide_alarm` 매트릭스) 와 devleop architecture (`should_fire` + 단일 helper call) 가 동시에 박혔다. 자동 머지가 절반씩 섞어 syntax error 발생.
- **왜**: 두 브랜치가 같은 함수 (`process_anomaly_inference`) 의 같은 영역을 **서로 incompatible 한 architecture 로 동시에 변경**. git 의 3-way merge 가 의도까지 판단 못 함.
- **어떻게**: `git merge --abort` 후 재시도 → 충돌 영역 수작업 해소 (우리 브랜치 architecture base + devleop 메트릭 카운터 6종 흡수).

---

## §2. 무엇이 일어났는가 — 구체적

### 2.1 분기 시점

```
main
  │
  └─ devleop ── (메트릭 6종 + Grafana 분리) ── 7d19a88
       │
       └─ feature/0519_alarm_business_logic ── (T1+T6+T3 + T4 decide_alarm) ── a7ecf84
```

두 브랜치가 같은 `power_service.py:process_anomaly_inference` 의 **rate limit + 알람 forward 영역** 을 동시에 진화.

### 2.2 같은 영역의 두 가지 architecture

| 항목 | 우리 브랜치 (T4) | devleop |
|---|---|---|
| 발화 분기 | `if combined in _FIRE_LEVELS:` + 그 안에서 직접 처리 | `should_fire = combined in _FIRE_LEVELS` 변수 도입 |
| Rate limit 통과 못 함 | `forward_inference_e2e(ml_payload, None)` + `continue` | `should_fire = False` 만 마킹 (continue 없음) |
| 발화 처리 | `mark_ai_state(FIRED)` + `mark_ai_recent` + `decide_alarm` 매트릭스 분기 → push_alarm + helper call | 단일 helper call `forward_inference_e2e(ml_payload, alarm_payload, push_payload, should_fire=should_fire)` |
| 정상 처리 | `mark_ai_state(INFERRED_NORMAL)` + `decide_alarm` | (분기 없음) |

두 architecture 가 **공존 불가**. 우리 브랜치는 `decide_alarm` 매트릭스 (T4 작업) 가 정적 임계치와 AI 결과를 통합 결정하는 진화한 구조. devleop 은 helper 안에서 should_fire 플래그로 분기하는 단순 구조.

### 2.3 자동 머지 결과 (깨짐)

git 의 3-way merge 가 두 architecture 를 모두 보존하려다 다음과 같이 박혔다:

```python
# Line 555-565 — devleop 의 5축 카운터 (호환됨, 잘 박힘)
if combined in _FIRE_LEVELS:
    if prediction == "anomaly":
        POWER_AI_AXIS_FIRED_TOTAL.labels("if").inc()
    ...

# Line 567-580 — devleop 의 should_fire + rate limit + 우리 브랜치의 continue (혼합 ❌)
should_fire = combined in _FIRE_LEVELS
if should_fire:
    ...
    if now_ts - last_ts < RATE_LIMIT_SEC:
        ...
        asyncio.create_task(forward_inference_e2e(ml_payload, None))
        continue                                              # ← 우리 브랜치

# Line 581-587 — 우리 브랜치 mark_ai_state + devleop POWER_AI_RATE_LIMITED 가
# 함수 인자 자리에 잘못 박힘 → SYNTAX ERROR
_last_fired_at[sensor_identifier] = now_ts
await mark_ai_state(
    device_id, channel, data_type, AIInferenceState.FIRED     # ← 인자
    # 정휘훈 작업 — rate limit 억제 카운터.                      # ← 주석이 인자 사이에
    POWER_AI_RATE_LIMITED_TOTAL.inc()                         # ← ❌ 인자 자리에 statement
    should_fire = False                                       # ← ❌ 인자 자리에 assignment
else:                                                         # ← ❌ 동떨어진 else

# Line 605-677 — devleop 의 단일 helper call 통째로 75줄 박힘 (중복 ❌)
# (우리 브랜치는 line 689 부터 decide_alarm 매트릭스로 같은 일 처리)

# Line 678-687 — 우리 브랜치 mark_ai_recent + INFERRED_NORMAL 분기
# Line 689-766 — 우리 브랜치 decide_alarm + push_alarm + helper call
```

→ Python interpreter 가 line 587 에서 `Expected ',', found name` 으로 거부. ruff 가 동일 에러 출력.

### 2.4 추가로 발견된 사이드 이슈

`metrics.py` 충돌 영역에서 **닫는 괄호 누락**. 우리 브랜치의 `AI_BROADCAST_LATENCY = Histogram(...)` 와 devleop 의 `POWER_AI_ALARM_FIRED_TOTAL = Counter(...)` 가 같은 위치에 추가되면서 둘 다 닫는 `)` 가 충돌 마커 안팎으로 흩어져 한쪽이 열린 채로 남음 — IDE diagnostics 가 `"("가 닫혀 있지 않음` 으로 잡아 발견.

---

## §3. 왜 이런 일이 생겼는가

### 3.1 직접 원인

같은 함수의 **동일 영역에서 incompatible 한 architecture 변경이 병렬 진행**.

- T4 (decide_alarm 매트릭스 도입) 는 우리 브랜치에서 약 2026-05-19~20 진행
- devleop 의 PR #69 (메트릭 + 단일 helper call) 는 같은 영역에 should_fire 플래그를 추가
- 두 변경 모두 `if combined in _FIRE_LEVELS:` 직후 영역에 다른 의도로 새 코드 삽입

### 3.2 근본 원인

| 요인 | 설명 |
|---|---|
| 분기 후 sync 없음 | feature 브랜치가 분기 후 devleop 와 한 번도 sync 안 한 상태에서 양쪽이 같은 영역을 진화 |
| architecture 결정 동기 부재 | T4 (decide_alarm) 와 devleop (should_fire) 가 같은 문제 (발화 분기) 를 다른 방식으로 해결. 사전 컨벤션·plan 공유 부재 |
| 자동 머지 한계 | git 의 3-way merge 는 line-level 충돌만 감지. **architecture-level 호환성** 은 사람이 봐야 함 |

이는 T3 트러블슈팅 ([2026_05_20_alarm_t3_troubleshooting.md](../../drf-server/docs/refactoring/2026_05_20_alarm_t3_troubleshooting.md)) 의 Pydantic `extra=ignore` silent drop 패턴과 정신적으로 같음 — **양 끝점은 정상인데 중간에서 데이터·의도가 사라짐**.

---

## §4. 어떻게 해소했는가

### 4.1 절차

1. `git merge --abort` — 깨진 충돌 상태 폐기, 깨끗한 워킹트리 복구
2. `git merge devleop --no-commit` 재시도 — 충돌 마커가 깨끗한 상태로 재생성됨
3. 충돌 영역별 수작업 해소:
   - `metrics.py` — 두 정의 모두 보존, 닫는 괄호 명시화
   - `power_service.py` import — 우리 브랜치 base + devleop 의 메트릭 6종 import 흡수, 중복 제거
   - `power_service.py` 5축 카운터 영역 — devleop 의 5축 fired counter 6개만 흡수, should_fire 변수는 버림
   - `power_service.py` rate limit 영역 — 우리 브랜치 architecture (continue + decide_alarm) 유지 + RATE_LIMITED·ALARM_FIRED 카운터 적절한 위치에 박기, devleop 의 단일 helper call 75줄 통째 삭제
4. ruff 통과 확인 → `git add` → `git commit` (pre-commit hook 통과)

### 4.2 결과

| 영역 | 보존 | 추가 |
|---|---|---|
| `decide_alarm` 매트릭스 (T4) | ✅ 우리 브랜치 그대로 | — |
| AI mute + mark_ai_recent (T4) | ✅ 우리 브랜치 그대로 | — |
| 정휘훈 메트릭 6종 | — | ✅ 6/6 모두 적절한 위치 |
| Grafana 대시보드 4종 | — | ✅ 그대로 |
| `AI_BROADCAST_LATENCY` (T4) | ✅ 우리 브랜치 그대로 | — |

### 4.3 검증 (이 문서 작성 시점)

| 항목 | 상태 |
|---|---|
| 충돌 마커 잔재 | ✅ 없음 |
| ruff syntax | ✅ 통과 |
| ruff-format | ✅ 통과 |
| pre-commit hook | ✅ 통과 |
| Docker 컨테이너 pytest | ⏳ 다음 단계 |
| 브라우저 E2E | ⏳ 다음 단계 |

---

## §5. 학습 + 예방

### 5.1 같은 패턴 재발 방지

1. **architecture-level 변경은 base branch (devleop) 와 자주 sync**
   - 본 케이스에서 feature 브랜치가 1주일 분기 진화한 후 머지 시도 → 충돌 누적
   - 권장: 큰 architecture 변경은 매일·격일 `git merge devleop` 으로 incremental sync
2. **같은 함수의 같은 영역을 두 브랜치가 건드릴 때 사전 협의**
   - T4 (decide_alarm) plan 작성 시점에 devleop 의 PR #69 가 같은 영역을 변경 중인 줄 몰랐음
   - 권장: plan 작성 단계에서 `git log devleop -- <대상 파일>` 로 상대 브랜치 변경 확인
3. **충돌 해소 직후 ruff syntax check + IDE diagnostics 확인**
   - 본 케이스에서 abort 전 충돌 해소가 깨진 상태로 commit 시도까지 갔음
   - ruff `Failed to parse` + IDE `"("가 닫혀 있지 않음` 두 신호로 architecture-level 깨짐을 즉시 감지 가능
4. **architecture-level 충돌은 line-by-line 보다 architecture 선택 후 재구성이 빠르다**
   - 본 케이스 — 우리 브랜치 architecture base 유지 + devleop 메트릭만 흡수 결정 후 수작업이 빨랐음
   - 옵션: `git merge -X ours <branch>` 로 우리 브랜치 우선 자동 해소 (메트릭은 수동 추가) 도 가능

### 5.2 일반 원칙 (T3 트러블슈팅과 공통)

| 패턴 | T3 (Pydantic) | 본 머지 충돌 |
|---|---|---|
| 양 끝점 정상 | DRF send ✅, JS receive ✅ | 우리 브랜치 ✅, devleop ✅ |
| 중간에서 손실·깨짐 | fastapi `AlarmPayload` silent drop | git 자동 머지 architecture 혼합 |
| 단위 테스트 한계 | 양 끝 단독 테스트는 통과 | 각 브랜치 단독 회귀는 통과 |
| 발견 경로 | E2E 브라우저 시각 검증 | ruff syntax check + IDE diagnostics |

→ **양방향·교차 변경의 중간 지점은 별도 검증 필요**. 두 사례 모두 양 끝점만 보면 정상이지만 통합 시점에서 깨짐.

---

## §6. 참고 자료

- 본 머지 commit: `c1eed97`
- devleop tip: `7d19a88 feat(monitoring): 전력 AI 5축 모니터링 메트릭 추가 및 대시보드 분리 (#69)`
- T4 plan (decide_alarm 매트릭스): [skill/plan/alarm-t4-ai-static-hierarchy.md](../../skill/plan/alarm-t4-ai-static-hierarchy.md)
- T3 트러블슈팅 (관련 silent drop 패턴): [drf-server/docs/refactoring/2026_05_20_alarm_t3_troubleshooting.md](../../drf-server/docs/refactoring/2026_05_20_alarm_t3_troubleshooting.md)
- 알람 흐름 As-Is (충돌 영역 architecture 배경): [docs/codereviews/2026_05_19/alarm-business-logic-as-is.md](../2026_05_19/alarm-business-logic-as-is.md)

---

> **본 문서 핵심**: feature 브랜치와 devleop 가 같은 함수의 같은 영역을 incompatible 한 architecture 로 동시에 진화 → git 자동 머지가 둘 다 보존하려다 architecture-level 으로 깨짐 → abort 후 수작업 재해소 (우리 브랜치 architecture base + devleop 메트릭 흡수). 학습 — 큰 architecture 변경 시 base branch 와 자주 sync + 충돌 해소 직후 ruff/IDE 로 syntax-level 검증 필수.
