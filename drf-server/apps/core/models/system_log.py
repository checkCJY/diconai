# core/models/system_log.py
from django.conf import settings
from django.db import models


class SystemLog(models.Model):
    """
    시스템 전체 감사 로그

    [APPEND-ONLY 정책]
    save() / delete() 오버라이드로 수정·삭제 차단
    4차에 PostgreSQL 트리거로 DB 레벨 강제 예정

    [action_type 확장 가능]
    v4 주요 action:
    - USER_CREATE / USER_DEACTIVATE
    - DEVICE_CREATE / DEVICE_DEACTIVATE / DEVICE_STATUS_CHANGE
    - GEOFENCE_CREATE / GEOFENCE_UPDATE / GEOFENCE_DEACTIVATE
    - THRESHOLD_UPDATE (4차)
    - PERMISSION_CHANGE
    - CHECKLIST_UPDATE
    - MANUAL_EVENT_ACTION

    [target 참조 방식]
    FK가 아닌 (target_model, target_id) 문자열 페어로 저장
    이유:
    - 여러 모델을 하나의 컬럼 구조로 표현 가능
    - 대상 모델이 삭제되어도 로그는 보존
    - FK의 무결성 검증 비용 제거

    [JSON 스키마 표준화]
    old_value, new_value는 JSONField이지만 action_type별 구조 표준화 필요
    4차 과제: 각 action_type별 스키마 문서화 + validator 추가

    [actor 정책]
    actor: SET_NULL — 관리자 탈퇴 후에도 이력 보존
    actor=NULL은 "탈퇴 관리자의 과거 행동" 또는 "시스템 자동 생성 로그"
    """

    class ActionType(models.TextChoices):
        # 사용자 관리
        USER_CREATE = "user_create", "사용자 생성"
        USER_DEACTIVATE = "user_deactivate", "사용자 비활성화"
        USER_UPDATE = "user_update", "사용자 정보 변경"
        PERMISSION_CHANGE = "permission_change", "권한 변경"

        # 장비 관리
        DEVICE_CREATE = "device_create", "장비 등록"
        DEVICE_DEACTIVATE = "device_deactivate", "장비 비활성화"
        DEVICE_STATUS_CHANGE = "device_status_change", "장비 상태 변경"

        # 구역 관리
        GEOFENCE_CREATE = "geofence_create", "구역 생성"
        GEOFENCE_UPDATE = "geofence_update", "구역 수정"
        GEOFENCE_DEACTIVATE = "geofence_deactivate", "구역 비활성화"

        # 임계치 관리 (4차)
        THRESHOLD_UPDATE = "threshold_update", "임계치 변경"

        # 체크리스트 관리
        CHECKLIST_UPDATE = "checklist_update", "체크리스트 변경"

        # 이벤트 관리 (수동)
        MANUAL_EVENT_ACTION = "manual_event_action", "이벤트 수동 조치"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="system_logs",
    )
    action_type = models.CharField(max_length=30, choices=ActionType.choices)
    target_model = models.CharField(
        max_length=50, blank=True, default="", verbose_name="대상 모델 이름"
    )
    target_id = models.CharField(
        max_length=50, blank=True, default="", verbose_name="대상 레코드 ID"
    )
    old_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    description = models.TextField(blank=True, default="")
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("SystemLog는 수정할 수 없습니다. APPEND-ONLY 정책.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("SystemLog는 삭제할 수 없습니다.")

    class Meta:
        db_table = "system_log"
        indexes = [
            models.Index(fields=["actor", "-created_at"], name="idx_syslog_actor_time"),
            models.Index(
                fields=["action_type", "-created_at"], name="idx_syslog_action_time"
            ),
            models.Index(
                fields=["target_model", "target_id", "-created_at"],
                name="idx_syslog_target_time",
            ),
            models.Index(fields=["-created_at"], name="idx_syslog_time"),
        ]
