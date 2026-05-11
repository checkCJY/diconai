from rest_framework import serializers
from apps.facilities.models import Facility, Equipment
from apps.facilities.models.devices import PowerDevice


# ── 기존 공장 API (map-editor 등 내부 사용) ───────────────────
class FacilityAdminListSerializer(serializers.ModelSerializer):
    facility_code = serializers.SerializerMethodField()
    power_devices = serializers.SerializerMethodField()
    manager_name = serializers.SerializerMethodField()

    def get_facility_code(self, obj):
        return f"FAC-{obj.id:03d}"

    def get_power_devices(self, obj):
        return list(
            obj.powerdevices.filter(is_active=True).values("device_id", "device_name")
        )

    def get_manager_name(self, obj):
        if obj.manager:
            full = obj.manager.get_full_name()
            return full if full else obj.manager.username
        return None

    class Meta:
        model = Facility
        fields = [
            "id",
            "facility_code",
            "name",
            "address",
            "power_devices",
            "manager",
            "manager_name",
            "notes",
            "is_active",
            "created_at",
        ]


class FacilityAdminWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Facility
        fields = ["name", "address", "manager", "notes", "is_active"]
        extra_kwargs = {
            "address": {"allow_blank": True},
            "manager": {"required": False, "allow_null": True},
            "is_active": {"required": False},
        }


# ── 공장 선택 드롭다운 ────────────────────────────────────────
class FacilitySelectSerializer(serializers.ModelSerializer):
    facility_code = serializers.SerializerMethodField()

    def get_facility_code(self, obj):
        return f"FAC-{obj.id:03d}"

    class Meta:
        model = Facility
        fields = ["id", "facility_code", "name"]


# ── 전력 장치 선택 드롭다운 (미연결 장치만) ────────────────────
class PowerDeviceSelectSerializer(serializers.ModelSerializer):
    class Meta:
        model = PowerDevice
        fields = ["id", "device_id", "device_name", "is_active"]


# ── 설비(Equipment) 관리 ──────────────────────────────────────
class EquipmentAdminListSerializer(serializers.ModelSerializer):
    equipment_code = serializers.SerializerMethodField()
    facility_code = serializers.SerializerMethodField()
    facility_name = serializers.CharField(source="facility.name", read_only=True)
    facility_address = serializers.CharField(source="facility.address", read_only=True)
    manager_name = serializers.SerializerMethodField()
    device_id = serializers.SerializerMethodField()
    device_name = serializers.SerializerMethodField()
    power_device_id = serializers.SerializerMethodField()

    def get_equipment_code(self, obj):
        return f"FAC-{obj.id:03d}"

    def get_facility_code(self, obj):
        return f"FAC-{obj.facility_id:03d}"

    def get_manager_name(self, obj):
        mgr = obj.facility.manager
        if mgr:
            full = mgr.get_full_name()
            return full if full else mgr.username
        return None

    def get_device_id(self, obj):
        return obj.power_device.device_id if obj.power_device else None

    def get_device_name(self, obj):
        return obj.power_device.device_name if obj.power_device else None

    def get_power_device_id(self, obj):
        return obj.power_device_id

    class Meta:
        model = Equipment
        fields = [
            "id",
            "equipment_code",
            "facility",
            "facility_code",
            "facility_name",
            "facility_address",
            "name",
            "notes",
            "manager_name",
            "device_id",
            "device_name",
            "power_device_id",
            "is_active",
            "created_at",
        ]


class EquipmentAdminWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Equipment
        fields = ["facility", "power_device", "name", "notes", "is_active"]
        extra_kwargs = {
            "power_device": {"required": False, "allow_null": True},
            "notes": {"required": False, "allow_blank": True},
            "is_active": {"required": False},
        }


# ── 기존 PowerDevice 관련 (하위 호환) ─────────────────────────
class PowerDeviceAdminListSerializer(serializers.ModelSerializer):
    facility_code = serializers.SerializerMethodField()
    facility_name = serializers.CharField(source="facility.name", read_only=True)
    facility_address = serializers.CharField(source="facility.address", read_only=True)
    manager_name = serializers.SerializerMethodField()

    def get_facility_code(self, obj):
        return f"FAC-{obj.facility_id:03d}"

    def get_manager_name(self, obj):
        mgr = obj.facility.manager
        if mgr:
            full = mgr.get_full_name()
            return full if full else mgr.username
        return None

    class Meta:
        model = PowerDevice
        fields = [
            "id",
            "facility",
            "facility_code",
            "facility_name",
            "facility_address",
            "device_id",
            "device_name",
            "manager_name",
            "is_active",
            "created_at",
        ]


class PowerDeviceAdminWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = PowerDevice
        fields = ["facility", "device_id", "device_name", "channel_count", "is_active"]
        extra_kwargs = {
            "channel_count": {"required": False},
            "is_active": {"required": False},
        }

    def create(self, validated_data):
        validated_data.setdefault("x", 0.0)
        validated_data.setdefault("y", 0.0)
        return super().create(validated_data)
