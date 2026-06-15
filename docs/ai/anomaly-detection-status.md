# IF + ARIMA 팀공유 문서 — 적용 현황 및 다음 단계 (2026-05-19)

> **본 문서의 목적**: [IF_ARIMA_팀공유.md](IF_ARIMA_팀공유.md) 의 권고 사항이 현재 diconai 코드베이스에 **어디까지 적용**되었는지 한 장에 매핑하고, **시연 (2026-06-14) 전·후 어떻게 진행할지** 로드맵을 제시. 팀원이 코드를 직접 보지 않고도 현재 상태와 다음 액션을 파악할 수 있도록 작성.
>
> **분석 시점**: 2026-05-19, 브랜치 `feature/power_zscore_cp` 6 commits 적용 직후.
> **짝 문서**: [IF_ARIMA_팀공유.md](IF_ARIMA_팀공유.md) — 원본 권고 (Part 1~8) / 본 문서 — 적용 현황 + 갭 + 로드맵.

---

## 0. 한눈에 보기 — 적용도 매트릭스

| 영역 | 적용도 | 핵심 코드/문서 |
|---|---|---|
| ARIMA 기초 (Part 2) | ✅ 완전 | `train_arima_power_model.py` (전력 ARIMA(1,1,1)), `ai/router._arima_forecast` (95% CI 위반) |
| Isolation Forest (Part 3) | ✅ 완전 | `train_anomaly_model.py`, `ai/router._get_or_load` |
| ARIMA + IF 결합 (Part 4) | ✅ 완전 | 가스 = 잔차 격하 모드, 전력 = un-downgrade 3축 → **5축 (2026-05-19)** |
| Diconai 데이터 구조 (Part 5) | ✅ 완전 | FastAPI 실시간 + DRF 영속화, 1Hz dummy + 1분 학습 |
| **정확도 보강** (Part 6-A) | ◑ 부분 | IF 4-피처 + 시각 휴리스틱 + Z-score + CP. SARIMA·STL·hour feature 미적용 |
| **확장성 보강** (Part 6-B) | ◑ 부분 | sensor_identifier 매칭 + TTL cache. LRU·클러스터링·Online ARIMA 미적용 |
| **CUSUM/EWMA** (방향 3·중기 #6) | ✅ **대체 적용** | STEP E **Change Point** (`change_point_service.py`, 2026-05-19) 가 동일 목적 |
| 시연 (2026-06-14) 대비 상태 | ✅ Ready | 5축 정책 엔진 완성. 시연 전 추가 모델 변경 X |

**한 줄 요약**: 문서가 진단한 "정확도 + 확장성" 양 축의 한계 중 **정확도** 는 5축 엔진으로 절반 가량 해소, **확장성** 은 1ch PoC 라 본격 부각 X. SARIMA / 클러스터링 / Online ARIMA 는 시연 후 sprint 의 핵심 과제.

---

## 1. Part 별 코드 적용 매핑

### Part 2. ARIMA — ✅ 완전 적용

| 권고 항목 | 적용 위치 | 비고 |
|---|---|---|
| ARIMA(p,d,q) 학습 | [`drf-server/apps/ml/management/commands/train_arima_power_model.py`](../../drf-server/apps/ml/management/commands/train_arima_power_model.py) | 전력 전용. 기본 `--p 1 --d 1 --q 1`. 가스 ARIMA 는 별도 도구 |
| ARIMA forecast + 95% CI | [`fastapi-server/ai/router.py _arima_forecast`](../../fastapi-server/ai/router.py) | `new_result.get_forecast(steps=1)` + `conf_int(alpha=0.05)`. CI 위반 여부 (`is_violation`) 반환 |
| 잔차 = 실제값 − 예측값 | 가스 IF 입력 피처로 사용 | `feature_service.compute_arima_residuals` — 가스 다변량 IF 의 15-피처 중 3개 (3가스 × 1 ARIMA 잔차) |
| **계절성 (SARIMA)** | ❌ 미적용 | 우회 — `_is_night_kst_iso` + 정격 30% 시각 휴리스틱 (`power_service.py` W3.2). 일·주 단위 패턴 SARIMA 미도입 |

**관련 한계** (문서 Part 2):
- 비선형/급격한 변화에 약함 → IF 가 보완 ✅
- (p,d,q) 센서별 튜닝 → 미적용 ❌ (모든 채널 `1,1,1` 사용)

---

### Part 3. Isolation Forest — ✅ 완전 적용

| 권고 항목 | 적용 위치 | 비고 |
|---|---|---|
| sklearn IsolationForest | [`drf-server/apps/ml/management/commands/train_anomaly_model.py`](../../drf-server/apps/ml/management/commands/train_anomaly_model.py) | 학습 명령. 가스 / 전력 동일 |
| anomaly score (decision_function) | [`fastapi-server/ai/router.py`](../../fastapi-server/ai/router.py) L222 | `entry.model.decision_function(row)[0]` + `predict(row)[0]` |
| **IF 입력 풍부화** (방향 #2) | ◑ **부분 적용** | 전력 = 4-피처 (`value`, `roll_mean`, `roll_std`, `diff` — `_build_feature_row` L244). 가스 = 15-피처 다변량 (3가스 × 4 + 3 ARIMA 잔차). **hour_of_day / day_of_week / 자기상관 미적용** |

**학습 시점 vs 본 문서 분석 시점 차이**: 문서가 "잔차 하나만 넣지 말고" 라고 권고했지만, 실제 IF 학습 명령은 이미 `value/roll_mean/roll_std/diff` 4-피처 사용 중 — 문서 작성자가 코드 미확인 또는 다른 시점 가정. **단기 액션 #3 (rolling std, 차분 추가) 는 이미 적용된 상태**.

---

### Part 4. ARIMA + IF 결합 — ✅ 도메인별 완전 적용

| 도메인 | 결합 방식 | 코드 위치 |
|---|---|---|
| 가스 | **격하 모드** — ARIMA 잔차를 IF 입력 피처 (15-피처 중 3) | `feature_service.build_multi_features(arima_results=...)` |
| 전력 | **un-downgrade** — ARIMA + IF 독립 판단자 → 3축 매트릭스 결합 | `combine_risk_3axis(threshold, IF, ARIMA)` 12 cell |
| 전력 (2026-05-19) | **5축 우선순위 엔진** — Threshold + IF + Z-score + CP + ARIMA | `combine_risk_5axis(threshold, IF, ARIMA, z, cp) → (combined, escalation_source)` |

전력 5축 엔진은 STEP 5 권고의 우선순위 매트릭스 (CRITICAL > ML_ANOMALY > ANOMALY_WARNING > TREND_SHIFT > PREDICTIVE_ALERT > NORMAL) 를 코드 구조로 직접 매핑. `combine_risk_3axis` 위임으로 회귀 가드 자동 보존.

**핵심 코드 패턴**:
```python
# fastapi-server/ai/risk_combine.py
def combine_risk_5axis(threshold, if_pred, arima, z, cp) -> tuple[str, str]:
    base = combine_risk_3axis(threshold, if_pred, arima)  # ← 3축 위임 (회귀 가드)
    if base != "normal":
        return base, ""
    if change_point: return "predict_warn", "change_point"
    if z_score_anomaly: return "predict_warn", "zscore"
    return "normal", ""
```

---

### Part 5. Diconai 현재 구조 — ✅ 정확히 매핑

| 항목 | 적용 |
|---|---|
| 대상 센서 | 가스 (CO/H2S/CO2 등 다변량), 전력 (watt/voltage/current 16채널) |
| 데이터 | 1Hz dummy + 1분 리샘플링 학습 |
| FastAPI 실시간 + DRF 영속화 분리 | ✅ |
| **활성 추론 채널** | 전력 = `_INFERENCE_ENABLED_CHANNELS = {(1, "watt")}` — **1채널 PoC**. 다채널 확장은 시연 후 |

---

### Part 6-A. 정확도 — ◑ 절반 해소

#### 문제 #1: ARIMA 계절성 못 잡음 → ◑ **우회 적용**

| 권고 (방향 #1) | 현재 상태 | 코드 |
|---|---|---|
| SARIMA 또는 STL+ARIMA | ❌ 미적용 | (없음) |
| **시각 컨텍스트 휴리스틱** | ✅ 우회 적용 | `power_service._is_night_kst_iso` + `_NIGHT_THRESHOLD_RATIO=0.30`. KST 22~05 + 정격 30% 초과 시 1단계 격상 |

**우회의 의미**: SARIMA 의 자동 계절 학습 대신 휴리스틱 (시각 + 정격 비율) 으로 야간 가동 검출. 정확도 trade-off 있지만 시연 가치 (학습 자료의 시각 컨텍스트 명시) 는 충족. 시연 후 SARIMAX 도입 검토 ([상위 plan §5.1](../plan/anomaly-detection-zscore-changepoint.md) 보류).

#### 문제 #2: 잔차에 trend 누적 → ◑ **부분 보완**

| 권고 | 현재 상태 |
|---|---|
| STL 분해로 잔차 정제 | ❌ 미적용 |
| 잔차 누적 drift 검출 | ✅ **부분 보완** — STEP E Change Point (`change_point_service.detect_change_point`) 가 prev 30 vs curr 30 평균/분산 비교로 trend break 시점 검출 |

**대체 적용 가치**: CP 가 trend 변화 *시점* 을 잡는다. STL 의 잔차 정제와 다른 메커니즘이지만 운영 가치 (drift 누적 인지) 는 유사.

#### 문제 #3: IF 입력 빈약 → ◑ **이미 다변량 + 본 sprint 5축으로 추가 축 확보**

| 권고 (방향 #2) | 현재 상태 |
|---|---|
| 잔차만 사용 X | ✅ 이미 다변량 (전력 4-피처 / 가스 15-피처) |
| Rolling std (5/15분) | ✅ `roll_std_30` 단일 윈도우 적용 |
| 잔차의 1차 차분 | ✅ `diff` 피처 적용 |
| 잔차 자기상관 | ❌ 미적용 |
| **hour_of_day / day_of_week** | ❌ 미적용 |

**문서 작성 시점 권고와 실제 코드의 불일치**: 문서는 "잔차 하나만" 가정했지만 실제 코드는 이미 4·15-피처 사용 중. 본 sprint 5축 엔진은 IF 외부에 별도 축 (Z-score / CP) 을 둠 — IF 안에 피처 추가 대신 외부 축으로 보강한 셈.

#### 문제 #4: 도메인 임계 휴리스틱 → ◑ 부분

| 권고 (방향 #4) | 현재 상태 |
|---|---|
| CAUTION = 안전 기준치 | ◑ 부분 — 정격 % 기반 (도메인 명확) |
| DANGER = 법규/정책 기반 | ◑ 부분 — 정격 100% 초과 |
| 잔차 임계 = σ + 안전 마진 | ❌ 미적용 — Z-score 3.0 (통계 단독) |

**시연 후 운영자 피드백 기반 재정의 필요** — 단기 액션 #4.

---

### Part 6-B. 확장성 — ◑ 부분 (1ch 환경이라 본격 부각 X)

#### 문제 #5: 디바이스마다 모델 → ◑ **부분 해결**

| 차원 | 현재 운영 |
|---|---|
| ARIMA | `sensor_identifier` 단위 (예: `power:device_1:ch1:watt`) — W1.1+W2.5 의 3축 매칭 |
| IF | `sensor_type` 단위 — 전력 1 모델, 가스 1 모델. 디바이스 통합 학습 |
| **현재 N** | 1ch (전력 device_1 ch1 watt) 만 활성. 디바이스 폭증 문제 미부각 |

#### 문제 #6: (p,d,q) 튜닝 → ❌ 미적용

- 전력 ARIMA 학습 시 `--p 1 --d 1 --q 1` 하드코딩 (기본값). auto-arima 미사용. 다채널 확장 시 부담 ↑

#### 문제 #7: 새 센서 종류 → ❌ 미적용

- MLModel 스키마 (`algorithm × sensor_type × sensor_identifier × version` 4축 unique) 는 이미 확장성 있음
- 그러나 실제 신규 센서 (수질·진동·온도) 학습 파이프라인 미준비

---

### Part 7. 해결 방향 — 적용 현황 상세

| 방향 | 적용도 | 상세 |
|---|---|---|
| **#1 SARIMA / STL** | ❌ | 시각 휴리스틱으로 우회. SARIMAX 는 [상위 plan §5.1](../plan/anomaly-detection-zscore-changepoint.md) 보류 |
| **#2 IF feature 풍부화** | ◑ | `value/roll_mean/roll_std/diff` 적용. `hour/day_of_week/잔차 자기상관` 미적용 |
| **#3 CUSUM / EWMA** | ✅ **대체** | STEP E Change Point (`change_point_service.py`, 2026-05-19 E1) 가 동일 목적 — drift 누적·trend break 검출. 다만 CUSUM 과는 알고리즘 다름 (two-window vs 누적합) |
| **#4 임계값 도메인 기반** | ◑ | 정격 % 기반 (도메인 명확) + Z=3.0 (통계). 안전 기준 공식 문서화 미진행 |
| **#5 클러스터링** | ❌ | PoC 미진행. 1ch 라 미부각 |
| **#6 Online ARIMA** | ❌ | batch refit 운영 (W5 후속). Kalman filter / 점진 update 도입 X |
| **#7 Lazy + LRU 캐시** | ◑ Lazy ✅ / LRU ❌ | `_cache: dict[tuple, _CachedModel]` + TTL eviction (`ML_MODEL_CACHE_TTL_SEC`). cache miss 시 디스크 로드. **LRU cap 없음 → 디바이스 N 증가 시 메모리 폭증 위험** |
| **#8 Global model** | ❌ | R&D — 장기 |

---

### Part 8. 액션 아이템 — 적용 현황

#### 단기 1~2주

| # | 액션 | 적용도 | 상세 |
|---|---|---|---|
| 1 | 계절성 분석 (FFT, ACF plot) | ❌ | 시각 휴리스틱 사용. SARIMA 도입 근거 마련 미진행 |
| 2 | STL 분해 + 잔차 분포 비교 | ❌ | 미진행 |
| 3 | IF 입력 풍부화 (rolling std, 차분) | ✅ **이미 적용 (문서 작성 시점에 이미 적용된 상태)** | 4-피처 학습 중. `feature_service.build_features` |
| 4 | 도메인 임계 재정의 | ◑ | 정격 기반 적용. 안전 기준 공식 문서화 미진행 |

#### 중기 1~2개월

| # | 액션 | 적용도 | 상세 |
|---|---|---|---|
| 5 | SARIMA / STL+ARIMA 교체 | ❌ | 시연 후 결정 |
| 6 | CUSUM/EWMA 결합 | ✅ **STEP E CP 로 대체** | 2026-05-19 E1 적용. two-window 알고리즘이지만 운영 가치 동일 |
| 7 | 디바이스 클러스터링 PoC | ❌ | 1ch 환경이라 미부각 |
| 8 | Lazy + LRU 캐시 | ◑ Lazy ✅ / LRU ❌ | TTL eviction 만 운영. LRU 미적용 |

#### 장기 3개월+

| # | 액션 | 적용도 |
|---|---|---|
| 9 | Online ARIMA | ❌ |
| 10 | 클러스터 기반 운영 | ❌ |
| 11 | Global model | ❌ |

---

## 2. 핵심 갭 분석

문서는 "정확도 + 확장성" 양 축으로 한계 진단. 본 sprint 까지 보강 결과:

| 축 | 문서 진단 (Part 6) | 현재 보강 | 잔여 갭 |
|---|---|---|---|
| **정확도** | IF 입력 빈약 + ARIMA 계절성 미인지 + 잔차 trend | IF 다변량 + 시각 휴리스틱 + Z-score (STEP D) + Change Point (STEP E) → **5축 정책 엔진** | SARIMA/STL · feature 추가 (hour, ACF) · CUSUM 누적 drift |
| **확장성** | N 디바이스 시 모델 폭증 | ARIMA = sensor_identifier 단위 / IF = sensor_type 단위 통합 + TTL cache. **1ch 환경** | LRU cap · 디바이스 클러스터링 · Online ARIMA · auto-arima 튜닝 |

### 한 줄 진단

> **정확도 갭의 절반은 5축 엔진 (Z-score + CP) 으로 해소 — 다음 갭은 SARIMA 와 IF feature 추가 (hour, ACF). 확장성 갭은 1ch 환경이라 본격 부각 X — 다채널 확장 시점에 LRU + 클러스터링이 동시에 필요.**

---

## 3. 권장 다음 단계 (시점별 로드맵)

### A. 시연 (2026-06-14) 전까지 — D-26 ~ D+0

**원칙**: 추가 모델 변경 X — 시각 휴리스틱 + 5축 + Z-score/CP 로 시연 충분.

| 항목 | 시점 | 비고 |
|---|---|---|
| `feature/power_zscore_cp` 5 commits 안정화 | D-26 ~ D-14 | 본 sprint 산출 |
| 시연 리허설 — Z-score / CP false positive 빈도 측정 | D-7 ~ D-3 | dummy 1주 가동 후 발화 카운트. threshold 튜닝 (Z=3.0 → 3.5/4.0?) |
| W4.b metrics 라벨 추가 (`ALARM_FIRED_TOTAL.algorithm_source`) | D-14 ~ D-7 | 발화 분포 가시화. Grafana 패널 sum without (algorithm_source) 보정 |
| 가스 D1 (Z-score) — 가스 담당자 진입 시 | 시연 전후 | 본 작업 §D2 패턴 재활용 가능 |

### B. 시연 후 sprint (D+1 ~ D+30) — 정확도 우선

**문서 단기 액션 #1·#2 진입** + **방향 #2 완성**:

| 순서 | 액션 | 효과 | 의존성 |
|---|---|---|---|
| 1 | 가스/전력 데이터 **FFT·ACF 분석** | 일·주 단위 주기성 정량 확인 → SARIMA 도입 근거 | 운영 데이터 1~2주 누적 |
| 2 | **STL 분해 PoC** | residual 분포 깨끗함 검증. IF false positive 측정 | A.1 분석 결과 |
| 3 | **IF feature 확장** — `hour_of_day` / `day_of_week` / 잔차 자기상관 | 방향 #2 완성. contextual / collective anomaly 추가 검출 | feature_service 확장 |
| 4 | **도메인 임계 공식 문서화** | 가스 안전기준 (CO 50ppm 등) · 전력 부하 정책 · Z-score 운영 threshold | 운영자 면담 |

**확장성 진입** (1ch → 다채널 PoC):

| 순서 | 액션 | 효과 |
|---|---|---|
| 5 | **Lazy + LRU 캐시** 도입 | 방향 #7 완성. `_cache` 에 LRU cap 추가 (운영 메모리 안정) |
| 6 | `_INFERENCE_ENABLED_CHANNELS` 16채널 확장 | 다채널 운영 시 모델 N 부담 측정 |

### C. 중기 (D+30 ~ D+90) — 정확도 본격 개선

| 항목 | 액션 |
|---|---|
| #5 SARIMA / STL+ARIMA 교체 | B.1·B.2 결과 기반. 일·주 주기 검출 시 SARIMA(p,d,q,P,D,Q,m) 학습 명령 추가 |
| #6 CUSUM 결합 | Change Point (STEP E) + CUSUM 누적합 → drift 누적 강화 |
| #7 디바이스 클러스터링 PoC | DTW 거리 / 시계열 임베딩으로 N 디바이스 군집화 → 클러스터당 모델 1개 |

### D. 장기 (D+90+) — 확장성 본격

| 항목 | 액션 |
|---|---|
| #9 Online ARIMA | Kalman filter 기반 점진 update. statsmodels `RecursiveLS` 또는 외부 lib |
| #10 클러스터 기반 운영 정착 | C.7 결과 안정화. 1000+ 디바이스 대응 |
| #11 Global model 실험 | LightGBM + device_id categorical feature 또는 시계열 파운데이션 모델 (R&D) |

---

## 4. 학습 시연 가치 — 본 sprint 까지 도달한 시점

본 sprint (D2/E1/F + 코드리뷰 보강) 으로 **STEP 5 권고와 코드의 1:1 일치** 가 가시화됨:

| STEP 5 권고 | 가스 | 전력 | 코드 위치 |
|---|---|---|---|
| STEP B Threshold | ✅ | ✅ | `core/power_thresholds.py`, `threshold_eval.py` |
| STEP C Sliding Window | ✅ | ✅ | `_power_windows` (IF 30) / `_cp_windows` (CP 60) |
| STEP D Z-score | ❌ | ✅ | `power_service._zscore_check` |
| STEP E Change Point | ❌ | ✅ | `change_point_service.detect_change_point` |
| STEP F Isolation Forest | ✅ (15피처) | ✅ (4피처) | `ai/router._get_or_load` + IF 추론 |
| STEP G ARIMA | ✅ (잔차 격하) | ✅ (CI 위반 독립) | `ai/router._get_or_load_arima` + `_arima_forecast` |
| 5축 정책 엔진 | ◑ (3축) | ✅ | `risk_combine.combine_risk_5axis` |

전력 도메인은 STEP 5 권고 매트릭스를 코드 구조로 **명시화** — 학습 자료의 "권고와 실제 코드의 일치" 항목을 시연 시 직접 확인 가능.

---

## 5. 본 분석의 다음 활용

| 시점 | 활용 방식 |
|---|---|
| 본 분석 머지 직후 | 팀 sync — 시연 준비 완료 + 시연 후 로드맵 공유 |
| 시연 리허설 (D-7) | 본 §3.A 항목 check |
| 시연 직후 (D+1) | §3.B sprint 진입 시 우선순위 기준 |
| 분기 회고 시 | 적용 현황 갱신 — 본 문서가 다음 분기 출발점 |

---

## 부록 A. 코드 위치 빠른 인덱스

| 영역 | 파일 |
|---|---|
| 5축 정책 엔진 | [`fastapi-server/ai/risk_combine.py`](../../fastapi-server/ai/risk_combine.py) — `combine_risk_5axis` (base=3axis 위임) |
| Z-score (STEP D) | [`fastapi-server/power/services/power_service.py`](../../fastapi-server/power/services/power_service.py) `_zscore_check` |
| Change Point (STEP E) | [`fastapi-server/power/services/change_point_service.py`](../../fastapi-server/power/services/change_point_service.py) `detect_change_point` |
| ARIMA forecast | [`fastapi-server/ai/router.py`](../../fastapi-server/ai/router.py) `_arima_forecast` |
| IF 추론 | [`fastapi-server/ai/router.py`](../../fastapi-server/ai/router.py) `_get_or_load`, `_build_feature_row` |
| IF 4-피처 학습 (전력) | [`drf-server/apps/ml/management/commands/train_anomaly_model.py`](../../drf-server/apps/ml/management/commands/train_anomaly_model.py) + `feature_service.build_features` |
| IF 15-피처 학습 (가스 다변량) | `feature_service.build_multi_features(arima_results=...)` |
| ARIMA 학습 (전력) | [`drf-server/apps/ml/management/commands/train_arima_power_model.py`](../../drf-server/apps/ml/management/commands/train_arima_power_model.py) |
| algorithm_source 라벨 | [`drf-server/apps/core/constants.py`](../../drf-server/apps/core/constants.py) `ALGORITHM_SOURCE_LABEL` ↔ `power_service.py` `_ALGORITHM_SOURCE_LABEL` |
| 추론 통합 흐름 | `power_service.process_anomaly_inference` |

## 부록 B. 관련 plan / 문서

| 종류 | 위치 |
|---|---|
| 상위 plan (5축 도입 의도) | [skill/plan/anomaly-detection-zscore-changepoint.md](../plan/anomaly-detection-zscore-changepoint.md) |
| 적용 plan (본 sprint) | [skill/plan/power-zscore-changepoint-apply.md](../plan/power-zscore-changepoint-apply.md) |
| 적용 보고 (refactor) | [drf-server/docs/refactoring/power-ai-zscore-changepoint-2026-05-19.md](../../drf-server/docs/refactoring/power-ai-zscore-changepoint-2026-05-19.md) |
| 코드 흐름 분석 (codereview) | [docs/codereviews/2026_05_19/power-5axis-policy-flow.md](../../docs/archive/codereviews/2026_05_19/power-5axis-policy-flow.md) |
| 살아있는 spec (전력 시스템 §4) | [docs/features/power_system/cjy_그_외_기술문서.md](../../docs/features/power_system/cjy_그_외_기술문서.md) |
| 직전 sprint (3축 un-downgrade) | [skill/전력 AI un-downgrade ... 보고.md](../전력%20AI%20un-downgrade%20(IF%20%2B%20ARIMA)%20통합%20작업%20복습%20및%20보고.md) |

---

> **이 문서의 핵심 메시지**:
> IF_ARIMA 팀공유 문서가 진단한 정확도·확장성 한계 중 **정확도** 는 본 sprint 5축 엔진 (Z-score + Change Point + ARIMA + IF + Threshold) 으로 절반 해소. **확장성** 은 1ch PoC 환경이라 본격 부각 X. 시연 (2026-06-14) 까지는 추가 모델 변경 없이 안정화에 집중. 시연 후 D+30 sprint 의 핵심 과제는 (a) SARIMA / STL 분해 도입 (정확도 본격) + (b) Lazy + LRU 캐시 (확장성 사전 대응) + (c) IF feature 확장 (hour / 자기상관).
