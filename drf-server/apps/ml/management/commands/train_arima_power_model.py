"""
전력 ARIMA 오프라인 학습 + MLModel row 생성 (W2.5).

ARIMA un-downgrade plan §6 (skill/plan/power-ai-un-downgrade-phase2-apply.md). 가스용
train_arima_model.py 는 가스 영역 보호 결정에 따라 0 변경 유지 — 본 명령은
전력 전용 신규. 가스 ARIMA 의 MLModel 통합은 가스 담당자 후속 task (plan §12).

사용 예:
    python manage.py train_arima_power_model \\
        --device-id 1 --channel 1 --data-type watt \\
        --since 2026-05-12 --until 2026-05-15 --activate

학습 결과:
- .pkl 파일: settings.ML_MODELS_DIR / "power_arima_v{version}_{sid_safe}.pkl"
- MLModel row 1건 (algorithm=arima, sensor_identifier="power:device_{}:ch{}:{}")
- --activate 시 같은 매칭 단위 (sensor_type, algorithm, sensor_identifier) 의
  기존 활성 ARIMA 만 비활성화 (다른 sensor_identifier 의 활성 모델은 영향 없음)
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import joblib
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.dateparse import parse_datetime
from statsmodels.tsa.arima.model import ARIMA

from apps.facilities.models import PowerDevice
from apps.ml.models import MLModel
from apps.ml.services.dataset_service import extract_normal_power_series


def _parse_dt(s: str) -> datetime:
    """ISO 8601 또는 YYYY-MM-DD → UTC aware datetime."""
    dt = parse_datetime(s)
    if dt is None:
        dt = datetime.strptime(s, "%Y-%m-%d")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _next_arima_version(sensor_identifier: str) -> int:
    """매칭 단위 (power, arima, sensor_identifier) 안 다음 version."""
    last = (
        MLModel.objects.filter(
            sensor_type="power",
            algorithm=MLModel.Algorithm.ARIMA,
            sensor_identifier=sensor_identifier,
        )
        .order_by("-version")
        .values_list("version", flat=True)
        .first()
    )
    return (last or 0) + 1


class Command(BaseCommand):
    help = "전력 ARIMA 학습 + MLModel row 생성 (W2.5)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--device-id", type=int, required=True, help="PowerDevice.id"
        )
        parser.add_argument("--channel", type=int, required=True, help="채널 1~16")
        parser.add_argument(
            "--data-type",
            choices=("current", "voltage", "watt"),
            required=True,
        )
        parser.add_argument("--since", required=True, help="ISO 또는 YYYY-MM-DD")
        parser.add_argument("--until", required=True, help="ISO 또는 YYYY-MM-DD")
        parser.add_argument("--p", type=int, default=1, help="ARIMA p (자기회귀)")
        parser.add_argument("--d", type=int, default=1, help="ARIMA d (차분)")
        parser.add_argument("--q", type=int, default=1, help="ARIMA q (이동평균)")
        parser.add_argument(
            "--max-rows",
            type=int,
            default=10000,
            # 3000 (이전 default) 시 5분 주기 데이터 기준 ~10일 윈도우 — 하루의 시간대
            # 변동(주간 0.55 / 야간 0.15) 일부만 학습되어 ConvergenceWarning + ci 폭 0
            # 회귀 발생 (2026-05-21 확인). 10000 으로 전체 시간대 패턴 학습 보장.
            help="학습에 사용할 최근 row 수 상한 (학습 시간 제한)",
        )
        parser.add_argument(
            "--activate",
            action="store_true",
            help="학습 후 같은 매칭 단위의 기존 활성 ARIMA 비활성화 + 본 모델 활성화",
        )

    def handle(self, *args, **options):
        since = _parse_dt(options["since"])
        until = _parse_dt(options["until"])
        order = (options["p"], options["d"], options["q"])
        # device_id (PK, --device-id 인자) → raw device_id (mac 주소) 변환.
        # 추론 측 (fastapi power_service) 의 sensor_identifier 생성과 일관성 보장:
        # 가스/전력 추론 모두 raw mac 사용 ("power:device_{mac}:ch{n}:{type}").
        # PK 사용 시 매칭 실패 → 404 silent fallback → ARIMA 미동작.
        try:
            device_obj = PowerDevice.objects.get(pk=options["device_id"])
        except PowerDevice.DoesNotExist as exc:
            raise CommandError(f"PowerDevice PK={options['device_id']} 없음") from exc
        raw_device_id = device_obj.device_id
        sensor_identifier = (
            f"power:device_{raw_device_id}"
            f":ch{options['channel']}:{options['data_type']}"
        )

        self.stdout.write(
            f"[1/4] dataset 추출 — {sensor_identifier} ({since} ~ {until})"
        )
        series = extract_normal_power_series(
            device_id=options["device_id"],
            channel=options["channel"],
            data_type=options["data_type"],
            since=since,
            until=until,
        )
        if len(series) < 50:
            raise CommandError(f"학습 데이터 부족: {len(series)}개 (최소 50개)")
        self.stdout.write(f"      raw rows = {len(series)}")

        values = series.values[-options["max_rows"] :].tolist()
        self.stdout.write(f"[2/4] ARIMA{order} 학습 중 — 최근 {len(values)} rows 사용")
        result = ARIMA(values, order=order).fit()

        version = _next_arima_version(sensor_identifier)
        models_dir = Path(settings.ML_MODELS_DIR)
        models_dir.mkdir(parents=True, exist_ok=True, mode=0o755)
        sid_safe = sensor_identifier.replace(":", "_")
        file_name = f"power_arima_v{version}_{sid_safe}.pkl"
        file_path = models_dir / file_name

        self.stdout.write(f"[3/4] joblib.dump → {file_path}")
        joblib.dump({"result": result, "order": order}, file_path)

        params = {
            "p": options["p"],
            "d": options["d"],
            "q": options["q"],
            "max_rows": options["max_rows"],
            "device_id": options["device_id"],
            "channel": options["channel"],
            "data_type": options["data_type"],
        }

        self.stdout.write(f"[4/4] MLModel row 생성 — version v{version}")
        with transaction.atomic():
            if options["activate"]:
                MLModel.objects.filter(
                    sensor_type="power",
                    algorithm=MLModel.Algorithm.ARIMA,
                    sensor_identifier=sensor_identifier,
                    is_active=True,
                ).update(is_active=False)
            row = MLModel.objects.create(
                version=version,
                sensor_type="power",
                algorithm=MLModel.Algorithm.ARIMA,
                sensor_identifier=sensor_identifier,
                file_path=file_name,
                training_data_range_from=since,
                training_data_range_to=until,
                training_sample_count=len(values),
                feature_columns=[],  # ARIMA 단변량 — feature_columns 개념 없음
                params_json=params,
                is_active=options["activate"],
            )

        self.stdout.write(self.style.SUCCESS("학습 완료"))
        self.stdout.write(f"  MLModel.id          = {row.id}")
        self.stdout.write(f"  sensor_identifier   = {sensor_identifier}")
        self.stdout.write(f"  file_path           = {file_path}")
        self.stdout.write(f"  order               = {order}")
        self.stdout.write(f"  is_active           = {options['activate']}")
