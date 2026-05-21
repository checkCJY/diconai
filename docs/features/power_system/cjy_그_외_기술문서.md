# 전력 시스템 — 기술 문서 (Tech)

> 대상 기능: 더미/실제 전력 장비 → FastAPI 수신 → DRF 저장 파이프라인 + **AI 추론 / 5축 정책 엔진** (§4 이하, 2026-05-19 추가)

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

---

## 4. 🤖 AI 추론 / 5축 정책 엔진

> 추가일: 2026-05-19 (브랜치 `feature/power_zscore_cp`). 전력 도메인이 STEP 5 권고 (Threshold + IF + Z-score + Change Point + ARIMA) 5축 완성한 시점 기록.
>
> 시간순 상세: [drf-server/docs/refactoring/power-ai-zscore-changepoint-2026-05-19.md](../../../drf-server/docs/refactoring/power-ai-zscore-changepoint-2026-05-19.md) (적용 보고) + [docs/codereviews/2026_05_19/power-5axis-policy-flow.md](../../codereviews/2026_05_19/power-5axis-policy-flow.md) (흐름·함수 분석).

### 4.1 📁 AI 관련 파일 구조

```text
fastapi-server/
├── ai/
│   ├── router.py                    # IF/ARIMA 모델 로더 + 추론 엔드포인트 (3축 매칭)
│   └── risk_combine.py              # combine_risk / combine_risk_3axis / combine_risk_5axis
└── power/services/
    ├── power_service.py             # process_anomaly_inference — IF + Z-score + CP +
    │                                #   ARIMA + night_abnormal + 5축 결합 + 알람 발화
    ├── change_point_service.py      # [신규] STEP E Change Point 탐지 + 상태머신
    ├── quality_guard.py             # 통신단절·오버플로우·센서고정 사전 차단
    └── threshold_eval.py            # calculate_power_risk — 정격 대비 threshold

drf-server/
├── apps/core/constants.py           # ALGORITHM_SOURCE_LABEL (fastapi 측과 동기)
├── apps/alerts/models/alarm_record.py  # AlarmRecord.algorithm_source CharField
└── apps/ml/                         # MLModel / MLAnomalyResult / 학습 명령
    └── management/commands/
        ├── train_anomaly_model.py   # IF 학습 (모든 sensor_type)
        └── train_arima_power_model.py  # ARIMA 학습 (전력 전용, sensor_identifier 단위)
```

### 4.2 🔄 AI 추론 파이프라인 흐름

```
[POST /api/power/watt] (§3 수집 파이프라인 진입 후)
      │
      ▼
[FastAPI — power_service.process_anomaly_inference]
   │
   ├─ (0) quality_guard — 통신단절(-1) / 오버플로우 / 센서고정(분산=0) 사전 skip
   │
   ├─ (1) IF 추론 윈도우 누적 — _power_windows[(channel, data_type)] deque(maxlen=30)
   │      윈도우 < 30 면 추론 skip (초반 통계 불안정 보호)
   │
   ├─ (2) IF 추론 — sklearn IsolationForest
   │      pred = "anomaly" if model.predict(row) == -1 else "normal"
   │      score = model.decision_function(row)[0]
   │
   ├─ (3) Z-score (STEP D) — _zscore_check(window, value, threshold=3.0) → (bool, z)
   │      윈도우 mean/std 로 |z| 계산. >= 3 면 fire.
   │      fire 시 dedicated 로그: [zscore] device=... value=... |z|=... >= 3.0
   │
   ├─ (4) Change Point (STEP E) — detect_change_point(key, value) → (bool, meta)
   │      별도 _cp_windows deque(maxlen=60) — prev[0:30] vs curr[30:60] 비교.
   │      상태머신 STABLE → SHIFT 전이 시점만 True (중복 발화 방지).
   │      fire 시 로그: [change_point] device=... STABLE->SHIFT mean_shift=... std_ratio=...
   │
   ├─ (5) ARIMA forecast (sensor_identifier 단위) — _arima_forecast
   │      pkl 없는 채널은 silent fallback (arima_violation=False).
   │      forecast / 95% CI / 위반 여부 반환.
   │
   ├─ (6) threshold_risk — calculate_power_risk(value, 정격) → normal/warning/danger
   │
   ├─ (7) 5축 결합 — combine_risk_5axis (§4.3 상세)
   │      returns (combined, escalation_source)
   │
   ├─ (8) night_abnormal 시각 분기 — KST 22~05 + watt > 정격 30% 시 한 단계 격상
   │
   ├─ (9) algorithm_source 결정 (§4.4 상세) — 6단계 priority
   │
   ├─ (10) 추론 로그 — [anomaly_inference] device=... z=... cp=... combined=... score=...
   │
   └─ (11) forward_inference_e2e — async fire-and-forget
          • DRF MLAnomalyResult 저장 (운영 추적, 매번)
          • should_fire (combined ∈ caution/predict_warn/danger) + rate_limit 60s 통과 시:
              - AlarmRecord 저장 (algorithm_source 동행)
              - WebSocket push (anomaly_meta payload — §4.6)
```

### 4.3 🧮 5축 정책 엔진 — `combine_risk_5axis`

STEP 5 우선순위 매트릭스: CRITICAL > ML_ANOMALY > ANOMALY_WARNING > TREND_SHIFT > PREDICTIVE_ALERT > NORMAL.

```python
def combine_risk_5axis(
    threshold_risk, if_prediction, arima_violation,
    z_score_anomaly, change_point,
) -> tuple[str, str]:
    """Returns (combined, escalation_source)."""
    base = combine_risk_3axis(threshold_risk, if_prediction, arima_violation)
    if base != "normal":
        return base, ""                          # 3축이 driver — z/cp 무시
    if change_point:
        return "predict_warn", "change_point"
    if z_score_anomaly:
        return "predict_warn", "zscore"
    return "normal", ""
```

**매핑표**:

| 우선순위 | STEP 5 권고 | 조건 | combined | escalation_source |
|---|---|---|---|---|
| 1 | CRITICAL | threshold = danger | "danger" | "" |
| 2 | ML_ANOMALY (강함) | IF anomaly + ARIMA viol | 3축 격상 (warning/danger) | "" |
| 2 | ML_ANOMALY | IF anomaly 단독 | 3축 base | "" |
| 3 | ANOMALY_WARNING | Z-score, base=normal | "predict_warn" | "zscore" |
| 4 | TREND_SHIFT | CP, base=normal | "predict_warn" | "change_point" |
| 5 | PREDICTIVE_ALERT | ARIMA viol 단독 | 3축 base (predict_warn) | "" |
| 6 | NORMAL | 모두 False | "normal" | "" |

**핵심 설계 — base 위임**: `combine_risk_5axis` 는 신규 매트릭스를 정의하지 않고 `combine_risk_3axis` (W3.1 12-cell) 위임 + 추가 격상만 처리. 회귀 가드 자동 (z=F·cp=F 일 때 5축 결과 == 3축).

**escalation_source 의 의미**: "z/cp 가 실제 risk 격상에 기여했는가" 명시. base 가 이미 발화 등급이면 z/cp 발생해도 ""—라벨이 driver 와 어긋나지 않음 (코드리뷰 §2.1 보강).

### 4.4 🏷 algorithm_source 우선순위 + 라벨

`AlarmRecord.algorithm_source` 필드 + 알람 토스트 prefix 결정 흐름:

```python
if night_escalated:                                # KST 22~05 야간 격상
    algorithm_source = "night_abnormal"
elif prediction == "anomaly" and arima_violation:  # 두 AI 동의
    algorithm_source = "combined"
elif escalation_source == "change_point":          # CP 가 격상 driver
    algorithm_source = "change_point"
elif arima_violation:                              # ARIMA 단독
    algorithm_source = "arima"
elif escalation_source == "zscore":                # Z-score 가 격상 driver
    algorithm_source = "zscore"
elif prediction == "anomaly":                      # IF 단독
    algorithm_source = "isolation_forest"
else:                                              # threshold 단독 발화 등
    algorithm_source = ""                          # UI fallback "AI"
```

**라벨 매핑** (단일 진실 공급원 — fastapi `_ALGORITHM_SOURCE_LABEL` ↔ drf `ALGORITHM_SOURCE_LABEL` 양쪽 동기):

| 코드값 | UI 라벨 | 의미 |
|---|---|---|
| `night_abnormal` | "야간 가동" | KST 22~05 + 정격 30% 초과 격상 |
| `combined` | "IF+ARIMA" | 두 AI 모델 동의 |
| `change_point` | "급변" | CP STABLE→SHIFT 전이 (격상 driver) |
| `arima` | "ARIMA" | ARIMA forecast CI 위반 |
| `zscore` | "Z-score" | Z-score \|z\| >= 3 (격상 driver) |
| `isolation_forest` | "IF" | IF 학습 분포 outlier |
| `""` (빈값) | "AI" (fallback) | threshold 단독 발화 / 미정 |

운영자가 UI 토스트에서 즉시 출처 인식: `[Z-score 이상 감지] CH1 watt=5341 (combined=predict_warn)`.

### 4.5 📚 STEP 5 권고와 코드 1:1 매핑 (학습 시연 가치)

| STEP 5 권고 | 가스 적용 | 전력 적용 (2026-05-19 기준) | 코드 위치 |
|---|---|---|---|
| STEP B — Threshold | ✅ | ✅ | `core/power_thresholds.py` / `threshold_eval.py` |
| STEP C — Sliding Window | ✅ | ✅ | `_power_windows` (IF 30) / `_cp_windows` (CP 60) |
| STEP D — Z-score | ❌ | ✅ | `power_service._zscore_check` |
| STEP E — Change Point | ❌ | ✅ | `change_point_service.detect_change_point` |
| STEP F — Isolation Forest | ✅ (15피처 다변량) | ✅ (4피처 단변량) | `ai/router._get_or_load` + IF 추론 |
| STEP G — ARIMA | ✅ (IF 입력 피처) | ✅ (CI 위반 독립 판단자) | `ai/router._get_or_load_arima` + `_arima_forecast` |
| 5축 정책 엔진 | ◑ (3축) | ✅ (5축) | `risk_combine.combine_risk_5axis` |

→ 전력 도메인은 **STEP 5 권고의 5축 우선순위 매트릭스를 코드 구조로 명시화** 완성. 시연 시 "권고와 실제 코드의 1:1 일치" 가시화 가능.

### 4.6 📡 anomaly_meta payload 구조 (WebSocket / UI)

`forward_inference_e2e` 의 push_payload 안 `anomaly_meta` — UI 가 알람 토스트·이벤트 패널에서 디테일 표시 시 사용:

```python
"anomaly_meta": {
    # 기존 (W3.2 + W4.a 시점)
    "combined_risk": combined,                   # "normal"|"caution"|"predict_warn"|"warning"|"danger"
    "anomaly_score": score,                      # IF decision_function 결과
    "device_id": device_id,
    "channel": channel,
    "data_type": data_type,
    "algorithm_source": algorithm_source,        # §4.4 라벨 코드
    "arima_forecast": ...,                       # float | None
    "arima_ci": [lower, upper],                  # [float, float] | None

    # §F (2026-05-19) 추가 — 5축 입력 노출
    "z_score_anomaly": z_score_anomaly,          # bool
    "change_point": change_point,                # bool
    "cp_mean_shift": ...,                        # float | None (change_point=True 일 때만)
    "cp_std_ratio": ...,                         # float | None
}
```

UI 활용 예시:
- `algorithm_source="zscore"` + `anomaly_meta` z 값 노출 시 "평소대비 4.17σ 튐" 디테일 표시 가능
- `algorithm_source="change_point"` 시 `cp_mean_shift` / `cp_std_ratio` 로 "추세 변화 강도" 표시

### 4.7 📑 시간순 문서 인덱스 (전력 AI sprint 진행 순서)

| 시점 | 단계 | 문서 |
|---|---|---|
| 2026-05-13 | IF 윈도우 비교 | [docs/changelog/ml/if_window_comparison_2026_05_13.md](../../changelog/ml/if_window_comparison_2026_05_13.md) |
| 2026-05-13 | power dummy 패턴 정리 | [docs/changelog/ml/power_dummy_audit_2026_05_13.md](../../changelog/ml/power_dummy_audit_2026_05_13.md) |
| 2026-05-14 | IF 알람 결합 (트랙 1 v2) | [docs/changelog/ml/if_alarm_binding_power_2026_05_14.md](../../changelog/ml/if_alarm_binding_power_2026_05_14.md) |
| 2026-05-18 | IF + ARIMA un-downgrade (3축) | [skill/전력 AI un-downgrade ... 보고.md](../../../skill/전력%20AI%20un-downgrade%20(IF%20%2B%20ARIMA)%20통합%20작업%20복습%20및%20보고.md) |
| 2026-05-19 | Z-score + CP + 5축 + 코드리뷰 보강 | [drf-server/docs/refactoring/power-ai-zscore-changepoint-2026-05-19.md](../../../drf-server/docs/refactoring/power-ai-zscore-changepoint-2026-05-19.md) + [docs/codereviews/2026_05_19/power-5axis-policy-flow.md](../../codereviews/2026_05_19/power-5axis-policy-flow.md) |

본 § 4 (살아있는 spec) 는 위 시간순 문서들의 **현 시점 합본** — 시간순 docs 가 "어떻게 도달했는가", 본 § 가 "지금 어떻게 동작하는가".
