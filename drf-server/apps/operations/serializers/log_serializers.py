"""
operations/serializers/log_serializers.py

시스템 로그(AppLog)와 연동 로그(IntegrationLog) 조회용 직렬화 담당.

흐름에서 이 파일의 위치:
  DB에서 꺼낸 ORM 객체 → [이 파일] → JSON 응답

로그는 읽기 전용이라 응답용 시리얼라이저만 존재한다.
등록/수정/삭제용 시리얼라이저가 없는 이유:
  - AppLog, IntegrationLog는 모두 APPEND-ONLY 모델이다.
  - 모델의 save()가 수정을 막고, delete()가 삭제를 막는다.
  - 관리자 화면에서도 조회만 허용한다.
"""

from rest_framework import serializers

from apps.operations.models.app_log import AppLog
from apps.operations.models.integration_log import IntegrationLog


class AppLogSerializer(serializers.ModelSerializer):
    """
    흐름 위치: SystemLogAdminListView → AdminPagination → [이 시리얼라이저] → JSON.
    역할: AppLog 1건을 JSON으로 변환.

    level_display를 추가하는 이유:
      - level은 DB에 "ERROR", "WARNING", "INFO" 같은 문자열로 저장된다.
      - AppLog.level은 TextChoices가 아닌 자유 문자열(CharField)이라
        get_level_display()가 없다.
      - 화면에서 색상 뱃지를 구분하려면 level 원본값이 필요하므로 그대로 내린다.

    log_category_display를 추가하는 이유:
      - log_category는 TextChoices("error"/"batch"/"service")라
        DB에는 코드값이 저장된다.
      - 화면에 "오류"/"배치"/"서비스"(한글)를 보여주려면 display값이 필요하다.
    """

    log_category_display = serializers.CharField(
        source="get_log_category_display", read_only=True
    )

    class Meta:
        model = AppLog
        fields = [
            "id",
            "log_category",
            "log_category_display",  # "error" → "오류"
            "service_module",        # 어느 서비스/모듈에서 발생했는지
            "level",                 # ERROR / WARNING / INFO
            "message",               # 로그 본문
            "extra",                 # 부가 정보 (JSON)
            "created_at",
        ]


class IntegrationLogAdminSerializer(serializers.ModelSerializer):
    """
    흐름 위치: IntegrationLogAdminListView → AdminPagination → [이 시리얼라이저] → JSON.
    역할: IntegrationLog 1건을 JSON으로 변환.

    기존 IntegrationLogCreateSerializer(입력용)와 이름이 다른 이유:
      - 기존 것은 FastAPI → DRF 연동 기록 생성(쓰기)용이다.
      - 이 시리얼라이저는 관리자 화면 조회(읽기)용이다.
      - 같은 이름을 쓰면 import할 때 어느 용도인지 구분이 안 된다.

    integration_type_display, result_display를 추가하는 이유:
      - 두 필드 모두 TextChoices라 DB에는 코드값("collect", "success")으로 저장된다.
      - 화면에서는 "수집", "성공" 같은 한글이 필요하다.
    """

    integration_type_display = serializers.CharField(
        source="get_integration_type_display", read_only=True
    )
    result_display = serializers.CharField(
        source="get_result_display", read_only=True
    )

    class Meta:
        model = IntegrationLog
        fields = [
            "id",
            "integration_type",
            "integration_type_display",  # "collect" → "수집"
            "target_system",             # 연동 대상 시스템
            "result",
            "result_display",            # "success" → "성공"
            "description",
            "extra",
            "created_at",
        ]
