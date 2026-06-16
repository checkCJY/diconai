"""계정 로그인 실패 잠금 회귀 가드 (P1 신규).

CustomUser.record_failed_login(max_attempts=5)은 실패 카운터를 올리고 5회째에
계정을 잠근다(account_locked_until). 로그인 성공 시 reset_failed_login 으로 해제.
이 임계/해제가 깨지면 무차별 대입 방어가 무력화된다(user.py L120-137).
"""

import pytest


@pytest.mark.django_db
def test_single_failed_login_increments_but_not_locked(worker_user):
    """로그인 실패 1회 → failed_login_count 증가, 아직 미잠금."""
    worker_user.record_failed_login()
    worker_user.refresh_from_db()
    assert worker_user.failed_login_count == 1
    assert worker_user.is_locked is False


@pytest.mark.django_db
def test_fifth_failed_login_locks_account(worker_user):
    """5회 실패 → 계정 잠금(is_locked) + account_locked_until 설정."""
    for _ in range(5):
        worker_user.record_failed_login()
    worker_user.refresh_from_db()
    assert worker_user.failed_login_count == 5
    assert worker_user.is_locked is True
    assert worker_user.account_locked_until is not None


@pytest.mark.django_db
def test_reset_failed_login_clears_counter_and_lock(worker_user):
    """로그인 성공(reset) → 카운터 0 + 잠금 해제."""
    for _ in range(5):
        worker_user.record_failed_login()
    worker_user.reset_failed_login()
    worker_user.refresh_from_db()
    assert worker_user.failed_login_count == 0
    assert worker_user.account_locked_until is None
    assert worker_user.is_locked is False
