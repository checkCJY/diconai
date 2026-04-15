from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    """
    AbstractUser가 ["username", "password", "email", "is_active] 모두제공
    확장 필드에 관해서는 UserProfile 모델 확인
    """

    pass


class UserProfile(models.Model):
    """
    ─── UserProfile (1:1 연결) ───
    user              = CustomUser OneToOne FK
    name              = 이름
    department        = 부서명
    position          = 직책
    phone             = 연락처
    role              = 역할 (admin / manager / worker) choices
    login_fail_count  = 로그인 실패 횟수
    is_locked         = 계정 잠금 여부
    created_at        = 생성일시 (auto)
    updated_at        = 수정일시 (auto)
    """

    class Role(models.TextChoices):
        SUPERUSER = "superuser", "슈퍼관리자"
        STAFF = "staff", "관리자"
        USER = "user", "일반사용자"

    user = models.OneToOneField(
        CustomUser, on_delete=models.CASCADE, related_name="profile"
    )
    name = models.CharField(max_length=50)
    department = models.CharField(max_length=100, blank=True)
    position = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    role = models.CharField(max_length=30, choices=Role.choices, default=Role.USER)
    login_fail_count = models.PositiveSmallIntegerField(default=0)
    is_locked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.user.username})"


class LoginLog(models.Model):
    """
    ─── LoginLog (보안 감사용) ───
    user              = CustomUser FK
    action            = login / logout choices
    timestamp         = 발생일시 (auto)
    """

    class Action(models.TextChoices):
        LOGIN = "login", "로그인"
        LOGOUT = "logout", "로그아웃"

    user = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="login_logs"
    )
    action = models.CharField(max_length=10, choices=Action.choices)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.user.username} - {self.action} ({self.timestamp})"
