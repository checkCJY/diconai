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
