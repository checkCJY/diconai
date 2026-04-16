from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    """
    로그인 계정 모델
    user_type으로 관리자/작업자 화면 분기
    facility_id NULL 허용 — 슈퍼관리자 등 특정 공장 미소속 계정 고려
    """

    class UserType(models.TextChoices):
        ADMIN = "admin", "관리자"
        WORKER = "worker", "작업자"

    user_type = models.CharField(
        max_length=20, choices=UserType.choices, default=UserType.WORKER
    )
    facility = models.ForeignKey(
        "sensors.Facility",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
    )
    phone = models.CharField(max_length=15, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.username} ({self.user_type})"

    class Meta:
        db_table = "custom_user"


class LoginLog(models.Model):
    """
    보안 감사용 로그인 이력
    is_login=True: 로그인 / False: 로그아웃
    나머지 변경 이력은 SystemLog에서 관리
    """

    user = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="login_logs"
    )
    is_login = models.BooleanField(default=False)
    ip_address = models.CharField(max_length=100, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        action = "로그인" if self.is_login else "로그아웃"
        return f"{self.user.username} - {action} ({self.timestamp})"

    class Meta:
        db_table = "login_log"
        ordering = ["-timestamp"]
