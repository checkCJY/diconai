import re

from django.contrib.auth import authenticate, get_user_model
from rest_framework import serializers

User = get_user_model()

_PWD_PATTERNS = [
    re.compile(r"[a-zA-Z]"),
    re.compile(r"[0-9]"),
    re.compile(r"[^a-zA-Z0-9]"),
]


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(
        write_only=True,
        max_length=100,
        error_messages={"max_length": "비밀번호는 100자 이하로 입력해주세요."},
    )

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
        User = get_user_model()
        username = attrs["username"]

        # 사용자 존재 여부 조회 (잠금/비활성 상태 판별용)
        try:
            user_obj = User.objects.get(username=username)
        except User.DoesNotExist:
            user_obj = None

        # 계정 잠금 확인
        if user_obj and user_obj.is_locked:
            self._login_failure = "failed_locked"
            raise serializers.ValidationError(
                "계정이 잠겼습니다. 잠시 후 다시 시도해주세요."
            )

        # 비활성 계정 확인
        if user_obj and not user_obj.is_active:
            self._login_failure = "failed_inactive"
            raise serializers.ValidationError("비활성화된 계정입니다.")

        # 인증 시도
        user = authenticate(
            request=self.context.get("request"),
            username=username,
            password=attrs["password"],
        )

        if not user:
            # 실패 횟수 누적 — 임계치(5회) 도달 시 자동 잠금
            if user_obj:
                user_obj.record_failed_login()
            self._login_failure = "failed_password"
            raise serializers.ValidationError(
                "아이디 또는 비밀번호가 올바르지 않습니다."
            )

        # 로그인 성공 — 실패 카운터 초기화
        user.reset_failed_login()
        attrs["user"] = user
        return attrs


class MyProfileSerializer(serializers.ModelSerializer):
    department = serializers.SerializerMethodField()

    def get_department(self, obj):
        dept = obj.department  # property
        return dept.name if dept else None

    position = serializers.CharField(source="position.name", default=None)
    facility = serializers.CharField(source="facility.name", default=None)

    class Meta:
        model = User
        fields = [
            "name",
            "username",
            "email",
            "phone",
            "facility",
            "department",
            "position",
        ]


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8, max_length=16)
    new_password_confirm = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        types = sum(bool(p.search(value)) for p in _PWD_PATTERNS)
        if types < 2:
            raise serializers.ValidationError(
                "8~16자의 영문, 숫자, 특수문자를 조합하여 입력해 주세요."
            )
        return value

    def validate(self, attrs):
        user = self.context["request"].user
        if not user.check_password(attrs["current_password"]):
            raise serializers.ValidationError(
                {
                    "current_password": "현재 비밀번호가 일치하지 않습니다. 다시 확인해 주세요."
                }
            )
        if attrs["new_password"] == attrs["current_password"]:
            raise serializers.ValidationError(
                {
                    "new_password": "현재 사용 중인 비밀번호는 신규 비밀번호로 사용할 수 없습니다."
                }
            )
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": "입력하신 신규 비밀번호와 일치하지 않습니다."}
            )
        return attrs
