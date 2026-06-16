## `power_dummy.py` — 전력 더미 시뮬레이터 (v3, IF 학습 데이터용)

실제 전력 센서 장비 없이 fastapi 전력 endpoint 에 더미 데이터를 주기적으로 전송합니다. 한 루프에서 16채널 × (W, A, V, ON/OFF) 를 한 번에 계산해 4개 endpoint 에 송신.

**v2 → v3 진화 핵심**: v2 의 `random.randint` 균등 분포 + 시계열 자기상관 없음 = IF 학습 부적합 → v3 의 채널 정격 기반 + 시간대별 base_load + 시나리오 6종 + 상태머신 (RAMP/HOLD/DOWN).

가스의 `gas_dummy.py` 가 9종 가스 농도를 한 페이로드로 보내는 반면, 전력은 16채널 × 3종 + ON/OFF 가 한 틱에 4 페이로드 분기. 시나리오도 가스는 농도 임계 위주, 전력은 다축 패턴 (motor_stuck = W↓ + A↓ + V유지) 학습용.

---

### 전체 구조 한눈에 보기

```
run()
    └─ while True:
        ├─ _build_tick()
        │     ├─ get_scenario_mode() — settings.DUMMY_SCENARIO_MODE (mixed/normal/...)
        │     ├─ _apply_mode(mode)
        │     │     ├─ mixed → maybe_trigger(ch별, p=0.005, weights, hold)
        │     │     └─ scenario 단일 → enter_scenario(ch, scenario)
        │     │     └─ FIXED (normal/warning/danger) → 상태머신 미사용
        │     │
        │     └─ for ch in 1..16:
        │           ├─ if FIXED_LEVELS → _fixed_level_value(ch, level)
        │           └─ else → _compute_channel_tick(ch, hour)
        │                 ├─ base_load_ratio(hour, ch) → 시간대별 부하 0.0~1.0
        │                 ├─ normal_w/a/v = rated × ratio × gauss(0.05)
        │                 └─ step(ChannelState) → out (RAMP/HOLD/DOWN)
        │                       ├─ out.is_anomaly=False → normal 값 반환
        │                       └─ out.is_anomaly=True  → mix(normal, scenario, weight)
        │
        ├─ send_data(POWER_ONOFF_URL,   onoff_payload, "POWER_ONOFF")
        ├─ send_data(POWER_CURRENT_URL, current_payload, "POWER_CURRENT")
        ├─ send_data(POWER_VOLTAGE_URL, voltage_payload, "POWER_VOLTAGE")
        ├─ send_data(POWER_WATT_URL,    watt_payload, "POWER_WATT")
        └─ time.sleep(DUMMY_SEND_INTERVAL_SEC)
```

---

### 왜 v3 가 IF 학습용으로 재설계되었는가

**선택**: v2 의 `random.randint` 균등 분포를 폐기하고 (a) 채널 정격 기반 + (b) 시간대별 base_load + (c) 시나리오 가중치 + (d) 상태머신 도입.

**배경**: v2 데이터로 IF 학습 시 학습 데이터 자체가 "랜덤 노이즈" 분포 → IF 가 "정상 영역" 을 모름. 실제 운영에서는 정상값도 자기상관 (이전 값에 가까움) + 시간대 패턴 (낮 0.55 / 밤 0.15) 을 가짐. v3 는 그 패턴을 모사.

```python
# v3 의 정상값
normal_w = rated["w"] * base_load_ratio(hour, ch) * _gauss_factor(0.05)
```

**트레이드오프**:
- ↑ **IF 학습 적합** — 정상값이 시간대·채널·정격 의존 → IF 가 "8시 ch1 = W 3750 부근" 같은 분포를 학습.
- ↑ **시연 신뢰성** — 차트가 시간대별로 자연스럽게 변동. 시연 중 "왜 야간에 갑자기 떨어지나" 같은 질문에 도메인적으로 답변 가능.
- ↑ **시나리오 라벨링** — 매 row 에 `is_anomaly` + `anomaly_type` 동봉 → 학습 데이터셋 추출 시 라벨 ground truth 자동.
- ↓ **결정론적 패턴** — base_load 가 hour 함수로 고정. 실제 공장은 휴일/주말/계절 변동이 있는데 본 더미는 없음. 운영 환경 IF 가 더미 학습으로 잘 작동하는지 별도 검증 필요.
- ↓ **CHANNEL_RATED 시드와 분기** — 본 파일 + `migrations/0017_seed_power_channel_meta.py` 양쪽에 채널 정격 보관. 한쪽 변경 시 다른 쪽 잊으면 더미 vs DB 분기. 주석 (`시드와 갈라지지 않게 변경 시 양쪽 동시 수정 필수`) 만 있음.

---

### 왜 시나리오 6종 + 가중치 (30/8/7/20/20/15) 인가

**선택**: overload (30) / voltage_drop (8) / phase_loss (7) / degradation (20) / night_abnormal (20) / motor_stuck (15) = 합 100.

```python
SCENARIO_WEIGHTS = [30, 8, 7, 20, 20, 15]
```

**배경**: W0 plan (`power-ai-un-downgrade-phase2-apply` §3) — P0 (overload + degradation + night_abnormal) = 70, P1 (motor_stuck) = 15, 보조 (voltage_drop + phase_loss) = 15.
- overload = 룰 + IF + ARIMA 모두 동의 (시연 핵심)
- degradation = ARIMA trend break 시연
- night_abnormal = 야간 가동 (`_NIGHT_ESCALATION` 검증용)
- motor_stuck = 다축 상관 (W↓+A↓+V유지 — IF 다변량 학습)
- voltage_drop / phase_loss = 도메인 사고 패턴 (보조)

**트레이드오프**:
- ↑ **시연 핵심 시나리오 가중치 ↑** — overload + degradation = 50% 발생. 시연 중 알람 자주 발화 → 데모 효과.
- ↑ **다축 상관 학습** — motor_stuck (W↓+A↓+V유지) 가 IF 의 다변량 학습 가치 검증.
- ↑ **W0 변경 흔적 보존** — `spike` 가 SCENARIO_PATTERNS 에 없지만 PowerData.AnomalyType.SPIKE 는 남아 있음 (옛 row 호환). 도메인 진화의 흔적.
- ↓ **가중치 하드코딩** — admin 토글 없음. 시나리오 분포 조정 시 코드 수정 + 더미 재시작 필요.
- ↓ **MIXED_TRIGGER_PROBABILITY=0.005 마법 숫자** — `16채널 × 0.005 = 0.08 → 평균 12.5틱당 1건` 주석. 시연 환경에서 알람 분포의 의도된 모양인지 운영 검증 부족.
- ↓ **multi 플래그 처리** — voltage_drop 만 `multi=True` (전 채널 동시 적용). 다른 시나리오는 단일 모터 채널. multi 도입 의도 (`Phase 3 다채널 학습 가치`) 가 주석에 있지만 다른 시나리오로 확장 시 정책 모호.

---

### 왜 base_load_ratio 가 0.50/0.55 로 낮춰져 있는가

**선택**: 모터 채널의 시간대별 부하 baseline 을 0.50 (8~12시) / 0.55 (13~18시) / 0.30 (19~22시) / 0.15 (야간).

```python
def base_load_ratio(hour, ch):
    if ch in LIGHTING_CHANNELS: return 0.4
    if ch in PANEL_CHANNELS:    return 0.5
    if 8 <= hour < 12:  return 0.50
    if 13 <= hour < 18: return 0.55
    if 19 <= hour < 22: return 0.30
    return 0.15
```

**배경**: T4 D2 시연 검증 (2026-05-20) — 이전 0.60/0.70 + gauss(0.05) 노이즈 가 정적 80% 임계 부근에 자주 도달 → 시나리오 모드 무관 자연 발화 다발. baseline 을 0.50/0.55 로 낮춰 80% 와 거리 확보 → T4 cover 시연이 noise 에 묻히지 않도록.

**트레이드오프**:
- ↑ **시연 안정성** — baseline 이 50% 부근이라 80% 임계 도달 자연 빈도 ↓. overload 시나리오 (factor 1.10) 발화 시 명확한 신호.
- ↑ **CP 시연 가치** — baseline 이 안정적이라 시나리오 진입 시 CP (two-window mean_shift) 가 잘 잡힘.
- ↓ **운영 환경 부합도 ↓** — 실제 공장의 평균 부하는 도메인마다 60~80% 가 흔함. 더미 데이터로 학습한 IF 가 실제 운영 시 baseline 차이로 위양성↑ 가능.
- ↓ **튜닝 흔적이 코드에만** — 0.60→0.50 변경 이유가 docstring 에 적혀 있지만 PR/changelog 에는 없음. 신규 개발자가 "왜 0.50?" 질문 시 답이 함수 안 주석.

---

### 왜 한 틱에 4 endpoint 전송인가

**선택**: 한 `_build_tick()` 호출 후 onoff/current/voltage/watt 4개 endpoint 에 직렬 전송.

```python
send_data(FASTAPI_POWER_ONOFF_URL,   tick["onoff"],   "POWER_ONOFF")
send_data(FASTAPI_POWER_CURRENT_URL, tick["current"], "POWER_CURRENT")
send_data(FASTAPI_POWER_VOLTAGE_URL, tick["voltage"], "POWER_VOLTAGE")
send_data(FASTAPI_POWER_WATT_URL,    tick["watt"],    "POWER_WATT")
```

**배경**: fastapi 의 데이터 종별 endpoint 분기를 따름. 한 endpoint 가 4종을 받으면 fastapi 의 라우팅이 복잡해짐 (data_type 분기 필수).

**트레이드오프**:
- ↑ **fastapi 라우팅 단순** — endpoint 별 핸들러가 한 종 만 처리. `power_router` 의 schema validation 명확.
- ↑ **부분 장애 격리** — current endpoint 가 죽어도 voltage/watt 는 계속 전송. fastapi 측에서 종별 안정성 분리.
- ↓ **직렬 전송 — 시각 불일치** — 4개 request 가 직렬이라 measured_at 이 같아도 fastapi 도착 시각 차이. AI 추론 시 같은 시점의 4종 데이터가 다른 timer 로 들어와 `_power_windows` 누적 시차 발생.
- ↓ **에러 복구 없음** — `send_data` 가 ConnectionError/Timeout 시 로그만, 재시도 0. fastapi 가 잠시 죽으면 그 틱 데이터 통째로 손실. 더미 데이터라 영향 0 이지만 실 운영 시뮬 부족.
- ↓ **4 request RTT** — 1초 주기 sleep 안에 4 request × ~10ms 가 들어가야 함. 네트워크 지연 환경에서 sleep 시간보다 송신 시간이 길면 주기 drift.

대안: gRPC streaming 또는 한 endpoint 에 4종을 한 페이로드로 묶기 (단점: schema 복잡도).

---

### 왜 anomaly_labels 가 페이로드 동봉인가

**선택**: 시나리오 발화 시 페이로드에 `anomaly_labels={ch: type}` 추가.

```python
if anomaly_labels:
    current_payload["anomaly_labels"] = anomaly_labels
    voltage_payload["anomaly_labels"] = anomaly_labels
    watt_payload["anomaly_labels"] = anomaly_labels
```

**배경**: fastapi → DRF 의 `PowerDataBulkIngestSerializer` 가 페이로드의 `anomaly_labels` 를 읽어 row 의 `is_anomaly=True, anomaly_type=label` 저장. IF 학습 시 라벨 ground truth 자동.

**트레이드오프**:
- ↑ **학습 라벨 자동** — 더미가 발화시킨 시나리오가 즉시 DB row 에 라벨. 별 라벨 파일 관리 0.
- ↑ **3 endpoint 일관 라벨** — current/voltage/watt 셋에 같은 라벨 동봉. 같은 시점·채널의 3종이 모두 is_anomaly=True. cross-axis 분석 자연스러움.
- ↓ **onoff 페이로드에는 라벨 없음** — `onoff_payload` 에는 `anomaly_labels` 미동봉. 운영 의도 (ON/OFF 는 이상 라벨 의미 없음?) 인지 누락인지 모호.
- ↓ **운영 환경에서는 anomaly_labels 가 항상 없음** — 실제 센서는 라벨 안 보냄. fastapi/DRF 의 페이로드 검증이 anomaly_labels 옵션을 항상 허용해야 함. 더미 전용 필드라는 점이 schema 에 명시 안 됨.

---

### 왜 _gauss_factor 가 clamp [0.5, 1.5] 인가

**선택**: 정규분포 noise 를 0.5~1.5 로 clamp.

```python
def _gauss_factor(stddev=0.05):
    return max(0.5, min(1.5, random.gauss(1.0, stddev)))
```

**배경**: stddev=0.05 이면 3σ 가 [0.85, 1.15]. clamp [0.5, 1.5] 는 극단 outlier (10σ 등 매우 드문 케이스) 방지. 정격 ×0.5 미만 또는 ×1.5 초과는 정상 운영 영역 외.

**트레이드오프**:
- ↑ **outlier 차단** — 정상 운영 모드에서 우연히 정격 200% 같은 noise 발생 안 함. IF 학습 시 "정상 영역" 이 명확히 정격 ±15%.
- ↑ **clamp 가 안전핀** — stddev 가 큰 값으로 호출 (예: 0.5) 되어도 [0.5, 1.5] 안에서만. 잘못된 stddev 인자에도 시스템 안정.
- ↓ **clamp 자체가 분포 왜곡** — clamp 영역 안 분포가 잘린 정규분포. 통계 의미상 약간의 bias. 실제 noise 가 정규분포가 아니라면 (예: 모터 시동 시 spike) 본 clamp 가 그 분포도 잡지 못함.
- ↓ **noise 가 multiplicative** — `rated × gauss_factor` 곱셈 noise. 정격 1kW 채널은 noise 폭이 ±150W, 정격 15kW 채널은 ±2250W. 채널별 노이즈 크기 차이가 의도된 건지 (큰 채널 = 큰 절대 노이즈) 검증 필요.

---

### 왜 device_id 가 하드코딩 "63200c3afd12" 인가

**선택**: DEVICE_ID 모듈 상수.

```python
DEVICE_ID = "63200c3afd12"
```

**배경**: 단일 디바이스 운영 환경. mac 주소 같은 형식 — 실제 모듈러 디바이스의 mac 값을 모방. fastapi 가 device_id 로 PowerDevice lookup 시 매칭.

**트레이드오프**:
- ↑ **시연 환경 단순** — 디바이스 1대 가정. 환경 변수 설정 없이 즉시 실행.
- ↓ **다중 디바이스 더미 불가** — 디바이스 2대 환경 시뮬 시 dummy 인스턴스 2개 띄워야 함. DEVICE_ID 환경 변수 또는 CLI 인자 도입 필요.
- ↓ **`L-3` 항목 (skill/코드리뷰.md) 과 동일 패턴** — 가스 더미도 facility_id=1 하드코딩. 두 더미가 같은 패턴 — 다중 시설/디바이스 환경 테스트 시 양쪽 수정 필요.
