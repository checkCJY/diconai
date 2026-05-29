"""reference/serializers/code_admin.py

공통 코드 관리 어드민 API 직렬화기.

[설계 원칙]
- 읽기용(Read) serializer: 응답 필드를 명시적으로 선언, count 같은 계산 필드 포함.
- 쓰기용(Write) serializer: 저장에 필요한 입력 필드만 노출, 검증 로직 포함.
"""

from rest_framework.serializers import (
    CharField,
    IntegerField,
    ModelSerializer,
    ValidationError,
)

from apps.reference.models.code_group import CodeGroup
from apps.reference.models.common_code import CommonCode


# ── CodeGroup ──────────────────────────────────────────────────────────────

class CodeGroupSerializer(ModelSerializer):
    """코드 그룹 읽기용 — 목록·상세 응답에 사용."""

    # 소속 코드 수 (사용 여부 무관 전체 카운트)
    code_count = IntegerField(source="codes.count", read_only=True)

    class Meta:
        model = CodeGroup
        fields = [
            "id",
            "code",
            "name",
            "scope",          # 관리범위
            "description",
            "is_active",
            "code_count",     # 사용 코드 수 (계산 필드)
            "updated_at",
        ]


class CodeGroupWriteSerializer(ModelSerializer):
    """코드 그룹 쓰기용 — 등록·수정 요청 본문 검증에 사용."""

    class Meta:
        model = CodeGroup
        fields = ["code", "name", "scope", "description", "is_active"]

    def validate_code(self, value):
        # 그룹 코드 형식: 대문자·숫자·언더스코어만 허용 (예: GAS_TYPE)
        import re
        if not re.fullmatch(r"[A-Z0-9_]+", value):
            raise ValidationError("대문자·숫자·언더스코어만 허용됩니다.")
        return value


# ── CommonCode ─────────────────────────────────────────────────────────────

class CommonCodeSerializer(ModelSerializer):
    """공통 코드 읽기용 — 목록·상세 응답에 사용."""

    # 소속 그룹 코드 문자열 (예: "GAS_TYPE") — JS 에서 표시용으로 사용
    group_code = CharField(source="group.code", read_only=True)

    class Meta:
        model = CommonCode
        fields = [
            "id",
            "group_code",     # 소속 그룹 코드 (읽기전용)
            "code",
            "name",
            "description",
            "sort_order",
            "is_active",
            "updated_at",
        ]


class CommonCodeWriteSerializer(ModelSerializer):
    """공통 코드 쓰기용 — 등록·수정 요청 본문 검증에 사용.

    group 은 URL 에서 받으므로 여기서는 선언하지 않음.
    (뷰에서 serializer.save(group=group) 으로 주입)
    """

    class Meta:
        model = CommonCode
        fields = ["code", "name", "description", "sort_order", "is_active"]

    def validate_code(self, value):
        # 코드 형식: 대문자·숫자·언더스코어만 허용 (예: CO, H2S)
        import re
        if not re.fullmatch(r"[A-Z0-9_]+", value):
            raise ValidationError("대문자·숫자·언더스코어만 허용됩니다.")
        return value
