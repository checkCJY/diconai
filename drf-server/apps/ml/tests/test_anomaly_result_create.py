"""POST /api/ml/anomaly-results/ 통합 테스트 (T1-3)."""

import pytest
from rest_framework.test import APIClient

from apps.ml.models import MLAnomalyResult


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def valid_payload():
    return {
        "ml_model": None,
        "model_version_snapshot": 3,
        "sensor_type": "power",
        "sensor_identifier": "power:device_1:ch1:watt",
        "measured_at": "2026-05-13T10:00:00Z",
        "anomaly_score": -0.05,
        "prediction": "anomaly",
        "risk_classified": "predict_warn",
        "feature_snapshot_json": {
            "value": 8200,
            "roll_mean": 4500,
            "roll_std": 50,
            "diff": 100,
        },
    }


@pytest.mark.django_db
def test_create_anomaly_result_success(api_client, valid_payload):
    response = api_client.post("/api/ml/anomaly-results/", valid_payload, format="json")
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["sensor_identifier"] == "power:device_1:ch1:watt"
    assert body["prediction"] == "anomaly"
    assert body["risk_classified"] == "predict_warn"

    row = MLAnomalyResult.objects.get(id=body["id"])
    assert row.anomaly_score == -0.05
    assert row.feature_snapshot_json == valid_payload["feature_snapshot_json"]


@pytest.mark.django_db
def test_create_anomaly_result_missing_required_field(api_client, valid_payload):
    valid_payload.pop("sensor_identifier")
    response = api_client.post("/api/ml/anomaly-results/", valid_payload, format="json")
    assert response.status_code == 400
    # 프로젝트 전역 exception handler 가 error.details 로 wrapping
    assert "sensor_identifier" in response.json()["error"]["details"]


@pytest.mark.django_db
def test_create_anomaly_result_invalid_prediction_enum(api_client, valid_payload):
    valid_payload["prediction"] = "invalid_value"
    response = api_client.post("/api/ml/anomaly-results/", valid_payload, format="json")
    assert response.status_code == 400
    assert "prediction" in response.json()["error"]["details"]


@pytest.mark.django_db
def test_create_anomaly_result_invalid_risk_classified(api_client, valid_payload):
    valid_payload["risk_classified"] = "warning"  # RiskClassified 에 없는 값
    response = api_client.post("/api/ml/anomaly-results/", valid_payload, format="json")
    assert response.status_code == 400
    assert "risk_classified" in response.json()["error"]["details"]
