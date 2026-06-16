"""_is_night_kst_iso 단위 테스트 (W3.2 + /review Critical #2 회귀 가드).

ARIMA un-downgrade plan §7 — night_abnormal 시각 분기. dummy 가 시각 무관
데이터 생성, 추론 측이 measured_at hour KST 22~05 검사로 판정 책임.
KST wrap-around (22 → 익일 05) edge case 보호.
"""

import pytest

from power.services.power_service import _is_night_kst_iso


@pytest.mark.parametrize(
    "iso,expected,desc",
    [
        # 야간 (22 KST ~ 익일 05 KST = UTC 13 ~ 익일 20)
        ("2026-05-18T13:00:00+00:00", True, "22 KST 야간 시작 (UTC 13)"),
        ("2026-05-18T14:30:00+00:00", True, "23:30 KST 야간 중 (UTC 14:30)"),
        ("2026-05-18T18:00:00+00:00", True, "03 KST 야간 중 (UTC 18)"),
        ("2026-05-18T19:30:00+00:00", True, "04:30 KST 야간 중 (UTC 19:30)"),
        ("2026-05-18T19:59:59+00:00", True, "04:59:59 KST 야간 마지막 (UTC 19:59:59)"),
        # 비야간 (05 KST ~ 22 KST = UTC 20 ~ 13)
        ("2026-05-18T20:00:00+00:00", False, "05 KST 비야간 시작 (UTC 20)"),
        ("2026-05-18T21:00:00+00:00", False, "06 KST 비야간 (UTC 21)"),
        ("2026-05-18T03:00:00+00:00", False, "12 KST 점심 (UTC 03)"),
        ("2026-05-18T08:00:00+00:00", False, "17 KST 오후 (UTC 08)"),
        (
            "2026-05-18T12:59:59+00:00",
            False,
            "21:59:59 KST 비야간 마지막 (UTC 12:59:59)",
        ),
        # wrap-around 경계 (start=22, end=5 → 22 포함, 5 미포함)
        ("2026-05-18T12:59:59+00:00", False, "21:59:59 KST (야간 직전)"),
        ("2026-05-18T13:00:00+00:00", True, "22:00 KST (야간 시작 포함)"),
        ("2026-05-18T19:59:59+00:00", True, "04:59:59 KST (야간 마지막 포함)"),
        ("2026-05-18T20:00:00+00:00", False, "05:00 KST (야간 종료, 비야간 시작)"),
    ],
)
def test_is_night_kst_iso(iso, expected, desc):
    """ISO 시각의 KST 야간(22~05) 판정 + wrap-around 경계 일치."""
    assert _is_night_kst_iso(iso) is expected, f"failed: {desc}"


# ---------------------------------------------------------------------------
# 예외 / 비정상 입력
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "iso",
    [
        "invalid",
        "",
        "2026-99-99",
        "not-a-date",
    ],
)
def test_is_night_kst_iso_invalid_returns_false(iso):
    """parse 실패 시 보수적으로 False (야간 분기 진입 안 함)."""
    assert _is_night_kst_iso(iso) is False


def test_is_night_kst_iso_none_returns_false():
    """None 입력 시 False (TypeError 처리)."""
    assert _is_night_kst_iso(None) is False  # type: ignore[arg-type]


def test_is_night_kst_iso_naive_datetime_assumes_utc():
    """timezone-naive ISO 는 UTC 로 해석 (`fromisoformat` + 명시적 tzinfo)."""
    # naive UTC 13:00 = KST 22:00 → True
    assert _is_night_kst_iso("2026-05-18T13:00:00") is True
    # naive UTC 03:00 = KST 12:00 → False
    assert _is_night_kst_iso("2026-05-18T03:00:00") is False


def test_is_night_kst_iso_different_timezone():
    """다른 timezone 입력도 UTC 환산 후 KST 변환."""
    # KST 시각 22:00 = +09:00 22:00
    assert _is_night_kst_iso("2026-05-18T22:00:00+09:00") is True
    # KST 시각 12:00 = +09:00 12:00
    assert _is_night_kst_iso("2026-05-18T12:00:00+09:00") is False
