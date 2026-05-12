"""
사용자 관리 어드민 시리얼라이저 — 등록/수정/상세/목록 4종.

[department vs facility 처리 비대칭]
- `department_id`: UserDepartment 중간 테이블에 (user, department, is_primary=True)
  row를 별도로 생성/갱신해야 하므로 명시 pop + 분기 처리.
- `facility_id`: CustomUser.facility 직접 FK라 `source="facility"`로 매핑하면
  DRF가 validated_data에 Facility 객체를 넣어줌. 그래도 가독성을 위해 명시 pop +
  setattr (department 패턴과 시각적 일관성).

[partial PATCH의 "키 누락 vs null"]
Update에서 `"facility" in validated_data` 플래그로 두 케이스를 구분:
- 키 누락 → 변경 없음 (기존 facility 유지)
- 키 명시(None 포함) → setattr로 적용 (None이면 비우기)
이 의미를 살리지 않으면 PATCH로 facility를 비울 방법이 사라진다.

[Detail의 SerializerMethodField 일관성]
`facility_id`도 SerializerMethodField로 통일 — department_id/position_id와 동일
패턴 유지를 위해. 단순 `IntegerField(read_only=True)`로도 동작하지만 다음 개발자가
혼란스럽지 않도록.
"""

import re

from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from apps.accounts.models import Department
from apps.facilities.models.facility import Facility

User = get_user_model()

_PWD_PATTERNS = [
    re.compile(r"[a-zA-Z]"),
    re.compile(r"[0-9]"),
    re.compile(r"[^a-zA-Z0-9]"),
]


class AccountsAdminListSerializer(serializers.ModelSerializer):
    """사용자 목록 조회용 (읽기 전용)"""

    department = serializers.SerializerMethodField()

    def get_department(self, obj):
        dept = obj.department  # property (UserDepartment is_primary=True)
        return dept.name if dept else None

    position = serializers.CharField(source="position.name", default=None)
    facility_name = serializers.CharField(
        source="facility.name", default=None, read_only=True
    )
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
            "facility_name",
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
    department_id = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.filter(is_active=True),
        required=False,
        allow_null=True,
    )
    facility_id = serializers.PrimaryKeyRelatedField(
        queryset=Facility.objects.filter(is_active=True),
        source="facility",
        required=False,
        allow_null=True,
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
        from apps.accounts.models.user_department import UserDepartment

        password = validated_data.pop("password")
        status = validated_data.pop("status")
        department = validated_data.pop("department_id", None)  # Department 객체
        # facility_id 필드는 source="facility"로 매핑되어 validated_data["facility"]에 Facility 객체로 들어옴.
        # 단순 FK라 junction 모델 없이 직접 setattr로 처리 (department와 다른 점).
        facility = validated_data.pop("facility", None)

        user = User(**validated_data)
        user.set_password(password)
        if facility is not None:
            user.facility = facility
        if status == "inactive":
            user.is_active = False
        user.save()

        if department:
            UserDepartment.objects.create(
                user=user, department=department, is_primary=True
            )

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
            "department_id",
            "facility_id",
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
    facility_id = serializers.SerializerMethodField()
    facility_name = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    def get_department_id(self, obj):
        return obj.department_id  # property

    def get_department_name(self, obj):
        dept = obj.department  # property
        return dept.name if dept else None

    def get_position_id(self, obj):
        return obj.position_id

    def get_position_name(self, obj):
        return obj.position.name if obj.position else None

    def get_facility_id(self, obj):
        return obj.facility_id

    def get_facility_name(self, obj):
        return obj.facility.name if obj.facility else None

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
            "facility_id",
            "facility_name",
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
    department_id = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.filter(is_active=True),
        required=False,
        allow_null=True,
    )
    facility_id = serializers.PrimaryKeyRelatedField(
        queryset=Facility.objects.filter(is_active=True),
        source="facility",
        required=False,
        allow_null=True,
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
        from apps.accounts.models.user_department import UserDepartment

        password = validated_data.pop("password", None)
        status_val = validated_data.pop("status", None)
        department = validated_data.pop("department_id", None)  # Department 객체
        # facility_id 필드는 source="facility"로 매핑됨. partial PATCH에서 "facility" 키가
        # 없으면 미변경, 있으면 (None 포함) 값으로 setattr — 이 동작이 비우기를 가능케 함.
        facility_provided = "facility" in validated_data
        facility = validated_data.pop("facility", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if facility_provided:
            instance.facility = facility

        if department is not None:
            UserDepartment.objects.update_or_create(
                user=instance,
                is_primary=True,
                defaults={"department": department},
            )

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
            "department_id",
            "facility_id",
            "position",
            "phone",
            "password",
            "status",
        ]
