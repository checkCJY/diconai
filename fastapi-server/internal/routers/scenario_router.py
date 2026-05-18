# internal/routers/scenario_router.py — 시연 시나리오 모드 컨트롤
#
# 더미가 polling으로 현재 모드를 조회하고, 프론트엔드(대시보드)가 POST로
# 모드를 변경한다. 환경변수 DUMMY_SCENARIO_MODE로 부팅 시 초기값이 결정된다.
#
# 모드값:
#   mixed         — 확률 기반 (기본 동작)
#   normal        — 모든 가스/전력 정상 범위 강제
#   warning       — 모든 가스/전력 주의 범위 강제
#   danger        — 모든 가스/전력 위험 범위 강제
#   overload      — 전력 단일 시나리오: 과부하 (IF 학습 격리 테스트)
#   voltage_drop  — 전력 단일 시나리오: 저전압
#   spike         — 전력 단일 시나리오: 순간 스파이크
#   phase_loss    — 전력 단일 시나리오: 3상 결상
#   degradation   — 전력 단일 시나리오: 점진 열화
#   co_leak       — 가스 단일 시나리오: 일산화탄소 누출
#   h2s_leak      — 가스 단일 시나리오: 황화수소 누출
#   fire          — 가스 단일 시나리오: 화재/폭발 전조
#   chemical_spill — 가스 단일 시나리오: 유해화학물 다중 누출
# 단일 시나리오 모드는 다른 도메인 더미는 fallback("mixed") 처리.

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from core.config import settings
from websocket.state import scenario_mode

router = APIRouter(prefix="/internal/scenario", tags=["internal"])

ALLOWED_MODES = {
    "mixed",
    "normal",
    "warning",
    "danger",
    # power_dummy 단일 시나리오 모드 (IF 학습 데이터 격리 테스트)
    # W0 변경 (skill/plan/power-ai-un-downgrade-phase2-apply.md §3):
    # spike 제거, night_abnormal/motor_stuck 신규. dummies/_scenario.py 와 동기화.
    "overload",
    "voltage_drop",
    "phase_loss",
    "degradation",
    "night_abnormal",
    "motor_stuck",
    # gas_dummy 단일 시나리오 모드
    "co_leak",
    "h2s_leak",
    "fire",
    "chemical_spill",
}


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


@router.get(
    "/mode",
    summary="현재 시나리오 모드 조회",
    description=(
        "더미 스크립트가 polling으로 호출. 환경변수 `DUMMY_SCENARIO_MODE`로 부팅 시 초기값.\n\n"
        "모드: `mixed` / `normal` / `warning` / `danger` / "
        "전력 `overload`·`voltage_drop`·`phase_loss`·`degradation`·`night_abnormal`·`motor_stuck` / "
        "가스 `co_leak`·`h2s_leak`·`fire`·`chemical_spill`."
    ),
)
async def get_mode() -> dict:
    return {"mode": scenario_mode["value"]}


@router.post(
    "/mode",
    summary="시나리오 모드 변경",
    description=(
        "프론트엔드 시연 컨트롤·테스트 스크립트에서 호출해 더미 데이터의 위험도/시나리오를 강제한다.\n\n"
        "**공통 모드** (가스·전력·위치 더미 모두 적용)\n"
        "- `mixed`: 확률 기반 (기본 동작)\n"
        "- `normal` / `warning` / `danger`: 전 채널/가스 동일 레벨 강제\n\n"
        "**전력 전용 단일 시나리오 모드** (IF 학습 격리 테스트 — 가스/위치는 fallback 'mixed')\n"
        "- `overload` / `voltage_drop` / `phase_loss` / `degradation`\n"
        "- `night_abnormal` (KST 22~05 시간대 외 진입 무시) / `motor_stuck`\n\n"
        "**가스 전용 단일 시나리오 모드** (IF 학습 격리 테스트 — 전력/위치는 fallback 'mixed')\n"
        "- `co_leak` / `h2s_leak` / `fire` / `chemical_spill`"
    ),
    responses={
        400: {"description": "허용되지 않은 모드값"},
        422: {"description": "ModePayload 검증 실패"},
    },
)
async def set_mode(payload: ModePayload) -> dict:
    if payload.mode not in ALLOWED_MODES:
        raise HTTPException(status_code=400, detail="허용되지 않은 모드입니다.")
    scenario_mode["value"] = payload.mode
    return {"mode": scenario_mode["value"]}
