# 전력 시스템 — 요구사항 정의서 (PRD)

## 1. 요구사항 정의서 (POWER-01)

### 1.1. 기본 정보

- **기능명:** 전력 데이터 실시간 수신 및 저장
- **중요도:** 상
- **관련 화면/컴포넌트:**
  - `fastapi-server/power_system/router_cjy.py` — 수신 엔드포인트
  - `drf-server/apps/monitoring/` — 저장 및 조회
  - 대시보드 전력 패널 (3/4순위 작업 완료 후 연동 예정)

---

### 1.2. 비즈니스 로직 및 기능 요구사항

**선행 조건 (Pre-condition)**
- FastAPI 서버(port 8001)와 DRF 서버(port 8000)가 모두 실행 중이어야 함
- 수신할 `device_id`에 해당하는 `PowerDevice`가 DRF DB에 등록되어 있어야 함
  - 미등록 시 PowerDevice.DoesNotExist → 500 반환

**기본 흐름 (Happy Path)**

1. 더미 센서 또는 실제 전력 장비가 FastAPI로 HTTP POST 전송
2. FastAPI `router_cjy.py`에서 Pydantic 스키마로 페이로드 검증
3. `measured_at = datetime.now(timezone.utc)` 주입 (장치 측정 시각, UTC)
4. 페이로드 변환
   - ON/OFF: `to_snapshot()` → `{"1": bool, ..., "16": bool}`
   - 측정값: `to_channel_values()` → `[{channel, value, risk_level}, ...]`
5. DRF 엔드포인트로 비동기 POST 전송 (httpx, timeout=5s)
6. DRF `serializers_cjy.py`에서 `device_id` → `PowerDevice` FK 조회
7. DB 저장
   - ON/OFF: `PowerEvent.objects.create()`
   - 측정값: `PowerData.objects.bulk_create(ignore_conflicts=True)`
8. FastAPI가 DRF 응답을 그대로 클라이언트에 반환

**데이터 검증 (Validation)**

| 검증 위치 | 항목 | 규칙 |
|-----------|------|------|
| FastAPI (Pydantic) | slave01~slave72 (ON/OFF) | integer, 0 or 255 |
| FastAPI (Pydantic) | slave01~slave72 (측정값) | float, >= -1 (-1은 통신 불능) |
| FastAPI (Pydantic) | device_id | string, max_length=50 |
| FastAPI (router) | measured_at | datetime.now(timezone.utc), naive 금지 |
| DRF (Serializer) | snapshot 키 | "1"~"16" 문자열 (1-based) |
| DRF (Serializer) | snapshot 값 | bool (True=ON, False=OFF) |
| DRF (Serializer) | data_type | "current" / "voltage" / "watt" |
| DRF (Serializer) | channel | integer, 1~16 |
| DRF (Serializer) | risk_level | "normal" / "warning" / "danger" |

**후행 조건 (Post-condition)**

- `PowerEvent` 테이블: ON/OFF 스냅샷 1행 저장, `changed_channels` 자동 계산 포함
- `PowerData` 테이블: 채널별 측정값 최대 16행 저장 (long-format)
- 동일 시각 중복 전송 시 uq 충돌 무시 (`ignore_conflicts=True`)
- `value == -1` 채널(통신 불능)도 DB에 저장됨 → 집계 쿼리 시 `WHERE value != -1` 조건 필수

---

### 1.3. 예외 및 에러 처리 (Edge Cases)

| 상황 | 처리 |
|------|------|
| device_id 미등록 | `PowerDevice.DoesNotExist` → DRF 500 → FastAPI 502 반환 |
| slave 값이 0/255 이외 (ON/OFF) | Pydantic ValidationError → FastAPI 422 |
| slave 값이 -1 미만 (측정값) | Pydantic ValidationError → FastAPI 422 |
| snapshot 키가 1~16 범위 외 | DRF ValidationError → 400 |
| snapshot 값이 bool 아닌 경우 | DRF ValidationError → 400 |
| measured_at 형식 오류 | DRF ValidationError → 400 |
| DRF 서버 5초 내 응답 없음 | FastAPI 504 반환 |
| 동일 (device, channel, data_type, measured_at) 중복 | `ignore_conflicts=True`로 무시, 정상 응답 |
| value == -1 채널 포함 | 정상 저장, 집계 쿼리에서 필터링 필요 |
| changed_channels 최초 수신 | None 저장 (비교 대상 없음) |

---

### 1.4. 비기능적 요구사항 (보안/성능/로깅)

**시계열 보장**
- `measured_at`은 반드시 `timezone.utc` 기준 aware datetime 사용
- `datetime.now()` (naive) 사용 금지 — PostgreSQL `USE_TZ=True` 환경에서 시계열 오염 발생

**성능**
- 전력 데이터 전송 주기: 1분에 1회 (4종 × 16채널 = 최대 64행/분)
- `PowerData` bulk_create로 채널당 개별 INSERT 제거
- DRF 호출 timeout: 5초

**보안**
- DRF 수신 엔드포인트 현재 `AllowAny` 적용 (내부 서비스 전용)
- 추후 서비스 토큰(`DRF_SERVICE_TOKEN`) 인증 정책 결정 후 `IsAuthenticated`로 전환 예정

**미결 사항**
- `risk_level` 현재 `NORMAL` 고정 → `thresholds.py` 전력 임계치 정의 후 계산 로직 추가 예정
- 3순위/4순위 (WebSocket 통합 + HTML 화면 출력) — GitHub 팀 머지 완료 후 진행
