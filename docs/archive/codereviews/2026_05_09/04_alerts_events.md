# 04. 알람·이벤트 (Alerts · Events · Celery↔FastAPI Bridge)

## 1. 범위

### 1.1 API 엔드포인트
| URL | 메서드 | 뷰 | 권한 |
|---|---|---|---|
| `/alerts/api/my-status/` | GET | MyStatusView | IsAuthenticated |
| `/alerts/api/worker-summary/` | GET | WorkerSummaryView | IsAuthenticated (관리자만) |
| `/alerts/api/alarms/` | GET | AlarmRecordViewSet (RO) | IsAuthenticated |
| `/alerts/api/alarms/<id>/` | GET | AlarmRecordViewSet (RO) | IsAuthenticated |
| `/alerts/api/alarms/summary/` | GET | AlarmRecordViewSet.summary action | IsAuthenticated |
| `/alerts/api/events/` | GET, POST, ... | EventViewSet | IsAuthenticated |
| `/alerts/api/events/<id>/` | GET, PATCH, DELETE | EventViewSet | IsAuthenticated |
| **fastapi** `/internal/alarms/push/` | POST | push_alarm | localhost 전용 |
| **fastapi** `/ws/worker/{user_id}/` | WS | worker_clients | (인증 미정) |

### 1.2 백엔드 파일
- [drf-server/apps/alerts/views/alarm_record.py](../../../drf-server/apps/alerts/views/alarm_record.py) — 296줄 (MyStatusView, WorkerSummaryView, AlarmRecordViewSet)
- [drf-server/apps/alerts/views/event.py](../../../drf-server/apps/alerts/views/event.py)
- [drf-server/apps/alerts/services/alarm_service.py](../../../drf-server/apps/alerts/services/alarm_service.py)
- [drf-server/apps/alerts/services/event_service.py](../../../drf-server/apps/alerts/services/event_service.py)
- [drf-server/apps/alerts/services/merge_policy.py](../../../drf-server/apps/alerts/services/merge_policy.py)
- [drf-server/apps/alerts/services/policy_matcher.py](../../../drf-server/apps/alerts/services/policy_matcher.py)
- [drf-server/apps/alerts/selectors/{active_events,alarm_timeline,event_history}.py](../../../drf-server/apps/alerts/selectors/)
- [drf-server/apps/alerts/tasks.py](../../../drf-server/apps/alerts/tasks.py) — **432줄** Celery 태스크
- [fastapi-server/internal/routers/alarm_router.py](../../../fastapi-server/internal/routers/alarm_router.py) — 66줄 브리지
- [fastapi-server/websocket/state.py](../../../fastapi-server/websocket/state.py) — `active_alarms`, `alarm_signal`, `worker_clients`

### 1.3 프론트엔드 파일
- [drf-server/static/js/shared/alarm-ws.js](../../../drf-server/static/js/shared/alarm-ws.js) — 35줄, 비대시보드 페이지용 알람 수신
- [drf-server/static/js/shared/alarm-popup.js](../../../drf-server/static/js/shared/alarm-popup.js) — 팝업 렌더
- [drf-server/static/js/shared/worker-ws.js](../../../drf-server/static/js/shared/worker-ws.js) — 작업자 개인 채널
- [drf-server/static/js/detail/event_list.js](../../../drf-server/static/js/detail/event_list.js)
- [drf-server/static/js/detail/event_detail.js](../../../drf-server/static/js/detail/event_detail.js)
- [drf-server/templates/components/alarm_popup.html](../../../drf-server/templates/components/alarm_popup.html)
- [drf-server/templates/snb_details/monitoring_events.html](../../../drf-server/templates/snb_details/monitoring_events.html), [event_detail.html](../../../drf-server/templates/snb_details/event_detail.html)

## 2. 기능 흐름

### 2.1 센서 임계치 초과 → 브라우저 알람 (핵심 시퀀스)
```
1. fastapi gas_router/power_router 수신 → service에서 임계치 비교
2. fastapi가 DRF로 측정값 POST (/api/monitoring/gas|power/data/)
3. DRF GasData/PowerData.save() → signal/post_save 또는 Celery delay
4. Celery 태스크 (apps/alerts/tasks.py):
   ├─ policy_matcher: 어떤 정책에 해당하는지
   ├─ merge_policy: 같은 sensor + 짧은 시간 내 병합 여부
   ├─ AlarmRecord 생성 (혹은 Event에 묶기)
   └─ POST http://127.0.0.1:8001/internal/alarms/push/ (localhost)
5. fastapi alarm_router.push_alarm:
   ├─ client_host in ("127.0.0.1","::1","localhost") 체크
   ├─ active_alarms.append(payload) + alarm_signal.set()
   └─ 지오펜스 + worker_id 있으면 worker_clients[user_id].send_json()
6. fastapi alarm_flush_loop이 alarm_signal에 깨어남
7. broadcast.build_broadcast_payload() → sensor_clients 전체 broadcast
8. 브라우저 alarm-ws.js (WSClient 통해 /ws/sensors/ 구독):
   ├─ data.alarms[]를 alarm_level/message/sensor_name 키로 변환
   ├─ alarm.is_new_event=true → AlarmPopup.show()
   ├─ CustomEvent('newAlarmEvent') dispatch
   └─ risk_level=='normal' → AlarmToast (해소 토스트)
```

### 2.2 본인 위험도 조회 (worker UI)
```
1. /dashboard/safety/* 페이지 진입 → fetch GET /alerts/api/my-status/
2. MyStatusView.get:
   ├─ Event.filter(worker=request.user).exclude(status=RESOLVED)
   ├─ DANGER 있으면 "danger", WARNING 있으면 "warning", 없으면 "normal"
   └─ 응답 봉투 {status, code, data:{worker_id, status, active_risk_level}}
```

### 2.3 관리자 위험도 집계
```
1. 관리자 페이지 → GET /alerts/api/worker-summary/
2. WorkerSummaryView.get:
   ├─ user_type 체크 (PermissionDenied raise)
   ├─ facility 없으면 0 응답
   ├─ facility 작업자 ids 조회
   ├─ Event 조회 + Python에서 worker_max_level 계산
   └─ {total/normal/warning/danger}_count 응답
```

### 2.4 이벤트 상세
```
1. /dashboard/monitoring/events/<id>/ → event_detail.js
2. GET /alerts/api/events/<id>/ + GET /alerts/api/alarms/?event=<id>
3. EventViewSet + AlarmRecordViewSet 응답 → 타임라인 렌더
```

## 3. 백엔드 소견

### 3.1 일반 코드 리뷰
- **[중] 응답 봉투 일관성 결여**
  [MyStatusView/WorkerSummaryView](../../../drf-server/apps/alerts/views/alarm_record.py#L80)는 `{"status":"success","code":200,"data":{...}}` 봉투. 한편 [AlarmRecordViewSet.summary](../../../drf-server/apps/alerts/views/alarm_record.py#L280)는 `{"last_24h_total":..,"last_24h_danger":..}` raw. drf-server 전반의 봉투 정책이 settings의 `EXCEPTION_HANDLER`(standard_exception_handler)와 어긋남 — 실패 시는 표준화, 성공 시는 view마다 자유. 정책 통일 필요.
- **[중] 권한 체크가 view body에서 raise**
  [WorkerSummaryView.get:150-151](../../../drf-server/apps/alerts/views/alarm_record.py#L150-L151) `if user_type not in (...) raise PermissionDenied`. `permission_classes = [IsSuperAdminOrFacilityAdmin]`로 옮기는 게 일관·테스트 쉬움.
- **[중] WorkerSummaryView 집계 Python에서 수행**
  [alarm_record.py:199-215](../../../drf-server/apps/alerts/views/alarm_record.py#L199-L215) defaultdict + for loop. Django ORM의 `Case/When` + aggregate로 1쿼리 처리 가능. 작업자 수가 많아질수록 비효율.
- **[중] view에서 직접 Event/AlarmRecord ORM 조회**
  alerts에는 selectors/가 풀 구조로 존재하는데 [MyStatusView.get:81-87](../../../drf-server/apps/alerts/views/alarm_record.py#L81-L87)가 직접 `Event.objects.filter(...)`. selectors/active_events.py로 위임하면 정의 한 곳·캐시·테스트 모두 이득.
- **[하] LEVEL_PRIORITY = {DANGER:2, WARNING:1}**
  [alarm_record.py:31](../../../drf-server/apps/alerts/views/alarm_record.py#L31) 모듈 상수. RiskLevel enum에 priority property로 두는 게 더 응집도 높음.
- **[중] tasks.py 432줄 — 매우 큰 단일 파일**
  실제 본문은 보지 않았지만 432줄에 정책 매칭·병합·Celery·HTTP 호출·로깅이 한데. 도메인별 분리(`tasks/alarm_create.py`, `tasks/notification_send.py` 등) 고려.

### 3.2 아키텍처/레이어
- **[참고] alerts는 컨벤션 모범 사례**
  selectors(3) + services(4) + views(2)로 분리 잘 되어 있음. 단, view가 여전히 selector를 쓰지 않고 직접 ORM 호출하는 경우 산재 — selector를 활용하도록 통일.
- **[중] 정책 매칭(policy_matcher.py)·병합(merge_policy.py)을 Celery 외에서 호출 가능?**
  관리자 UI가 "정책 미리보기" 같은 기능 추가 시 service 재사용 가능해야 함. service들이 Celery context에 묶여 있지 않은지(예: Celery task 데코레이터 안에 비즈니스 로직 인라인) 확인 필요.

### 3.3 보안 관점 (요약)
- **[상] /internal/alarms/push/ — localhost 검증만으로 충분한가**
  [alarm_router.py:48-50](../../../fastapi-server/internal/routers/alarm_router.py#L48-L50) `request.client.host in (127.0.0.1, ::1, localhost)`. 같은 호스트의 다른 프로세스가 알람을 임의 push할 수 있음. **추가 인증** 권장: shared secret(`DRF_SERVICE_TOKEN`을 양방향 사용) 또는 mutual auth. 현재 fastapi → drf 방향엔 토큰을 보내지만 drf → fastapi 방향엔 없음.
- **[상] /ws/worker/{user_id}/ 인증 부재 (가능성)**
  worker_clients 채널이 user_id만으로 식별 → 임의 user_id로 접속 시 다른 사람의 개인 알람 수신 가능 여부 확인 필요. JWT 핸드셰이크 토큰(쿼리 또는 첫 메시지)으로 인증 필수. (09 도메인에서 정밀 검증)
- **[중] AlarmPayload `extra: "allow"`**
  [alarm_router.py:18](../../../fastapi-server/internal/routers/alarm_router.py#L18) Pydantic이 미정의 필드를 통과시킴. DRF 측이 임의 키를 넣어도 그대로 active_alarms에 적재. 의도(유연성)는 이해되나, 알람 페이로드는 정확히 명세되어야 다운스트림(브라우저)에서 안전. `extra="ignore"` + 명시 필드만 허용 권장.
- **[중] `except Exception: worker_clients.pop()`**
  [alarm_router.py:62-63](../../../fastapi-server/internal/routers/alarm_router.py#L62-L63) 광범위 except. 어떤 에러든 클라이언트를 큐에서 제거. 일시적 네트워크 오류로도 영구 제거 → 다음 메시지부터 미수신. 적어도 로깅 + WebSocket 관련 예외만 잡도록 좁히기.

## 4. 프론트엔드(JS/HTML) 소견

### 4.1 백엔드 contract 정합성
- **[상] alarm-ws.js의 키 리네이밍이 fragility 핵심**
  [alarm-ws.js:16-23](../../../drf-server/static/js/shared/alarm-ws.js#L16-L23):
  - `risk_level` → `alarm_level`
  - `summary` → `message`
  - `source_label` → `sensor_name`
  - 그 외(`is_new_event`, `gas_type`, `event_id`) 그대로
  서버가 `summary`를 `description`으로 바꾸면 silent 누락. 백엔드와 프론트가 같은 이름을 쓰는 게 fragility 최소. 정 리네이밍이 필요하면 `shared/alarm-mapper.js`에 매핑 함수 단일화 + 단위 테스트.
- **[중] CustomEvent 'newAlarmEvent' — 누가 구독?**
  [alarm-ws.js:28](../../../drf-server/static/js/shared/alarm-ws.js#L28) document.dispatchEvent. 어떤 모듈이 listen 하는지 grep 필요. 명시되지 않은 의존 — 문서화 또는 EventBus 패턴(`shared/event-bus.js`)으로 단일화.

### 4.2 알람 노이즈/UX
- **[중] alarms[] 배열 모두 즉시 팝업?**
  [alarm-ws.js:25-27](../../../drf-server/static/js/shared/alarm-ws.js#L25-L27) `is_new_event=true`인 모든 알람에 `AlarmPopup.show`. 1초 broadcast tick에 5개 이상 알람 동시 도착 시 팝업 5개 → UX 폭주. 큐잉/throttle 또는 그룹핑(같은 sensor 1개로) 검토.
- **[하] AlarmToast 미정의 시 silent skip**
  `if (typeof AlarmToast !== 'undefined')` — 페이지에 로드 안 됐을 때 silent. 의도이긴 하나 디버깅 시 혼란.

### 4.3 ws-client.js 캐시 의존
- **[중] 같은 페이지에서 dashboard/websocket.js + shared/alarm-ws.js 둘 다 로드 시 단일 연결 보장**
  WSClient 캐시 동작. 다만 두 파일이 각자 `onMessage` 등록 → 메시지 콜백 두 번 실행됨(연결만 단일). 중복 처리 방지를 위한 메시지 dedupe 필요 여부 확인. 문서화 명확히.

## 5. 개선 제안

### D1. /internal/alarms/push/ 인증 강화 [상 · 소]
- **왜 필요?**: localhost 검증만으로 같은 호스트의 다른 프로세스 위변조 가능. 컨테이너/호스트 공유 환경에서 위험.
- **장점**: 호스트 내 격리·추적 가능.
- **단점**: Celery 태스크가 토큰을 헤더에 추가해야 함 (1줄).
- **변경 위치**: [tasks.py](../../../drf-server/apps/alerts/tasks.py) FASTAPI 호출 시 `Authorization: Bearer <DRF_SERVICE_TOKEN>` 헤더, [alarm_router.py:47](../../../fastapi-server/internal/routers/alarm_router.py#L47) 진입점에서 토큰 검증.

### D2. /ws/worker/{user_id}/ JWT 인증 [상 · 중]
- **왜 필요?**: 임의 user_id로 접속 시 다른 사용자의 개인 알람을 가로챌 가능성.
- **장점**: 개인 알림 격리 / 정보 누출 차단.
- **단점**: JS도 JWT를 쿼리/첫 메시지로 전송 (1줄).
- **변경 위치**: 09 도메인의 ws_router worker 엔드포인트, [shared/worker-ws.js](../../../drf-server/static/js/shared/worker-ws.js).

### D3. 응답 봉투 정책 통일 [중 · 중]
- **왜 필요?**: 일부 view는 `{status, code, data}` 봉투, 일부는 raw. 클라이언트가 두 가지 패턴 모두 처리해야 함.
- **장점**: 클라이언트 단일 처리·에러 핸들링 단일화.
- **단점**: 기존 응답 사용처(JS) 갱신 필요.
- **변경 위치**: 정책 결정 후 `apps/core/responses.py::success(data)` 헬퍼로 일관 적용. 새 view는 헬퍼 강제.

### D4. WorkerSummaryView 권한 클래스 화 + 1쿼리 집계 [중 · 소]
- **왜 필요?**: view body의 if-raise는 권한 클래스보다 발견 어려움. 집계는 ORM에서.
- **장점**: 일관성·성능 향상.
- **단점**: 없음.
- **변경 위치**: `permission_classes = [IsSuperAdminOrFacilityAdmin]` 추가, aggregation을 [selectors/active_events.py](../../../drf-server/apps/alerts/selectors/active_events.py)에 위임 (Case/When + Count).

### D5. AlarmPayload 명시 필드만 허용 [중 · 소]
- **왜 필요?**: `extra="allow"`는 위변조·타이포에 무방비.
- **장점**: 다운스트림 안전·OpenAPI 문서 정확.
- **단점**: 신규 필드 추가 시 schema 갱신 필요(좋은 일).
- **변경 위치**: [alarm_router.py:18](../../../fastapi-server/internal/routers/alarm_router.py#L18) `extra="ignore"` 또는 `forbid`.

### D6. selectors 적극 활용 [중 · 중]
- **왜 필요?**: alerts는 selectors가 풀 구조인데 view에서 직접 ORM 호출. 같은 정책이 여러 view에서 반복.
- **장점**: 정책 변경 1곳·캐시·테스트 용이.
- **단점**: import 정리.
- **변경 위치**: [MyStatusView.get](../../../drf-server/apps/alerts/views/alarm_record.py#L80), [WorkerSummaryView.get](../../../drf-server/apps/alerts/views/alarm_record.py#L149) 모두 selectors/active_events.py 위임.

### D7. alarm-ws.js 키 매핑 단일화 [중 · 소]
- **왜 필요?**: 백엔드 키 변경 시 silent 누락 위험. 매핑이 한 줄씩 흩어져 있음.
- **장점**: 한 곳 변경 / 테스트 가능.
- **단점**: 가장 좋은 건 매핑 자체를 없애고 백엔드와 동일 키 사용.
- **변경 위치**: 추천 — 백엔드 키 그대로 사용. 차선 — [shared/alarm-mapper.js](../../../drf-server/static/js/shared/) 신규.

### D8. 알람 폭주 방지 (UX) [중 · 소]
- **왜 필요?**: 동시 알람 다수 시 팝업 누적 → 사용자 차단.
- **장점**: 사용자 신뢰 향상.
- **단점**: 그룹핑 정책 합의 필요(예: 같은 source_label은 5초 내 1개만).
- **변경 위치**: [alarm-popup.js](../../../drf-server/static/js/shared/alarm-popup.js)에 throttle/queue.

### D9. tasks.py 분할 [하 · 중]
- **왜 필요?**: 432줄 단일 파일은 추적·git 충돌 어려움.
- **변경 위치**: [tasks/alarm_pipeline.py, tasks/notify_external.py](../../../drf-server/apps/alerts/tasks/) (도메인별).

### D10. CustomEvent → EventBus [하 · 소]
- **왜 필요?**: document.dispatchEvent는 누가 구독하는지 grep해야 알 수 있음.
- **변경 위치**: [shared/event-bus.js](../../../drf-server/static/js/shared/) 신규.

## 6. 구현 추천 순서

### 1단계 — 보안 (즉시) ⚡
- **D1** /internal/alarms/push/ 인증 토큰
- **D2** /ws/worker/{user_id}/ JWT (09와 함께)
- **D5** AlarmPayload `extra="ignore"` (한 줄)
- **이유**: 알람 위변조 + 개인 알림 정보 누출은 직접적 사고로 이어짐. 변경 작은데 효과 큼.

### 2단계 — 정합성·일관성 (1주 내) 🔧
- **D3** 응답 봉투 정책 통일
- **D4** WorkerSummaryView 권한 + 집계 ORM화
- **D6** selectors 활용 통일
- **이유**: 컨벤션 정합성 + 성능 함께 개선.

### 3단계 — UX (다음 sprint) ✨
- **D7** alarm-ws 키 매핑 단일화 (또는 백엔드 키 통일)
- **D8** 알람 throttle/queue
- **D10** EventBus 패턴

### 4단계 — 클린업 (여유 시) 🧹
- **D9** tasks.py 분할

### ⚠️ 주의사항 (초보자용)
- **D1·D2 보안 변경은 e2e 테스트(PR-H) 회귀 필수**: 인증 강화로 기존 테스트가 깨지면 알람 흐름 자체가 막힘. PR-H 4종 테스트가 모두 통과하는지 확인 후 머지.
- **D7 키 통일은 PR 두 개로 분리 권장**: ① alarm-mapper.js 도입(매핑 단일화) → ② 매핑 제거 + 백엔드 키 통일. 한 번에 하면 어디서 깨졌는지 격리 어려움.
- **D8 throttle은 운영에서 알람 누락처럼 보일 수 있음**: 사용자 교육 + 같은 소스의 누적 알람을 별도 보드에서 볼 수 있게 보강.
