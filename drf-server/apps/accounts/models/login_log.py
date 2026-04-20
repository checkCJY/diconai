# accounts/models/login_log.py
from django.conf import settings
from django.db import models


class LoginLog(models.Model):
    """
    로그인/로그아웃 이력

    [APPEND-ONLY 정책]
    ⚠️ 이 테이블은 UPDATE/DELETE 금지 — 감사 로그 불변성
    save() / delete() 오버라이드로 앱 레벨 방어
    4차: PostgreSQL 트리거로 DB 레벨 방어 추가 예정

    [user CASCADE 금지]
    CustomUser는 DELETE 금지(Soft Delete)이므로 user CASCADE는 무의미.
    SET_NULL로 이력 보존.
    """

    class LoginResult(models.TextChoices):
        SUCCESS = "success", "성공"
        FAILED_PASSWORD = "failed_password", "비밀번호 오류"
        FAILED_LOCKED = "failed_locked", "계정 잠금"
        FAILED_INACTIVE = "failed_inactive", "비활성 계정"
        LOGOUT = "logout", "로그아웃"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="login_logs",
        verbose_name="사용자",
    )
    is_login = models.BooleanField(
        default=False, verbose_name="로그인 여부 (False=로그아웃)"
    )
    login_result = models.CharField(
        max_length=20, choices=LoginResult.choices, verbose_name="로그인 결과"
    )
    ip_address = models.GenericIPAddressField(
        null=True, blank=True, verbose_name="접속 IP"
    )
    user_agent = models.CharField(
        max_length=300, blank=True, default="", verbose_name="User-Agent"
    )
    session_key = models.CharField(
        max_length=40,
        blank=True,
        default="",
        verbose_name="세션 키 (로그인-로그아웃 쌍 매칭용)",
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        """기존 레코드 수정 차단"""
        if self.pk is not None:
            raise ValueError("LoginLog는 수정할 수 없습니다. APPEND-ONLY 정책.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """삭제 차단"""
        raise ValueError("LoginLog는 삭제할 수 없습니다. APPEND-ONLY 정책.")

    class Meta:
        db_table = "login_log"
        indexes = [
            models.Index(fields=["user", "-timestamp"], name="idx_login_user_time"),
            models.Index(fields=["ip_address", "-timestamp"], name="idx_login_ip_time"),
            models.Index(
                fields=["login_result", "-timestamp"], name="idx_login_result_time"
            ),
            models.Index(fields=["-timestamp"], name="idx_login_time"),
        ]
