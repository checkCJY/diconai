# accounts/models/user.py
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone
from datetime import timedelta

from apps.core.constants import UserType


class CustomUser(AbstractUser):
    """
    시스템 전체 로그인 계정

    [소프트 삭제 정책 — 전체 시스템 핵심 규칙]
    ⚠️ 계정은 절대 DELETE 금지 — 반드시 deactivate()로만 비활성화
    이유: AlarmRecord, EventLog, SystemLog 등 전체 모델이 CustomUser FK를
    SET_NULL로 보존하는 전략에 의존. 실제 DELETE 시 이 전략 전체가 무력화됨.

    [user_type 정책]
    SUPER_ADMIN    : 전체 공장 관리, facility=NULL 가능
    FACILITY_ADMIN : 소속 공장만 관리, facility 지정 필수
    WORKER         : 현장 작업자, facility 지정 필수
    VIEWER         : 읽기 전용 (외부 감사)

    [facility 정책]
    단일 공장 소속 — 다중 공장 순환 근무는 현재 미지원
    4차 이후: UserFacility M:N 중간 테이블 전환 예정
    """

    phone_validator = RegexValidator(
        regex=r"^\+?1?\d{9,15}$", message="전화번호 형식이 올바르지 않습니다."
    )

    name = models.CharField(
        max_length=30,
        blank=True,
        default="",
        verbose_name="실명",
    )
    user_type = models.CharField(
        max_length=20,
        choices=UserType.choices,
        default=UserType.WORKER,
        verbose_name="사용자 유형",
    )
    position = models.ForeignKey(
        "accounts.Position",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
        verbose_name="직급",
    )
    facility = models.ForeignKey(
        "facilities.Facility",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
        verbose_name="소속 공장",
    )
    phone = models.CharField(
        max_length=15,
        blank=True,
        default="",
        validators=[phone_validator],
        verbose_name="비상 연락처",
    )
    discord_id = models.CharField(
        max_length=32,
        blank=True,
        default="",
        verbose_name="Discord 사용자 ID",
        help_text="Discord 개인 멘션용 숫자 ID. 비어 있으면 멘션 대상 제외.",
    )

    # 보안 필드
    failed_login_count = models.PositiveSmallIntegerField(
        default=0, verbose_name="연속 로그인 실패 횟수"
    )
    account_locked_until = models.DateTimeField(
        null=True, blank=True, verbose_name="계정 잠금 해제 시각"
    )

    # Soft Delete 필드
    deactivated_at = models.DateTimeField(
        null=True, blank=True, verbose_name="비활성화 시각"
    )

    updated_at = models.DateTimeField(auto_now=True)

    @property
    def department(self):
        """주 소속 부서 반환. UserDepartment.is_primary=True 기준."""
        m = (
            self.dept_memberships.filter(is_primary=True)
            .select_related("department")
            .first()
        )
        return m.department if m else None

    @property
    def department_id(self):
        m = (
            self.dept_memberships.filter(is_primary=True)
            .values("department_id")
            .first()
        )
        return m["department_id"] if m else None

    @property
    def is_locked(self) -> bool:
        """계정 잠금 상태 여부"""
        return (
            self.account_locked_until is not None
            and self.account_locked_until > timezone.now()
        )

    def record_failed_login(self, max_attempts: int = 5, lockout_minutes: int = 30):
        """로그인 실패 카운터 증가. 임계치 초과 시 계정 잠금."""
        self.failed_login_count += 1
        if self.failed_login_count >= max_attempts:
            self.account_locked_until = timezone.now() + timedelta(
                minutes=lockout_minutes
            )
        self.save(
            update_fields=["failed_login_count", "account_locked_until", "updated_at"]
        )

    def reset_failed_login(self):
        """로그인 성공 시 실패 카운터 초기화."""
        self.failed_login_count = 0
        self.account_locked_until = None
        self.save(
            update_fields=["failed_login_count", "account_locked_until", "updated_at"]
        )

    def deactivate(self):
        """계정 비활성화 — 퇴직/탈퇴 처리의 유일한 방법."""
        self.is_active = False
        self.deactivated_at = timezone.now()
        self.save(update_fields=["is_active", "deactivated_at", "updated_at"])

    def delete(self, *args, **kwargs):
        """삭제 차단 — Soft Delete 강제."""
        raise ValueError("CustomUser는 삭제할 수 없습니다. deactivate()를 사용하세요.")

    class Meta:
        db_table = "custom_user"
        indexes = [
            models.Index(
                fields=["facility", "user_type", "is_active"],
                name="idx_user_facility_type_active",
            ),
            models.Index(
                fields=["user_type", "is_active"], name="idx_user_type_active"
            ),
        ]
        constraints = [
            # email partial unique — NULL이 아닌 경우만 중복 방지
            models.UniqueConstraint(
                fields=["email"],
                condition=models.Q(email__isnull=False) & ~models.Q(email=""),
                name="uq_user_email_notnull",
            )
        ]
