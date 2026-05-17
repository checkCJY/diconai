# apps/ml/management/commands/train_anomaly_model.py
"""
오프라인 학습 커맨드 — sklearn IsolationForest 학습 + .pkl 저장 + MLModel row 생성.

전력 사용 예:
    python manage.py train_anomaly_model \\
        --sensor-type power --device-id 1 --channel 3 --data-type watt \\
        --since 2026-05-12 --until 2026-05-13 \\
        --contamination 0.01 --n-estimators 100 --window 30

가스 사용 예:
    python manage.py train_anomaly_model \\
        --sensor-type gas --sensor-id 1 --gas-name co \\
        --since 2026-05-12 --until 2026-05-13 \\
        --contamination 0.01 --activate

학습 결과:
- .pkl 파일: settings.ML_MODELS_DIR / "{sensor_type}_if_v{version}.pkl"
- MLModel row 1건 (sensor_type, version, file_path 등 메타)
- 옵션 `--activate` 지정 시 is_active=True 로 표시 (기존 활성 모델은 자동 비활성화)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.dateparse import parse_datetime
from sklearn.ensemble import IsolationForest

from apps.ml.models import MLModel
from apps.ml.services.dataset_service import (
    TimeSeries,
    extract_normal_gas_series,
    extract_normal_gas_multi_series,
    extract_normal_power_series,
)
from apps.ml.services.feature_service import (
    DEFAULT_WINDOW,
    build_features,
    build_multi_features,
)


def _parse_dt(s: str) -> datetime:
    """ISO 8601 또는 YYYY-MM-DD 파싱 — naive 면 UTC 부여."""
    dt = parse_datetime(s)
    if dt is None:
        # YYYY-MM-DD fallback
        dt = datetime.strptime(s, "%Y-%m-%d")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _fetch_series(sensor_type: str, opts: dict) -> TimeSeries:
    """sensor_type 별 dataset 추출 — 전력/가스 둘 다 지원."""
    if sensor_type == "power":
        return extract_normal_power_series(
            device_id=opts["device_id"],
            channel=opts["channel"],
            data_type=opts["data_type"],
            since=opts["since"],
            until=opts["until"],
        )
    if sensor_type == "gas":
        return extract_normal_gas_series(
            sensor_id=opts["sensor_id"],
            gas_name=opts["gas_name"],
            since=opts["since"],
            until=opts["until"],
        )
    raise CommandError(f"알 수 없는 sensor_type: {sensor_type}")


def _next_version(sensor_type: str) -> int:
    last = (
        MLModel.objects.filter(sensor_type=sensor_type)
        .order_by("-version")
        .values_list("version", flat=True)
        .first()
    )
    return (last or 0) + 1


class Command(BaseCommand):
    help = "Isolation Forest 학습 + MLModel row 생성"

    def add_arguments(self, parser):
        parser.add_argument(
            "--sensor-type",
            required=True,
            choices=("power", "gas"),
        )
        parser.add_argument("--device-id", type=int, help="(power) PowerDevice.id")
        parser.add_argument("--channel", type=int, help="(power) 채널 1~16")
        parser.add_argument(
            "--data-type",
            choices=("current", "voltage", "watt"),
            help="(power) 측정 종류",
        )
        parser.add_argument("--sensor-id", type=int, help="(gas) GasSensor.id")
        # 이성현 수정 — 단일(co) 또는 다변량(co,h2s,co2) 콤마 구분 입력 지원
        parser.add_argument(
            "--gas-name",
            help="(gas) 학습할 가스 종류. 단일: co  다변량: co,h2s,co2",
        )

        parser.add_argument("--since", required=True, help="ISO 또는 YYYY-MM-DD")
        parser.add_argument("--until", required=True, help="ISO 또는 YYYY-MM-DD")
        parser.add_argument("--window", type=int, default=DEFAULT_WINDOW)
        parser.add_argument("--contamination", type=float, default=0.01)
        parser.add_argument("--n-estimators", type=int, default=100)
        parser.add_argument("--random-state", type=int, default=42)
        parser.add_argument(
            "--activate",
            action="store_true",
            help="학습 후 is_active=True 로 표시 + 동일 sensor_type 의 기존 활성 모델 비활성화",
        )

    def handle(self, *args, **options):
        sensor_type: str = options["sensor_type"]
        since = _parse_dt(options["since"])
        until = _parse_dt(options["until"])
        opts = {
            "device_id": options.get("device_id"),
            "channel": options.get("channel"),
            "data_type": options.get("data_type"),
            "sensor_id": options.get("sensor_id"),
            "gas_name": options.get("gas_name"),
            "since": since,
            "until": until,
        }

        if sensor_type == "power" and not all(
            (opts["device_id"], opts["channel"], opts["data_type"])
        ):
            raise CommandError(
                "sensor-type=power 는 --device-id / --channel / --data-type 필수."
            )
        if sensor_type == "gas" and not all((opts["sensor_id"], opts["gas_name"])):
            raise CommandError("sensor-type=gas 는 --sensor-id / --gas-name 필수.")

        self.stdout.write(f"[1/5] dataset 추출 — sensor_type={sensor_type}")
        # 이성현 수정 — gas 다변량 분기: gas_name 콤마 분리 후 multi series 추출
        if sensor_type == "gas":
            _VALID = {"co", "h2s", "co2", "o2", "no2", "so2", "o3", "nh3", "voc"}
            gas_names = [g.strip() for g in opts["gas_name"].split(",")]
            invalid = [g for g in gas_names if g not in _VALID]
            if invalid:
                raise CommandError(f"알 수 없는 gas_name: {invalid}")
            series_list = extract_normal_gas_multi_series(
                sensor_id=opts["sensor_id"],
                gas_names=gas_names,
                since=opts["since"],
                until=opts["until"],
            )
            min_len = min(len(s) for s in series_list)
            self.stdout.write(f"      raw rows = {min_len} (gas_names={gas_names})")
            if min_len < options["window"] * 10:
                raise CommandError(
                    f"학습 데이터 부족: {min_len} rows (최소 {options['window'] * 10})"
                )
            self.stdout.write(f"[2/5] feature engineering — window={options['window']}")
            # 이성현 추가 — ARIMA pkl 로드 후 잔차 피처 활성화 (파일 없으면 경고 후 12피처 유지)
            _models_dir = Path(settings.ML_MODELS_DIR)
            arima_results = {}
            for _gn in gas_names:
                _p = _models_dir / f"arima_{_gn}.pkl"
                if _p.exists():
                    arima_results[_gn] = joblib.load(_p)["result"]
                    self.stdout.write(f"      ARIMA 로드: arima_{_gn}.pkl")
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f"      ARIMA 없음 (건너뜀): arima_{_gn}.pkl"
                        )
                    )
            fm = build_multi_features(
                series_list,
                gas_names,
                window=options["window"],
                drop_warmup=True,
                arima_results=arima_results if arima_results else None,
            )

        else:
            series = _fetch_series(sensor_type, opts)
            self.stdout.write(
                f"      raw rows = {len(series)} (sensor_identifier={series.sensor_identifier})"
            )
            if len(series) < options["window"] * 10:
                raise CommandError(
                    f"학습 데이터 부족: {len(series)} rows (최소 {options['window'] * 10})"
                )
            self.stdout.write(f"[2/5] feature engineering — window={options['window']}")
            fm = build_features(series, window=options["window"], drop_warmup=True)

        self.stdout.write(
            f"      feature shape = {fm.features.shape}, columns = {fm.columns}"
        )

        self.stdout.write(
            f"[3/5] IsolationForest fit — contamination={options['contamination']}, "
            f"n_estimators={options['n_estimators']}"
        )
        model = IsolationForest(
            contamination=options["contamination"],
            n_estimators=options["n_estimators"],
            random_state=options["random_state"],
            n_jobs=-1,
        )
        model.fit(fm.features)

        version = _next_version(sensor_type)
        models_dir = Path(settings.ML_MODELS_DIR)
        # 0o755 — 컨테이너 user UID 매핑(docker-compose user) 환경에서도 fastapi 가
        # 같은 uid 로 read 가능하도록 완화. ml_models 는 .gitignore + 웹 서버 미서빙이라
        # dev 단계 보안 영향 미미. 운영 진입 시 별도 secure path 권장.
        models_dir.mkdir(parents=True, exist_ok=True, mode=0o755)
        file_name = f"{sensor_type}_if_v{version}.pkl"
        file_path = models_dir / file_name
        self.stdout.write(f"[4/5] joblib.dump → {file_path}")
        joblib.dump(
            {
                "model": model,
                "feature_columns": fm.columns,
                "window": options["window"],
            },
            file_path,
        )

        params = {
            "contamination": options["contamination"],
            "n_estimators": options["n_estimators"],
            "random_state": options["random_state"],
            "window": options["window"],
            # power 학습 시 채워짐
            "device_id": opts["device_id"],
            "channel": opts["channel"],
            "data_type": opts["data_type"],
            # gas 학습 시 채워짐
            "sensor_id": opts["sensor_id"],
            "gas_name": opts["gas_name"],
        }

        self.stdout.write(f"[5/5] MLModel row 생성 — version v{version}")
        with transaction.atomic():
            if options["activate"]:
                MLModel.objects.filter(sensor_type=sensor_type, is_active=True).update(
                    is_active=False
                )
            row = MLModel.objects.create(
                version=version,
                sensor_type=sensor_type,
                model_type=MLModel.ModelType.ISOLATION_FOREST,
                file_path=file_name,
                training_data_range_from=since,
                training_data_range_to=until,
                training_sample_count=len(fm),
                feature_columns=fm.columns,
                params_json=params,
                is_active=options["activate"],
            )

        # 학습 검증 (자기 자신에 대한 예측)
        pred = model.predict(fm.features)
        score = model.decision_function(fm.features)
        n_anom = int((pred == -1).sum())
        self.stdout.write(self.style.SUCCESS("학습 완료"))
        self.stdout.write(f"  MLModel.id           = {row.id}")
        self.stdout.write(f"  file_path            = {file_path}")
        self.stdout.write(
            f"  in-sample anomaly    = {n_anom} / {len(fm)} "
            f"({n_anom / len(fm) * 100:.2f}%, "
            f"contamination 설정 {options['contamination']:.2%})"
        )
        self.stdout.write(
            f"  score range          = [{score.min():.4f}, {score.max():.4f}]"
        )
        self.stdout.write(f"  params               = {json.dumps(params, default=str)}")
