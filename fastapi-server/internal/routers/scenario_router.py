# internal/routers/scenario_router.py — 시연 시나리오 모드 컨트롤
#
# 더미가 polling으로 현재 모드를 조회하고, 프론트엔드(대시보드)가 POST로
# 모드를 변경한다. 환경변수 DUMMY_SCENARIO_MODE로 부팅 시 초기값이 결정된다.
#
# 모드값:
#   mixed   — 확률 기반 (기본 동작)
#   normal  — 모든 가스/전력 정상 범위 강제
#   warning — 모든 가스/전력 주의 범위 강제
#   danger  — 모든 가스/전력 위험 범위 강제

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from core.config import settings
from websocket.state import scenario_mode

router = APIRouter(prefix="/internal/scenario")

ALLOWED_MODES = {"mixed", "normal", "warning", "danger"}


class ModePayload(BaseModel):
    mode: str

    @field_validator("mode")
    @classmethod
    def _validate(cls, v: str) -> str:
        if v not in ALLOWED_MODES:
            raise ValueError(f"mode must be one of {sorted(ALLOWED_MODES)}")
        return v


# 부팅 시 환경변수 값으로 초기화 (Settings 기본값 적용)
if settings.DUMMY_SCENARIO_MODE in ALLOWED_MODES:
    scenario_mode["value"] = settings.DUMMY_SCENARIO_MODE


@router.get("/mode")
async def get_mode() -> dict:
    """현재 시나리오 모드를 반환한다. 더미가 polling으로 호출."""
    return {"mode": scenario_mode["value"]}


@router.post("/mode")
async def set_mode(payload: ModePayload) -> dict:
    """시나리오 모드를 변경한다. 프론트 컨트롤에서 호출."""
    if payload.mode not in ALLOWED_MODES:
        raise HTTPException(status_code=400, detail="허용되지 않은 모드입니다.")
    scenario_mode["value"] = payload.mode
    return {"mode": scenario_mode["value"]}
