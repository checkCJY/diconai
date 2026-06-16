# apps/ml/services/feature_service.py
"""
Feature engineering — 1D 시계열 → 다차원 피처 행렬.

IF 가 시간 종속성을 학습할 수 있도록 raw value 외에 sliding window 파생변수를 추가.
도메인 무관 (전력 W/A/V·가스 ppm 모두 동일 함수 사용).

생성되는 피처:
- value        : 원본 측정값
- roll_mean_N  : 최근 N 틱 이동 평균
- roll_std_N   : 최근 N 틱 이동 표준편차
- diff         : 직전 틱 대비 변화량 (1차 차분)

설계 선택:
- pandas 미사용 (numpy 만으로 충분, 의존성 최소화)
- 윈도우 시작 부분의 NaN 행은 `drop_warmup=True` 로 잘라낼지 호출자가 결정
- 멀티변수 피처는 호출자가 column stack — 본 함수는 단일 변수만
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from apps.ml.services.dataset_service import TimeSeries


DEFAULT_WINDOW = 30  # 기본 sliding window 길이 (틱; dummy 1초 간격이면 30초)


@dataclass
class FeatureMatrix:
    """피처 추출 결과."""

    columns: list[str]  # 피처 컬럼 이름 — train/predict 일관성 보장용
    features: np.ndarray  # shape (N, len(columns)) float64
    measured_at: np.ndarray  # shape (N,) datetime64[ns] — 피처와 1:1 정렬
    is_anomaly: np.ndarray  # shape (N,) bool — 평가 라벨 (학습엔 사용 안 함)

    def __len__(self) -> int:
        return int(self.features.shape[0])


def _rolling_mean(values: np.ndarray, window: int) -> np.ndarray:
    """edge 는 NaN, 중간은 N 틱 평균."""
    if window <= 1:
        return values.copy()
    n = values.shape[0]
    out = np.full(n, np.nan, dtype=np.float64)
    if n < window:
        return out
    # cumsum 기반 O(N) 이동 평균
    csum = np.cumsum(values, dtype=np.float64)
    out[window - 1] = csum[window - 1] / window
    out[window:] = (csum[window:] - csum[:-window]) / window
    return out


def _rolling_std(values: np.ndarray, window: int) -> np.ndarray:
    """ddof=0 (모분산 분모 N) — IF 입력 안정성 우선."""
    if window <= 1:
        return np.zeros_like(values, dtype=np.float64)
    n = values.shape[0]
    out = np.full(n, np.nan, dtype=np.float64)
    if n < window:
        return out
    csum = np.cumsum(values, dtype=np.float64)
    csum2 = np.cumsum(values * values, dtype=np.float64)
    mean = np.empty(n, dtype=np.float64)
    mean[window - 1] = csum[window - 1] / window
    mean[window:] = (csum[window:] - csum[:-window]) / window
    sq_mean = np.empty(n, dtype=np.float64)
    sq_mean[window - 1] = csum2[window - 1] / window
    sq_mean[window:] = (csum2[window:] - csum2[:-window]) / window
    var = np.maximum(sq_mean[window - 1 :] - mean[window - 1 :] ** 2, 0.0)
    out[window - 1 :] = np.sqrt(var)
    return out


def _first_diff(values: np.ndarray) -> np.ndarray:
    """1차 차분 — 첫 원소는 NaN."""
    n = values.shape[0]
    out = np.full(n, np.nan, dtype=np.float64)
    if n >= 2:
        out[1:] = values[1:] - values[:-1]
    return out


def build_features(
    series: TimeSeries,
    window: int = DEFAULT_WINDOW,
    drop_warmup: bool = True,
) -> FeatureMatrix:
    """시계열 1개에서 IF 학습/추론 피처 행렬을 생성한다.

    drop_warmup=True (기본): 윈도우 워밍업 구간(앞 window-1 행)을 잘라내 NaN 없는
    행렬을 반환. 학습 시 NaN 입력은 sklearn 이 거부하므로 권장.
    drop_warmup=False: NaN 그대로 반환 (호출자가 처리)
    """
    values = series.values
    columns = ["value", f"roll_mean_{window}", f"roll_std_{window}", "diff"]
    features = np.column_stack(
        [
            values,
            _rolling_mean(values, window),
            _rolling_std(values, window),
            _first_diff(values),
        ]
    )

    if drop_warmup:
        # roll_mean 이 NaN 이 아닌 첫 인덱스부터 사용 (window-1 이후) + diff 도 NaN 이 아닌 1 이후
        start = max(window - 1, 1)
        features = features[start:]
        measured_at = series.measured_at[start:]
        is_anomaly = series.is_anomaly[start:]
    else:
        measured_at = series.measured_at
        is_anomaly = series.is_anomaly

    return FeatureMatrix(
        columns=columns,
        features=features,
        measured_at=measured_at,
        is_anomaly=is_anomaly,
    )


# 이성현 추가 — ARIMA 잔차 계산 함수 (학습 및 추론 공용)
def compute_arima_residuals(
    values: np.ndarray,
    arima_result,
) -> np.ndarray:
    """학습된 ARIMA 파라미터를 values 에 적용해 잔차 배열을 반환한다.

    잔차 = 실제값 - ARIMA 예측값. 값이 클수록 정상 패턴 이탈 → IF 이상 신호 보강.
    arima_result: statsmodels ARIMAResultsWrapper (pkl 에서 로드한 객체).
    """
    new_result = arima_result.apply(endog=values.tolist())
    resid = np.asarray(new_result.resid, dtype=np.float64)
    # 첫 번째 원소는 NaN 인 경우가 있음 → 0 으로 대체
    return np.where(np.isnan(resid), 0.0, resid)


# 이성현 추가 — 다변량 피처 행렬 빌더 (여러 가스 TimeSeries 수평 스택)
# 이성현 수정 — arima_results 매개변수 추가 (None 이면 기존 12피처 유지, 제공 시 15피처)
def build_multi_features(
    series_list: list[TimeSeries],
    gas_names: list[str],
    window: int = DEFAULT_WINDOW,
    drop_warmup: bool = True,
    arima_results: dict | None = None,
) -> FeatureMatrix:
    """여러 가스 TimeSeries → 다변량 피처 행렬.

    arima_results={gas_name: ARIMAResultsWrapper} 를 넘기면
    각 가스마다 arima_resid 1개를 추가 → 12피처 → 15피처.
    gas_names=["co","h2s","co2"] → 15피처 — ai/router.py _build_multi_feature_row 와 동일 순서.
    """
    fms = [
        build_features(s, window=window, drop_warmup=drop_warmup) for s in series_list
    ]
    min_len = min(len(fm) for fm in fms)

    columns: list[str] = []
    feature_parts: list[np.ndarray] = []
    # 이성현 수정 — series 도 같이 순회 (ARIMA 잔차 계산에 원본값 필요)
    for gas_name, fm, series in zip(gas_names, fms, series_list):
        columns.extend(f"{gas_name}_{col}" for col in fm.columns)
        feature_parts.append(fm.features[-min_len:])
        # 이성현 추가 — ARIMA 잔차 피처 (arima_results 없으면 건너뜀)
        if arima_results and gas_name in arima_results:
            resid = compute_arima_residuals(series.values, arima_results[gas_name])
            if drop_warmup:
                start = max(window - 1, 1)
                resid = resid[start:]
            columns.append(f"{gas_name}_arima_resid")
            feature_parts.append(resid[-min_len:].reshape(-1, 1))

    return FeatureMatrix(
        columns=columns,
        features=np.column_stack(feature_parts),
        measured_at=fms[0].measured_at[-min_len:],
        is_anomaly=fms[0].is_anomaly[-min_len:],
    )
