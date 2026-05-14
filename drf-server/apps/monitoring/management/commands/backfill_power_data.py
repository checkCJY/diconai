"""
backfill_power_data — IF 학습용 PowerData 백필 management 커맨드

[배경]
fastapi-server/dummies/power_dummy.py 는 measured_at = now_utc_iso() 고정이라
실시간 송신만 가능. 6개월치를 실시간으로 모으는 건 비현실 → 시간 가속 backfill.

[동기화 주의 — 더미와 갈라지면 학습 데이터와 운영 데이터 분포 불일치]
power_dummy.py v3 의 CHANNEL_RATED / SCENARIO_PATTERNS / base_load_ratio /
maybe_trigger / step 로직을 인라인 복제. 더미 변경 시 양쪽 동시 수정 필요.
원본: fastapi-server/dummies/power_dummy.py:72-189 (state machine 로직은
fastapi-server/dummies/_state_machine.py:60-148).

[더미 vs 백필 차이 — T1 작업 시 주의]
- measured_at: 인자(`--start-date`) 기반 과거 timestamp (더미는 now)
- received_at: measured_at 과 동일 (더미는 auto_now_add → 통신 지연 반영)
- risk_level: NORMAL 일괄 (더미 경로는 evaluate_power_risk 자동) — bulk_create 가
  save() 우회하기 때문. T1 결합 매트릭스 통합 테스트는 더미 실시간 가동 권장
- 처리 경로: ORM bulk_create 직접 (더미는 fastapi router → DRF serializer)
- PowerEvent / AlarmRecord 생성 안 함 (학습용 raw 데이터만)

실행:
    python manage.py backfill_power_data \\
        --start-date 2025-11-13 \\
        --duration-days 180 \\
        --interval-sec 30

검증·재현 가이드: docs/changelog/ml/power_dummy_audit_2026_05_13.md
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.core.constants import RiskLevel, SensorStatus
from apps.facilities.models import PowerDevice
from apps.monitoring.models import PowerData


# ---------------------------------------------------------------------------
# power_dummy.py v3 인라인 복제
# ---------------------------------------------------------------------------
# 채널별 정격 — power_dummy.py:72-89 와 동일.
# 정격 변경 시 facilities/migrations/0017_seed_power_channel_meta.py 도 동시 수정.
CHANNEL_RATED: dict[int, dict[str, float]] = {
    1: {"w": 7500, "a": 30, "v": 380},
    2: {"w": 3700, "a": 15, "v": 380},
    3: {"w": 5500, "a": 22, "v": 380},
    4: {"w": 4000, "a": 16, "v": 380},
    5: {"w": 2200, "a": 10, "v": 380},
    6: {"w": 3700, "a": 15, "v": 380},
    7: {"w": 1500, "a": 7, "v": 380},
    8: {"w": 5500, "a": 22, "v": 380},
    9: {"w": 15000, "a": 50, "v": 380},
    10: {"w": 7500, "a": 30, "v": 380},
    11: {"w": 7500, "a": 30, "v": 380},
    12: {"w": 3000, "a": 14, "v": 380},
    13: {"w": 3000, "a": 14, "v": 380},
    14: {"w": 5500, "a": 22, "v": 380},
    15: {"w": 1000, "a": 5, "v": 220},
    16: {"w": 2200, "a": 10, "v": 380},
}
# 채널 분류 — power_dummy.py:92-94 와 동일 (motor 는 명시 X, 잔여 채널이 motor).
LIGHTING_CHANNELS = {15}
PANEL_CHANNELS = {9, 10, 11, 16}

# 시나리오 5종 — power_dummy.py:119-161 와 동일.
SCENARIO_PATTERNS: dict[str, dict] = {
    "overload": {
        "w_factor": 1.10,
        "a_factor": 1.10,
        "v_factor": 0.93,
        "ramp_up": 5,
        "hold": 60,
        "ramp_down": 10,
    },
    "voltage_drop": {
        "w_factor": 0.85,
        "a_factor": 1.10,
        "v_factor": 0.88,
        "ramp_up": 3,
        "hold": 30,
        "ramp_down": 5,
    },
    "spike": {
        "w_factor": 1.30,
        "a_factor": 1.30,
        "v_factor": 1.00,
        "ramp_up": 1,
        "hold": 1,
        "ramp_down": 1,
    },
    "phase_loss": {
        "w_factor": 0.05,
        "a_factor": 0.05,
        "v_factor": 0.05,
        "ramp_up": 2,
        "hold": 30,
        "ramp_down": 5,
    },
    "degradation": {
        "w_factor": 1.05,
        "a_factor": 1.05,
        "v_factor": 1.00,
        "ramp_up": 60,
        "hold": 30,
        "ramp_down": 5,
    },
}
SCENARIO_NAMES = list(SCENARIO_PATTERNS.keys())
# 가중치 — power_dummy.py:164-170 와 동일. 도메인 통계 부재 시 임의값.
SCENARIO_WEIGHTS = [6, 4, 2, 2, 1]
# mixed 모드 채널당 진입 확률 — power_dummy.py:178 와 동일.
# 16채널 × 0.005 → 평균 12.5틱당 1건 시나리오 진입.
MIXED_TRIGGER_PROBABILITY = 0.005

NORMAL_STATE = "normal"
RAMP_UP_STATE = "ramp_up"
HOLD_STATE = "hold"
RAMP_DOWN_STATE = "ramp_down"


@dataclass
class ChannelState:
    """채널 1개의 시나리오 진행 상태 — _state_machine.py:34-43 와 동일."""

    state: str = NORMAL_STATE
    scenario: str | None = None
    ticks_in_state: int = 0
    ramp_up_ticks: int = 5
    hold_ticks: int = 10
    ramp_down_ticks: int = 10


@dataclass
class StateOutput:
    """step() 결과 — weight 0.0=정상, 1.0=시나리오 100%, 0~1=RAMP 보간."""

    weight: float
    is_anomaly: bool
    anomaly_type: str | None


def step(cs: ChannelState) -> StateOutput:
    """1틱 진행 후 현재 출력 반환. HOLD 만료 시 RAMP_DOWN 자동 전이.

    _state_machine.py:81-121 와 동일 로직.
    """
    cs.ticks_in_state += 1
    if cs.state == NORMAL_STATE:
        return StateOutput(0.0, False, None)
    if cs.state == RAMP_UP_STATE:
        weight = min(1.0, cs.ticks_in_state / cs.ramp_up_ticks)
        if cs.ticks_in_state >= cs.ramp_up_ticks:
            cs.state = HOLD_STATE
            cs.ticks_in_state = 0
        return StateOutput(weight, True, cs.scenario)
    if cs.state == HOLD_STATE:
        if cs.ticks_in_state >= cs.hold_ticks:
            cs.state = RAMP_DOWN_STATE
            cs.ticks_in_state = 0
        return StateOutput(1.0, True, cs.scenario)
    # RAMP_DOWN
    remaining = max(0, cs.ramp_down_ticks - cs.ticks_in_state)
    weight = remaining / cs.ramp_down_ticks
    if cs.ticks_in_state >= cs.ramp_down_ticks:
        cs.state = NORMAL_STATE
        cs.scenario = None
        cs.ticks_in_state = 0
        return StateOutput(0.0, False, None)
    return StateOutput(weight, True, cs.scenario)


def maybe_trigger(cs: ChannelState) -> None:
    """NORMAL 채널을 가중치 기반 시나리오로 확률적 진입시킨다.

    _state_machine.py:124-148 와 동일. 이미 진행 중인 채널은 무시.
    """
    if cs.state != NORMAL_STATE or random.random() >= MIXED_TRIGGER_PROBABILITY:
        return
    picked = random.choices(SCENARIO_NAMES, weights=SCENARIO_WEIGHTS, k=1)[0]
    pattern = SCENARIO_PATTERNS[picked]
    cs.state = RAMP_UP_STATE
    cs.scenario = picked
    cs.ticks_in_state = 0
    cs.ramp_up_ticks = max(1, pattern["ramp_up"])
    cs.hold_ticks = max(1, pattern["hold"])
    cs.ramp_down_ticks = max(1, pattern["ramp_down"])


def base_load_ratio(hour: int, ch: int) -> float:
    """채널×시간대 기저 부하 비율 (정격 대비 0.0~1.0).

    power_dummy.py:100-113 와 동일. 평일 공장 가동 패턴 가정.
    """
    if ch in LIGHTING_CHANNELS:
        return 0.4
    if ch in PANEL_CHANNELS:
        return 0.5
    if 8 <= hour < 12:
        return 0.60
    if 13 <= hour < 18:
        return 0.70
    if 19 <= hour < 22:
        return 0.30
    return 0.15


def gauss_noise(stddev: float = 0.05) -> float:
    """1.0 주변 가우스 노이즈 — clamp [0.5, 1.5]. power_dummy.py:187-189 동일."""
    return max(0.5, min(1.5, random.gauss(1.0, stddev)))


def compute_tick(
    ch: int, hour: int, cs: ChannelState
) -> tuple[float, float, float, bool, str | None]:
    """채널 1개의 1틱 (W, A, V, is_anomaly, anomaly_type) 계산.

    state machine 진행 후 normal 값과 scenario 값을 weight 로 선형 보간.
    power_dummy.py:192-230 와 동일 (페이로드 포맷팅만 다름).
    """
    rated = CHANNEL_RATED[ch]
    base = base_load_ratio(hour, ch)
    nw = rated["w"] * base * gauss_noise(0.05)
    na = rated["a"] * base * gauss_noise(0.05)
    nv = rated["v"] * gauss_noise(0.01)
    out = step(cs)
    if not out.is_anomaly:
        return round(nw, 1), round(na, 2), round(nv, 1), False, None
    pat = SCENARIO_PATTERNS[out.anomaly_type]
    sw = rated["w"] * pat["w_factor"] * gauss_noise(0.03)
    sa = rated["a"] * pat["a_factor"] * gauss_noise(0.03)
    sv = rated["v"] * pat["v_factor"] * gauss_noise(0.01)
    w = nw * (1 - out.weight) + sw * out.weight
    a = na * (1 - out.weight) + sa * out.weight
    v = nv * (1 - out.weight) + sv * out.weight
    return round(w, 1), round(a, 2), round(v, 1), True, out.anomaly_type


class Command(BaseCommand):
    help = "Backfill PowerData rows from a past start date for IF training."

    def add_arguments(self, parser):
        parser.add_argument(
            "--start-date",
            required=True,
            help="ISO date (YYYY-MM-DD). Backfill begins at this UTC midnight.",
        )
        parser.add_argument("--duration-days", type=int, default=180)
        parser.add_argument("--interval-sec", type=int, default=30)
        parser.add_argument(
            "--device-id",
            type=int,
            default=None,
            help="PowerDevice.id (default: first active device)",
        )
        parser.add_argument("--batch-size", type=int, default=50000)
        parser.add_argument("--seed", type=int, default=42)

    def handle(self, *args, **opts):
        """`--start-date` 부터 `--duration-days` × `--interval-sec` 만큼 PowerData
        bulk_create 백필. 매 틱 16채널 × (W,A,V) = 48 행 생성. batch_size 단위로
        transaction.atomic commit (메모리·락 분산).

        risk_level 은 NORMAL 일괄 (bulk_create 가 save() 우회 → evaluate_power_risk
        호출 안 됨). T1 결합 매트릭스 통합 테스트는 더미 실시간 가동으로 보완 필요.
        """
        random.seed(opts["seed"])

        device_id = opts["device_id"]
        if device_id is None:
            device = PowerDevice.objects.filter(is_active=True).first()
            if device is None:
                raise CommandError(
                    "No active PowerDevice. Pass --device-id explicitly."
                )
            device_id = device.id

        try:
            start = datetime.fromisoformat(opts["start_date"]).replace(
                tzinfo=timezone.utc
            )
        except ValueError as exc:
            raise CommandError(f"Invalid --start-date: {exc}") from exc

        duration = timedelta(days=opts["duration_days"])
        end = start + duration
        interval = timedelta(seconds=opts["interval_sec"])
        total_ticks = int(duration.total_seconds() // opts["interval_sec"])
        total_rows = total_ticks * 16 * 3
        batch_size = opts["batch_size"]

        self.stdout.write(
            f"PowerData backfill: device_id={device_id} | "
            f"window {start.isoformat()} → {end.isoformat()} | "
            f"interval={opts['interval_sec']}s | "
            f"ticks={total_ticks:,} | rows={total_rows:,} | batch={batch_size:,}"
        )

        states = {ch: ChannelState() for ch in range(1, 17)}
        buffer: list[PowerData] = []
        flushed = 0
        ts = start

        while ts < end:
            hour = ts.hour
            for ch in range(1, 17):
                maybe_trigger(states[ch])
            for ch in range(1, 17):
                w, a, v, is_anom, anom_type = compute_tick(ch, hour, states[ch])
                for data_type, val in (("watt", w), ("current", a), ("voltage", v)):
                    buffer.append(
                        PowerData(
                            power_device_id=device_id,
                            channel=ch,
                            data_type=data_type,
                            value=val,
                            sensor_status=SensorStatus.ACTIVE,
                            risk_level=RiskLevel.NORMAL,
                            is_anomaly=is_anom,
                            anomaly_type=anom_type,
                            measured_at=ts,
                            received_at=ts,
                        )
                    )
            if len(buffer) >= batch_size:
                with transaction.atomic():
                    PowerData.objects.bulk_create(buffer, batch_size=batch_size)
                flushed += len(buffer)
                buffer.clear()
                pct = flushed * 100 / total_rows
                self.stdout.write(
                    f"  flushed {flushed:,} / {total_rows:,} ({pct:.1f}%)  cursor={ts.isoformat()}"
                )
            ts += interval

        if buffer:
            with transaction.atomic():
                PowerData.objects.bulk_create(buffer, batch_size=batch_size)
            flushed += len(buffer)

        self.stdout.write(self.style.SUCCESS(f"Done. {flushed:,} rows inserted."))
