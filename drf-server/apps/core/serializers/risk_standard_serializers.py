"""core/serializers/risk_standard_serializers.py

위험 기준 관리 어드민 API 시리얼라이저.
RiskLevelStandard 레코드는 fixture 시드 3개 고정(normal/warning/danger) — 생성·삭제 없음.
code 필드는 RiskLevel enum 과 1:1 매핑이므로 수정 불가(읽기 전용).
"""

from rest_framework import serializers

from apps.core.models.risk_level_standard import RiskLevelStandard


class RiskStandardListSerializer(serializers.ModelSerializer):
    """목록 및 상세 읽기 전용 시리얼라이저."""

    # "normal" → "정상" 등 AlertIntensity choices 한글 라벨
    alert_intensity_display = serializers.CharField(
        source="get_alert_intensity_display", read_only=True
    )

    class Meta:
        model = RiskLevelStandard
        fields = [
            "id",
            "code",               # 단계코드 (읽기 전용)
            "name",               # 단계명
            "display_color",      # 색상 토큰
            "alert_intensity",
            "alert_intensity_display",  # 알림강도 한글
            "event_priority",     # 우선순위
            "is_active",          # 사용여부
            "description",
            "updated_at",         # 최근수정일
        ]


class RiskStandardUpdateSerializer(serializers.ModelSerializer):
    """수정 전용 시리얼라이저 — code 필드 제외.

    code 는 RiskLevel enum 과 1:1 동기화 정책상 운영자 변경 금지.
    """

    class Meta:
        model = RiskLevelStandard
        fields = [
            "name",
            "display_color",
            "alert_intensity",
            "event_priority",
            "is_active",
            "description",
        ]
