# CM-07 / MN-03 — 이벤트 현황 & 실시간 유해가스 현황 기능정의서

> 작성자: 정휘훈 / 최종 수정: 2026-04-27
> 브랜치: `feature/cm07-mn03-alarm-event.v3`
> 대상 기능 ID: **CM-07** (이벤트 현황 / 이벤트 상세), **MN-03** (실시간/AI 예측 유해가스 현황)

---

## 1. 기능 목록표

| 대분류 | 화면명 | 기능ID | 기능명 | 기능 목적 | 사용자 시나리오 | 디자인 요소 | 백엔드 처리 | 프론트엔드 처리 |
|--------|--------|--------|--------|-----------|-----------------|-------------|-------------|-----------------|
| 모니터링 | 이벤트 현황 | CM-07-01 | 이벤트 목록 조회 | 발생한 이벤트를 상태별로 조회 | 탭 필터(조치 필요/조치 중/조치 완료) 클릭 → 목록 갱신 | 필터 탭, 테이블, 상태 뱃지 | `GET /alerts/api/events/?status=` | `event_list.js` API 호출 및 테이블 렌더 |
| 모니터링 | 이벤트 상세 | CM-07-02 | 이벤트 상세 조회 | 단일 이벤트의 상세 정보 및 연관 알람 확인 | 목록 행 클릭 → 상세 페이지 이동 | 요약 카드, 상세 패널, 연관 모니터링 | `GET /alerts/api/events/{id}/` | `event_detail.js` 렌더 |
| 모니터링 | 이벤트 상세 | CM-07-03 | 조치 상태 변경 | 이벤트 조치 상태를 단계적으로 변경 | 버튼 선택 → 확인 팝업 → API 호출 | 상태 변경 패널, 확인 모달 | `PATCH /alerts/api/events/{id}/update_status/` | 모달 confirm 후 API 호출 및 화면 갱신 |
| 모니터링 | 유해가스 현황 | MN-03-01 | 가스 실시간 모니터링 | 9종 유해가스 농도를 WebSocket으로 실시간 표시 | 페이지 진입 → WebSocket 연결 → 차트 자동 갱신 | 3×3 차트 그리드, 센서 목록, 가스 리스트, 상태 바 | FastAPI `ws://127.0.0.1:8001/ws/sensors/` | `websocket_gas.js` + `gas_monitoring.js` |
| 모니터링 | 유해가스 현황 | MN-03-02 | AI 예측 탭 전환 | 실시간/AI 예측 탭 전환 (AI는 4차 구현 예정) | "AI 예측" 탭 클릭 → 미연동 배너 표시, 동일 데이터 표시 | 탭 버튼, AI 공지 배너 | — (미연동) | `switchGasTab()` |
| 모니터링 | 유해가스 현황 | MN-03-03 | 가스 카드 선택 연동 | 차트 카드 클릭 시 가스 리스트 테이블 하이라이트 | 차트 카드 클릭 → 좌측 테이블 해당 행 하이라이트 | 카드 선택 테두리, 테이블 행 하이라이트 | — | `_onGasCardClick()` |
| 모니터링 | 유해가스 현황 | MN-03-04 | WebSocket 연결 상태 UI | 연결 시도/재연결 대기 상태를 시각적으로 표시 | 연결 실패 → 카운트다운 배너 표시 → 재연결 성공 시 배너 숨김 | 연결 배너(스피너 + 카운트다운 텍스트), 스켈레톤 카드 | — | `websocket_gas.js`: `_showBanner()`, `_startCountdown()` |
| 모니터링 | 유해가스 현황 | MN-03-05 | 데이터 없음 상태 처리 | 가스 데이터 stale 시 스켈레톤 또는 "데이터가 존재하지 않습니다." 표시 | 더미 데이터 미전송 → 8초 후 스켈레톤/오버레이 전환 | 스켈레톤 카드(깜빡임), 차트 오버레이 텍스트 | FastAPI `gas_loading: true` 플래그 | `gas_loading` 체크 → `updateGasPage({})` + `_showAllOverlay('empty')` |
| 대시보드 | 대시보드 메인 | MN-03-06 | 대시보드 가스 패널 개선 | 스마트 전력 패널과 동일한 UX 패턴 적용 | KPI 박스 확인 / AI 예측 화살표로 9종 전환 / 오류·데이터없음 시 문구 표시 | KPI 박스, AI nav(◁▷), 위험도 색상 뱃지, 초기 스켈레톤 행 | FastAPI `gas_loading` 플래그 | `_setGasPanelError(msg)` 문구 전환, `_renderAIGasNav()` 9종 전환 |

---

## 2. 요구사항 정의서

### [REQ-CM-07-01] 이벤트 목록 조회

- **분류**: 기능적 요구사항
- **중요도**: 상
- **기능 목적**: 발생한 이벤트를 상태별 필터 탭으로 구분해 조회
- **요구사항 상세 설명**:
  - 기본 탭: 조치 필요 (`pending` = active + acknowledged)
  - 탭 3종: 조치 필요 / 조치 중 (`in_progress`) / 조치 완료 (`resolved`)
  - 각 탭에 건수 표시 (페이지 로드 시 3개 탭 건수 동시 조회)
  - 목록 컬럼: 조치 상태 / No. / 위험 상태 / 이벤트명 / 발생원 / 발생 시간 / 상세 내용
  - 행 클릭 시 이벤트 상세 페이지(`/dashboard/monitoring/events/{id}/`)로 이동
  - `resolved` 상태 행은 흐리게 표시 (`.resolved` 클래스)
- **백엔드 처리 및 인터페이스**:
  - `EventViewSet` (ReadOnlyModelViewSet): `?status=pending|in_progress|resolved` 필터 지원
  - `select_related('source_sensor', 'source_power_device', 'source_geofence', 'worker')` + `prefetch_related('alarms')` N+1 방지
  - `EventListSerializer`: 알람 건수(`alarm_count`), 위험도/상태 한글 표시명, 담당자명 포함
- **예외 사항 및 비고**:
  - 이벤트 없음 → "이벤트가 없습니다." 빈 행 표시
  - API 실패 → "데이터를 불러올 수 없습니다." 표시

---

### [REQ-CM-07-02] 이벤트 상세 조회

- **분류**: 기능적 요구사항
- **중요도**: 상
- **기능 목적**: 단일 이벤트의 발생 정보, 알람 내역, 연관 모니터링 정보를 확인
- **요구사항 상세 설명**:
  - 상단 요약 카드: 위험 뱃지 / 조치 상태 뱃지 / 발생원 / 발생 시간 / 연관 작업자
  - 좌측 상세 패널: 상세 내용 / 권고 조치 (고정 텍스트) / 연관 대상 정보 / 발생 추이 (알람 건수)
  - 우측: 조치 상태 변경 패널 + 연관 모니터링 정보 패널
  - `EVENT_ID`를 Django 템플릿 컨텍스트로 주입 (`{{ event_id }}`)
- **백엔드 처리 및 인터페이스**:
  - `EventDetailSerializer`: `alarms` 목록, `acknowledged_by_name`, `resolved_by_name`, `acknowledged_at`, `resolved_at` 포함
- **예외 사항 및 비고**:
  - API 실패 → `alert()` 후 빈 화면 유지

---

### [REQ-CM-07-03] 조치 상태 변경

- **분류**: 기능적 요구사항
- **중요도**: 상
- **기능 목적**: 이벤트 조치 상태를 단계적으로 변경하고 처리자/시간 기록
- **요구사항 상세 설명**:
  - 선택 가능 상태: 조치 중 / 조치 완료
  - 상태 머신 전이 규칙 (백엔드 검증):
    - `active` → `acknowledged`, `in_progress`, `resolved`
    - `acknowledged` → `in_progress`, `resolved`
    - `in_progress` → `resolved`
    - `resolved` → 변경 불가 (버튼 비활성화)
  - "변경" 버튼 클릭 → 확인 모달 표시 → "확인" 클릭 → API 호출
  - 성공 시 화면 즉시 갱신 (페이지 리로드 없음)
- **백엔드 처리 및 인터페이스**:
  - `in_progress` 전이 시 `acknowledged_by = request.user`, `acknowledged_at = now()` 자동 기록
  - `resolved` 전이 시 `resolved_by = request.user`, `resolved_at = now()` 자동 기록
  - 허용되지 않은 전이 → 400 에러 반환
- **예외 사항 및 비고**:
  - 변경 대상 미선택 시 `alert()` 안내
  - API 400 에러 시 서버 반환 메시지 `alert()` 표시

---

### [REQ-MN-03-01] 실시간 유해가스 모니터링

- **분류**: 기능적 요구사항
- **중요도**: 상
- **기능 목적**: 9종 유해가스 농도를 WebSocket으로 실시간 수신, 위험도와 함께 시각화
- **요구사항 상세 설명**:
  - 대상 가스 9종: O2, CO, CO2, H2S, NO2, SO2, O3, NH3, VOC
  - 좌측: 센서 목록 테이블 (센서ID / 주요 위험 가스 / 연결 상태 / 위험 상태) + 위험/주의/정상 카운트 뱃지
  - 좌측: 가스 리스트 테이블 (가스 종류 / 현재 농도 / 단위 / 위험도)
  - 우측: 3×3 차트 그리드 (Chart.js 막대 그래프 + chartjs-plugin-annotation 임계선/임계 범위)
  - 하단 상태 바: 센서명 / 상태 메시지 / 경고 메시지 / 실시간 시계
  - WebSocket 연결 실패/끊김 시 3초 후 자동 재연결
  - O2는 역방향 위험 기준 (낮을수록 위험) 별도 처리
- **디자인 요구사항**:
  - 차트 카드 클릭 ↔ 좌측 가스 리스트 테이블 행 하이라이트 양방향 연동
  - 위험도 뱃지: 위험 `#f85149` / 주의 `#e3b341` / 정상 `#3fb950` — 박스 형태 색상 표시
  - 임계 범위 배경색: 위험 `rgba(248,81,73,0.18)` / 주의 `rgba(227,179,65,0.18)`
  - 서버에서 `safe` 위험도가 내려올 경우 `normal`로 정규화 처리 (`_normalizeRisk()`)
- **백엔드 처리 및 인터페이스**:
  - WebSocket 서버: `ws://127.0.0.1:8001/ws/sensors/` (FastAPI)
  - 수신 페이로드: `co, h2s, co2, o2, no2, so2, o3, nh3, voc` (측정값) + `{gas}_risk` (위험도) + `gas_loading` (stale 여부)
  - `GasDataCreateSerializer`: 데이터 저장 후 `trigger_gas_alarms()` 호출하여 알람 자동 생성
- **예외 사항 및 비고**:
  - WebSocket 연결 오류 시 "수신 오류" 뱃지 표시, 데이터는 `-`로 표시
  - AI 예측 탭: 미연동 안내 배너 표시, 실시간 데이터로 대체 렌더

---

### [REQ-MN-03-04] WebSocket 연결 상태 UI

- **분류**: 기능적 요구사항
- **중요도**: 중
- **기능 목적**: WebSocket 연결 시도/재연결 대기 상태를 사용자에게 시각적으로 명확히 전달
- **요구사항 상세 설명**:
  - 연결 시도 중: 상단 배너에 스피너 + "연결 시도 중..." 텍스트 표시
  - 연결 실패/끊김: 차트 그리드 스켈레톤(깜빡임) + 좌측 테이블 스켈레톤 행 + 배너에 "N초 후 재연결 시도..." 카운트다운
  - 카운트다운 완료 후 자동으로 재연결 시도 (3초 주기)
  - 데이터 수신 성공 시: 배너 숨김, 스켈레톤 제거, 정상 렌더링
- **디자인 요구사항**:
  - 배너: 파란 계열 border + 배경 (`rgba(56,139,253,0.08)`)
  - 스피너: `conn-spin` keyframe 회전 애니메이션
  - 스켈레톤: `skeleton-shimmer` keyframe (좌→우 shimmer)
- **백엔드 처리 및 인터페이스**: 없음 (순수 프론트엔드 처리)
- **예외 사항 및 비고**:
  - 카운트다운 도중 추가 오류 발생 시 중복 타이머 방지 (`_clearCountdown()`)
  - 스켈레톤은 차트 그리드(9개) + 센서 테이블(1행) + 가스 리스트(9행) 모두 적용

---

### [REQ-MN-03-05] 데이터 없음 상태 처리

- **분류**: 기능적 요구사항
- **중요도**: 상
- **기능 목적**: 가스 센서 데이터가 stale(8초 초과 미수신)이거나 비어있을 때, 스켈레톤 또는 "데이터가 존재하지 않습니다." 오버레이로 명확히 구분
- **요구사항 상세 설명**:
  - **연결 오류/재연결 대기 중**: 차트 그리드 + 좌측 테이블 스켈레톤(깜빡임)
  - **연결됐으나 데이터 없음** (`gas_loading: true` 수신 시): 각 차트 카드 위에 "데이터가 존재하지 않습니다." 오버레이, 좌측 테이블은 `-` 상태
  - 대시보드 패널도 동일 처리: `gas_loading: true` → KPI/테이블 스켈레톤 전환
- **디자인 요구사항**:
  - "데이터가 존재하지 않습니다." 오버레이: `ui-exception.js`의 `showChartOverlay(canvas, 'empty')` 활용
  - "데이터를 불러올 수 없습니다." 오버레이: `showChartOverlay(canvas, 'error')` (통신 장애 구분)
- **백엔드 처리 및 인터페이스**:
  - FastAPI `gas_latest["updated_at"]` 타임스탬프 갱신 (`gas_service.py`)
  - `build_broadcast_payload()`: 마지막 가스 데이터 수신 후 8초 초과 시 `gas_loading: True` 플래그 포함, 가스 측정값 페이로드에서 제외
  - 전력의 `power_loading` 플래그와 동일한 패턴
- **예외 사항 및 비고**:
  - `gas_loading: false` → 정상 측정값 페이로드 포함
  - 서버 재시작 직후: `gas_latest["updated_at"] = None` → 즉시 stale 처리

---

### [REQ-MN-03-06] 대시보드 가스 패널 개선

- **분류**: 기능적 요구사항
- **중요도**: 중
- **기능 목적**: 대시보드 메인의 유해가스 패널을 스마트 전력 패널과 동일한 UX 패턴으로 통일
- **요구사항 상세 설명**:
  - **패널 12 (위험 현황)**: KPI 박스 — "현재 가장 위험한 가스" 이름 + 위험도, 아래 9종 테이블
  - **패널 13 (AI 예측)**: ◁/▷ 화살표로 9종 가스 전환, 현재 농도/예측 최대 농도 KPI, 가스별 히스토리 차트
  - 위험도 뱃지: `.brisk.safe` (정상 초록) / `.brisk.caution` (주의 노랑) / `.brisk.danger` (위험 빨강) 색상 박스 표시
  - **통신 오류** (`ws.onerror` / `ws.onclose`) 시: KPI·위험도 `'-'` 처리 + 테이블 비움 + `#gasPanelMsg`에 **"데이터를 불러올 수 없습니다."** 문구 표시
  - **데이터 없음** (`gas_loading: true` 수신) 시: 동일 방식으로 **"데이터가 존재하지 않습니다."** 문구 표시
  - 정상 데이터 수신 시: `_clearGasPanelMsg()` 호출 후 KPI·테이블 정상 갱신
- **디자인 요구사항**:
  - 초기 로드: HTML에 스켈레톤 행 4개 삽입 (`skel-text`, `skel-sm`, `skel-badge`) — 데이터 수신 전까지 유지
  - 가스별 차트 히스토리: `_aiGasHist[key]` — 최대 30포인트 유지
  - 위험도 클래스 매핑: `normal → safe`, `warning → caution`, `danger → danger`
- **백엔드 처리 및 인터페이스**: FastAPI `gas_loading` 플래그 수신
- **예외 사항 및 비고**:
  - AI 예측 패널은 더미 예측값 (현재 농도 × 1.3) 사용, 실제 AI 연동은 4차 예정

---

## 3. API 명세서

### 3-1. 이벤트 목록 조회

| 항목 | 내용 |
|------|------|
| 기능 | 이벤트 목록 조회 (상태 필터) |
| 사용자 | 인증된 사용자 (IsAuthenticated) |
| 메서드 | GET |
| URL | `/alerts/api/events/` |
| params | `status`: `pending` \| `in_progress` \| `resolved` (선택) |

**Response — 200 OK**
```json
[
  {
    "id": 1,
    "event_type": "gas_threshold",
    "risk_level": "danger",
    "risk_level_display": "위험",
    "status": "active",
    "status_display": "발생",
    "source_label": "GAS-001",
    "summary": "CO 농도 위험 수준 초과 감지",
    "first_detected_at": "2026-04-27T09:00:00+09:00",
    "last_detected_at": "2026-04-27T09:05:00+09:00",
    "alarm_count": 3,
    "worker_name": "홍길동"
  }
]
```

**Response — 401 Unauthorized**
```json
{"detail": "자격 인증데이터(authentication credentials)가 제공되지 않았습니다."}
```

---

### 3-2. 이벤트 상세 조회

| 항목 | 내용 |
|------|------|
| 기능 | 이벤트 상세 조회 |
| 사용자 | 인증된 사용자 |
| 메서드 | GET |
| URL | `/alerts/api/events/{id}/` |

**Response — 200 OK**
```json
{
  "id": 1,
  "event_type": "gas_threshold",
  "risk_level": "danger",
  "risk_level_display": "위험",
  "status": "in_progress",
  "status_display": "조치 중",
  "source_label": "GAS-001",
  "summary": "CO 농도 위험 수준 초과 감지",
  "first_detected_at": "2026-04-27T09:00:00+09:00",
  "last_detected_at": "2026-04-27T09:05:00+09:00",
  "alarm_count": 3,
  "worker_name": "홍길동",
  "acknowledged_by_name": "관리자1",
  "resolved_by_name": null,
  "acknowledged_at": "2026-04-27T09:10:00+09:00",
  "resolved_at": null,
  "alarms": [
    {
      "id": 10,
      "alarm_level": "danger",
      "created_at": "2026-04-27T09:00:00+09:00"
    }
  ]
}
```

**Response — 404 Not Found**
```json
{"detail": "찾을 수 없습니다."}
```

---

### 3-3. 이벤트 조치 상태 변경

| 항목 | 내용 |
|------|------|
| 기능 | 이벤트 조치 상태 변경 |
| 사용자 | 인증된 사용자 |
| 메서드 | PATCH |
| URL | `/alerts/api/events/{id}/update_status/` |

**Request**
```json
Content-Type: application/json
{
  "status": "in_progress"
}
```

**Response — 200 OK**: 변경된 이벤트 상세 (3-2 형식과 동일)

**Response — 400 Bad Request**
```json
{"error": "현재 상태(resolved)에서 in_progress로 변경할 수 없습니다."}
```

---

### 3-4. FastAPI WebSocket 센서 페이로드 (ws/sensors/)

| 항목 | 내용 |
|------|------|
| 구분 | WebSocket 수신 (FastAPI → 브라우저) |
| URL | `ws://127.0.0.1:8001/ws/sensors/` |
| 주기 | 1초 |

**Payload 예시 — 정상 수신 시**
```json
{
  "device_id": "sensor-01",
  "timestamp": "2026-04-27T17:07:50",
  "gas_loading": false,
  "co": 15, "h2s": 4, "co2": 954, "o2": 19.08,
  "no2": 0.4, "so2": 0.75, "o3": 0.04, "nh3": 9, "voc": 0.14,
  "co_risk": "normal", "h2s_risk": "normal", "co2_risk": "normal",
  "o2_risk": "normal", "no2_risk": "normal", "so2_risk": "normal",
  "o3_risk": "normal", "nh3_risk": "normal", "voc_risk": "normal",
  "power_loading": false,
  "total_power_kw": 1287,
  "power_change_pct": 0.0,
  "equipment": [ ... ],
  "alarms": [],
  "worker_positions": {}
}
```

**Payload 예시 — 가스 데이터 stale (8초 초과 미수신)**
```json
{
  "device_id": "sensor-01",
  "timestamp": "2026-04-27T17:08:05",
  "gas_loading": true,
  "power_loading": false,
  "total_power_kw": 1287,
  ...
}
```

**`gas_loading` 플래그 처리 규칙**

| 조건 | `gas_loading` | 프론트엔드 동작 |
|------|--------------|-----------------|
| 센서 데이터 정상 수신 (8초 이내) | `false` | 가스 패널/차트 정상 렌더 |
| 마지막 수신 후 8초 초과 | `true` | 대시보드: 문구 표시 / 상세: "데이터가 존재하지 않습니다." 오버레이 |
| 서버 재시작 직후 (미수신) | `true` | 동일 |

---

### 3-5. 더미 데이터 스크립트 명세 (개발/테스트 환경)

> 실제 센서 장비 대신 터미널에서 실행하는 개발용 데이터 주입 스크립트.
> 실서비스에서는 실제 IoT 장비가 동일 엔드포인트로 데이터를 전송한다.

#### gas_dummy.py — 가스 센서 더미

| 항목 | 내용 |
|------|------|
| 대상 서버 | FastAPI (`http://127.0.0.1:8001`) |
| 공통 `device_id` | `"63200c3afd12"` |

**① 장비 정보 등록 (최초 1회)**

- **Endpoint**: `POST /api/sensors/info`

```json
{
  "device_id": "63200c3afd12",
  "device_name": "63200c3afd12",
  "software_version": "1.0.1",
  "location": { "x": 140, "y": 160 }
}
```

**② 가스 측정 데이터 (1초 주기 반복)**

- **Endpoint**: `POST /api/sensors/gas`
- 생성 규칙: `DANGER_EVENT_PROB = 0.1` (10% 확률로 위험 범위, 90% 정상 범위)
- `status` 필드는 `core.gas_thresholds.calculate_gas_status()`로 자동 결정

```json
{
  "timestamp": "2026-04-28T00:00:00+00:00",
  "device_id": "63200c3afd12",
  "device_name": "63200c3afd12",
  "location": { "x": 140, "y": 160 },
  "co": 12, "h2s": 4, "co2": 550, "o2": 20.5, "lel": 2,
  "no2": 1.25, "so2": 0.5, "o3": 0.03, "nh3": 10, "voc": 0.25,
  "status": "NORMAL"
}
```

---

#### power_dummy.py — 전력 설비 더미

| 항목 | 내용 |
|------|------|
| 대상 서버 | FastAPI (`http://127.0.0.1:8001`) |
| 공통 `device_id` | `"63200c3afd12"` |
| 전송 주기 | 3초 (루프당 4개 엔드포인트 순차 전송) |
| 채널 수 | 16개 (`slave01`~`slave72`) |

**전송 순서**: `onoff` → `current` → `voltage` → `watt`

| 엔드포인트 | 측정 항목 | 생성 규칙 |
|-----------|----------|----------|
| `POST /api/power/onoff` | ON/OFF 상태 | 70% ON(255) / 30% OFF(0) |
| `POST /api/power/current` | 전류(A) | 50% → 1~30 랜덤 정수 / 50% → 0 |
| `POST /api/power/voltage` | 전압(V) | 50% → 215~225 랜덤 정수 / 50% → 0 |
| `POST /api/power/watt` | 전력(W) | 50% → 50~5000 랜덤 정수 / 50% → 0 |

**Payload 공통 형식**
```json
{
  "device_id": "63200c3afd12",
  "slave01": 255,
  "slave02": 0,
  "slave11": 15,
  ...
  "slave72": 3400
}
```

---

#### 작업자 위치 — FastAPI 내부 시뮬레이션

> 가스/전력과 달리 별도 외부 스크립트 없이 FastAPI 내부에서 자동 시뮬레이션.

| 항목 | 내용 |
|------|------|
| 담당 파일 | `fastapi-server/positioning/services/position_service.py` |
| 방식 | 서버 내부 틱(1초)마다 `update_worker_positions()` 호출 |
| 시뮬레이션 대상 | 작업자 4명 (작업자 A~D), 초기 좌표·이동방향·속도 하드코딩 |
| 경계 처리 | 맵 범위(`x: 0~1290, y: 0~590`) 벗어나면 방향 반전 |
| DRF 저장 | `POST {DRF_BASE_URL}/api/positioning/receive/`로 갱신 데이터 전송 |

---

## 4. 상태 전이 흐름도

### Event 조치 상태 머신

```
active ──────────────────────────────────┐
  │                                      │
  ├──→ acknowledged ────────────────────►│
  │         │                           │
  │         ├──→ in_progress ──────────►│
  │         │         │                 │
  └─────────┴─────────┴──────────────►resolved (종단)
```

### 유해가스 현황 — WebSocket 데이터 흐름

```
FastAPI WebSocket Server (ws://127.0.0.1:8001/ws/sensors/)
  │
  │  { co, h2s, ..., {gas}_risk, gas_loading }
  ▼
websocket_gas.js (연결 관리 + 재연결 + 배너 카운트다운)
  │
  ├── gas_loading: true ──→ updateGasPage({}) + _showAllOverlay('empty')
  │                         → "데이터가 존재하지 않습니다." 오버레이
  │
  ├── 빈 페이로드 ({}) ──→ 동일 처리
  │
  ├── 통신 오류/재연결 대기 ──→ showSkeleton(grid, 9) + _showLeftSkeleton()
  │                              → 차트·테이블 스켈레톤(깜빡임) + 카운트다운 배너
  │
  └── 정상 데이터 ──→ updateGasPage(data, true)
                       │
                       ▼
                   gas_monitoring.js
                     ├── renderGasGrid()       → 3×3 Chart.js 차트 갱신
                     ├── renderGasListTable()  → 좌측 가스 리스트 테이블 갱신
                     ├── renderSensorTable()   → 좌측 센서 목록 + 카운트 갱신
                     └── updateGasStatusBar()  → 하단 상태 바 갱신
```

### gas_loading stale 판단 흐름 (FastAPI)

```
gas_dummy.py (터미널 더미 스크립트)
  │  POST /gas/data/ (1초 주기)
  ▼
gas_service.py
  ├── latest_gas_snapshot.update(gas_snapshot)
  └── gas_latest["updated_at"] = now()   ← 타임스탬프 갱신
                │
                ▼
broadcast.py (1초 주기)
  ├── gas_age_sec = now() - gas_latest["updated_at"]
  ├── gas_stale = gas_age_sec > 8초 or updated_at is None
  │
  ├── gas_stale = False → payload에 가스 측정값 포함 + gas_loading: False
  └── gas_stale = True  → 가스 측정값 제외 + gas_loading: True
```

### 대시보드 가스 패널 — 연결 상태별 동작

```
ws.onmessage 수신
  ├── data.gas_loading === true  → _setGasPanelError('데이터가 존재하지 않습니다.')
  │                                  → KPI '-' / 테이블 비움 / 문구 표시
  └── data.co !== undefined      → _clearGasPanelMsg() + 정상 렌더
                                     (KPI 갱신 + 테이블 갱신 + AI nav 갱신)

ws.onerror / ws.onclose         → _setGasPanelError('데이터를 불러올 수 없습니다.')
                                    → KPI '-' / 테이블 비움 / 문구 표시 + 3초 후 재연결
```

### 이벤트 상세 상태 변경 흐름

```
사용자 — 버튼 선택(조치 중 / 조치 완료)
  │
  ▼
"변경" 버튼 클릭 → 확인 모달 표시
  │
  ▼
"확인" 클릭 → PATCH /alerts/api/events/{id}/update_status/
  │
  ├── 200 OK → renderDetail(응답 데이터) 화면 즉시 갱신
  └── 400 Bad Request → alert(서버 에러 메시지)
```

---

## 5. 디렉토리 경로

```
drf-server/
│
├── apps/alerts/
│   ├── serializers/
│   │   ├── __init__.py              # EventViewSet export 추가
│   │   └── event.py                 # EventListSerializer, EventDetailSerializer [신규]
│   ├── views/
│   │   ├── __init__.py              # EventViewSet export 추가
│   │   └── event.py                 # EventViewSet (list, retrieve, update_status) [신규]
│   └── urls.py                      # /api/events/ 라우터 등록
│
├── apps/dashboard/
│   ├── views.py                     # monitoring_events_page, monitoring_event_detail_page 추가
│   └── urls.py                      # /monitoring/events/, /monitoring/events/<id>/ 추가
│
├── apps/monitoring/
│   └── serializers/gas_data.py      # create() 내 trigger_gas_alarms() 연동 추가
│
├── templates/snb_details/
│   ├── monitoring_gas.html          # 실시간/AI 예측 유해가스 현황 페이지 [신규]
│   │                                # — #gas-conn-banner (카운트다운 배너) 포함
│   ├── monitoring_events.html       # 이벤트 현황 목록 페이지 [신규]
│   └── event_detail.html            # 이벤트 상세 페이지 [신규]
│
├── templates/dashboard/panels/
│   ├── gas_panel.html               # KPI 박스 + AI nav(◁▷) + 스켈레톤 행 [수정]
│   └── event_panel.html             # "상세 보기" → href 링크 연결
│
├── static/js/detail/
│   ├── ui-exception.js              # UI 예외 처리 공통 유틸 (showSkeleton, showChartOverlay 등)
│   ├── gas_monitoring.js            # 가스 모니터링 렌더 함수 [신규]
│   │                                # — _normalizeRisk() (safe→normal 정규화)
│   │                                # — renderGasGrid(), renderGasListTable(), renderSensorTable()
│   ├── websocket_gas.js             # WebSocket 연결 관리 [신규]
│   │                                # — _showBanner(), _hideBanner(), _startCountdown()
│   │                                # — _handleError(): 스켈레톤 + 카운트다운
│   │                                # — _showLeftSkeleton(): 좌측 테이블 스켈레톤
│   │                                # — gas_loading 처리: 'empty' 오버레이
│   ├── event_list.js                # 이벤트 목록 조회 및 필터 탭 [신규]
│   └── event_detail.js              # 이벤트 상세 조회 및 상태 변경 [신규]
│
├── static/js/dashboard/
│   ├── websocket.js                 # [수정]
│   │                                # — _GAS_META, _aiGasHist, _renderAIGasNav() 추가
│   │                                # — _setGasPanelError(msg): KPI '-' + 테이블 비움 + 문구 표시
│   │                                #     통신 오류 → "데이터를 불러올 수 없습니다."
│   │                                #     gas_loading → "데이터가 존재하지 않습니다."
│   │                                # — 위험도 클래스 매핑: _riskClass[] 적용
│   └── panels/
│       └── gas-panel.js             # DOMContentLoaded 초기 상태 설정
│
└── static/css/detail/
    ├── gas_monitoring.css           # 유해가스 현황 전용 스타일 [신규]
    │                                # — .gas-conn-msg, .conn-spinner (연결 배너)
    │                                # — .status-badge.safe (정상 초록 뱃지)
    └── event_monitoring.css         # 이벤트 현황/상세 전용 스타일 [신규]

fastapi-server/
│
├── websocket/
│   ├── state.py                     # [수정] gas_latest: dict = {"updated_at": None} 추가
│   └── services/broadcast.py        # [수정] gas stale 판단 + gas_loading 플래그 추가
│
└── gas/
    └── services/gas_service.py      # [수정] gas_latest["updated_at"] 타임스탬프 갱신
```

---

## 6. URL 정의서

| 구분 | 메서드 | URL | 설명 |
|------|--------|-----|------|
| HTTP | GET | `/dashboard/monitoring/gas/` | 실시간/AI 예측 유해가스 현황 페이지 |
| HTTP | GET | `/dashboard/monitoring/events/` | 이벤트 현황 목록 페이지 |
| HTTP | GET | `/dashboard/monitoring/events/<int:event_id>/` | 이벤트 상세 페이지 |
| REST | GET | `/alerts/api/events/` | 이벤트 목록 조회 (`?status=pending\|in_progress\|resolved`) |
| REST | GET | `/alerts/api/events/{id}/` | 이벤트 상세 조회 |
| REST | PATCH | `/alerts/api/events/{id}/update_status/` | 이벤트 조치 상태 변경 |
| WS | — | `ws://127.0.0.1:8001/ws/sensors/` | 유해가스 + 전력 통합 실시간 스트리밍 (FastAPI) |

---

## 7. 가스 임계치 기준표

| 가스 | 라벨 | 단위 | 주의 임계치 | 위험 임계치 | Y축 최대 | 비고 |
|------|------|------|-------------|-------------|----------|------|
| O2  | 산소 | % | 18.0 | 16.0 | 25 | 역방향 (낮을수록 위험) |
| CO  | 일산화탄소 | ppm | 25 | 200 | 300 | |
| CO2 | 이산화탄소 | ppm | 1000 | 5000 | 6000 | |
| H2S | 황화수소 | ppm | 10 | 15 | 30 | |
| NO2 | 이산화질소 | ppm | 3 | 5 | 10 | |
| SO2 | 이산화황 | ppm | 2 | 5 | 10 | |
| O3  | 오존 | ppm | 0.06 | 0.12 | 0.2 | |
| NH3 | 암모니아 | ppm | 25 | 35 | 50 | |
| VOC | 유기화합물 | ppm | 0.5 | 1.0 | 2.0 | |

---

## 8. UI 예외 상태 처리 기준

### 8-1. 유해가스 현황 상세 페이지 (`monitoring_gas.html`)

> `ui-exception.js` 기반 공통 규칙. 필수 스펙 항목.

| 상태 | 트리거 | 차트 그리드 | 좌측 테이블 | 연결 배너 |
|------|--------|-------------|-------------|-----------|
| 초기 연결 시도 | 페이지 로드 | 스켈레톤 9개 (shimmer) | 스켈레톤 행 | "연결 시도 중..." + 스피너 |
| 통신 오류 / 재연결 대기 | `ws.onerror` / `ws.onclose` | 차트 틀 유지 + **"데이터를 불러올 수 없습니다." 오버레이** + 배지 회색화 | `-` 행 | "N초 후 재연결 시도..." 카운트다운 |
| 연결됐으나 데이터 없음 | `gas_loading: true` 수신 | 차트 틀 유지 + **"데이터가 존재하지 않습니다." 오버레이** + 배지 회색화 | `-` 행 | 숨김 |
| 정상 수신 | 유효한 가스 데이터 수신 | 차트 렌더 + 오버레이 제거 + 배지 색상 복원 | 측정값 + 위험도 뱃지 | 숨김 |

### 8-2. 대시보드 가스 패널 (`gas_panel.html`)

> 전력 패널(`_setPowerPanelError`)과 동일한 패턴. `#gasPanelMsg` 요소에 문구 표시.

| 상태 | 트리거 | KPI 박스 | 가스 테이블 | 패널 메시지(`#gasPanelMsg`) |
|------|--------|----------|-------------|------------------------------|
| 초기 로드 | HTML 정적 스켈레톤 | 스켈레톤 | 스켈레톤 행 4개 | 숨김 |
| 통신 오류 / 재연결 대기 | `ws.onerror` / `ws.onclose` | `'-'` | 비움 | **"데이터를 불러올 수 없습니다."** |
| 연결됐으나 데이터 없음 | `gas_loading: true` 수신 | `'-'` | 비움 | **"데이터가 존재하지 않습니다."** |
| 정상 수신 | 유효한 가스 데이터 수신 | 가스명 + 위험도 | 9종 갱신 | 숨김 |
