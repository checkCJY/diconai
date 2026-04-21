import re

from django.contrib.auth import authenticate
from rest_framework import serializers

_PWD_PATTERNS = [
    re.compile(r"[a-zA-Z]"),
    re.compile(r"[0-9]"),
    re.compile(r"[^a-zA-Z0-9]"),
]


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate_username(self, value):
        if not re.fullmatch(r"[a-zA-Z0-9]+", value):
            raise serializers.ValidationError(
                "아이디는 영문 또는 숫자만 입력할 수 있습니다."
            )
        if not (4 <= len(value) <= 20):
            raise serializers.ValidationError("아이디를 4~20자로 입력해주세요.")
        return value

    def validate_password(self, value):
        if len(value) < 8:
            raise serializers.ValidationError("비밀번호를 8자 이상 입력해야 합니다.")
        types = sum(bool(p.search(value)) for p in _PWD_PATTERNS)
        if types < 2:
            raise serializers.ValidationError(
                "비밀번호는 영문, 숫자, 특수문자 중 2가지 이상을 포함해야 합니다."
            )
        return value

    def validate(self, attrs):
        user = authenticate(
            request=self.context.get("request"),
            username=attrs["username"],
            password=attrs["password"],
        )
        if not user:
            raise serializers.ValidationError(
                "아이디 또는 비밀번호가 올바르지 않습니다."
            )
        attrs["user"] = user
        return attrs
