from rest_framework import serializers
from apps.facilities.models import PowerDevice, PowerDeviceInspection


class PowerDeviceAdminListSerializer(serializers.ModelSerializer):
    power_id = serializers.SerializerMethodField()
    connection_status = serializers.SerializerMethodField()
    inspection_status = serializers.SerializerMethodField()
    latest_inspection_date = serializers.SerializerMethodField()
    department_name = serializers.SerializerMethodField()
    manager_name = serializers.SerializerMethodField()

    class Meta:
        model = PowerDevice
        fields = [
            "id",
            "power_id",
            "device_code",
            "device_id",
            "device_name",
            "department",
            "department_name",
            "manager",
            "manager_name",
            "ip_address",
            "port",
            "is_active",
            "status",
            "connection_status",
            "connection_checked_at",
            "connection_ok",
            "last_reading",
            "notes",
            "inspection_status",
            "latest_inspection_date",
        ]

    def get_power_id(self, obj):
        return obj.power_id

    def get_connection_status(self, obj):
        if not obj.is_active:
            return "inactive"
        if obj.status in ("offline", "error"):
            return "disconnected"
        return "normal"

    def get_inspection_status(self, obj):
        latest = obj.inspections.order_by("-inspection_date", "-created_at").first()
        if not latest:
            return "done"
        if latest.status == "action_needed" and not latest.is_actioned:
            return "needed"
        return "done"

    def get_latest_inspection_date(self, obj):
        latest = obj.inspections.order_by("-inspection_date", "-created_at").first()
        return latest.inspection_date if latest else None

    def get_department_name(self, obj):
        return obj.department.name if obj.department else None

    def get_manager_name(self, obj):
        if not obj.manager:
            return None
        return obj.manager.get_full_name().strip() or obj.manager.username


class PowerDeviceAdminWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = PowerDevice
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
            "status",
            "notes",
            "x",
            "y",
        ]

    def validate_device_code(self, value):
        instance = self.instance
        qs = PowerDevice.objects.filter(device_code=value)
        if instance:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists():
            raise serializers.ValidationError("이미 사용 중인 장비 코드입니다.")
        return value

    def validate_device_id(self, value):
        instance = self.instance
        qs = PowerDevice.objects.filter(device_id=value)
        if instance:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists():
            raise serializers.ValidationError("이미 등록된 장비 ID입니다.")
        return value


class PowerDeviceInspectionSerializer(serializers.ModelSerializer):
    inspector_name = serializers.SerializerMethodField()
    action_user_name = serializers.SerializerMethodField()

    class Meta:
        model = PowerDeviceInspection
        fields = [
            "id",
            "device",
            "inspection_type",
            "inspection_date",
            "inspector",
            "inspector_name",
            "status",
            "notes",
            "expected_action_date",
            "is_actioned",
            "action_date",
            "action_user",
            "action_user_name",
            "action_notes",
            "created_at",
        ]

    def get_inspector_name(self, obj):
        if not obj.inspector:
            return None
        return obj.inspector.get_full_name().strip() or obj.inspector.username

    def get_action_user_name(self, obj):
        if not obj.action_user:
            return None
        return obj.action_user.get_full_name().strip() or obj.action_user.username


class PowerDeviceInspectionWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = PowerDeviceInspection
        fields = [
            "device",
            "inspection_type",
            "inspection_date",
            "inspector",
            "status",
            "notes",
            "expected_action_date",
        ]


class PowerDeviceActionWriteSerializer(serializers.Serializer):
    action_notes = serializers.CharField()
    action_user = serializers.IntegerField(required=False, allow_null=True)
