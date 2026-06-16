# T3 ack 시그널 트러블슈팅 + 데이터 흐름 변경 정리

작성일: 2026-05-20
브랜치: `feature/0519_alarm_business_logic`
부모 작업: T1+T6+T3 통합 — [2026_05_19_alarm_t1_t6.md](2026_05_19_alarm_t1_t6.md)

---

## 1. 작업 전체 요약 (10 commit)

| 단계 | Commit | 핵심 |
|---|---|---|
| **T1+T6** | 0d4177c | summary·정상화 메시지 정리 (ML 용어 제거, 천단위 포맷) |
|  | 4fac3f6 | fastapi push_payload 에 `message` 필드 동봉 |
|  | fbe7966 | 이벤트 패널 fallback — alarm_type 한글 라벨 |
|  | 252bcec | T1+T6 코드리뷰 적용 결과 문서 |
|  | ce5ad43 | algorithm 별 워딩 세분화 + 룰 정적 임계치 워딩 |
|  | eb9533a | 압연기 단독 테스트 스크립트 + COMMANDS |
| **T3** | 3e03296 | EventAck 하이브리드 — 토스트에 확인자명 시그널 |
|  | e2b2ca6 | RESOLVED dedup key 분리 + dedup 4 레이어 설계 문서화 |
| **사이드 수정** | 0fdc4d5 | `event_ack_selector` typo (Phase 1 사전 버그) |
|  | **0b84be5** | **T3 fastapi AlarmPayload 에 event_ack_users 필드 추가** ← 핵심 |

---

## 2. T3 트러블슈팅 상세

### 2.1 증상

T3 구현 (commit 3e03296) 완료 후 브라우저 검증:

- 백엔드 `EventAcknowledgement` DB 정상 저장 (관리자 + 테스트 ack 2건)
- celery task `_push_to_ws` 가 `event_ack_users: ['관리자', '테스트']` 포함된 payload 전송 (httpx 200 OK)
- 회귀 테스트 59건 통과
- **그러나 브라우저 모달 본문에 `(관리자, 테스트 확인 중)` 시그널 미표시**

운영자 화면에서는 일반 알람 메시지만 보이고 새로 추가된 ack 시그널 텍스트가 나타나지 않음.

### 2.2 디버그 단계별 진행

#### Step 1 — JS 캐시 의심 (오판)
첫 가설: 브라우저가 옛 JS 캐시 사용 중. 사용자가 강력 새로고침·시크릿 창 시도. 콘솔 검증:
```js
typeof _formatAckSignal  // → "function" ✓
AlarmMapper.fromSensorsAlarm({event_ack_users:['a','b']}).event_ack_users  // → ['a','b'] ✓
```
→ JS 는 새 버전 정상 로드. 가설 폐기.

#### Step 2 — 백엔드 데이터 의심 (오판)
서버에서 `_get_event_ack_names(743)` 직접 호출 결과 `['관리자', '테스트']`. push_payload 시뮬레이션 + `_push_to_ws()` 강제 발사 — 모두 정상. 가설 폐기.

#### Step 3 — fastapi 중간 단계 의심 (정답)
`alarm_router.py` 의 `AlarmPayload` 스키마 확인:

```python
class AlarmPayload(BaseModel):
    model_config = {"extra": "ignore"}  # ← 핵심
    alarm_type: str
    risk_level: str
    ...
    # event_ack_users 필드 정의 없음
```

**Pydantic `extra: "ignore"`** 가 정의 안 된 필드를 silent drop. DRF 가 보낸 `event_ack_users` 가 fastapi 통과 시 **에러 없이 사라짐**.

### 2.3 원인

T3 C1 (commit 3e03296) 작업 시:
- ✅ `drf-server/apps/alerts/tasks.py` 에 `event_ack_users` 추가 (5개 push_to_ws 위치)
- ✅ `drf-server/static/js/shared/alarm-mapper.js` 평탄화
- ✅ `drf-server/static/js/shared/alarm-popup.js` 토스트·모달 렌더링
- ❌ `fastapi-server/internal/routers/alarm_router.py` 의 **AlarmPayload 스키마 갱신 누락**

DRF Celery → fastapi 사이의 HTTP 경계에서 데이터 손실. 양 끝 (DRF backend, JS frontend) 은 정상이라 단위 테스트로 잡히지 않음.

### 2.4 수정 (commit 0b84be5)

`fastapi-server/internal/routers/alarm_router.py` AlarmPayload 에 1줄 추가:

```python
# T3 (2026-05-19) — 다중 관리자 환경 ack 시그널. 활성 Event 의 EventAck 한 사용자명 list.
# 토스트·모달 본문에 "(N 확인 중)" 시그널 표시용 (dedup 과 분리 — 안전망 유지).
# AlarmPayload.model_config="extra:ignore" 라 명시 정의 필수 (누락 시 silent drop).
event_ack_users: list[str] = []
```

fastapi 재시작 + 강제 push 후 모달에 `(관리자, 테스트 확인 중)` 표시 확인. 검증 완료.

---

## 3. 데이터 흐름 — Before vs After

### 3.1 전체 알람 흐름 (T1+T3 적용 후)

```
[1] IoT 센서 (또는 dummy)
       │ POST /api/power/watt
       ▼
[2] fastapi/power/routers/power_router.py
       │ PowerWattPayload 검증
       │ process_anomaly_inference() — IF + ARIMA 추론 + 5축 정책 엔진
       ▼
[3] fastapi/services/anomaly_alarm.py forward_inference_e2e()
       ├── (a) push_alarm → Redis 큐 (즉시 broadcast — AI 직접 push)
       ├── (b) ML forward → POST /api/ml/anomaly-results/
       └── (c) Alarm forward → POST /alerts/api/anomaly-alarm-records/
                  │
                  ▼
[4] drf/apps/alerts/views — AlarmRecord + Event 생성
       │ create_alarm_and_event() 안 _should_repopup 판정
       ▼
[5] drf/apps/alerts/tasks.py — Celery task 발화 (fire_*_task)
       │ payload = {
       │   "event_id": event.id,
       │   "message": alarm.get_short_message(),
       │   "event_ack_users": _get_event_ack_names(event.id),  ← T3 NEW
       │   ...
       │ }
       │ _push_to_ws(payload) → httpx POST
       ▼
[6] fastapi/internal/routers/alarm_router.py — push_alarm_handler
       │ AlarmPayload 검증 ← T3 버그 발생 지점 (이전: silent drop)
       │ 수정 후: event_ack_users 보존 ✓
       │ alarm_queue.push_alarm(alarm) → Redis LPUSH (fingerprint dedup)
       ▼
[7] fastapi/websocket/services/alarm_queue.py alarm_flush_loop
       │ Redis BRPOP → active_alarms 큐
       │ broadcast → sensor_clients (WebSocket)
       ▼
[8] 브라우저 dashboard/websocket.js onMessage()
       │ data.alarms.forEach(alarm => {
       │   const alarmData = AlarmMapper.fromSensorsAlarm(alarm);  ← 평탄화
       │   AlarmPopup.show(alarmData);  ← 모달
       │   EventPanel.addItem(alarmData);
       │ });
       ▼
[9] AlarmPopup.show() — 모달 렌더링
       │ _formatAckSignal(data.event_ack_users) → "(이름1, 이름2 확인 중)"
       │ msgEl.appendChild(ackEl)  ← T3 NEW
       ▼
[10] 운영자 화면
       모달 본문:
         압연기
         압연기 정적 임계치 초과 (12,000.0 W)
         위험 기준 2860 초과 (측정 12000)
         (관리자, 테스트 확인 중)   ← T3 시그널
```

### 3.2 `event_ack_users` 필드의 각 단계별 변환

| 단계 | 위치 | 값 (예시) | 형태 |
|---|---|---|---|
| 5 | drf tasks.py `_get_event_ack_names(743)` | `['관리자', '테스트']` | `list[str]` |
| 5 | drf `_push_to_ws()` HTTP body | `"event_ack_users": ["관리자","테스트"]` | JSON array |
| 6 | fastapi `AlarmPayload` (BEFORE FIX) | **사라짐** (silent drop) | `None` |
| 6 | fastapi `AlarmPayload` (AFTER FIX) | `['관리자', '테스트']` | `list[str]` |
| 7 | fastapi `alarm_queue` Redis push | `event_ack_users: ["관리자","테스트"]` | JSON array |
| 7 | fastapi WS broadcast | `alarms[0].event_ack_users: ["관리자","테스트"]` | JSON array |
| 8 | JS `AlarmMapper._common()` | `event_ack_users: ["관리자","테스트"]` | JS array |
| 9 | JS `_formatAckSignal()` | `"(관리자, 테스트 확인 중)"` | string |
| 10 | DOM `<span class="msg-ack-signal">` | `(관리자, 테스트 확인 중)` | 화면 텍스트 |

### 3.3 Before (T1+T6+T3 적용 전 — 옛 상태) vs After

#### 토스트/모달 메시지 내용

| 영역 | Before | After |
|---|---|---|
| AI 알람 본문 | `[IF 이상 감지] 송풍기A watt=7925.8 (score 0.0292, combined=warning)` | `송풍기A 이상 수치 탐지 (7,925.8 W)` |
| 룰 알람 본문 | `전력 임계치 초과 (15.8 W)` | `정적 임계치 초과 (15.8 W)` |
| 정상화 메시지 | `정상 복귀` | `송풍기A 정상 복귀` |
| 사용자 확인 시그널 | 없음 | `(관리자 확인 중)` / `(관리자, 테스트 확인 중)` / `(관리자 외 2명 확인 중)` |
| 이벤트 패널 fallback | `gas_anomaly_ai` (영문 코드) | `가스 AI 이상 감지` (한국어) |

#### Algorithm 별 워딩 매핑 (T1)

| algorithm_source | Before | After |
|---|---|---|
| isolation_forest | `송풍기A IF 이상 감지 (7925.8 W)` | `송풍기A 이상 수치 탐지 (7,925.8 W)` |
| arima | `송풍기A ARIMA 이상 감지 (820.5 W)` | `송풍기A 이상 패턴 탐지 (820.5 W)` |
| combined | `송풍기A IF+ARIMA 이상 감지` | `송풍기A 이상 수치·패턴 동시 탐지` |
| zscore | `송풍기A Z-score 이상 감지` | `송풍기A 통계 이상 수치` |
| change_point | `송풍기A 급변 이상 감지` | `송풍기A 패턴 변화 탐지` |
| night_abnormal | `송풍기A 야간 가동 이상 감지` | `송풍기A 야간 이상 가동` |

#### Push Payload 키 변경 (T1+T3)

| 키 | Before | After |
|---|---|---|
| `message` | 일부 push 에만 있음 (불일관) | 모든 push 에 동봉 (단일 진실 공급원) |
| `event_ack_users` | 없음 | `list[str]` (활성 Event 의 EventAck 사용자명) |

---

## 4. 학습 사항

### 4.1 Pydantic `extra: "ignore"` 의 위험

```python
class AlarmPayload(BaseModel):
    model_config = {"extra": "ignore"}  # 미정의 필드 silent drop
    ...
```

**장점**: 들어오는 데이터에 모르는 필드가 있어도 검증 실패하지 않음. 하위 호환성·확장성 좋음.

**위험**: 새 필드를 양쪽 (송신 + 수신) 에 추가해야 할 때 한쪽만 추가하면 **에러 없이 데이터 사라짐**. 단위 테스트로 안 잡힘 — 양 끝은 정상 동작하지만 중간에서 손실.

대응:
- 양방향 통신 필드 추가 시 **체크리스트**: DRF 송신 / fastapi 수신 스키마 / fastapi 송신 / JS 수신 4 지점 모두 확인
- 또는 `model_config = {"extra": "forbid"}` 로 변경하면 미정의 필드 도착 시 422 에러 — 누락 즉시 발견 가능 (단 운영 영향 검토 필요)

### 4.2 양방향 push payload 변경 체크리스트

DRF → fastapi → WS → JS 흐름에서 필드 추가 시:

1. ✅ DRF 측 송신: `drf-server/apps/alerts/tasks.py` `_push_to_ws()` payload 에 필드 추가
2. ✅ DRF 측 데이터 생성: 필드 값 조회 헬퍼 (예: `_get_event_ack_names`)
3. ⚠️ **fastapi 측 수신 스키마**: `fastapi-server/internal/routers/alarm_router.py` `AlarmPayload` 에 필드 명시 정의
4. ✅ fastapi → WS broadcast: `alarm_queue.py` `push_alarm()` 가 dict 그대로 전달 (스키마 검증된 모델 dump)
5. ✅ JS 측 매핑: `drf-server/static/js/shared/alarm-mapper.js` `_common()` 평탄화
6. ✅ JS 측 렌더링: `alarm-popup.js` / `event-panel.js` 등에서 사용

### 4.3 디버그 방법

**문제 격리** 5단계 (위 흐름의 각 노드별 검증):

```bash
# (1) DRF 데이터 생성 검증
docker compose exec drf python manage.py shell -c "
from apps.alerts.tasks import _get_event_ack_names
print(_get_event_ack_names(743))
"

# (2) DRF 송신 payload 검증 — 강제 push
docker compose exec drf python manage.py shell -c "
from apps.alerts.tasks import _push_to_ws
_push_to_ws({...})
"

# (3) fastapi 수신 + 재전송 검증 — 로그
docker compose logs fastapi | grep alarms/push

# (4) WS broadcast 검증 — 브라우저 DevTools Network → WS Messages

# (5) JS 렌더링 검증 — 브라우저 콘솔
typeof _formatAckSignal === 'function'
AlarmMapper.fromSensorsAlarm({event_ack_users:['a','b']}).event_ack_users
```

---

## 5. T3 시그널 동작 사양 (구현 완료)

### 5.1 백엔드 헬퍼

```python
# drf-server/apps/alerts/tasks.py
def _get_event_ack_names(event_id: int | None) -> list[str]:
    """활성 Event 의 EventAck 사용자명 list. dedup 과 분리, 시그널만 보강."""
    if not event_id:
        return []
    return list(
        EventAcknowledgement.objects.filter(event_id=event_id)
        .select_related("user")
        .values_list("user__name", flat=True)
    )
```

5개 `_push_to_ws` 위치 (가스 DANGER L171, 가스 WARNING L244, 가스 재발화 L311, 전력 DANGER L419, 전력 WARNING L485) 모두 `"event_ack_users": _get_event_ack_names(event.id)` 동봉.

### 5.2 JS 포맷터

```js
// drf-server/static/js/shared/alarm-popup.js:125
function _formatAckSignal(ackUsers) {
  if (!Array.isArray(ackUsers) || ackUsers.length === 0) return '';
  if (ackUsers.length === 1) return `(${ackUsers[0]} 확인 중)`;
  if (ackUsers.length === 2) return `(${ackUsers[0]}, ${ackUsers[1]} 확인 중)`;
  return `(${ackUsers[0]} 외 ${ackUsers.length - 1}명 확인 중)`;
}
```

### 5.3 표시 사양

| ack 명수 | 토스트/모달 표시 |
|---|---|
| 0명 | 시그널 미렌더 (단일 운영자 환경 영향 0) |
| 1명 | `(홍길동 확인 중)` |
| 2명 | `(홍길동, 김민수 확인 중)` |
| 3명 이상 | `(홍길동 외 2명 확인 중)` |

### 5.4 dedup 과의 관계

- **dedup**: 시간 기반 (60s) — 같은 알람 토스트 중복 차단 (사용자 무관)
- **EventAck**: 사용자별 — "내가 봤다" 운영 이력
- **시그널**: 시각 보강만 — dedup·ack 동작은 그대로

다중 관리자 환경:
- A·B·C 모두 알람 받음 (dedup 사용자별 분리 X, 안전망 유지)
- A 가 ack → A 의 EventAcknowledgement 1행 + A 의 _AckStore 에 event_id 추가
- 60s 후 같은 알람 재발화 → B·C 토스트에 `(A 확인 중)` 시그널
- A 본인 화면: _AckStore 차단으로 모달 X (의도된 user-scoped dedup)

---

## 6. 사이드 수정 — 사전 버그 (commit 0fdc4d5)

T3 디버그 중 발견된 사전 버그 (Phase 1 commit 68c3683 에서 도입).

### 위치
`drf-server/apps/alerts/selectors/event_ack_selector.py:73`

### 증상
대시보드 헤더의 "🔔 미확인 알람 N" 배지 로드 시 `GET /alerts/api/alarms/summary/` 가 500 에러.

### 원인
```python
.exclude(event_acknowledgements__user_id=user_id)
```
Event 모델의 EventAcknowledgement related_name 은 `acknowledgements` 인데 `event_acknowledgements` 로 잘못 참조. Django `FieldError: Cannot resolve keyword 'event_acknowledgements' into field`.

### 수정
```python
.exclude(acknowledgements__user_id=user_id)
```

T3 와 무관하나 디버그 환경 노이즈 제거 위해 같은 PR 에 포함.

---

## 7. 검증

| 영역 | 통과 |
|---|---|
| 회귀 테스트 (drf alerts) | 59건 ✅ |
| 회귀 테스트 (fastapi) | 173건 ✅ |
| 브라우저 검증 — T1 워딩 | ✅ (압연기 이상 수치 탐지 등) |
| 브라우저 검증 — T1 천단위 포맷 | ✅ (12,000.0 W) |
| 브라우저 검증 — T3 시그널 (1명) | ✅ |
| 브라우저 검증 — T3 시그널 (2명) | ✅ ("(관리자, 테스트 확인 중)" 확인) |
| 사전 500 버그 | ✅ 해소 |

---

## 8. 시연 D-day (2026-06-14) 까지 잔여

T1+T6+T3 = 시연 전 작업 완료. 시연 후 sprint:

- **T2**: 위험도 4단계 색상 (RiskLevel enum 확장 vs anomaly_meta.combined_risk 분기)
- **T4**: AI vs 룰 분리·통합 결정 (운영자 시연 피드백 후)
- **T5**: 모달·자동닫힘·이탈 정책 (60s 무응답 격상, catch-up 폭주 cap)
- **T7**: JS 인프라 정리 (AlarmMapper 스키마 명시화, CustomEvent 정리)

부모 plan: [skill/plan/alarm-post-ai-redesign.md](../../../skill/plan/alarm-post-ai-redesign.md)
