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
    """로딩된 모델 + 학습 메타 + 로딩 시각."""

    __slots__ = ("model", "feature_columns", "window", "version", "loaded_at")

    def __init__(
        self, model, feature_columns: list[str], window: int, version: int
    ) -> None:
        self.model = model
        self.feature_columns = feature_columns
        self.window = window
        self.version = version
        self.loaded_at = time.time()


_cache: dict[str, _CachedModel] = {}
_cache_lock = Lock()


def _is_expired(entry: _CachedModel) -> bool:
    ttl = settings.ML_MODEL_CACHE_TTL_SEC
    if ttl <= 0:
        return False
    return (time.time() - entry.loaded_at) > ttl


async def _fetch_active_model_meta(sensor_type: str) -> dict:
    """DRF 에서 active 모델 메타 조회. file_path 는 ML_MODELS_DIR 기준 상대 경로."""
    url = f"{settings.DRF_BASE_URL}/api/ml/models/active/?sensor_type={sensor_type}"
    async with httpx.AsyncClient(timeout=settings.DRF_REQUEST_TIMEOUT_SEC) as client:
        res = await client.get(url)
        if res.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail=f"active 모델 없음 (sensor_type={sensor_type})",
            )
        res.raise_for_status()
        return res.json()


def _load_pkl(file_name: str) -> tuple[object, list[str], int]:
    """ML_MODELS_DIR 아래 .pkl 로드 → (model, feature_columns, window)."""
    path = Path(settings.ML_MODELS_DIR) / file_name
    if not path.exists():
        raise HTTPException(
            status_code=500,
            detail=f"모델 파일 없음: {path} (drf-server 와 같은 volume 마운트 확인)",
        )
    bundle = joblib.load(path)
    return bundle["model"], bundle["feature_columns"], bundle["window"]


async def _get_or_load(sensor_type: str) -> _CachedModel:
    """sensor_type 의 active 모델을 캐시에서 가져오거나 새로 로드."""
    with _cache_lock:
        entry = _cache.get(sensor_type)
        if entry is not None and not _is_expired(entry):
            return entry

    meta = await _fetch_active_model_meta(sensor_type)
    model, columns, window = _load_pkl(meta["file_path"])
    entry = _CachedModel(
        model=model,
        feature_columns=columns,
        window=window,
        version=meta["version"],
    )
    with _cache_lock:
        _cache[sensor_type] = entry
    logger.info(
        "[ai] model loaded sensor_type=%s version=%s file=%s",
        sensor_type,
        meta["version"],
        meta["file_path"],
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


def _build_multi_feature_row(
    windows: dict[str, list[float]], window: int
) -> np.ndarray:
    """다변량 추론 1회용 — 가스별 슬라이딩 윈도우를 수평 스택해 1행 피처 반환.

    예: {"co": [...30개], "h2s": [...30개], "co2": [...30개]} → shape (1, 12)
    가스 1개당 4피처(value, roll_mean, roll_std, diff) x 3가스 = 12피처
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
    description="TTL 만료 전이라도 강제 reload. 학습 직후 운영자가 호출.",
)
async def reload_model(sensor_type: str = "power") -> dict:
    with _cache_lock:
        _cache.pop(sensor_type, None)
    return {"status": "ok", "evicted": sensor_type}
