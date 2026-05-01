# 기능정의서 — CM-07 알람 팝업 개선 및 4차 고도화 계획

> 작성일: 2026-04-30
> 작성자: CJY
> 브랜치: `feature/MN-04_refactor`
> 대상 기능 ID: **CM-07** (실시간 알림 팝업 / 이벤트 현황 실시간 갱신)

---

## 1. 기능 목록표

| 대분류 | 화면명 | 기능ID | 기능명 | 기능 목적 | 사용자 시나리오 | 엣지 정보 | 유효성 처리 | 예외 조건 | 에러 처리 | 백엔드 처리 | 프론트엔드 처리 | 참고사항 |
|:--|:--|:--|:--|:--|:--|:--|:--|:--|:--|:--|:--|:--|
| 모니터링 | 알람 팝업 | CM-07-A1 | 팝업 버튼 동작 수정 | X·확인 버튼으로 팝업 닫기 | 팝업 표시 → X 또는 확인 클릭 → 팝업 닫힘 | 대시보드 외 페이지에서 init 미호출 | DOMContentLoaded 자동 init | 버튼 요소 없음 → optional chaining 처리 | 무시 (팝업 없는 페이지) | 없음 | `alarm-popup.js` DOMContentLoaded 자동 init 추가 | 기존에는 `app.js`만 init 호출 |
| 모니터링 | 알람 팝업 | CM-07-A2 | 상세 확인 URL 수정 | 알람 ID 기반 이벤트 상세 페이지 이동 | 상세 확인 클릭 → `/dashboard/monitoring/events/{id}/` 이동 | event_id 없을 시 목록 페이지로 fallback | event_id 존재 여부 체크 | id 없음 → 목록 `/dashboard/monitoring/events/` | fallback 이동 | 없음 | `_currentId` 추적, `_goDetail()` URL 수정 | `event_id`는 WebSocket 메시지에 포함 |
| 모니터링 | 이벤트 현황 | CM-07-A3 | 이벤트 목록 실시간 갱신 | 알람 수신 즉시 목록/카운트 자동 갱신 | 알람 팝업 표시 → 새로고침 없이 목록 업데이트 | 병합 알람(`is_new_event=False`)도 갱신 필요 | 없음 | `event-tbody` 없는 페이지 → 이벤트 무시 | 무시 | `active_alarms` WS 메시지 유지 | `newAlarmEvent` 커스텀 이벤트로 `loadCounts()` + `loadEvents()` 재호출 | `alarm-ws.js`, `worker-ws.js` 모두 적용 |
| 모니터링 | 알람 팝업 | CM-07-A4 | 미조치 이벤트 재알림 | 조치 전 동일 이벤트 5분 후 팝업 재발송 | 알람 발생 → 5분 미조치 → 새 센서 데이터 수신 → 팝업 재표시 | 쿨다운 이내 병합 → 재알림 없음 | `last_notified_at` 기준 5분 경과 여부 | DB 락 발생 시 Celery retry (5초) | retry 후 재처리 | `Event.last_notified_at` + `RENOTIFY_COOLDOWN_MINUTES=5` | `is_new_event=True`로 팝업 재표시 | SQLite 환경에서 DB 락으로 지연 가능 |

---

## 2. 요구사항 정의서

### [REQ-CM-07-A1] 팝업 버튼 동작 수정

- **분류**: 버그 수정
- **중요도**: 상
- **기능 목적**: 모든 페이지에서 알람 팝업 버튼(X, 확인, 상세 확인)이 동작하도록 보장
- **요구사항 상세 설명**:
  - 기존에는 `app.js`의 `initApp()` 에서만 `AlarmPopup.init()` 호출
  - `monitoring_events.html`, `event_detail.html`, `monitoring_realtime.html` 등 대시보드 외 페이지는 `init()` 미호출 → 버튼 이벤트 리스너 미등록
  - `alarm-popup.js` 하단에 `DOMContentLoaded` 리스너 추가하여 스크립트 로드 시 자동 init
  - `_inited` 플래그로 이중 등록 방지
- **백엔드 처리**: 없음
- **예외 사항**: `alarm-popup.html`이 include되지 않은 페이지에서는 요소 없음 → optional chaining(`?.`)으로 무시

---

### [REQ-CM-07-A2] 상세 확인 URL 수정

- **분류**: 버그 수정
- **중요도**: 상
- **기능 목적**: 상세 확인 버튼 클릭 시 해당 이벤트 상세 페이지로 직접 이동
- **요구사항 상세 설명**:
  - 기존 `_goDetail()`은 `/dashboard/monitoring/events/` 목록 페이지로 고정 이동
  - WebSocket 메시지의 `event_id`를 `_currentId`에 저장
  - `_goDetail()` 에서 `_currentId` 있으면 `/dashboard/monitoring/events/{id}/`, 없으면 목록 페이지로 fallback
  - `close()` 호출 시 `_currentId = null` 초기화
- **백엔드 처리**: 없음 (event_id는 `tasks.py`에서 이미 WS 메시지에 포함)

---

### [REQ-CM-07-A3] 이벤트 목록 실시간 갱신

- **분류**: 기능 개선
- **중요도**: 상
- **기능 목적**: 알람 수신 즉시 페이지 새로고침 없이 이벤트 목록과 카운트 갱신
- **요구사항 상세 설명**:
  - 기존에는 `alarm-ws.js`에서 `is_new_event=True`일 때만 `newAlarmEvent` 발행
  - 병합 알람(`is_new_event=False`)도 WS 메시지는 전송되므로 목록 갱신 필요
  - `newAlarmEvent` 발행을 `is_new_event` 조건 밖으로 이동 → 모든 알람에서 발행
  - `event_list.js`에서 `newAlarmEvent` 수신 시 `loadCounts()` + `loadEvents(currentStatus)` 재호출
  - `worker-ws.js`(지오펜스 알람)에도 동일한 `newAlarmEvent` 발행 추가
- **백엔드 처리**: 없음 (기존 WS 메시지 구조 유지)

---

### [REQ-CM-07-A4] 미조치 이벤트 재알림

- **분류**: 기능 개선
- **중요도**: 상
- **기능 목적**: 조치 전 동일 이벤트가 지속될 때 5분 주기로 팝업 재발송
- **요구사항 상세 설명**:
  - `Event` 모델에 `last_notified_at` 필드 추가 (nullable DateTimeField)
  - 신규 이벤트 생성 시 `last_notified_at = now()` 저장
  - 병합 처리 시 `now() - last_notified_at >= 5분` 이면 `last_notified_at` 갱신 후 `alarm` 반환 → `is_new_event=True`로 팝업 재발송
  - 쿨다운 이내(`< 5분`) 병합 시 기존대로 `return active_event, None` → 팝업 없음
  - 쿨다운 상수: `RENOTIFY_COOLDOWN_MINUTES = 5` (필요 시 조정)
- **백엔드 처리**: `event_service.py` 병합 분기에 쿨다운 로직 추가, `Event` 모델 필드 추가
- **예외 사항**: SQLite 환경에서 DB 락 발생 시 Celery가 5초 후 retry — 재알림 시점 지연 가능

---

## 3. API 명세서

> 이번 개선은 기존 API 구조 변경 없음. WebSocket 메시지 구조 및 내부 HTTP 엔드포인트 유지.

### WebSocket 메시지 구조 (`/ws/sensors/`)

```json
{
  "alarms": [
    {
      "alarm_type": "gas_threshold",
      "risk_level": "danger",
      "source_label": "테스트기기",
      "summary": "[긴급] H₂S 위험 수준 초과 (50.0 ppm) — 즉시 대피하세요.",
      "is_new_event": true,
      "event_id": 42,
      "gas_type": "h2s",
      "measured_value": 50.0,
      "threshold_value": 10.0
    }
  ]
}
```

### 내부 알람 푸시 (`POST /internal/alarms/push/`)

| 필드 | 타입 | 설명 |
|:--|:--|:--|
| `alarm_type` | string | `gas_threshold` / `geofence_intrusion` |
| `risk_level` | string | `danger` / `warning` / `normal` |
| `is_new_event` | bool | **True**: 신규 이벤트 또는 쿨다운 초과 재알림 → 팝업 발송 |
| `event_id` | int? | 이벤트 ID (상세 페이지 이동에 사용) |
| `source_label` | string | 발생원 이름 |
| `summary` | string | 알람 요약 메시지 |

---

## 4. 흐름도

### 알람 팝업 버튼 동작 흐름

```
페이지 로드
    └─ DOMContentLoaded
           └─ AlarmPopup.init()  ← 모든 페이지에서 자동 실행
                  ├─ #alarm-popup-close   → close()
                  ├─ #alarm-popup-confirm → close()
                  └─ #alarm-popup-detail  → _goDetail() → /events/{_currentId}/
```

### 알람 수신 → 목록 갱신 흐름

```
FastAPI WebSocket 메시지 수신 (alarm-ws.js / worker-ws.js)
    ├─ is_new_event=True  → AlarmPopup.show(alarmData)
    └─ [항상] document.dispatchEvent('newAlarmEvent')
                │
                └─ event_list.js 리스너
                       ├─ loadCounts()      ← 탭 카운트 갱신
                       └─ loadEvents(currentStatus)  ← 목록 갱신
```

### 재알림 쿨다운 흐름

```
센서 측정값 수신 → trigger_gas_alarms() → fire_danger_alarm_task.delay()
    └─ create_alarm_and_event()
           ├─ 활성 Event 없음
           │      └─ 신규 Event 생성 + last_notified_at=now() → alarm 반환 → is_new_event=True → 팝업
           └─ 활성 Event 있음 (병합)
                  ├─ now() - last_notified_at >= 5분
                  │      └─ last_notified_at 갱신 + alarm 반환 → is_new_event=True → 팝업 재발송
                  └─ now() - last_notified_at < 5분
                         └─ None 반환 → is_new_event=False → 팝업 없음
```

---

## 5. 파일별 역할

| 서버 | 파일 경로 | 변경 내용 |
|:--|:--|:--|
| Frontend | `static/js/shared/alarm-popup.js` | DOMContentLoaded 자동 init 추가 / `_currentId` 추적 / `_goDetail()` URL 수정 |
| Frontend | `static/js/shared/alarm-ws.js` | `newAlarmEvent` 발행을 `is_new_event` 조건 밖으로 이동 |
| Frontend | `static/js/shared/worker-ws.js` | `newAlarmEvent` 발행 추가 |
| Frontend | `static/js/detail/event_list.js` | `newAlarmEvent` 리스너 추가 → `loadCounts()` + `loadEvents()` 재호출 |
| DRF | `apps/alerts/models/event.py` | `last_notified_at` 필드 추가 |
| DRF | `apps/alerts/services/event_service.py` | `RENOTIFY_COOLDOWN_MINUTES` 상수 / 병합 분기에 쿨다운 로직 추가 |
| DRF | `apps/alerts/migrations/0002_add_last_notified_at_to_event.py` | 마이그레이션 생성 및 적용 |

---

## 6. 디렉토리 경로

```
drf-server/
├── apps/
│   └── alerts/
│       ├── models/
│       │   └── event.py                  ← last_notified_at 필드 추가
│       ├── services/
│       │   └── event_service.py          ← 쿨다운 로직 추가
│       └── migrations/
│           └── 0002_add_last_notified_at_to_event.py  ← 신규
└── static/js/
    ├── shared/
    │   ├── alarm-popup.js                ← 자동 init / URL 수정
    │   ├── alarm-ws.js                   ← newAlarmEvent 위치 수정
    │   └── worker-ws.js                  ← newAlarmEvent 추가
    └── detail/
        └── event_list.js                 ← newAlarmEvent 리스너 추가
```

---

## 7. URL 정의서

| 서버 구분 | 메서드 | URL | 설명 |
|:--|:--|:--|:--|
| DRF | GET | `/dashboard/monitoring/events/` | 이벤트 목록 페이지 |
| DRF | GET | `/dashboard/monitoring/events/{id}/` | 이벤트 상세 페이지 (상세 확인 버튼 이동 대상) |
| DRF | GET | `/alerts/api/events/?status={status}` | 이벤트 목록 API (목록 갱신 시 호출) |
| FastAPI | WS | `ws://127.0.0.1:8001/ws/sensors/` | 브라우저 실시간 알람 수신 |
| FastAPI | WS | `ws://127.0.0.1:8001/ws/worker/{userId}/` | 작업자 개인 알람 수신 |
| FastAPI | POST | `http://127.0.0.1:8001/internal/alarms/push/` | Celery → FastAPI 내부 알람 브리지 |

---

## 8. 생성/처리 조건

### 알람 팝업 표시 조건
| 조건 | 팝업 표시 여부 |
|:--|:--|
| 신규 이벤트 생성 (`is_new_event=True`) | O |
| 병합 이벤트 + 쿨다운 5분 초과 | O (재알림) |
| 병합 이벤트 + 쿨다운 5분 이내 | X |
| 정상화 알람 (`risk_level=normal`) | X (토스트만 표시) |

### 이벤트 목록 갱신 조건
| 조건 | 목록 갱신 여부 |
|:--|:--|
| 신규 이벤트 알람 수신 | O |
| 병합 알람 수신 (`is_new_event=False`) | O (이번 개선으로 추가) |
| 정상화 알람 수신 | O |

### `last_notified_at` 갱신 조건
| 상황 | 처리 |
|:--|:--|
| 신규 Event 생성 | `last_notified_at = now()` |
| 병합 + 쿨다운 초과 | `last_notified_at = now()` 갱신 후 `alarm` 반환 |
| 병합 + 쿨다운 이내 | 갱신 없음, `None` 반환 |

---

## 9. 서버 실행 명령어

```bash
# DRF 서버
cd drf-server
.venv/bin/python manage.py runserver 0.0.0.0:8000

# Celery 워커
cd drf-server
.venv/bin/celery -A config worker -l info

# FastAPI 서버
cd fastapi-server
uvicorn app:app --host 0.0.0.0 --port 8001 --reload

# 마이그레이션 (이번 작업 신규)
cd drf-server
.venv/bin/python manage.py migrate alerts 0002
```

---

## 10. 테스트 방법 및 결과

### 확인 포인트 1 — 팝업 버튼 동작
1. `http://127.0.0.1:8000/dashboard/monitoring/events/` 접속
2. 테스트 알람 발생 → 팝업 표시
3. X 버튼 클릭 → 팝업 닫힘 확인
4. 확인 버튼 클릭 → 팝업 닫힘 확인
5. 상세 확인 클릭 → `/dashboard/monitoring/events/{id}/` 이동 확인

### 확인 포인트 2 — 이벤트 목록 실시간 갱신
1. 이벤트 현황 페이지 진입 (탭: 조치 필요)
2. 알람 발생 → 새로고침 없이 목록에 이벤트 행 추가 확인
3. 카운트 뱃지 숫자 증가 확인

### 확인 포인트 3 — 재알림
```
# Celery 로그에서 확인
new_event=True  → 신규 이벤트 (팝업 O)
new_event=False → 쿨다운 이내 병합 (팝업 X)
new_event=True  → 5분 후 재알림 (팝업 O)
```

---
---

# 4차 고도화 계획

> 현재 단계(3차)에서 구조적 제약으로 미적용 항목 정리
> 우선순위: **상 > 중 > 하**

---

## [4차-01] SQLite → PostgreSQL 전환 (우선순위: 상)

### 배경 및 문제
- 현재 SQLite 사용으로 Celery 멀티 워커 동시 쓰기 시 `database is locked` 발생
- `create_alarm_and_event()`의 `select_for_update()`가 SQLite에서 실질적으로 무력화
- 알람 처리 실패 → Celery retry 5초 지연 → 알람 수신 체감 지연

### Celery 로그에서 확인된 증상
```
ERROR/ForkPoolWorker-1] DANGER 알람 생성 실패: database is locked
INFO/ForkPoolWorker-1] Task retry: Retry in 5s: OperationalError('database is locked')
```

### 적용 내용
1. PostgreSQL 설치 및 DB 생성
2. `settings.py` DATABASES 설정 변경
   ```python
   DATABASES = {
       'default': {
           'ENGINE': 'django.db.backends.postgresql',
           'NAME': 'diconai',
           'USER': 'diconai_user',
           'PASSWORD': '...',
           'HOST': 'localhost',
           'PORT': '5432',
       }
   }
   ```
3. `psycopg2-binary` 패키지 추가
4. 기존 SQLite 데이터 마이그레이션 (`dumpdata` → `loaddata`)
5. `select_for_update()` 정상 동작 검증

### 기대 효과
- DB 락 오류 완전 해소
- Celery 워커 수 증가 가능 → 다중 알람 동시 처리
- `select_for_update()`로 이벤트 병합 레이스 컨디션 방지

---

## [4차-02] 알람 즉시 브로드캐스트 (우선순위: 상)

### 배경 및 문제
- 현재 `alarm_flush_loop()`가 5초마다 폴링하여 알람을 브라우저에 전달
- FastAPI가 알람을 받은 즉시 전송하지 않아 최대 5초 체감 지연 발생

### 현재 흐름
```
Celery → _push_to_ws() → FastAPI active_alarms.append()
    → alarm_flush_loop() sleep(5) → 브라우저 전송  ← 최대 5초 대기
```

### 적용 내용
`alarm_router.py`에서 알람 수신 즉시 연결된 클라이언트에 직접 브로드캐스트

```python
# internal/routers/alarm_router.py
from websocket.services.broadcast import build_broadcast_payload
from websocket.state import active_alarms, sensor_clients, worker_clients

@router.post("/alarms/push/")
async def push_alarm(request: Request, alarm: AlarmPayload):
    ...
    active_alarms.append(payload)

    # 즉시 브로드캐스트 (폴링 루프 대기 없음)
    if sensor_clients:
        broadcast = build_broadcast_payload()
        dead = []
        for ws in list(sensor_clients):
            try:
                await ws.send_json(broadcast)
            except Exception:
                dead.append(ws)
        for ws in dead:
            sensor_clients.remove(ws)
    ...
```

> ⚠️ 3차에서 시도했으나 알람이 뜨지 않는 현상 발생 → 원인 재분석 후 적용
> PostgreSQL 전환 후 DB 락 문제 해소 상태에서 재시도 권장

### 기대 효과
- 알람 수신 → 브라우저 전달 지연: 5초 → ~수백ms

---

## [4차-03] gas_type 병합 키 추가 (우선순위: 중)

### 배경 및 문제
- 현재 이벤트 병합 키: `(facility_id, event_type, sensor_id)`
- 동일 기기에서 O2, CO2 등 **다른 가스 타입** 알람이 동시 발생해도 하나의 이벤트로 병합
- Redis 알람 상태 키는 `alarm:state:{sensor_id}:{gas}` — 가스 타입별로 관리하는 것과 불일치

### 적용 내용
1. `Event` 모델에 `gas_type` 필드 추가 (nullable CharField)
2. `event_service.py` 병합 쿼리에 `gas_type` 필터 추가
   ```python
   if gas_type:
       event_qs = event_qs.filter(alarms__gas_type=gas_type).distinct()
   ```
3. `Event.objects.create()` 시 `gas_type` 저장
4. 마이그레이션 생성 및 적용

### 기대 시나리오
```
기기-1 O2 임계치 초과  → Event #10 (gas_type=o2) 생성 → 팝업 O
기기-1 CO2 임계치 초과 → Event #11 (gas_type=co2) 생성 → 팝업 O  (현재는 #10에 병합 → 팝업 X)
```

---

## [4차-04] 알람 에스컬레이션 정책 고도화 (우선순위: 하)

### 배경
- 현재 재알림 쿨다운은 단순 5분 고정
- 미조치 시간이 길어질수록 재알림 주기를 줄여 긴급도 상승 표현 필요

### 적용 내용
| 미조치 경과 시간 | 재알림 주기 |
|:--|:--|
| 0 ~ 5분 | 최초 1회 |
| 5 ~ 15분 | 5분마다 |
| 15 ~ 30분 | 3분마다 |
| 30분 이상 | 1분마다 |

- `Event` 모델에 `escalation_level` 필드 추가 (0~3)
- `event_service.py` 병합 분기에서 경과 시간 기반 쿨다운 계산

---

## [4차-05] Celery 워커 최적화 (우선순위: 중)

### 배경
- PostgreSQL 전환 이후 동시성 문제 해소되나 워커 수/설정 미최적화 상태

### 적용 내용
```python
# settings.py
CELERY_WORKER_CONCURRENCY = 4          # CPU 코어 수에 맞게 조정
CELERY_TASK_ACKS_LATE = True           # 태스크 완료 후 ack → 실패 시 재처리 보장
CELERY_WORKER_PREFETCH_MULTIPLIER = 1  # 태스크 과도 선점 방지
CELERY_TASK_ROUTES = {
    'apps.alerts.tasks.fire_danger_alarm_task':  {'queue': 'alarm_high'},
    'apps.alerts.tasks.fire_warning_alarm_task': {'queue': 'alarm_low'},
    'apps.alerts.tasks.fire_clear_notification_task': {'queue': 'alarm_low'},
}
```
- DANGER 알람 전용 high-priority 큐 분리 → 경보 처리 지연 최소화

---

## 4차 적용 우선순위 요약

| 순위 | 항목 | 이유 |
|:--|:--|:--|
| 1 | PostgreSQL 전환 [4차-01] | DB 락이 모든 알람 지연의 근본 원인 |
| 2 | 즉시 브로드캐스트 [4차-02] | PostgreSQL 전환 후 재시도 필요 |
| 3 | gas_type 병합 키 [4차-03] | 다중 가스 동시 알람 정확도 향상 |
| 4 | Celery 워커 최적화 [4차-05] | PostgreSQL 전환 후 효과 극대화 |
| 5 | 에스컬레이션 정책 [4차-04] | 운영 경험 축적 후 적용 |
