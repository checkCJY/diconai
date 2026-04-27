import re

from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

User = get_user_model()

_PWD_PATTERNS = [
    re.compile(r"[a-zA-Z]"),
    re.compile(r"[0-9]"),
    re.compile(r"[^a-zA-Z0-9]"),
]


class AccountsAdminListSerializer(serializers.ModelSerializer):
    """사용자 목록 조회용 (읽기 전용)"""

    department = serializers.CharField(source="department.name", default=None)
    position = serializers.CharField(source="position.name", default=None)
    last_login_at = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    def get_last_login_at(self, obj):
        if obj.last_login:
            return obj.last_login.strftime("%Y-%m-%d %H:%M:%S")
        return None

    def get_status(self, obj):
        if not obj.is_active:
            return "inactive"
        if obj.is_locked:
            return "locked"
        return "active"

    class Meta:
        model = User
        fields = [
            "id",
            "name",
            "username",
            "department",
            "position",
            "user_type",
            "phone",
            "status",
            "last_login_at",
            "date_joined",
        ]


class AccountsAdminCreateSerializer(serializers.ModelSerializer):
    """사용자 등록용"""

    username = serializers.CharField(
        validators=[
            UniqueValidator(
                queryset=User.objects.all(),
                message="이미 사용 중인 아이디입니다.",
            )
        ]
    )
    password = serializers.CharField(write_only=True, min_length=8, max_length=20)
    status = serializers.ChoiceField(
        choices=["active", "locked", "inactive"],
        write_only=True,
        required=True,
    )

    def validate_password(self, value):
        if " " in value:
            raise serializers.ValidationError("비밀번호에는 공백을 입력할 수 없습니다.")
        types = sum(bool(p.search(value)) for p in _PWD_PATTERNS)
        if types < 2:
            raise serializers.ValidationError(
                "비밀번호는 영문, 숫자, 특수문자 중 2가지 이상을 포함해 주세요."
            )
        return value

    def create(self, validated_data):
        password = validated_data.pop("password")
        status = validated_data.pop("status")
        user = User(**validated_data)
        user.set_password(password)
        if status == "inactive":
            user.is_active = False
        user.save()
        if status == "locked":
            user.account_locked_until = timezone.now() + timedelta(days=36500)
            user.save(update_fields=["account_locked_until"])
        return user

    class Meta:
        model = User
        fields = [
            "username",
            "password",
            "name",
            "email",
            "department",
            "position",
            "user_type",
            "phone",
            "status",
        ]


class AccountsAdminDetailSerializer(serializers.ModelSerializer):
    """사용자 상세 조회용 — 수정 모달 pre-fill에 필요한 FK ID 포함"""

    department_id = serializers.SerializerMethodField()
    department_name = serializers.SerializerMethodField()
    position_id = serializers.SerializerMethodField()
    position_name = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    def get_department_id(self, obj):
        return obj.department_id

    def get_department_name(self, obj):
        return obj.department.name if obj.department else None

    def get_position_id(self, obj):
        return obj.position_id

    def get_position_name(self, obj):
        return obj.position.name if obj.position else None

    def get_status(self, obj):
        if not obj.is_active:
            return "inactive"
        if obj.is_locked:
            return "locked"
        return "active"

    class Meta:
        model = User
        fields = [
            "id",
            "name",
            "username",
            "email",
            "department_id",
            "department_name",
            "position_id",
            "position_name",
            "user_type",
            "phone",
            "status",
        ]


class AccountsAdminUpdateSerializer(serializers.ModelSerializer):
    """사용자 수정용"""

    password = serializers.CharField(
        write_only=True, required=False, min_length=8, max_length=20
    )
    status = serializers.ChoiceField(
        choices=["active", "locked", "inactive"],
        write_only=True,
        required=False,
    )

    def validate_password(self, value):
        if " " in value:
            raise serializers.ValidationError("비밀번호에는 공백을 입력할 수 없습니다.")
        types = sum(bool(p.search(value)) for p in _PWD_PATTERNS)
        if types < 2:
            raise serializers.ValidationError(
                "비밀번호는 영문, 숫자, 특수문자 중 2가지 이상을 포함해 주세요."
            )
        return value

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        status_val = validated_data.pop("status", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if password:
            instance.set_password(password)

        if status_val == "active":
            instance.is_active = True
            instance.account_locked_until = None
            instance.failed_login_count = 0
        elif status_val == "inactive":
            instance.is_active = False
            instance.deactivated_at = timezone.now()
        elif status_val == "locked":
            instance.is_active = True
            instance.account_locked_until = timezone.now() + timedelta(days=36500)

        instance.save()
        return instance

    class Meta:
        model = User
        fields = [
            "name",
            "email",
            "department",
            "position",
            "phone",
            "password",
            "status",
        ]
