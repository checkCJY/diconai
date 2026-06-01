# AI / ML 도메인

> 코드리뷰용 흐름 이해 문서. 관련 커밋: `f0932c9`(fastapi/ai + apps/ml)
> 책임 분리: **drf = 오프라인 학습·모델 메타 / fastapi = 실시간 추론**. Django ML 계산이 메인 API 를 막지 않도록 분리.

---

## 1. 파일 맵

| 레이어 | 파일 | 핵심 심볼 |
|---|---|---|
| drf 학습 커맨드 | `apps/ml/management/commands/train_anomaly_model.py` | IF 학습 (가스 단/다변량, 전력) |
| drf 학습 커맨드 | `apps/ml/management/commands/train_arima_power_model.py` | 전력 ARIMA 학습 |
| drf 상관분석 | `apps/ml/management/commands/measure_channel_correlation.py` | 16채널 Pearson/DTW PoC |
| drf 데이터셋 | `apps/ml/services/dataset_service.py` | `extract_normal_power_series`, `extract_normal_gas_multi_series` |
| drf 피처 | `apps/ml/services/feature_service.py` | `build_features`, `build_multi_features` |
| drf 메타 API | `apps/ml/views.py` | `ActiveMLModelView` (GET /api/ml/models/active/) |
| drf 모델 | `apps/ml/models/ml_model.py`, `ml_anomaly_result.py` | `MLModel`, `MLAnomalyResult` |
| fastapi 추론 ★ | `ai/router.py` | `_get_or_load`, `_get_or_load_arima`, `_build_feature_row`, `_arima_forecast`, `predict`, `reload_model` |
| fastapi 결합 ★ | `ai/risk_combine.py` | `combine_risk_5axis`, `combine_risk_3axis` |

## 2. 학습 ↔ 추론 분리 시퀀스

```
[학습 — drf, 오프라인 / 수동 또는 Celery]
  manage.py train_anomaly_model --sensor-type gas --gas-name co,h2s,co2 --activate
    └─ dataset_service: 정상 데이터 추출 (is_anomaly=False)
    └─ feature_service.build_multi_features: 슬라이딩 윈도우 피처
    └─ sklearn IsolationForest.fit
    └─ joblib.dump({"model","feature_columns","window"}) → ML_MODELS_DIR/*.pkl
    └─ MLModel.objects.create(version, file_path, sensor_identifier, is_active=True)
         (--activate 시 같은 매칭단위 기존 활성 자동 비활성)
                          │  .pkl 은 docker named volume 으로 fastapi 와 공유
                          ▼
[메타 조회 — drf API]
  GET /api/ml/models/active/?sensor_type=&algorithm=&sensor_identifier=
    └─ is_active=True row 의 file_path/version 반환 (404 면 모델 미등록)
                          ▲ fastapi 가 캐시 miss 시 호출
                          │
[추론 — fastapi, 실시간 / 매 센서 데이터마다]
  gas_service / power_service
    └─ _get_or_load("gas", sensor_identifier=...) → 캐시 or DRF fetch + pkl 로드
    └─ model.predict(feature_row) → score/prediction
    └─ combine_risk_5axis(...) → 최종 위험도
```

## 3. 모델 캐시 (ai/router.py)

- **3축 캐시 키**: `(sensor_type, algorithm, sensor_identifier)`. IF·ARIMA 가 같은 `_cache` dict 에 분리 키로 공존.
- `_get_or_load` (IF 전용) / `_get_or_load_arima` (ARIMA) — 반환 타입 고정 위해 함수 분리. IF 함수에 `algorithm != "isolation_forest"` 면 400.
- **404 억제**: 모델 미등록 시 데이터 1건마다 DRF 찌르지 않게 `_NO_MODEL_TTL_SEC=60` 캐시:
  ```python
  if time.time() - _no_model_at.get(cache_key, 0) < _NO_MODEL_TTL_SEC:
      return None    # 60초간 DRF 재호출 없이 즉시 None
  ```
- **TTL**: `ML_MODEL_CACHE_TTL_SEC` 초과 시 재로드 (0 이하면 무만료).
- **핫리로드**: `/ai/reload` 또는 DRF 콜백 → `_cache` evict → 다음 호출 시 새 모델. 재시작 불필요.

## 4. 피처 (학습 ↔ 추론 동일 수식 — 깨지면 추론 무의미)

| 종류 | 피처 | 차원 |
|---|---|---|
| 단변량 (전력 watt) | `[value, roll_mean, roll_std, diff]` | 4 |
| 다변량 (가스 co+h2s+co2) | 가스별 4피처 × 3 | 12 |
| 다변량 + ARIMA 잔차 | 가스별 (4 + arima_resid) × 3 | 15 |

⚠ drf `feature_service.build_features` 와 fastapi `ai/router._build_feature_row` 가 **같은 수식을 각자 구현**(의존성 분리). 한쪽만 바꾸면 학습-추론 피처 mismatch → 추론 결과 무의미. **반드시 동기.**

```python
# ai/router._build_feature_row — 추론 1회용
arr = np.asarray(window_values[-window:])
return np.array([[arr[-1], arr.mean(), arr.std(ddof=0), arr[-1]-arr[-2]]])
```

## 5. ARIMA forecast 자기충족 함정 (중요)

`ai/router._arima_forecast` 가 `values[:-1]` 로 학습 후 마지막 값을 **외부 값으로** 비교:
```python
def _arima_forecast(values, arima_result, alpha=0.05):
    new_result = arima_result.apply(endog=values[:-1])   # ★ 마지막 값 제외하고 fit
    forecast = new_result.get_forecast(steps=1)          # 1-step ahead
    ci = forecast.conf_int(alpha=alpha)
    actual = values[-1]                                  # fit 에 안 들어간 값
    return {"is_violation": actual < ci_lower or actual > ci_upper, ...}
```
- ❌ `apply(values)` 전체 fit 후 `actual=values[-1]` 비교 → actual 이 fit 의 일부라 forecast 가 actual 근처로 따라감 → **자기충족 false negative** (위반인데 위반 아니라고 판정).
- ✅ `values[:-1]` 로 training 해 진짜 1-step ahead 예측과 비교.

## 6. 5축 결합 (ai/risk_combine.py)

```python
combine_risk_5axis(threshold, if_pred, arima_viol, z_anom, change_point) -> (combined, escalation_source)
combine_risk_3axis(threshold, if_pred, arima_viol) -> str    # base 매트릭스 (12-cell)
combine_risk(threshold, ml_pred) -> str                       # deprecated 2축, 테스트/호환
```
- base = `combine_risk_3axis` (threshold × IF × ARIMA). 두 AI(IF+ARIMA) 동의 시 격상, 단일 발화 시 보수적 (3축이 2축보다 한 단계 낮음 — 신뢰도 반영).
- Z·CP 는 base=normal 일 때만 `predict_warn` 격상. 상세 규칙 [power.md](power.md) §4.
- `_AXIS_WEIGHTS`: 가중평균용 — **현재 미사용** (max 우선순위 결합). 향후 전환 대비 보존.
- `combine_risk_3axis` 는 매트릭스에 없는 조합 시 **ValueError** (fail-fast — 운영 데이터에서 미정의 조합 즉시 발견).

## 7. DB 모델 (apps/ml/models)

- **MLModel** — 학습 산출물 메타. `is_active=True` 가 추론 대상. 같은 (sensor_type, algorithm, sensor_identifier) 매칭 단위에서 activate 시 기존 활성 자동 비활성 (다른 단위는 보존).
- **MLAnomalyResult** — 추론 결과 기록. `risk_classified` 는 결합 매트릭스 4단계 분류 (help_text 에 "STEP D 결합" 명시).

## 8. 리뷰 시 주의 (함정)

1. **sensor_identifier 포맷 일관** ⚠️: 전력 `power:device_{mac}:ch{n}:{type}`, 가스 `gas:sensor_{pk}:{gas_label}`. **PK vs mac 혼동** 시 학습 모델과 추론 매칭 실패 → 404 silent fallback → IF 미동작. train 커맨드가 PK→mac 변환하는 이유.
2. **피처 수식 동기** (§4) — drf/fastapi 양쪽 동시 수정.
3. **ARIMA 자기충족** (§5) — `values[:-1]` 유지 필수.
4. **가스 ARIMA 미통합**: 가스 ARIMA 는 아직 MLModel 정식 경로 밖 — gas_service 가 pkl 직접 로드(`_arima_models`). 전력만 `_get_or_load_arima` 경유. 가스 통합은 후속 작업.
5. **measure_channel_correlation** 은 PoC 커맨드 (운영 경로 아님) — multivariate IF 적합성 검증용 1회성.

## 9. 관련 문서
- 5축 사용처: [power.md](power.md)
- 가스 IF 흐름: [gas.md](gas.md) §5
