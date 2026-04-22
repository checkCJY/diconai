# 전력 시스템 — 기술 문서 (Tech)

> 대상 기능: 더미/실제 전력 장비 → FastAPI 수신 → DRF 저장 파이프라인

---

## 1. 📁 신규 추가 파일 및 디렉토리

```text
fastapi-server/
├── main.py                                  # [수정] power_router include 추가
└── power_system/
    ├── schemas.py                           # [기존] Pydantic 검증 스키마 정의
    │                                        #   PowerOnOffPayload, PowerCurrentPayload,
    │                                        #   PowerVoltagePayload, PowerWattPayload
    │                                        #   SLAVE_KEYS, SLAVE_TO_CHANNEL 매핑 포함
    └── router_cjy.py                        # [신규] 전력 수신 엔드포인트 4개
                                             #   Pydantic 검증 → measured_at UTC 주입
                                             #   → DRF 비동기 전송 (httpx)

drf-server/
├── config/
│   └── urls.py                              # [수정] monitoring/ 라우팅 추가
└── apps/monitoring/
    ├── serializers/
    │   └── serializers_cjy.py               # [신규] 전력 데이터 수신 시리얼라이저
    │                                        #   PowerEventIngestSerializer_cjy
    │                                        #   PowerDataBulkIngestSerializer_cjy
    ├── views/
    │   └── views_cjy.py                     # [신규] 전력 데이터 수신 뷰 2개
    │                                        #   PowerEventIngestView_cjy
    │                                        #   PowerDataBulkIngestView_cjy
    └── urls_cjy.py                          # [신규] 전력 수신 URL 라우팅
```

---

## 2. 🔗 신규 URL 및 엔드포인트 명세

### FastAPI Endpoints (port 8001)

| Method | URI | 역할 |
|--------|-----|------|
| POST | `/api/power/onoff` | 16채널 ON/OFF 스냅샷 수신 → PowerEvent 저장 |
| POST | `/api/power/current` | 16채널 전류(A) 수신 → PowerData 저장 |
| POST | `/api/power/voltage` | 16채널 전압(V) 수신 → PowerData 저장 |
| POST | `/api/power/watt` | 16채널 전력(W) 수신 → PowerData 저장 |

### Backend API Endpoints (DRF, port 8000)

| Method | URI | 역할 |
|--------|-----|------|
| POST | `/monitoring/api/power/event/` | FastAPI로부터 PowerEvent 수신 및 DB 저장 |
| POST | `/monitoring/api/power/data/` | FastAPI로부터 PowerData 16채널 일괄 수신 및 DB 저장 |

---

## 3. 🔄 데이터 흐름도 (Data Flow Diagram)

```
[더미 센서 / 실제 전력 장비]
  │  HTTP POST
  │  power_dummy_sender.py → run_power_sender() 로 전송
  ▼
[FastAPI — power_system/router_cjy.py]
  │  1. Pydantic 스키마 검증
  │     - ON/OFF : PowerOnOffPayload (slave01~slave72, 값: 0 or 255)
  │     - 측정값 : PowerCurrentPayload / VoltagePayload / WattPayload (값: -1 이상 float)
  │  2. measured_at = datetime.now(timezone.utc) 주입
  │     (naive datetime 금지 — USE_TZ=True 환경 시계열 오염 방지)
  │  3. 페이로드 변환
  │     - ON/OFF : to_snapshot() → {"1": bool, ..., "16": bool}
  │     - 측정값 : to_channel_values() → [{channel, value, risk_level}, ...]
  │     (risk_level 현재 NORMAL 고정 — thresholds.py 구현 후 계산 로직 추가 예정)
  ▼
[DRF — monitoring/serializers/serializers_cjy.py]
  │  4. device_id → PowerDevice FK 조회
  │
  ├─ (ON/OFF 경로) ────────────────────────────────────────────────
  │   5-A. PowerEventIngestSerializer_cjy
  │        - snapshot 구조 검증 (키: "1"~"16", 값: bool)
  │        - 직전 스냅샷과 비교 → changed_channels 자동 계산
  │          (최초 수신 시 None, 이후 변경된 채널 번호 리스트)
  │        - PowerEvent.objects.create()
  │
  └─ (측정값 경로) ─────────────────────────────────────────────────
      5-B. PowerDataBulkIngestSerializer_cjy
           - 16채널 PowerData 일괄 생성
           - bulk_create(ignore_conflicts=True)
             (동일 시각 중복 전송 시 uq 충돌 무시)
           - value == -1 채널(통신 불능)도 저장
             (집계 쿼리에서 WHERE value != -1 조건 필수)
  ▼
[PostgreSQL]
  power_event 테이블 / power_data 테이블
  ▼
[확인]
  Django Admin → http://localhost:8000/admin/
  Power events / Power datas 항목에서 데이터 누적 확인
```
