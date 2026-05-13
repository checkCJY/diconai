"""
run_anomaly_e2e — IF 추론 → 알람 발화 vertical slice (PoC)

[목적]
T1 본격 분리 (Celery, rate limit, 추론 트리거 자동화) 전에 e2e 동작 확인.
한 번 실행하면 추론 → MLAnomalyResult 저장 → risk_classified 분류 → 발화 시 화면에
ANOMALY 알람 표시까지 동기로 처리.

[흐름]
1. PowerData 최근 N(window) 틱 추출
2. fastapi /ai/predict 호출 → anomaly_score, prediction
3. evaluate_power_risk(value, channel, device_id) → threshold_risk
4. combine_risk(threshold_risk, prediction) → risk_classified
5. MLAnomalyResult ORM 저장
6. risk_classified ∈ {CAUTION, PREDICT_WARN, DANGER} 발화:
   - create_alarm_and_event(alarm_type=ANOMALY, power_device, ...)
   - _push_to_ws(alarm_data)
7. 결과 출력

[PoC 단순화 — 정식화는 T1-4~T1-6]
- Celery 우회, 동기 실행
- rate limit 없음 — 매 호출 시 발화
- dedupe 없음
- combined → risk_level 매핑 단순 (CAUTION/PREDICT_WARN → WARNING, DANGER → DANGER)

[실행]
    docker exec diconai-drf-1 python manage.py run_anomaly_e2e \\
        --device-id 1 --channel 1 --data-type watt
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.alerts.tasks import _push_to_ws
from apps.core.constants import AlarmType, RiskLevel
from apps.facilities.models import PowerDevice
from apps.facilities.services.threshold_service import evaluate_power_risk
from apps.ml.models import MLAnomalyResult, MLModel
from apps.ml.services.risk_combine_service import combine_risk
from apps.monitoring.models import PowerData


_RC = MLAnomalyResult.RiskClassified
_FIRE_LEVELS = {_RC.CAUTION, _RC.PREDICT_WARN, _RC.DANGER}

# combined_risk → AlarmRecord.risk_level 매핑 (PoC 단순)
_COMBINED_TO_RISK = {
    _RC.NORMAL: RiskLevel.NORMAL,
    _RC.CAUTION: RiskLevel.WARNING,
    _RC.PREDICT_WARN: RiskLevel.WARNING,
    _RC.DANGER: RiskLevel.DANGER,
}


class Command(BaseCommand):
    help = "IF 추론 → 알람 발화 e2e PoC (T1-4~T1-6 분리 전 동작 확인용)"

    def add_arguments(self, parser):
        parser.add_argument("--device-id", type=int, default=1)
        parser.add_argument("--channel", type=int, default=1)
        parser.add_argument(
            "--data-type", choices=("current", "voltage", "watt"), default="watt"
        )
        parser.add_argument(
            "--use-latest-anomaly",
            action="store_true",
            help="가장 최근 anomaly 라벨 시점 기준 window — anomaly 케이스 e2e 검증용",
        )

    def handle(self, *args, **opts):
        import httpx

        device_id = opts["device_id"]
        channel = opts["channel"]
        data_type = opts["data_type"]
        sensor_identifier = f"power:device_{device_id}:ch{channel}:{data_type}"

        device = PowerDevice.objects.filter(id=device_id).first()
        if device is None:
            raise CommandError(f"PowerDevice id={device_id} 없음")

        # 1. 최근 N(window) 틱 — 일단 active 모델의 window 가져오기
        active_model = MLModel.objects.filter(
            sensor_type="power", is_active=True
        ).first()
        if active_model is None:
            raise CommandError("active power MLModel 없음 — 먼저 train_anomaly_model")
        window = active_model.params_json.get("window", 30)

        # 기준 timestamp — 최신 또는 가장 최근 anomaly 시점
        base_qs = (
            PowerData.objects.filter(
                power_device_id=device_id, channel=channel, data_type=data_type
            )
            .exclude(value__isnull=True)
            .exclude(value__lt=0)
        )

        if opts["use_latest_anomaly"]:
            anomaly_row = (
                base_qs.filter(is_anomaly=True).order_by("-measured_at").first()
            )
            if anomaly_row is None:
                raise CommandError("anomaly 라벨된 데이터 없음")
            cutoff = anomaly_row.measured_at
            self.stdout.write(
                f"[0/6] anomaly 시점 사용 — {cutoff} ({anomaly_row.anomaly_type})"
            )
            rows = list(
                base_qs.filter(measured_at__lte=cutoff).order_by("-measured_at")[
                    :window
                ]
            )
        else:
            rows = list(base_qs.order_by("-measured_at")[:window])

        if len(rows) < window:
            raise CommandError(
                f"표본 부족: {len(rows)} < window {window}. backfill 또는 더미 가동 필요"
            )
        rows.reverse()  # 오래된 → 최신
        window_values = [r.value for r in rows]
        latest = rows[-1]

        self.stdout.write(
            f"[1/6] window {window} 틱 추출 OK — last={latest.value} @ {latest.measured_at}"
        )

        # 2. fastapi /predict
        fastapi_url = "http://fastapi:8001/ai/predict"
        resp = httpx.post(
            fastapi_url,
            json={
                "sensor_type": "power",
                "sensor_identifier": sensor_identifier,
                "window_values": window_values,
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        pred = resp.json()
        self.stdout.write(
            f"[2/6] /ai/predict OK — anomaly_score={pred['anomaly_score']:.4f} "
            f"prediction={pred['prediction']} (model v{pred['model_version']})"
        )

        # 3. threshold_risk
        threshold_risk = evaluate_power_risk(
            latest.value, channel=channel, device_id=device_id
        )
        self.stdout.write(f"[3/6] threshold_risk = {threshold_risk}")

        # 4. combine_risk
        risk_classified = combine_risk(threshold_risk, pred["prediction"])
        self.stdout.write(f"[4/6] risk_classified = {risk_classified}")

        # 5. MLAnomalyResult 저장
        anomaly_row = MLAnomalyResult.objects.create(
            ml_model=active_model,
            model_version_snapshot=active_model.version,
            sensor_type="power",
            sensor_identifier=sensor_identifier,
            measured_at=latest.measured_at,
            anomaly_score=pred["anomaly_score"],
            prediction=pred["prediction"],
            risk_classified=risk_classified,
            feature_snapshot_json=pred["features"],
        )
        self.stdout.write(f"[5/6] MLAnomalyResult id={anomaly_row.id} saved")

        # 6. 발화
        if risk_classified not in _FIRE_LEVELS:
            self.stdout.write(
                self.style.SUCCESS(f"[6/6] {risk_classified} — 발화 안 함 (정상 범위)")
            )
            return

        from apps.alerts.services.event_service import create_alarm_and_event

        risk_level = _COMBINED_TO_RISK[risk_classified]
        summary = (
            f"[AI 이상 패턴] {device.device_name} ch{channel} {data_type}={latest.value} "
            f"(IF score {pred['anomaly_score']:.4f}, combined={risk_classified})"
        )
        event, alarm = create_alarm_and_event(
            facility_id=device.facility_id,
            alarm_type=AlarmType.ANOMALY,
            power_device_id=device_id,
            measured_value=latest.value,
            threshold_value=None,
            risk_level=risk_level,
            source_label=f"{device.device_name} ch{channel}",
            summary=summary,
            detected_at=timezone.now(),
        )

        if alarm is None:
            # 쿨다운/dedupe — 같은 Event 안에 알람 안 추가됨
            self.stdout.write(
                self.style.WARNING(
                    f"[6/6] alarm=None (쿨다운/dedupe). Event id={event.id} 만 갱신, "
                    "WS 푸시 skip"
                )
            )
            return

        # PoC: AlarmPayload schema (fastapi internal/alarm_router.py) 필수 필드 충족.
        # combined_risk/anomaly_score 등 ANOMALY 고유 필드는 schema 미정의로 무시됨 (extra=ignore).
        # T1-7 에서 AlarmPayload schema 확장으로 정식 노출 예정.
        alarm_data = {
            "alarm_type": AlarmType.ANOMALY,
            "risk_level": risk_level,
            "source_label": f"{device.device_name} ch{channel}",
            "summary": summary,
            "is_new_event": event is not None,
            "event_id": event.id if event else None,
            "measured_value": latest.value,
        }
        _push_to_ws(alarm_data, raise_on_failure=False)
        self.stdout.write(
            self.style.SUCCESS(
                f"[6/6] 발화 완료 — AlarmRecord id={alarm.id}, "
                f"Event id={event.id if event else 'None'}, WS 푸시 OK"
            )
        )
