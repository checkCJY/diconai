from rest_framework import serializers

from apps.facilities.models import GasSensor, GasSensorInspection


class GasSensorAdminListSerializer(serializers.ModelSerializer):
    sensor_id = serializers.SerializerMethodField()
    facility_name = serializers.CharField(source="facility.name", read_only=True)
    department_name = serializers.SerializerMethodField()
    manager_name = serializers.SerializerMethodField()
    connection_status = serializers.SerializerMethodField()
    inspection_status = serializers.SerializerMethodField()
    latest_inspection_date = serializers.SerializerMethodField()

    def get_sensor_id(self, obj):
        return obj.sensor_id

    def get_department_name(self, obj):
        return obj.department.name if obj.department else None

    def get_manager_name(self, obj):
        if obj.manager:
            full = obj.manager.get_full_name()
            return full if full.strip() else obj.manager.username
        return None

    def get_connection_status(self, obj):
        if not obj.is_active:
            return "inactive"
        if obj.status in ("offline", "error"):
            return "disconnected"
        return "normal"

    def get_inspection_status(self, obj):
        latest = obj.inspections.order_by("-inspection_date", "-created_at").first()
        if not latest:
            return "needed"
        if latest.status == "action_needed" and not latest.is_actioned:
            return "needed"
        return "done"

    def get_latest_inspection_date(self, obj):
        latest = (
            obj.inspections.order_by("-inspection_date")
            .values("inspection_date")
            .first()
        )
        return latest["inspection_date"] if latest else None

    class Meta:
        model = GasSensor
        fields = [
            "id",
            "sensor_id",
            "device_code",
            "device_id",
            "device_name",
            "facility",
            "facility_name",
            "department",
            "department_name",
            "manager",
            "manager_name",
            "ip_address",
            "port",
            "connection_checked_at",
            "connection_ok",
            "connection_status",
            "status",
            "last_reading",
            "is_active",
            "notes",
            "inspection_status",
            "latest_inspection_date",
            "created_at",
        ]


class GasSensorAdminWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = GasSensor
        fields = [
            "facility",
            "device_code",
            "device_id",
            "device_name",
            "department",
            "manager",
            "ip_address",
            "port",
            "connection_checked_at",
            "connection_ok",
            "is_active",
            "notes",
            "x",
            "y",
        ]
        extra_kwargs = {
            "department": {"required": False, "allow_null": True},
            "manager": {"required": False, "allow_null": True},
            "ip_address": {"required": False, "allow_blank": True},
            "port": {"required": False, "allow_null": True},
            "connection_checked_at": {"required": False, "allow_null": True},
            "connection_ok": {"required": False, "allow_null": True},
            "notes": {"required": False, "allow_blank": True},
            "x": {"required": False},
            "y": {"required": False},
            "device_code": {"required": False, "allow_blank": True},
        }

    def validate_device_id(self, value):
        qs = GasSensor.objects.filter(device_id=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("이미 등록된 장비 ID입니다.")
        return value

    def create(self, validated_data):
        validated_data.setdefault("x", 0.0)
        validated_data.setdefault("y", 0.0)
        return super().create(validated_data)


class GasSensorInspectionSerializer(serializers.ModelSerializer):
    inspection_type_display = serializers.CharField(
        source="get_inspection_type_display", read_only=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    inspector_name = serializers.SerializerMethodField()
    action_user_name = serializers.SerializerMethodField()

    def get_inspector_name(self, obj):
        if obj.inspector:
            full = obj.inspector.get_full_name()
            return full.strip() or obj.inspector.username
        return None

    def get_action_user_name(self, obj):
        if obj.action_user:
            full = obj.action_user.get_full_name()
            return full.strip() or obj.action_user.username
        return None

    class Meta:
        model = GasSensorInspection
        fields = [
            "id",
            "sensor",
            "inspection_type",
            "inspection_type_display",
            "inspection_date",
            "inspector",
            "inspector_name",
            "status",
            "status_display",
            "notes",
            "expected_action_date",
            "is_actioned",
            "action_date",
            "action_user",
            "action_user_name",
            "action_notes",
            "created_at",
        ]


class GasSensorInspectionWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = GasSensorInspection
        fields = [
            "sensor",
            "inspection_type",
            "inspection_date",
            "inspector",
            "status",
            "notes",
            "expected_action_date",
        ]
        extra_kwargs = {
            "inspection_date": {"required": False},
            "inspector": {"required": False, "allow_null": True},
            "expected_action_date": {"required": False, "allow_null": True},
        }

    def validate(self, data):
        status = data.get("status", "")
        expected = data.get("expected_action_date")
        if (
            status == GasSensorInspection.InspectionStatus.ACTION_NEEDED
            and not expected
        ):
            raise serializers.ValidationError(
                {"expected_action_date": "예상 조치일을 입력해 주세요."}
            )
        if expected and data.get("inspection_date"):
            if expected < data["inspection_date"]:
                raise serializers.ValidationError(
                    {
                        "expected_action_date": "예상 조치일은 점검일과 같거나 이후 날짜로 입력해주세요."
                    }
                )
        return data


class GasSensorActionWriteSerializer(serializers.Serializer):
    action_notes = serializers.CharField()
    action_user = serializers.IntegerField(required=False, allow_null=True)
