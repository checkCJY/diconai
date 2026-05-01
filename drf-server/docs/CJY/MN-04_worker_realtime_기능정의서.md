# 기능정의서 — MN-04 작업자 현황 실시간 연동
> 작성일: 2026-05-01
> 브랜치: feature/MN-04_refactor

---

## 1. 기능 목록표

| 대분류 | 화면명 | 기능ID | 기능명 | 기능 목적 | 사용자 시나리오 | 엣지 정보 | 유효성 처리 | 예외 조건 | 에러 처리 | 백엔드 처리 | 프론트엔드 처리 | 참고사항 |
|:--|:--|:--|:--|:--|:--|:--|:--|:--|:--|:--|:--|:--|
| 대시보드 | 작업자 현황 패널 (safety_panel) | MN-04-A | 작업자 현황 패널 실시간 지오펜스 연동 | 작업자/관리자 뷰를 WebSocket 기반으로 전환하여 지오펜스 진입·이탈 시 상태를 실시간 반영 | 작업자: 본인 위치가 위험 지오펜스 진입 시 패널이 즉시 '위험'으로 변경됨. 관리자: 전체 작업자의 정상/주의/위험 인원 수가 실시간 갱신됨 | WS 연결 전에는 '--' 대기 상태 유지. 지오펜스 미등록 시 모두 '정상' 표시 | user.id와 worker_positions의 worker_id 일치 여부 확인 | 본인 worker_id가 위치 데이터에 없으면 대기 상태 유지 | WS 연결 끊김 시 자동 재연결(3초). 지오펜스 미로드 시 전부 '정상' | FastAPI: worker_positions 상태 관리. MapPanel: Ray Casting 지오펜스 판정 후 workerStatusComputed 이벤트 발행 | worker-panel.js가 workerStatusComputed 이벤트 수신 후 DOM 갱신 | HTTP 폴링(2초) 방식에서 WebSocket 이벤트 방식으로 완전 전환 |
| 대시보드 | 맵 패널 (map-panel) | MN-04-B | updateWorkerPositions 이벤트 확장 | 모든 작업자(맵 마커 유무 무관)에 대한 지오펜스 판정 결과를 CustomEvent로 브로드캐스트 | 위치 수신 시마다 지오펜스 상태를 계산하여 패널·모니터링 페이지에 동시 전파 | 마커 없는 작업자도 지오펜스 판정 포함 | Array 및 {worker_id: {...}} 객체 형식 모두 허용 | _geofences 미로드 시 모두 'normal' 반환 | 배열·객체 정규화 처리로 타입 오류 방지 | FastAPI /ws/sensors/ 및 /ws/positions/ 양쪽 경로 모두 처리 | dispatchEvent('workerStatusComputed') | 기존 /ws/positions/ 경로의 객체 타입 전달 버그도 함께 수정 |
| 모니터링 | 작업자 모니터링 페이지 | MN-04-C | 실시간 작업자 목록 연동 | 하드코딩 더미 데이터를 제거하고 DB + WebSocket 데이터로 실시간 작업자 목록 표시 | 관리자가 페이지 접근 시 DB에서 작업자 목록 로드. 이후 위치 수신마다 상태·구역·연결상태 자동 갱신 | DB 작업자 없으면 WS 위치 데이터로 즉석 등록(A안 폴백). 지오펜스 없으면 이동 상태 표시 | Auth.apiFetch JWT 인증. 관리자 권한 없으면 403 | API 실패 시 WS 데이터만으로 동작 | WS 연결 끊김 시 3초 재연결 | DRF WorkerListAPIView + FastAPI /ws/sensors/ | 초기 로드 후 WebSocket으로 행별 갱신 | B안 전환 시 DB 작업자만 표시하도록 폴백 제거 필요 |
| 모니터링 | 작업자 모니터링 페이지 | MN-04-D | 작업자 위험 현황 패널 정리 | PPE 항목 제거 및 라벨·아이콘 개선 | 행 클릭 시 우측 디테일 패널 표시. 체크리스트/VR 항목 아이콘으로 시각화 | PPE는 IoT/AI 미연동으로 제거 | 없음 | 없음 | 알림 전송 버튼 클릭 시 토스트 메시지 표시 | 없음 | 아이콘: 📋 체크리스트, 🥽 VR 교육. 그리드 2열 전환 | PPE 연동 완료 후 재추가 예정 |
| 인증 | 공통 | MN-04-E | /api/auth/me/ user.id 추가 | 작업자 본인 식별을 위해 me 엔드포인트에 user.id 반환 추가 | worker-panel.js 초기화 시 Auth.getMe()로 본인 worker_id 취득 | 없음 | IsAuthenticated | 없음 | 없음 | MeView 응답에 "id": user.id 추가 | Auth.getMe() 반환값에서 me.id 참조 | layout.js를 통한 localStorage 저장 미적용 (getMe() 직접 호출) |

---

## 2. 요구사항 정의서

### MN-04-A: 작업자 현황 패널 실시간 지오펜스 연동

**분류:** 실시간 데이터 연동 / 프론트엔드
**중요도:** 상
**기능 목적:** HTTP 폴링(2초) 방식의 `MyStatusView` / `WorkerSummaryView` API 의존을 제거하고, WebSocket 기반 지오펜스 판정으로 실시간 상태 표시

**요구사항 상세:**
- 작업자 뷰: `Auth.getMe()` 로 취득한 `user.id`를 `workerStatusComputed` 이벤트의 `statuses` 맵에서 조회하여 본인 상태를 렌더링
- 관리자 뷰: `statuses` 전체를 순회하여 danger / warning / normal 인원 집계 후 KPI 카드·비율 바 갱신
- 첫 WS 메시지 수신 전까지는 `--` 대기 상태 유지 (기존 로딩 스켈레톤 대체)
- WS 연결 끊김 시 상태는 마지막 수신값 유지, 재연결 후 자동 갱신

**예외 사항:**
- 지오펜스 미등록: MapPanel._geofences 빈 배열 → 모든 작업자 'normal' 반환
- 본인 worker_id가 worker_positions에 없음: 대기 상태 유지, 에러 메시지 미표시

---

### MN-04-B: MapPanel updateWorkerPositions 이벤트 확장

**분류:** 프론트엔드 공통 모듈
**중요도:** 상
**기능 목적:** 지오펜스 판정 결과를 MapPanel 내부에서만 소비하지 않고 CustomEvent로 외부에 노출하여 여러 패널이 동일 판정 결과를 재활용

**요구사항 상세:**
- `positions` 파라미터를 Array 및 객체 (`{worker_id: {...}}`) 양쪽 허용 (기존 /ws/positions/ 경로 버그 수정 포함)
- 지오펜스 판정을 마커 유무와 무관하게 모든 작업자에 대해 선행 수행
- 판정 완료 후 `document.dispatchEvent(new CustomEvent('workerStatusComputed', { detail: statuses }))` 발행
- statuses 스키마: `{ [worker_id]: { status: 'normal'|'warning'|'danger', geofence_name: string|null, worker_name: string } }`
- 이후 마커 업데이트는 기존 로직 유지 (setter 불필요한 재렌더 방지)

**예외 사항:**
- MapPanel 초기화 전 WS 메시지 도착: `_geofences` 빈 배열로 판정 → 전부 normal, 이후 geofence 로드 후 재판정

---

### MN-04-C: 실시간 작업자 모니터링 페이지 연동

**분류:** 페이지 기능 / 실시간 연동
**중요도:** 중
**기능 목적:** `/dashboard/monitoring/workers/` 페이지의 하드코딩 더미 데이터를 제거하고 실제 DB + WebSocket으로 동작

**요구사항 상세:**
1. **초기 로드:** `GET /dashboard/api/workers-list/` → 작업자 목록(id, name, department) → 테이블 초기 렌더
2. **지오펜스 로드:** `GET /api/geofences/` → 클라이언트 측 판정에 사용
3. **실시간 갱신:** `/ws/sensors/` WebSocket → `worker_positions` 수신마다 처리
   - 각 작업자 x,y → `_findGeofence()` → risk_level → status (warning → caution CSS 매핑)
   - updated_at 기준 10초 이내 → connected: true
   - geofence name or movement_status → zone 컬럼
4. **폴백 (A안):** DB 목록에 없는 worker_id가 위치 데이터로 오면 즉석 등록 (더미 테스트용)

**B안 전환 조건 (미구현, 추후 적용):**
- A안 폴백 코드 제거: `_workerMap[workerId]` 없을 때 무시
- `WorkerListAPIView` 응답에 실제 worker 계정(user_type='worker')이 등록된 상태 전제
- DB worker_id와 FastAPI worker_positions의 worker_id가 일치해야 함 (더미 스크립트 수정 필요)

**예외 사항:**
- API 403: 비관리자 접근 차단 (Auth 미들웨어)
- API 실패: 빈 테이블 + WS 수신 시 즉석 등록으로 동작 유지
- WS 미연결: 테이블은 초기 로드 상태로 유지 (status: normal, connected: false)

---

### MN-04-D: 위험 현황 패널 UI 정리

**분류:** UI/UX
**중요도:** 하

**요구사항 상세:**
- PPE 착용 항목 제거 (IoT 센서·AI 영상 분석 미연동 상태)
- 라벨: "인신 확인 체크리스트" → "안전 확인 체크리스트"
- 아이콘: 체크리스트 📋, VR 교육 🥽
- 그리드 3열 → 2열, 아이콘 박스 36×36 → 44×44
- 알림 전송 버튼: 클릭 시 토스트 "추후 기능 연동 예정" 3초 표시

---

## 3. API 명세서

### DRF

#### GET /api/auth/me/
인증된 사용자 기본 정보 반환. **user.id 필드 추가됨.**

```json
// Response 200
{
  "id": 1,
  "username": "worker_a",
  "role": "worker",
  "menu_tree": [...]
}
```

#### GET /dashboard/api/workers-list/
관리자 소속 공장의 활성 작업자 목록 반환.

```json
// Request Header: Authorization: Bearer <JWT>
// Response 200
{
  "workers": [
    {
      "id": 1,
      "name": "작업자 A",
      "department": "공정관리팀",
      "department_id": 2,
      "is_present": true
    }
  ],
  "departments": [
    { "id": 2, "name": "공정관리팀" }
  ]
}
// Response 403: 비관리자 접근
{ "error": "권한이 없습니다." }
```

#### GET /api/geofences/
활성 지오펜스 목록 반환.

```json
// Response 200
[
  {
    "id": 1,
    "name": "A구역",
    "shape_type": "polygon",
    "polygon": [[100, 200], [300, 200], [300, 400], [100, 400]],
    "risk_level": "danger",
    "description": "용접 구역"
  }
]
```

---

### FastAPI

#### POST /api/positioning/receive
IoT 장비 또는 더미 스크립트로부터 작업자 위치 배열 수신.

```json
// Request Body
[
  {
    "worker_id": 1,
    "worker_name": "작업자 A",
    "facility_id": 1,
    "x": 250.5,
    "y": 310.2,
    "movement_status": "moving",
    "measured_at": "2026-05-01T09:00:00+00:00"
  }
]
// Response 201
{ "received": true, "count": 4 }
```

#### WS /ws/sensors/
브라우저 실시간 통합 데이터 스트림. 5초 주기 브로드캐스트.

```json
// 페이로드 (관련 필드만 발췌)
{
  "worker_positions": {
    "1": {
      "x": 250.5,
      "y": 310.2,
      "facility_id": 1,
      "worker_name": "작업자 A",
      "movement_status": "moving",
      "updated_at": "2026-05-01T09:00:00+00:00"
    }
  }
}
```

---

### CustomEvent (프론트엔드 내부)

#### workerStatusComputed
MapPanel.updateWorkerPositions() 호출 완료 시 document에 발행.

```javascript
// event.detail 스키마
{
  1: { status: "danger",  geofence_name: "A구역",  worker_name: "작업자 A" },
  2: { status: "normal",  geofence_name: null,      worker_name: "작업자 B" },
  3: { status: "warning", geofence_name: "B구역",  worker_name: "작업자 C" },
  4: { status: "normal",  geofence_name: null,      worker_name: "작업자 D" }
}
// status 값: 'normal' | 'warning' | 'danger'  (geofence.risk_level 그대로)
// CSS 매핑: warning → .caution 클래스
```

---

## 4. 흐름도

### MN-04-A/B: 대시보드 작업자 현황 패널

```
[position_dummy / IoT]
  │ POST /api/positioning/receive (1초마다)
  ▼
[FastAPI] worker_positions 상태 갱신
  │ broadcast_loop() 5초마다
  ▼
[Browser] /ws/sensors/ 수신
  │
  ├─ MapPanel.updateWorkerPositions(posArray)
  │     │
  │     ├─ 각 작업자 x,y → _pointInPolygon() → inGeofence
  │     ├─ statuses[worker_id] = { status, geofence_name, worker_name }
  │     ├─ 마커 색상 갱신 (기존 로직 유지)
  │     └─ document.dispatchEvent('workerStatusComputed', statuses)
  │
  └─ worker-panel.js addEventListener('workerStatusComputed')
        │
        ├─ [작업자 뷰] statuses[myWorkerId].status → 상태 블록 갱신
        └─ [관리자 뷰] Object.values(statuses) 집계 → KPI 카드·비율 바 갱신
```

### MN-04-C: 작업자 모니터링 페이지

```
[페이지 로드]
  │
  ├─ GET /dashboard/api/workers-list/  → 초기 테이블 렌더 (status: normal)
  └─ GET /api/geofences/              → _geofences 캐시
  │
  ▼
[WS /ws/sensors/ 연결]
  │ onmessage: worker_positions
  ▼
_processPositions(workerPositions)
  │
  ├─ 각 worker: _findGeofence(x, y) → risk_level → CSS status
  ├─ _isConnected(updated_at) → connected boolean
  ├─ _workerMap에 있으면 → _updateRow() (행 부분 갱신)
  └─ _workerMap에 없으면 → _allRows.push() → renderWorkerTable() 전체 재렌더 [A안 폴백]
  │
  ▼
updateSummary(총원, 연결 중 인원)
```

---

## 5. 파일별 역할

| 서버 | 파일 경로 | 변경 유형 | 역할 |
|:--|:--|:--|:--|
| DRF | `apps/accounts/views/auth_views.py` | 수정 | MeView 응답에 `"id": user.id` 추가 |
| DRF | `templates/snb_details/monitoring_workers.html` | 수정 | PPE 항목 제거, 라벨 변경, B안 주석 추가, 로딩 행 추가 |
| Frontend | `static/js/dashboard/panels/map-panel.js` | 수정 | `updateWorkerPositions()` — 배열·객체 정규화, 전체 작업자 지오펜스 판정, `workerStatusComputed` 이벤트 발행 |
| Frontend | `static/js/dashboard/panels/worker-panel.js` | 전면 재작성 | HTTP 폴링 제거 → `workerStatusComputed` 이벤트 리스너 방식으로 전환 |
| Frontend | `static/js/detail/monitoring_workers.js` | 전면 재작성 | 하드코딩 더미 제거 → DB API + WS 데이터 기반 실시간 테이블 |
| Frontend | `static/css/detail/monitoring_workers.css` | 수정 | risk-item-grid 3열→2열, 아이콘 박스 크기 확대 |

---

## 6. 디렉토리 경로

```
drf-server/
├── apps/
│   └── accounts/
│       └── views/
│           └── auth_views.py              ← MeView user.id 추가
├── templates/
│   └── snb_details/
│       └── monitoring_workers.html        ← PPE 제거, 라벨·주석 수정
└── static/
    ├── css/
    │   └── detail/
    │       └── monitoring_workers.css     ← 그리드 2열, 아이콘 크기
    └── js/
        ├── dashboard/
        │   └── panels/
        │       ├── map-panel.js           ← updateWorkerPositions 확장
        │       └── worker-panel.js        ← 전면 재작성 (WS 이벤트 방식)
        └── detail/
            └── monitoring_workers.js     ← 전면 재작성 (실시간 연동)

fastapi-server/
└── dummies/
    └── position_dummy.py                  ← 변경 없음 (worker_id 1~4 그대로 사용)
```

---

## 7. URL 정의서

| 서버 구분 | 메서드 | URL | 설명 |
|:--|:--|:--|:--|
| DRF | GET | `/api/auth/me/` | 로그인 사용자 정보 (id·role·username). **이번 작업에서 id 필드 추가** |
| DRF | GET | `/dashboard/api/workers-list/` | 관리자 소속 공장 활성 작업자 목록 (기존 API 재활용) |
| DRF | GET | `/api/geofences/` | 활성 지오펜스 목록 (기존 API 재활용) |
| FastAPI | POST | `/api/positioning/receive` | 위치 데이터 수신 → worker_positions 갱신 (기존) |
| FastAPI | WS | `ws://127.0.0.1:8001/ws/sensors/` | 브라우저 통합 데이터 스트림 (기존, worker_positions 포함) |
| FastAPI | WS | `ws://127.0.0.1:8001/ws/positions/` | 위치 전용 고빈도 채널 (기존, 버그 수정됨) |
| DRF | GET | `/dashboard/monitoring/workers/` | 작업자 모니터링 페이지 |

---

## 8. 생성/처리 조건

### 지오펜스 판정 (Ray Casting)
- 알고리즘: `_pointInPolygon(x, y, polygon)` — 수평 광선 교차 횟수 홀짝 판정
- 기준 좌표: 공장 도면 픽셀 좌표 (좌상단 원점, x: 0~1290, y: 0~590)
- 우선순위: `_geofences` 배열 순서 기준 첫 번째 매칭 지오펜스 채택 (중복 영역 시 등록 순서 우선)
- 원형(circle) 지오펜스: 현재 미지원, polygon으로만 판정

### 위험도 → CSS 클래스 매핑
| geofence risk_level | workerStatusComputed status | CSS 클래스 | 표시 |
|:--|:--|:--|:--|
| danger | danger | .danger | 위험 |
| warning | warning | .caution | 주의 |
| normal (미진입) | normal | .normal | 정상 |

### 연결 상태 판정
- `connected = (Date.now() - new Date(updated_at)) < 10,000ms`
- 10초 이상 위치 미수신 → `connected: false`, 행 흐림 처리

### 관리자 KPI 집계
- 위험 인원 > 0: `#mn04-danger-block`에 `.active` 클래스 추가 (pulse 애니메이션)
- 비율 바: `flex` 속성으로 normal : warning : danger 비율 시각화

### A안 폴백 조건 (현재 적용 중)
- `_workerMap[workerId]` 미존재 시: WS의 `worker_name`, `facility_id` 등으로 즉석 등록
- 해제 조건: DB에 실제 worker 계정 등록 + B안 전환 시 해당 코드 블록 제거

---

## 9. 서버 실행 명령어

```bash
# 터미널 1: DRF 서버
cd /home/cjy/diconai/drf-server
python manage.py runserver 8000

# 터미널 2: FastAPI 서버
cd /home/cjy/diconai/fastapi-server
uvicorn app:app --reload --port 8001

# 터미널 3: 위치 더미 전송 (작업자 4명, 1초 주기)
cd /home/cjy/diconai/fastapi-server
python -m dummies.position_dummy
```

---

## 10. 테스트 방법 및 결과

### 사전 조건
- 지오펜스 1개 이상 등록 필요 (관리자 계정으로 맵 패널에서 생성 또는 DB 직접 삽입)
- FastAPI 서버 실행 중
- position_dummy 실행 중

---

### 테스트 1: 관리자 뷰 — 대시보드 작업자 현황 패널

**접속:** 관리자 계정 로그인 → `http://localhost:8000/dashboard/`

**확인 포인트:**
```
[ ] 총원 4명 표시 (position_dummy 4명 기준)
[ ] 5초 이내 첫 WS 수신 후 '--' → 숫자로 갱신
[ ] 작업자가 지오펜스 진입 시 위험/주의 카운트 증가
[ ] 위험 인원 > 0일 때 좌측 위험 블록 붉게 강조 + pulse 애니메이션
[ ] 지오펜스 이탈 시 정상으로 복귀
```

---

### 테스트 2: 작업자 뷰 — 대시보드 작업자 현황 패널

**접속:** worker_id가 1~4 중 하나인 계정 로그인 → `http://localhost:8000/dashboard/`

**확인 포인트:**
```
[ ] 패널 초기: '위치 수신 중...' 또는 '--' 표시
[ ] WS 수신 후 본인 위치 기반 상태 표시 (정상/주의/위험)
[ ] 지오펜스 진입 시 패널 색상·텍스트 실시간 변경
[ ] 지오펜스 이탈 시 '정상' 복귀
```

**브라우저 콘솔 확인:**
```javascript
// 이벤트 수신 확인
document.addEventListener('workerStatusComputed', e => console.log(e.detail));
// 예상 출력: { 1: {status:'danger', geofence_name:'A구역'}, 2: {status:'normal', ...}, ... }
```

---

### 테스트 3: 작업자 모니터링 페이지

**접속:** 관리자 계정 → `http://localhost:8000/dashboard/monitoring/workers/`

**확인 포인트:**
```
[ ] 페이지 로드 시 '데이터 로딩 중...' 표시 후 작업자 목록 렌더
[ ] 전체 작업자 4명 / 현재 출입 작업자: WS 수신 후 갱신
[ ] 각 행: 작업자명, 소속(-), 작업지명(구역명 또는 이동 상태), 마지막 연결 시간, 연결 상태, 현재 상태 표시
[ ] 위험 지오펜스 진입 작업자 행 배경색 빨간색 변경
[ ] 연결 끊김(10초 미수신) 시 '● 연결 끊김' + 행 흐림 처리
[ ] 행 클릭 → 우측 디테일 패널 표시 (이름, 소속)
[ ] 디테일 패널: 체크리스트 📋, VR 교육 🥽 아이콘 표시
[ ] 알림 전송 버튼 클릭 → 우하단 토스트 "추후 기능 연동 예정" 3초 표시
[ ] 위험/주의/정상 배지 필터 클릭 시 해당 상태 작업자만 표시
```

---

### 향후 전환 필요 사항 (B안)

| 항목 | 현재 (A안) | B안 전환 후 |
|:--|:--|:--|
| 작업자 목록 소스 | DB + WS 폴백 자동 등록 | DB 등록 계정만 표시 (폴백 코드 제거) |
| 프로필 데이터 | WS worker_name만 표시 | `GET /api/workers/{id}/profile/` 호출 |
| position_dummy | worker_id 1~4 고정 | 실제 DB user.id와 일치하는 계정 생성 필요 |
| PPE 항목 | 제거 상태 | IoT/AI 연동 완료 후 재추가 |
