# apps/positioning/serializers/serializers.py
from rest_framework import serializers


class WorkerPositionReceiveSerializer(serializers.Serializer):
    """FastAPI로부터 작업자 위치 데이터 수신용 Serializer.

    node_id 는 PositionNode.device_id 그대로 (예: "NODE-001"). 미수신/미상 row는
    None 허용.
    """

    worker_id = serializers.IntegerField()
    facility_id = serializers.IntegerField()
    x = serializers.FloatField(min_value=0)
    y = serializers.FloatField(min_value=0)
    movement_status = serializers.ChoiceField(
        choices=["moving", "stationary", "idle"], default="moving"
    )
    measured_at = serializers.DateTimeField()
    node_id = serializers.CharField(
        required=False, allow_null=True, allow_blank=True, max_length=50
    )
