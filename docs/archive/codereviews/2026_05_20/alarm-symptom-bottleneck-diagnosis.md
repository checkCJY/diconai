# 알람 증상 → 병목 진단 (2026-05-20)

작성일: 2026-05-20
브랜치: `feature/0519_alarm_business_logic` (T1+T6+T3 완료 직후)
선행 문서:
- [docs/codereviews/2026_05_19/alarm-business-logic-as-is.md](../2026_05_19/alarm-business-logic-as-is.md) (As-Is 전체 흐름 + 29 후보 갭)
- [drf-server/docs/refactoring/2026_05_20_alarm_t3_troubleshooting.md](../../../../drf-server/docs/refactoring/2026_05_20_alarm_t3_troubleshooting.md) (T3 silent drop 사례)

목적: 운영자 경험상 짚인 3가지 증상 — **알람 누락 / 중복 / 조치완료 강제** — 을 현재 코드 동작에 매핑하여 어디서 막히는지 한 장에 정리. 수정은 본 문서 범위 밖.

---

## §1. 작성 배경

T1+T6+T3 작업이 시연 전 워딩·dedup·ack 시그널 영역을 마감했지만, 운영자 입장에서는 여전히 다음 3가지 증상이 발생:

| # | 증상 (운영자 표현) | 빈도 |
|---|---|---|
| A | 위험 발생 소리는 나는데 알람 모달이 안 뜸. 조치완료 후 다시 알람이 제대로 안 옴. 새로고침해야 옴. 어느 순간 갑자기 뒤늦게 팝업 | 자주 |
| B | AI 알람과 룰 알람이 같은 채널·시각에 둘 다. WS 재연결 후 한꺼번에 우르르. 단 재연결 시 일부는 누락 | 가끔 |
| C | 이벤트 현황 페이지에서 **조치 완료** 를 눌러야 다음 알람이 나옴 (RESOLVED 처리 강제). 추가로 들어온 **ack** 도 동작이 헷갈림 | 항상 (의도된 동작이라 매번) |

진단의 핵심 가설:
- 증상 A 의 "소리 났음" 은 [9] WS broadcast 까지 도달했다는 강한 신호. 즉 **[10] 브라우저 게이트** 가 1순위 의심.
- 증상 B 의 WS 재연결 누락은 **catch-up 결과가 클라 dedup 에 차단되는 시나리오** 가능성.
- 증상 C 는 코드 버그가 아니라 **운영자 멘탈 모델 분리 (ack vs RESOLVED)** 자체 문제 — [[operator_mental_model_simplicity]] 원칙 위배.

---

## §2. 현재 알람 흐름 — 코드 기준 (2026-05-20)

자세한 다이어그램은 [선행 As-Is 문서 §2](../2026_05_19/alarm-business-logic-as-is.md). 본 진단에 필요한 핵심 노드만 재기재.

```
[1] IoT/dummy ─ POST /api/power/watt
       ▼
[2] FastAPI process_anomaly_inference  (IF+ARIMA+Z+CP+threshold → 5축 결합)
       ├─ rate_limit (60s, 게이트 G1)
       └─ should_fire = combined ∈ _FIRE_LEVELS
       ▼
[3] anomaly_alarm.forward_inference_e2e
       ├─ (a) push_alarm 즉시 (FastAPI → Redis)
       ├─ (b) ML forward
       └─ (c) Alarm forward (DRF)
       ▼
[4] DRF AnomalyAlarmRecordCreateView → create_alarm_and_event
       ├─ Event 병합/신규/RESOLVED 판정
       └─ _should_repopup (게이트 G2 — cooldown 60s, 활성 Event 면 push 자체 skip)
       ▼
[5] DRF Celery fire_*_task → _push_to_ws (httpx)
       ▼
[6] FastAPI alarm_router (AlarmPayload, extra=ignore — T3 silent drop 자리)
       ▼
[7] alarm_queue.push_alarm
       └─ Redis fingerprint dedup (30s, 게이트 G3 — Celery retry burst 차단)
       ▼
[8] alarm_flush_loop (BRPOP) → broadcast → sensor_clients
       ▼
[9] 브라우저 alarm-ws.js  ← 여기까지 도달하면 "소리" 발생 (브라우저 알림음)
       ▼
[10] AlarmPopup.show — 게이트 4종 통과해야 모달 표시:
       G4. _AckStore (24h TTL) — 본인이 같은 event_id 를 ack 했으면 skip
       G5. _DedupStore (60s TTL) — 같은 dedup key 가 있으면 skip
       G6. 토스트/모달 분기 — risk_level 분기, __forceModal 격상 경로
       G7. 큐 풀 (MAX_QUEUE) — 초과 시 헤더 배지로 떨굼
```

### 게이트 7종 한눈에

| 게이트 | 위치 | TTL/조건 | 의도 | 운영자에게 보이는가 |
|---|---|---|---|---|
| G1. rate_limit | [power_service.py:64](../../../../fastapi-server/power/services/power_service.py#L64) | 60s | 센서 push 빈도 제한 | ❌ (서버 로그만) |
| G2. repopup_cooldown | [event_service.py](../../../../drf-server/apps/alerts/services/event_service.py) + [settings.py:382](../../../drf-server/config/settings.py#L382) | 60s | 활성 Event 재팝업 cooldown | ❌ (이벤트 패널 카운트만 ↑) |
| G3. push_dedup | [alarm_queue.py:40](../../../../fastapi-server/websocket/services/alarm_queue.py#L40) | 30s Redis fingerprint | Celery retry burst | ❌ |
| G4. _AckStore | [alarm-popup.js:14-30](../../../../drf-server/static/js/shared/alarm-popup.js#L14-L30) | **24h** localStorage | 본인이 ack 한 event 모달 차단 | ❌ (영구 침묵) |
| G5. _DedupStore | [alarm-popup.js:60-110](../../../../drf-server/static/js/shared/alarm-popup.js#L60-L110) | 60s localStorage | 다중 탭·burst 차단 | ❌ |
| G6. 토스트/모달 분기 | [alarm-popup.js:383-388](../../../../drf-server/static/js/shared/alarm-popup.js#L383-L388) | 경로 + DANGER 10s 무응답 → __forceModal | admin-panel 우상단 토스트 / 그 외 중앙 모달 | ✅ |
| G7. 큐 풀 (MAX_QUEUE) | [alarm-popup.js:405-414](../../../../drf-server/static/js/shared/alarm-popup.js#L405-L414) | 큐 초과 시 drop + 헤더 배지 | 폭주 방지 | ⚠️ (배지) |

추가 suppress (게이트는 아니지만 알람 발생 자체를 막음):
- **AI mute** — [`ai_fired:{device}:{ch}:{level}` Redis 키 (60s)](../../../../fastapi-server/services/ai_mute.py): AI 발화 시 룰 측 60s suppress
- **WS 끊김 fallback** — 60s 지속 시 catch-up API 30s 폴링

> **As-Is 문서 stale 1건 발견**: As-Is §5A.6 은 "DANGER 토스트 60s 무응답 → 모달 격상" 이라 기재. 실제 코드는 **10s** ([alarm-popup.js:385](../../../../drf-server/static/js/shared/alarm-popup.js#L385)). 코드를 truth source 로.

---

## §3. 증상별 병목 매핑

### 3.1 증상 A — "모달 안 뜸 / 새로고침해야 옴 / 뒤늦은 팝업"

**관찰 사실**: 소리는 났음 → [9] WS broadcast 까지 도달. → [10] 브라우저 게이트 의심.

| 후보 | 게이트 | "새로고침하면 옴" 일치도 | "뒤늦은 팝업" 일치도 |
|---|---|---|---|
| **G4. _AckStore 24h 차단** ⭐ | 본인이 같은 event 를 이전에 ack → localStorage 에 영구 (24h) 기록 → Event cooldown 만료 후 재발화도 본인 화면은 모달 X | 부분 (localStorage 동일이라 효과 같지만, 클라 reload 시 catch-up 으로 다른 event 발견 가능) | ✅ (다른 event_id 가 우연히 도착했을 때 갑자기 표시) |
| **G5. _DedupStore 60s 차단** | 60s 안 같은 dedup key 도착 → silent drop. RESOLVED dedup 은 T3 에서 별도 suffix 처리됨 | 부분 (60s 지나면 자동 해제) | ⚠️ (60s 후 자연 회복) |
| **G2. Event cooldown** | 활성 Event 살아있어 push 자체 안 옴 | ❌ (서버 측이라 새로고침 무관 — 소리도 없어야 함) | ❌ |
| **WS 메시지 도달 but 분기 실패** | risk_level 값이 비정상 (`""`/`null`) → G6 분기에서 어느 쪽도 안 감 | ✅ (새 WS 연결 시 정상값 도착 가능) | ⚠️ |
| **WS 연결 좀비 상태** | 브라우저 socket 죽은 줄 모름 — 일부 알람만 도착 | ✅ (새 WS = 회복) | ⚠️ |

→ **1순위 가설: G4 (_AckStore 24h 차단)**. 운영자 표현 "조치 완료 후 다시 알람이 제대로 안 옴" 은 **사용자가 모달의 "확인" 누름 → _AckStore 에 event_id 추가 → 같은 event 의 후속 알람 (cooldown 만료 후) 본인 화면 영구 차단** 패턴과 정확히 일치. 24h 동안 매번 새로고침해야 일부 회피 가능.

**근거 코드**:
- [alarm-popup.js:372](../../../../drf-server/static/js/shared/alarm-popup.js#L372) `if (_AckStore.has(eventId)) return;` — 같은 event_id 의 후속 push 본인 화면 silent skip
- [alarm-popup.js:646](../../../../drf-server/static/js/shared/alarm-popup.js#L646) `_AckStore.add(eventId)` — 모달의 "확인 완료" 클릭 시 추가

### 3.2 증상 B — "AI+룰 중복 / 재연결 우르르 / 재연결 일부 누락"

| 케이스 | 원인 | 코드 위치 |
|---|---|---|
| AI + 룰 같은 채널·시각 | `POWER_ANOMALY_AI` 와 `POWER_OVERLOAD` 별도 alarm_type. AI mute 60s 만료 후 / 격상 bypass 시 둘 다 발화 (§5A.3) | [power_alarm.py:119-207](../../../../drf-server/apps/monitoring/services/power_alarm.py#L119-L207), [ai_mute.py](../../../../fastapi-server/services/ai_mute.py) |
| 재연결 후 우르르 | catch-up API 가 since 이후 활성 알람 전체 일괄 반환. cap 없음 (§5A.9) | [drf-server/apps/alerts/views/event.py](../../../../drf-server/apps/alerts/views/event.py) |
| **재연결 시 일부 누락** ⭐ | catch-up 결과가 클라 도착 → AlarmPopup.show → **G5 (_DedupStore 60s)** 가 차단. 또는 **G4 (_AckStore)** 가 차단. catch-up 의도와 dedup 의도가 충돌 | [alarm-popup.js:372,380](../../../../drf-server/static/js/shared/alarm-popup.js#L372) |

→ **잠재 신규 버그**: catch-up 의 의미는 "WS 끊김 동안 놓친 것 복구" 인데, 클라 dedup/ack 가 60s 이내 또는 24h 이내 캐시되어 있으면 차단됨. 운영자가 다른 PC 에서 와서 화면 봤는데 정작 catch-up 결과가 자기 localStorage 에 의해 막히는 경우가 가능. 본 As-Is 문서 §5A.9 도 catch-up 폭주만 언급하고 "누락" 시나리오는 미문서화.

### 3.3 증상 C — "조치 완료해야 다음 알람 / ack 도 헷갈림"

이건 코드 버그가 아니라 **두 개념이 공존하는 멘탈 모델 문제** 입니다.

| 개념 | 액션 위치 | 효과 | 운영자 인식 |
|---|---|---|---|
| **Event.RESOLVED** (조치 완료) | 이벤트 현황 페이지 버튼 | Event 전역 종료 → cooldown 해제 → 모든 사용자 모달 close + 다음 발화 push 통과 | "**이걸 안 누르면** 다음 알람이 안 나옴" |
| **EventAcknowledgement** (ack) | 모달의 "확인 완료" 버튼 | **본인만** 모달 영구 차단 (24h). 다른 사용자에겐 `(N 확인 중)` 시그널 | "이게 뭔지 잘 모르겠음, 동작이 헷갈림" |

운영자 시나리오:
1. 같은 source 에서 위험 발생 → Event 생성 + 모달
2. 모달 "확인 완료" 클릭 → `_AckStore.add(event_id)` (본인 24h 영구 침묵)
3. 같은 source 에서 1분 후 새 위험 → 같은 Event 여전히 활성 → cooldown 만료 → 새 AlarmRecord + push
4. **G4 (_AckStore)** 가 본인 화면에서 silent skip → "안 옴" 인식
5. 운영자가 이벤트 현황에서 "조치 완료" (RESOLVED) 클릭 → Event 종료 → 다음 위험은 신규 Event 로 → 새 event_id 라 _AckStore 통과 → 모달 옴 → "조치완료 후에야 다음 알람 나옴" 인식

→ 즉 운영자의 멘탈 모델 "조치 완료를 눌러야 다음 알람" 은 **현 시스템이 그렇게 동작하도록 강제** 한 결과. ack 가 user-scoped 로 추가되면서 이 멘탈 모델과 충돌해 운영자가 더 헷갈림.

[[operator_mental_model_simplicity]] 원칙에 정면 위배. T5 sprint (모달·이탈 정책) 가 시연 후로 미뤄진 상태이나, 이 멘탈 모델 통합 자체는 T5 안에서 우선 다뤄야 할 가능성.

---

## §4. 시연 D-day (2026-06-14) 영향 분석

증상별 시연 노출 위험도 + fix 시 영향 평가:

| 증상 | 시연 시 노출 | fix 비용 | 시연 전 fix 권고 |
|---|---|---|---|
| 3.1 A (모달 안 뜸 / G4 차단) | **높음** — 시연 중 운영자가 모달 ack 후 다음 알람 못 받으면 시연 흐름 끊김 | 중간 — _AckStore TTL 단축 (24h → 60s) 또는 RESOLVED 시 ackStore 초기화 | ⚠️ 고려 필요 |
| 3.2 B-1 (AI+룰 중복) | 중간 — 시연자가 "AI 가 잡았고, 동시에 룰도 잡음" 설명 가능. 운영자에겐 거슬림 | 높음 — AI 가 발화 시 룰 완전 suppress 정책 (현재 60s 만) | ❌ 시연 후 (T4) |
| 3.2 B-2 (재연결 우르르) | 낮음 — 시연 환경에서 WS 끊김 의도적 재현 안 함 | 중간 — catch-up cap (최근 N건) | ❌ 시연 후 (T5) |
| 3.2 B-3 (재연결 누락) | 낮음 — 위와 동일 | 낮음 — catch-up payload 에 `__bypassDedup: true` 플래그 | ❌ 시연 후 (T5) |
| 3.3 C (멘탈 모델) | 중간 — 시연 시 "조치 완료를 눌러야 합니다" 설명이 자연스러우면 패스. 단 ack/RESOLVED 둘 다 설명하면 복잡 | 높음 — UX 통합 + 백엔드 정책 재설계 | ❌ 시연 후 (T5 우선 진입) |

⭐ **시연 영향 1순위**: §3.1 의 G4 (_AckStore 24h) — 시연 중 모달 클릭 한 번이 24시간 침묵을 만들어 무대 위에서 멈출 위험. 시연 전 최소한 TTL 을 60s ~ Event RESOLVED 까지로 단축 검토 필요.

---

## §5. 검증 명령 (수정 전 가설 확정용)

### G4 (_AckStore 24h 차단) 가설 검증

```js
// 브라우저 콘솔 — 시연 PC 에서 실행
const stored = JSON.parse(localStorage.getItem('diconai:alarm:acked_event_ids') || '[]');
console.log('Acked events count:', stored.length);
console.log('Oldest entry age (h):', stored.length ? ((Date.now() - stored[0].ts) / 1000 / 3600).toFixed(1) : 'n/a');
// 다수 누적되어 있고 24h 가까운 항목 있으면 → 1순위 가설 강화
```

### G5 (_DedupStore 60s) 가설 검증

```js
const dedup = JSON.parse(localStorage.getItem('diconai:alarm:popup:dedup') || '[]');
console.log('Dedup entries:', dedup.length);
console.log(dedup.map(e => ({key: e.key, ageS: ((Date.now() - e.ts) / 1000).toFixed(0)})));
```

### G2 (Event cooldown) 가설 검증

```bash
docker compose exec drf python manage.py shell -c "
from apps.alerts.models import Event
for e in Event.objects.filter(status='active').order_by('-created_at')[:10]:
    print(e.id, e.alarm_type, e.source_label, e.last_notified_at)
"
# last_notified_at 이 60s 안에 자주 갱신되는 Event 면 cooldown 으로 push skip 패턴
```

### Catch-up 누락 가설 검증

```bash
docker compose logs drf | grep "alarms/catch-up" | tail -20
# since 파라미터 + 반환 건수 패턴. 다중 PC 환경에서 since 가 어디 보존되는지 확인
```

### G6 분기 실패 가설 검증

```js
// 브라우저 콘솔 — WS 메시지 가로채기
const orig = WSClient.prototype._onMessage || null;
// alarm-ws.js 의 onMessage 에 console.log 박아 risk_level 값이 빈 문자열인 케이스 추적
```

---

## §6. 비범위

본 진단 문서는 **수정 없음**. 다음 항목은 본 문서에서 다루지 않음:

- 실제 수정 작업 — 별도 plan 으로 분리
- 시연 시나리오 리허설 결과 (D-7 별도 진행)
- T5 (모달·이탈 정책 sprint) 의 전체 설계 — 본 진단이 T5 진입 조기화 근거 자료가 될 뿐
- AI 알람 정확도 (false positive / false negative) 분석 — 본 문서는 도달성·UX 관점

---

## §7. 다음 단계 후보 (수정 결정 시)

본 문서가 짚은 1순위 가설 (G4 _AckStore 24h) 가 검증되면:

| 옵션 | 변경 | 영향 범위 | 시연 적합 |
|---|---|---|---|
| (a) _ACK_TTL_MS 60s 로 단축 | alarm-popup.js:14 한 줄 | 본인 모달 차단 60s 후 자동 해제 | ⭐ 시연 안전망 |
| (b) Event RESOLVED 시 클라 _AckStore 동기 삭제 | alarm-popup.js 에 RESOLVED handler 추가 | 운영자가 "조치 완료" 누르면 본인 ack 도 해제 | ⭐ 멘탈 모델 정합 |
| (c) _AckStore 자체 제거 | alarm-popup.js 의 G4 게이트 삭제 | dedup 만 60s — 본인이 ack 한 알람도 60s 후 다시 옴 | 토스트 폭주 위험 |
| (d) ack 동작을 RESOLVED 통합 | UX·백엔드 재설계 | T5 sprint 본격 | ❌ 시연 후 |

§3.2 / §3.3 의 다른 증상은 시연 후 sprint (T4, T5) 본격 진입 시 함께 다룸.

---

> **본 문서 핵심 메시지**: 운영자가 짚은 3가지 증상은 (A) 클라이언트 G4 _AckStore 24h 영구 차단이 1순위 의심, (B) catch-up 결과가 클라 dedup 에 차단되는 시나리오와 AI+룰 의도적 분리, (C) ack vs RESOLVED 멘탈 모델 분리 자체가 운영자에게 혼선을 만드는 구조. 시연 D-day (2026-06-14) 전까지 최소한 §7 (a)+(b) — _AckStore TTL 단축 + RESOLVED 시 동기 삭제 — 는 검토 필요. 다른 항목은 T5 sprint 본격 진입 시 통합 재설계 대상.
