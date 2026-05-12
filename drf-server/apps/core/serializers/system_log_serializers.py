"""
core/serializers/system_log_serializers.py

사용자 활동 로그(SystemLog) 관리자 조회용 직렬화 담당.

흐름에서 이 파일의 위치:
  DB에서 꺼낸 SystemLog ORM 객체 → [이 파일] → JSON 응답

왜 core 앱에 두는가:
  SystemLog 모델이 core 앱 소속이다.
  사용자 활동 로그(user activity)와 지도 편집 로그(map edit)는
  둘 다 SystemLog 모델을 필터링해서 쓰므로 같은 시리얼라이저를 재사용한다.

actor_name을 SerializerMethodField로 만드는 이유:
  actor는 User FK(SET_NULL)라 탈퇴 시 NULL이 된다.
  NULL이면 "탈퇴한 관리자"로 대체해야 하는데,
  ModelSerializer의 기본 필드(actor_id)는 이 처리를 할 수 없다.
  메서드 필드로 NULL 분기를 명시적으로 처리한다.
"""

from rest_framework import serializers

from apps.core.models.system_log import SystemLog


class SystemLogAdminSerializer(serializers.ModelSerializer):
    """
    흐름 위치: SystemLogAdminListView / MapEditLogAdminListView
               → AdminPagination → [이 시리얼라이저] → JSON.

    사용자 활동 로그와 지도 편집 로그가 같은 시리얼라이저를 쓰는 이유:
      두 뷰 모두 SystemLog 모델을 읽는다.
      화면에서 보여주는 컬럼이 거의 동일하다.
      뷰에서 queryset을 다르게 필터링하면 되므로
      시리얼라이저를 나눌 이유가 없다.
    """

    # actor가 NULL(탈퇴 관리자)이면 "탈퇴한 관리자" 반환
    actor_name = serializers.SerializerMethodField()

    # TextChoices → 한글 display 값
    action_type_display = serializers.CharField(
        source="get_action_type_display", read_only=True
    )
    result_display = serializers.CharField(
        source="get_result_display", read_only=True
    )

    def get_actor_name(self, obj) -> str:
        """
        왜 get_full_name() → username → fallback 순서인가:
          get_full_name()이 비어있는 계정(성명 미입력)도 있으므로
          비어있으면 username(로그인 ID)으로 대체하고,
          actor 자체가 NULL이면 "탈퇴한 관리자" 표시.
        """
        if obj.actor is None:
            return "탈퇴한 관리자"
        full_name = obj.actor.get_full_name().strip()
        return full_name if full_name else obj.actor.username

    class Meta:
        model = SystemLog
        fields = [
            "id",
            "actor_name",        # 행위자 이름 (탈퇴 시 "탈퇴한 관리자")
            "action_type",       # 코드값 ("user_create" 등)
            "action_type_display",  # 한글 표시 ("사용자 생성")
            "target_model",      # 대상 모델 이름
            "target_id",         # 대상 레코드 ID
            "target_name",       # 대상 이름 스냅샷 (삭제 후에도 이름 복원 가능)
            "result",
            "result_display",    # "success" → "성공"
            "description",
            "ip_address",
            "created_at",
        ]
