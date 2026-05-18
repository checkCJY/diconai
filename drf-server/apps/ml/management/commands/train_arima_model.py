# apps/ml/management/commands/train_arima_model.py
"""
ARIMA 오프라인 학습 커맨드 — CO/H2S/CO2 각각 ARIMA 학습 + .pkl 저장.

사용 예:
    python manage.py train_arima_model \
        --sensor-id 1 \
        --gas-names co,h2s,co2 \
        --since 2026-05-06 \
        --until 2026-05-15

학습 결과:
- .pkl 파일: settings.ML_MODELS_DIR / "arima_{gas_name}.pkl"
"""

# 16 ~27 - ARIMA 라이브러리와 DB에서 가스 데이터 꺼내는 함수를 불러옵니다.
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import joblib
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime
from statsmodels.tsa.arima.model import ARIMA

from apps.ml.services.dataset_service import extract_normal_gas_series


# --since 2026-05-06 같은 날짜 문자열을 파이썬 datetime 객체로 변환합니다. train_anomaly_model.py에 있던 것과 동일합니다.
def _parse_dt(s: str) -> datetime:
    dt = parse_datetime(s)
    if dt is None:
        dt = datetime.strptime(s, "%Y-%m-%d")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class Command(BaseCommand):
    help = "가스별 ARIMA 모델 학습 + .pkl 저장"

    def add_arguments(self, parser):
        # 이 함수는 명령어 실행 시 받을 인자들을 정의하는 곳.
        parser.add_argument(
            "--sensor-id", type=int, required=True, help="GasSensor.id"
        )  # 센서 PK
        # 가스 센서 DB PK를 받습니다. 정수(type=int), 필수(required=True).
        parser.add_argument(
            "--gas-names",  # co,h2s,co2
            required=True,
            help="학습할 가스 종류 (콤마 구분). 예: co,h2s,co2",
        )
        # 학습할 가스 종류를 콤마로 받습니다. 필수
        parser.add_argument(
            "--since", required=True, help="ISO 또는 YYYY-MM-DD"
        )  # 학습 시작 날짜
        parser.add_argument(
            "--until", required=True, help="ISO 또는 YYYY-MM-DD"
        )  # 학습 끝 날짜
        # 학습 데이터 날짜 범위입니다. 둘 다 필수.
        parser.add_argument(
            "--p", type=int, default=1, help="ARIMA p (자기회귀 차수)"
        )  # ARIMA p
        parser.add_argument(
            "--d", type=int, default=1, help="ARIMA d (차분 차수)"
        )  # ARIMA d
        parser.add_argument(
            "--q", type=int, default=1, help="ARIMA q (이동평균 차수)"
        )  # ARIMA q

    def handle(self, *args, **options):
        _VALID = {"co", "h2s", "co2", "o2", "no2", "so2", "o3", "nh3", "voc"}
        # "co,h2s,co2" → ["co", "h2s", "co2"] 로 분리합니다
        gas_names = [g.strip() for g in options["gas_names"].split(",")]  #
        invalid = [g for g in gas_names if g not in _VALID]
        if invalid:
            raise CommandError(f"알 수 없는 gas_name: {invalid}")

        since = _parse_dt(options["since"])
        until = _parse_dt(options["until"])
        order = (options["p"], options["d"], options["q"])
        models_dir = Path(settings.ML_MODELS_DIR)
        models_dir.mkdir(parents=True, exist_ok=True, mode=0o755)

        for gas_name in gas_names:
            self.stdout.write(f"[{gas_name}] 데이터 추출 중...")
            series = extract_normal_gas_series(  # DB에서 정상 데이터 꺼냄
                sensor_id=options["sensor_id"],
                gas_name=gas_name,
                since=since,
                until=until,
            )
            if len(series) < 50:
                raise CommandError(
                    f"[{gas_name}] 데이터 부족: {len(series)}개 (최소 50개)"
                )

            self.stdout.write(
                f"[{gas_name}] {len(series)}개 데이터로 ARIMA{order} 학습 중..."
            )
            # 이성현 추가 — 데이터가 많으면 학습 시간이 오래 걸리므로 최근 3000개만 사용
            values = series.values[-3000:].tolist()  # 최근 3000개만 사용
            model = ARIMA(values, order=order)  # ARIMA 모델 생성
            result = model.fit()  # 학습

            file_path = models_dir / f"arima_{gas_name}.pkl"
            joblib.dump({"result": result, "order": order}, file_path)  # pkl 저장
            # 저장되는 파일:
            # ml_models/arima_co.pkl
            # ml_models/arima_h2s.pkl
            # ml_models/arima_co2.pkl
            self.stdout.write(
                self.style.SUCCESS(f"[{gas_name}] 저장 완료 → {file_path}")
            )

        self.stdout.write(self.style.SUCCESS("전체 ARIMA 학습 완료"))
