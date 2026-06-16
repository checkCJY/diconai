"""Discord webhook 발송 — 알람을 외부 Discord 채널로 미러한다.

라우팅:
  - 관리자 채널: 모든 알람 broadcast (멘션 없음).
  - 작업자 채널:
      · 지오펜스(worker_id 있음) → 그 작업자 개인 멘션.
      · 가스/전력 DANGER       → @here 대피 broadcast.
      · 그 외(WARNING/정상화)   → 작업자 채널 미발송.

발송 실패·설정 누락은 전부 내부에서 삼킨다 — 알람 본류(WS/DB) 비차단.
DISCORD_ALARM_ENABLED=False 거나 webhook 미설정이면 아무것도 하지 않는다.
"""

import logging

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

# Discord 임베드 색상 (위험도별)
_RISK_COLOR = {"danger": 0xE74C3C, "warning": 0xF1C40F, "normal": 0x2ECC71}
_DEFAULT_COLOR = 0x95A5A6

# Discord 임베드 길이 제한
_TITLE_MAX = 256
_DESC_MAX = 4096

# webhook 지연이 Celery worker 점유로 번지지 않게 짧게.
_TIMEOUT_SEC = 3.0

# 작업자 채널에 대피 broadcast 하는 알람 타입
_WORKER_DANGER_TYPES = ("gas_threshold", "power_overload")


def _truncate(text: str, limit: int) -> str:
    """Discord 임베드 길이 제한 초과 시 말줄임."""
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _build_embed(alarm_data: dict) -> dict:
    """알람 payload를 Discord 임베드 1건으로 변환."""
    risk_level = alarm_data.get("risk_level", "")
    embed = {
        "title": _truncate(alarm_data.get("source_label") or "알람", _TITLE_MAX),
        "description": _truncate(
            alarm_data.get("summary") or alarm_data.get("message") or "", _DESC_MAX
        ),
        "color": _RISK_COLOR.get(risk_level, _DEFAULT_COLOR),
    }
    created_at = alarm_data.get("created_at")
    if created_at:
        embed["timestamp"] = created_at
    return embed


def _post(webhook_url: str, json_payload: dict, *, channel: str) -> None:
    """webhook POST — 실패는 경고 로그만 남기고 삼킨다."""
    try:
        resp = httpx.post(webhook_url, json=json_payload, timeout=_TIMEOUT_SEC)
        if resp.status_code >= 400:
            logger.warning(
                "Discord 발송 실패 channel=%s status=%s", channel, resp.status_code
            )
    except httpx.RequestError as exc:
        logger.warning("Discord 발송 오류 channel=%s error=%s", channel, exc)


def _get_worker_discord_id(worker_id: int) -> str:
    """작업자의 Discord ID 조회. 없으면 빈 문자열."""
    from django.contrib.auth import get_user_model

    return (
        get_user_model()
        .objects.filter(id=worker_id)
        .values_list("discord_id", flat=True)
        .first()
        or ""
    )


def send_alarm_to_discord(alarm_data: dict) -> None:
    """알람 1건을 Discord 채널로 발송 (fire-and-forget). 모듈 docstring 참고."""
    if not getattr(settings, "DISCORD_ALARM_ENABLED", False):
        return
    admin_url = getattr(settings, "DISCORD_WEBHOOK_ADMIN", "") or ""
    worker_url = getattr(settings, "DISCORD_WEBHOOK_WORKER", "") or ""
    if not admin_url and not worker_url:
        return

    embed = _build_embed(alarm_data)

    # 관리자 채널 — 모든 알람 broadcast.
    if admin_url:
        _post(admin_url, {"embeds": [embed]}, channel="admin")

    if not worker_url:
        return

    # 작업자 채널 — 지오펜스는 개인 멘션, 가스/전력 DANGER는 @here 대피.
    worker_id = alarm_data.get("worker_id")
    if worker_id:
        discord_id = _get_worker_discord_id(worker_id)
        if discord_id:
            _post(
                worker_url,
                {
                    "content": f"<@{discord_id}>",
                    "embeds": [embed],
                    "allowed_mentions": {"users": [discord_id]},
                },
                channel="worker",
            )
        return

    if (
        alarm_data.get("alarm_type") in _WORKER_DANGER_TYPES
        and alarm_data.get("risk_level") == "danger"
    ):
        _post(
            worker_url,
            {
                "content": "@here 🚨 즉시 대피",
                "embeds": [embed],
                "allowed_mentions": {"parse": ["everyone"]},
            },
            channel="worker",
        )
