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


class AccountsAdminUpdateSerializer(serializers.ModelSerializer):
    """사용자 수정용 (비밀번호 제외)"""

    class Meta:
        model = User
        fields = [
            "name",
            "department",
            "position",
            "user_type",
            "phone",
        ]
