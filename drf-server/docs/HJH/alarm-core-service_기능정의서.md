# 알람 코어 서비스 기능정의서

> 작성자: 정휘훈 / 최종 수정: 2026-04-29
> 브랜치: `feature/alarm-core-service`
> 관련 기능 ID: **CM-07** (이벤트 현황 / 실시간 알람 팝업 / 조치 이력)

---

## 1. 기능 목록표

| 대분류 | 화면명 | 기능ID | 기능명 | 기능 목적 | 사용자 시나리오 | 백엔드 처리 | 프론트엔드 처리 |
|--------|--------|--------|--------|-----------|-----------------|-------------|-----------------|
| 모니터링 | 전체 페이지 공통 | CM-07-04 | 실시간 위험 알람 팝업 | 새 위험/주의 이벤트 발생 시 어느 페이지에서나 즉시 팝업 표시 | 위험 감지 → Celery → FastAPI WS → 브라우저 팝업 | FastAPI `alarm_flush_loop` + `is_new_event` 플래그 | `alarm-ws.js` → `AlarmPopup.show()` |
| 모니터링 | 이벤트 상세 | CM-07-05 | 조치 상태 변경 이력 기록 | 조치 상태 변경 시 EventLog에 자동 기록 | 상태 변경 버튼 → API → EventLog 생성 | `EventLog.objects.create()` | — |

---

## 2. 요구사항 정의서

### [REQ-CM-07-04] 실시간 위험 알람 팝업

- **분류**: 기능적 요구사항
- **중요도**: 상
- **기능 목적**: 새 위험/주의 이벤트 발생 시 어느 페이지에서든 2초 이내 팝업으로 알림
- **요구사항 상세 설명**:
  - 새 이벤트(`is_new_event=True`)만 중앙 차단형 팝업 — 기존 활성 이벤트 반복 알람 없음
  - 이벤트 조치완료(`resolved`) 이후 동일 센서에서 새 위험 감지 시 팝업 재발생
  - 정상화(`risk_level=normal`) 알람은 우하단 토스트로 표시
  - 팝업 최대 큐 5개 (초과 시 무시)
  - 팝업 버튼: "상세 확인" (이벤트 상세 페이지 이동) / "확인" (닫기)
  - 수신 가능 페이지: 대시보드, 이벤트 현황, 이벤트 상세
- **백엔드 처리 및 인터페이스**:
  - Redis 상태 머신 (`alarm:state:{sensor_id}:{gas}`): 정상→위험 전환 시에만 Celery 실행
    - 위험→위험 유지: Celery 미실행 → 팝업 없음 (중복 방지 핵심)
  - Celery `fire_danger_alarm_task`: `create_alarm_and_event()` 결과로 `is_new_event` 결정
    - 활성 이벤트 없음 → 새 Event + AlarmRecord 생성 → `is_new_event=True`
    - 활성 이벤트 있음 → AlarmRecord 추가(merge) → `is_new_event=False`
  - FastAPI `POST /internal/alarms/push/` → `active_alarms` 리스트에 append
  - FastAPI `alarm_flush_loop` (2초 주기): `is_new_event=True` 존재 시 즉시 WebSocket 브로드캐스트
  - WebSocket 연결 즉시 전송: `include_alarms=False` (페이지 진입 시 팝업 방지)
- **예외 사항 및 비고**:
  - 클라이언트 없을 때 발생한 알람은 `active_alarms` 큐 보관 → 연결 즉시 2초 내 전달
  - 조치완료 후 가스가 계속 위험 상태이면 Redis가 `danger`를 유지해 새 Celery 미실행 → 팝업 없음
  - 가스가 정상으로 돌아왔다가 다시 위험될 때 비로소 새 이벤트 + 팝업 발생

---

### [REQ-CM-07-05] 조치 상태 변경 이력 기록 (EventLog)

- **분류**: 기능적 요구사항
- **중요도**: 중
- **기능 목적**: 이벤트 조치 상태 변경 시 담당자·시간·전후 상태를 EventLog에 자동 기록
- **요구사항 상세 설명**:
  - 상태 변경 API 호출 성공 시 EventLog 자동 생성 (별도 API 없음)
  - 기록 항목: `event`, `actor(request.user)`, `action`, `previous_status`, `new_status`
  - action 매핑:
    - `acknowledged` → `EventLog.Action.CONFIRMED`
    - `in_progress` → `EventLog.Action.STATUS_CHANGED`
    - `resolved` → `EventLog.Action.RESOLVED`
  - EventLog는 append-only (삭제/수정 없음)
  - 이벤트 최초 생성 시도 `EventLog.Action.CREATED` 자동 기록
  - 타임 윈도우(12시간) 초과 자동 분리 시 `EventLog.Action.RESOLVED` + note 포함
- **예외 사항 및 비고**:
  - 허용되지 않은 상태 전이(400 반환) 시 EventLog 미생성

---

## 3. API 명세서

### 3-1. FastAPI 내부 알람 푸시

| 항목 | 내용 |
|------|------|
| 기능 | Celery → FastAPI WebSocket 브로드캐스트 큐 알람 추가 |
| 호출자 | Celery 태스크 (DRF 내부) |
| 메서드 | POST |
| URL | `http://127.0.0.1:8001/internal/alarms/push/` |
| 접근 제한 | `127.0.0.1` / `::1` / `localhost` 전용 (외부 403) |

**Request**
```json
Content-Type: application/json
{
  "alarm_type": "gas_threshold",
  "gas_type": "h2s",
  "risk_level": "danger",
  "source_label": "63200c3afd12",
  "summary": "[긴급] H₂S (황화수소) 위험 수준 초과 (30 ppm) — 즉시 대피하고 관리자에게 보고하세요.",
  "is_new_event": true,
  "event_id": 42,
  "measured_value": 30.0,
  "threshold_value": 15.0
}
```

**Response — 200 OK**
```json
{"ok": true}
```

**Response — 403 Forbidden**
```json
{"detail": "내부 전용 엔드포인트입니다."}
```

---

### 3-2. 이벤트 조치 상태 변경 (기존 CM-07-03 확장)

| 항목 | 내용 |
|------|------|
| 메서드 | PATCH |
| URL | `/alerts/api/events/{id}/update_status/` |

**Request**
```json
{ "status": "resolved" }
```

**Response — 200 OK**: 변경된 이벤트 상세 반환 (EventLog 자동 생성 포함)

**Response — 400 Bad Request**
```json
{"error": "현재 상태(resolved)에서 in_progress로 변경할 수 없습니다."}
```

---

## 4. 흐름도

### 알람 생성 ~ 브라우저 팝업 전체 흐름

```
gas_dummy.py (1초 주기)
  │  POST /api/sensors/gas → FastAPI → DRF 저장
  ▼
trigger_gas_alarms() — DRF
  │
  ├── Redis alarm:state:{sensor_id}:{gas}
  │     정상 → 위험: Celery fire_danger_alarm_task.delay()
  │                   Redis state = "danger"
  │     위험 → 위험: 아무것도 안 함 (중복 방지)
  │     위험 → 정상: Celery fire_clear_notification_task.delay()
  │                   Redis state = "normal"
  │
  ▼
fire_danger_alarm_task (Celery)
  │
  ├── create_alarm_and_event()
  │     활성 이벤트 없음 → Event 생성 + AlarmRecord 생성 + EventLog(CREATED)
  │                        return (event, alarm)  → is_new_event=True
  │     활성 이벤트 있음 → AlarmRecord 추가 (merge)
  │                        return (event, None)   → is_new_event=False
  │
  └── POST /internal/alarms/push/ → FastAPI
        { is_new_event: True/False, risk_level, summary, ... }

FastAPI active_alarms = [ ... ]
  │
  ├── alarm_flush_loop (2초 주기)
  │     is_new_event=True 있으면 → 즉시 _send_to_all()
  │     없으면 → 스킵
  │
  └── broadcast_loop (30초 주기)
        → _send_to_all() (센서/전력 + 쌓인 알람)

브라우저 WebSocket 수신
  │
  ├── is_new_event=True  → AlarmPopup.show() → 중앙 팝업
  ├── is_new_event=False → 팝업 없음
  └── risk_level=normal  → AlarmToast.show() → 우하단 토스트
```

### 조치완료 후 재알람 조건

```
조치완료(RESOLVED)
  │
  ├── Redis state 유지 (danger)
  │     가스 계속 위험 → Celery 미실행 → 새 이벤트 없음
  │
  ├── 가스 정상화
  │     Redis state = "normal" → 정상화 토스트
  │
  └── 가스 다시 위험
        Redis: normal → danger 전환 → Celery 실행
        create_alarm_and_event(): 이전 이벤트 RESOLVED → 새 Event 생성
        is_new_event=True → 팝업 발생
```

### EventLog 기록 시점

```
Event 생성         → EventLog(CREATED)            — create_alarm_and_event()
상태 → confirmed   → EventLog(CONFIRMED)           — update_status API
상태 → in_progress → EventLog(STATUS_CHANGED)      — update_status API
상태 → resolved    → EventLog(RESOLVED)            — update_status API
12시간 초과 자동분리 → EventLog(RESOLVED, note 포함) — create_alarm_and_event()
```

---

## 5. 디렉토리 경로

```
drf-server/
├── apps/alerts/
│   ├── views/event.py          # update_status: EventLog 생성 추가
│   ├── services/event_service.py  # create_alarm_and_event: EventLog(CREATED) 추가
│   └── tasks.py                # fire_danger_alarm_task: is_new_event 플래그 전송
│
├── static/js/shared/
│   ├── alarm-popup.js          # AlarmPopup / AlarmToast (중앙 팝업 + 토스트)
│   └── alarm-ws.js             # [신규] 비대시보드 페이지용 알람 전용 WebSocket
│
└── templates/
    ├── components/alarm_popup.html         # 팝업 + 토스트 HTML
    ├── snb_details/monitoring_events.html  # alarm-popup.html + alarm-ws.js 추가
    └── snb_details/event_detail.html       # alarm-popup.html + alarm-ws.js 추가

fastapi-server/
├── app.py                              # alarm_flush_loop lifespan 등록
├── websocket/
│   ├── state.py                        # sensor_clients 이동 (공유 상태)
│   ├── routers/ws_router.py            # alarm_flush_loop 추가, include_alarms=False
│   └── services/broadcast.py          # include_alarms 파라미터 추가
└── internal/
    └── routers/alarm_router.py         # POST /internal/alarms/push/ (단순화)
```

---

## 6. URL 정의서

| 구분 | 메서드 | URL | 설명 |
|------|--------|-----|------|
| REST | PATCH | `/alerts/api/events/{id}/update_status/` | 이벤트 조치 상태 변경 + EventLog 기록 |
| HTTP | POST | `http://127.0.0.1:8001/internal/alarms/push/` | Celery → FastAPI WS 큐 브리지 (내부 전용) |
| WS | — | `ws://127.0.0.1:8001/ws/sensors/` | 알람 포함 통합 브로드캐스트 |
