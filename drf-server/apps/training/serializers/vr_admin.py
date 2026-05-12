"""
apps/training/serializers/vr_admin.py — VR 교육 어드민 입출력 변환.

[응답 키 정책 — Plan §4]
target_type은 화면 비노출. detail 응답에 포함하지 않는다.
facility_name / updated_by_name 은 평면화해서 함께 보낸다.
"""

from rest_framework import serializers

from apps.training.models import VRTrainingContent, VRTrainingRevision
from apps.training.validators import (
    validate_video_extension,
    validate_video_max_size,
    validate_video_mime,
)


class VRContentDetailSerializer(serializers.ModelSerializer):
    """VR 콘텐츠 단건 응답 직렬화 (read-only).

    [target_type 비노출]
    화면에서 적용 대상은 facility명으로만 표시하므로 target_type 필드는
    출력 fields에서 제외한다. service 레이어가 INSERT 시 기본값을 강제하므로
    응답에 노출할 필요 없음.

    [facility/updated_by 평면화]
    클라이언트가 별도 fetch 없이 facility명·수정자명을 바로 쓸 수 있도록
    SerializerMethodField로 1단계 평면화. 호출부는 `select_related`로 N+1
    회피.
    """

    facility_id = serializers.IntegerField(source="target_facility_id", read_only=True)
    facility_name = serializers.SerializerMethodField()
    updated_by_name = serializers.SerializerMethodField()

    class Meta:
        model = VRTrainingContent
        fields = [
            "id",
            "facility_id",
            "facility_name",
            "name",
            "description",
            "operation_note",
            "content_url",
            "duration_seconds",
            "is_active",
            "updated_at",
            "updated_by_name",
        ]
        read_only_fields = fields

    def get_facility_name(self, obj) -> str | None:
        """target_facility가 NULL이면 None — '전사 콘텐츠' 호환."""
        return obj.target_facility.name if obj.target_facility_id else None

    def get_updated_by_name(self, obj) -> str | None:
        """CustomUser의 `name` 우선, 없으면 username 폴백. updated_by 자체가
        NULL(탈퇴 사용자 등)이면 None.
        """
        user = obj.updated_by
        if user is None:
            return None
        return getattr(user, "name", None) or user.get_username()


class VRVideoUploadSerializer(serializers.Serializer):
    """multipart 영상 교체 요청의 입력 검증.

    [필드 정책]
    - file: 필수. validators.py의 세 검증(확장자/크기/MIME) 모두 통과해야 함.
    - name/description/operation_note: 모두 선택. 누락 시 기존 값을 유지하는
      PATCH 시맨틱을 service 레이어가 적용한다.

    [allow_blank 차이]
    name은 빈 문자열 비허용 — 빈 이름으로 덮어쓰는 사고 방지.
    description/operation_note는 빈 문자열 허용 — 운영자가 명시적으로 비울
    수 있도록.
    """

    file = serializers.FileField(
        validators=[
            validate_video_extension,
            validate_video_max_size,
            validate_video_mime,
        ]
    )
    name = serializers.CharField(max_length=200, required=False, allow_blank=False)
    description = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )
    operation_note = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )


class VRMetaUpdateSerializer(serializers.Serializer):
    """파일을 동반하지 않는 메타 수정 (PATCH).

    [최소 1개 요구]
    빈 body로 PATCH가 들어오면 service가 노옵 save를 수행하면서도 updated_at만
    움직여 감사 이력이 더러워지는 것을 막기 위해 검증 단계에서 차단.
    """

    name = serializers.CharField(max_length=200, required=False, allow_blank=False)
    description = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )
    operation_note = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )

    def validate(self, attrs):
        """수정 대상 필드가 적어도 1개는 와야 함."""
        if not attrs:
            raise serializers.ValidationError("수정할 필드가 없습니다.")
        return attrs


class VRRevisionListSerializer(serializers.ModelSerializer):
    """VR 교체 이력 read-only 응답.

    [UI 미사용 — 본 스코프]
    화면에서 이력 패널을 노출하지 않지만, 산재 감사 요건상 API는 완비해 둔다.
    추후 어드민에 [교체 이력] 모달이 추가되면 본 직렬화기를 그대로 사용.
    """

    replaced_by_name = serializers.SerializerMethodField()

    class Meta:
        model = VRTrainingRevision
        fields = [
            "id",
            "previous_name",
            "previous_url",
            "replaced_at",
            "replaced_by_name",
        ]
        read_only_fields = fields

    def get_replaced_by_name(self, obj) -> str | None:
        """교체자 이름 평면화. SET_NULL 정책으로 탈퇴자 row는 None."""
        user = obj.replaced_by
        if user is None:
            return None
        return getattr(user, "name", None) or user.get_username()
