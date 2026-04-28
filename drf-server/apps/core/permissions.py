# core/permissions.py — 시스템 공통 DRF 퍼미션 클래스
#
# 역할 계층 (UserType 기준):
#   super_admin > facility_admin > worker > viewer
#
# 사용법:
#   permission_classes = [IsAuthenticated, IsSuperAdmin]
#   permission_classes = [IsAuthenticated, IsSuperAdminOrFacilityAdmin]

from rest_framework.permissions import BasePermission

from apps.core.constants import UserType


class IsSuperAdmin(BasePermission):
    """슈퍼관리자(super_admin)만 허용."""

    message = "슈퍼관리자 권한이 필요합니다."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.user_type == UserType.SUPER_ADMIN
        )


class IsSuperAdminOrFacilityAdmin(BasePermission):
    """슈퍼관리자 또는 시설관리자(facility_admin)만 허용."""

    message = "관리자 이상의 권한이 필요합니다."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.user_type
            in (
                UserType.SUPER_ADMIN,
                UserType.FACILITY_ADMIN,
            )
        )
