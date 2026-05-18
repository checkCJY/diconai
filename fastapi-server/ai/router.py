# ai/router.py — IF 추론 엔드포인트
#
# DRF 가 학습한 .pkl 모델을 프로세스 메모리에 캐시 후 실시간 추론.
# Django ML 계산이 메인 API 흐름을 막지 않도록 fastapi 로 분리한다(skill 권고).
#
# 모델 파일 동기화:
#   drf-server 가 settings.ML_MODELS_DIR 에 .pkl 저장 → docker named volume 으로 본 서버에도 노출.
#   PoC 단계는 docker cp 임시 처리 (B-6 에서 docker-compose volume 추가).
#
# 모델 메타(file_path, version 등) 는 drf API `GET /api/ml/models/active/` 호출로 조회.
# 캐시 TTL 만료 또는 명시 reload 요청 시 메타 재조회 + .pkl 재로드.

from __future__ import annotations

import logging
import time
from pathlib import Path
from threading import Lock

import httpx
import joblib
import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"])


# ---------------------------------------------------------------------------
# 모델 캐시 — sensor_type 별 1개씩 (active 모델). 프로세스 메모리 영속.
# ---------------------------------------------------------------------------


class _CachedModel:
    """로딩된 IF 모델 + 학습 메타 + 로딩 시각."""

    __slots__ = ("model", "feature_columns", "window", "version", "loaded_at")

    def __init__(
        self, model, feature_columns: list[str], window: int, version: int
    ) -> None:
        self.model = model
        self.feature_columns = feature_columns
        self.window = window
        self.version = version
        self.loaded_at = time.time()


class _CachedArimaModel:
    """로딩된 ARIMA 결과 + 메타 + 로딩 시각 (W2 신규).

    IF 와 분리 — ARIMA pkl bundle 은 {"result": ARIMAResultsWrapper, "order": (p,d,q)}
    구조라 feature_columns/window 가 없음.
    """

    __slots__ = ("model", "version", "order", "loaded_at")

    def __init__(self, model, version: int, order: tuple) -> None:
        self.model = model  # statsmodels.tsa.arima.model.ARIMAResultsWrapper
        self.version = version
        self.order = order
        self.loaded_at = time.time()


# W2 — cache key 를 (sensor_type, algorithm, sensor_identifier) 3축 tuple 로 확장.
# 같은 dict 에 IF 와 ARIMA 가 분리된 키로 공존.
_cache: dict[tuple[str, str, str], _CachedModel | _CachedArimaModel] = {}
_cache_lock = Lock()


def _is_expired(entry: _CachedModel) -> bool:
    ttl = settings.ML_MODEL_CACHE_TTL_SEC
    if ttl <= 0:
        return False
    return (time.time() - entry.loaded_at) > ttl


async def _fetch_active_model_meta(
    sensor_type: str,
    algorithm: str = "isolation_forest",
    sensor_identifier: str = "",
) -> dict:
    """DRF active 모델 메타 조회 — W2 에서 3축 매칭 (algorithm, sensor_identifier).

    file_path 는 ML_MODELS_DIR 기준 상대 경로. default 호출은 기존 IF 매칭 회귀 0.
    """
    params = {
        "sensor_type": sensor_type,
        "algorithm": algorithm,
        "sensor_identifier": sensor_identifier,
    }
    url = f"{settings.DRF_BASE_URL}/api/ml/models/active/"
    async with httpx.AsyncClient(timeout=settings.DRF_REQUEST_TIMEOUT_SEC) as client:
        res = await client.get(url, params=params)
        if res.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"active 모델 없음 (sensor_type={sensor_type} "
                    f"algorithm={algorithm} sensor_identifier={sensor_identifier!r})"
                ),
            )
        res.raise_for_status()
        return res.json()


def _load_pkl(file_name: str) -> tuple[object, list[str], int]:
    """ML_MODELS_DIR 아래 IF .pkl 로드 → (model, feature_columns, window)."""
    path = Path(settings.ML_MODELS_DIR) / file_name
    if not path.exists():
        raise HTTPException(
            status_code=500,
            detail=f"모델 파일 없음: {path} (drf-server 와 같은 volume 마운트 확인)",
        )
    bundle = joblib.load(path)
    return bundle["model"], bundle["feature_columns"], bundle["window"]


def _load_arima_pkl(file_name: str) -> tuple[object, tuple]:
    """ML_MODELS_DIR 아래 ARIMA .pkl 로드 → (result, order) (W2 신규).

    train_arima_model.py / train_arima_power_model.py (W2.5) 가 저장한 bundle 형식:
    {"result": ARIMAResultsWrapper, "order": (p, d, q)}.
    """
    path = Path(settings.ML_MODELS_DIR) / file_name
    if not path.exists():
        raise HTTPException(
            status_code=500,
            detail=f"ARIMA 모델 파일 없음: {path}",
        )
    bundle = joblib.load(path)
    return bundle["result"], tuple(bundle.get("order", ()))


async def _get_or_load(
    sensor_type: str,
    algorithm: str = "isolation_forest",
    sensor_identifier: str = "",
) -> _CachedModel:
    """IF 모델 캐시/로드 — W2 에서 (sensor_type, algorithm, sensor_identifier) 3축 매칭.

    default 호출 (`_get_or_load("power")`) 은 algorithm="isolation_forest",
    sensor_identifier="" 매칭 → 기존 IF 동작 회귀 0.

    algorithm="arima" 는 본 함수가 받지 않음 — `_get_or_load_arima` 사용.
    (반환 타입을 _CachedModel 로 고정해 caller 가 cast 부담 안 지도록 분리.)
    """
    if algorithm != "isolation_forest":
        raise HTTPException(
            status_code=400,
            detail=(
                f"_get_or_load 는 isolation_forest 전용. "
                f"algorithm={algorithm!r} 는 _get_or_load_arima 사용"
            ),
        )

    cache_key = (sensor_type, algorithm, sensor_identifier)
    with _cache_lock:
        entry = _cache.get(cache_key)
        if isinstance(entry, _CachedModel) and not _is_expired(entry):
            return entry

    meta = await _fetch_active_model_meta(sensor_type, algorithm, sensor_identifier)
    model, columns, window = _load_pkl(meta["file_path"])
    entry = _CachedModel(
        model=model,
        feature_columns=columns,
        window=window,
        version=meta["version"],
    )
    with _cache_lock:
        _cache[cache_key] = entry
    logger.info(
        "[ai] IF loaded sensor_type=%s sensor_identifier=%r version=%s file=%s",
        sensor_type,
        sensor_identifier,
        meta["version"],
        meta["file_path"],
    )
    return entry


async def _get_or_load_arima(
    sensor_type: str,
    sensor_identifier: str,
) -> _CachedArimaModel:
    """ARIMA 모델 캐시/로드 — sensor_identifier 단위 매칭 (W2 신규).

    W2.5 (train_arima_power_model.py) 가 학습한 전력 ARIMA 를 W3 추론 분기가 호출.
    가스 ARIMA 의 MLModel 통합은 가스 담당자 후속 task (plan §12) — 그 시점부터
    가스 측도 본 헬퍼 경유 가능.
    """
    algorithm = "arima"
    cache_key = (sensor_type, algorithm, sensor_identifier)
    with _cache_lock:
        entry = _cache.get(cache_key)
        if isinstance(entry, _CachedArimaModel) and not _is_expired(entry):
            return entry

    meta = await _fetch_active_model_meta(sensor_type, algorithm, sensor_identifier)
    model, order = _load_arima_pkl(meta["file_path"])
    entry = _CachedArimaModel(
        model=model,
        version=meta["version"],
        order=order,
    )
    with _cache_lock:
        _cache[cache_key] = entry
    logger.info(
        "[ai] ARIMA loaded sensor_type=%s sensor_identifier=%r version=%s file=%s order=%s",
        sensor_type,
        sensor_identifier,
        meta["version"],
        meta["file_path"],
        order,
    )
    return entry


# ---------------------------------------------------------------------------
# Feature engineering — drf-server feature_service 와 동일 수식 (의존성 분리)
# ---------------------------------------------------------------------------


def _build_feature_row(window_values: list[float], window: int) -> np.ndarray:
    """추론 1회용 — 최근 window 틱 raw value 로 (value, roll_mean, roll_std, diff) 산출.

    학습 시의 feature_service.build_features 와 동일 시맨틱. 의존성 줄이려고 inline 구현.
    """
    if len(window_values) < window:
        raise HTTPException(
            status_code=400,
            detail=f"window_values 길이 부족: {len(window_values)} < {window}",
        )
    arr = np.asarray(window_values[-window:], dtype=np.float64)
    value = arr[-1]
    roll_mean = float(arr.mean())
    roll_std = float(arr.std(ddof=0))
    diff = float(arr[-1] - arr[-2])
    return np.array([[value, roll_mean, roll_std, diff]], dtype=np.float64)

    # 이성현 추가 — 다변량 추론용 피처 빌더 (co + h2s + co2 동시)


# 이성현 추가 — ARIMA 잔차 실시간 계산 헬퍼
def _compute_arima_resid(values: list[float], arima_result) -> float:
    """슬라이딩 윈도우를 ARIMA에 적용해 마지막 잔차(실제값 - 예측값)를 반환한다."""
    try:
        new_result = arima_result.apply(endog=values)
        resid = float(new_result.resid[-1])
        return 0.0 if np.isnan(resid) else resid
    except Exception:
        return 0.0


# 이성현 수정 — arima_results 매개변수 추가 (None 이면 12피처, 제공 시 15피처)
def _build_multi_feature_row(
    windows: dict[str, list[float]],
    window: int,
    arima_results: dict | None = None,
) -> np.ndarray:
    """다변량 추론 1회용 — 가스별 슬라이딩 윈도우를 수평 스택해 1행 피처 반환.

    arima_results 제공 시 각 가스 4피처 뒤에 arima_resid 삽입 → (1, 15)
    미제공 시 기존 12피처 → (1, 12)
    """
    if not windows:
        raise HTTPException(status_code=400, detail="windows 가 비어 있습니다.")
    parts: list[float] = []
    for gas_name, values in windows.items():
        if len(values) < window:
            raise HTTPException(
                status_code=400,
                detail=f"{gas_name} window_values 길이 부족: {len(values)} < {window}",
            )
        arr = np.asarray(values[-window:], dtype=np.float64)
        roll_mean = float(arr.mean())
        roll_std = float(arr.std(ddof=0))
        diff = float(arr[-1] - arr[-2])
        parts.extend([float(arr[-1]), roll_mean, roll_std, diff])
        # 이성현 추가 — 잔차를 각 가스 4피처 바로 뒤에 삽입 (학습 피처 순서와 동일)
        if arima_results and gas_name in arima_results:
            parts.append(_compute_arima_resid(values, arima_results[gas_name]))
    return np.array([parts], dtype=np.float64)


# ---------------------------------------------------------------------------
# 스키마
# ---------------------------------------------------------------------------


class PredictRequest(BaseModel):
    sensor_type: str = Field(description="power | gas")
    sensor_identifier: str = Field(
        description="예: 'power:device_1:ch3:watt'",
        max_length=64,
    )
    window_values: list[float] = Field(
        description="최근 N 틱 raw 측정값 (N ≥ 학습 시 window)",
        min_length=2,
    )


class PredictResponse(BaseModel):
    anomaly_score: float
    prediction: str  # normal | anomaly
    model_version: int
    sensor_identifier: str
    features: dict


# ---------------------------------------------------------------------------
# 엔드포인트
# ---------------------------------------------------------------------------


@router.post(
    "/predict",
    response_model=PredictResponse,
    summary="IF 이상탐지 추론",
    description=(
        "최근 N 틱 측정값으로 sliding window 피처를 산출하고 활성 IF 모델로 추론.\n"
        "모델은 sensor_type 별 active row (drf-server `MLModel.is_active=True`) 사용. "
        "캐시 TTL 만료 시 자동 재로드."
    ),
    responses={
        400: {"description": "window_values 길이 부족"},
        404: {"description": "active 모델 없음"},
        500: {"description": "모델 파일 누락 또는 DRF 조회 실패"},
    },
)
async def predict(req: PredictRequest) -> PredictResponse:
    if req.sensor_type not in ("power", "gas"):
        raise HTTPException(status_code=400, detail="sensor_type must be power|gas")

    entry = await _get_or_load(req.sensor_type)
    row = _build_feature_row(req.window_values, entry.window)

    score = float(entry.model.decision_function(row)[0])
    pred_int = int(entry.model.predict(row)[0])
    prediction = "anomaly" if pred_int == -1 else "normal"

    return PredictResponse(
        anomaly_score=score,
        prediction=prediction,
        model_version=entry.version,
        sensor_identifier=req.sensor_identifier,
        features={
            "value": float(row[0, 0]),
            "roll_mean": float(row[0, 1]),
            "roll_std": float(row[0, 2]),
            "diff": float(row[0, 3]),
        },
    )


@router.post(
    "/reload",
    summary="모델 캐시 무효화",
    description=(
        "TTL 만료 전이라도 강제 reload. 학습 직후 운영자가 호출.\n\n"
        "쿼리 파라미터:\n"
        "- `sensor_type` (필수): power | gas\n"
        "- `algorithm` (옵션): isolation_forest | arima. 미지정 시 sensor_type 안 모든 cache evict (편의)\n"
        "- `sensor_identifier` (옵션, default '')\n\n"
        "algorithm 미지정 + sensor_identifier 미지정 → sensor_type 전체 evict.\n"
        "둘 다 지정 → 해당 매칭 단위 1건 evict."
    ),
)
async def reload_model(
    sensor_type: str = "power",
    algorithm: str | None = None,
    sensor_identifier: str | None = None,
) -> dict:
    """W2 — 3축 매칭 단위 cache evict. algorithm 미지정 시 sensor_type 전체."""
    evicted: list[list[str]] = []
    with _cache_lock:
        if algorithm is None:
            keys_to_remove = [k for k in _cache if k[0] == sensor_type]
            for k in keys_to_remove:
                _cache.pop(k, None)
                evicted.append(list(k))
        else:
            cache_key = (sensor_type, algorithm, sensor_identifier or "")
            if _cache.pop(cache_key, None) is not None:
                evicted.append(list(cache_key))
    return {"status": "ok", "evicted": evicted}
