import re

from django.contrib.auth import get_user_model
from rest_framework import serializers

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

    password = serializers.CharField(write_only=True, min_length=8, max_length=16)

    def validate_password(self, value):
        types = sum(bool(p.search(value)) for p in _PWD_PATTERNS)
        if types < 2:
            raise serializers.ValidationError(
                "8~16자의 영문, 숫자, 특수문자를 조합하여 입력해 주세요."
            )
        return value

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user

    class Meta:
        model = User
        fields = [
            "username",
            "password",
            "name",
            "department",
            "position",
            "user_type",
            "phone",
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
