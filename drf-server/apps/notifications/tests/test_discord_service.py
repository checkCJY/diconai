"""discord_service 단위 테스트 — 라우팅·멘션·게이팅.

httpx.post 를 mock 해 실제 발송 없이 webhook URL·payload 만 검증한다.
DB 미사용 (discord_id 조회는 monkeypatch).
"""

from unittest.mock import patch

import apps.notifications.services.discord_service as ds

ADMIN = "https://discord.test/admin"
WORKER = "https://discord.test/worker"


def _enable(settings):
    settings.DISCORD_ALARM_ENABLED = True
    settings.DISCORD_WEBHOOK_ADMIN = ADMIN
    settings.DISCORD_WEBHOOK_WORKER = WORKER


def _urls(post):
    return [c.args[0] for c in post.call_args_list]


def _body_for(post, url):
    return next(c for c in post.call_args_list if c.args[0] == url).kwargs["json"]


def test_gas_danger_sends_admin_and_worker_here(settings):
    _enable(settings)
    with patch.object(ds.httpx, "post") as post:
        post.return_value.status_code = 204
        ds.send_alarm_to_discord(
            {
                "alarm_type": "gas_threshold",
                "risk_level": "danger",
                "source_label": "GS-001",
                "summary": "가스 위험",
            }
        )
    assert ADMIN in _urls(post)
    body = _body_for(post, WORKER)
    assert "@here" in body["content"]
    assert body["allowed_mentions"] == {"parse": ["everyone"]}


def test_gas_warning_admin_only(settings):
    _enable(settings)
    with patch.object(ds.httpx, "post") as post:
        post.return_value.status_code = 204
        ds.send_alarm_to_discord(
            {
                "alarm_type": "gas_threshold",
                "risk_level": "warning",
                "source_label": "GS-001",
                "summary": "가스 주의",
            }
        )
    assert _urls(post) == [ADMIN]  # 작업자 채널 미발송


def test_geofence_personal_mention(settings, monkeypatch):
    _enable(settings)
    monkeypatch.setattr(ds, "_get_worker_discord_id", lambda wid: "12345")
    with patch.object(ds.httpx, "post") as post:
        post.return_value.status_code = 204
        ds.send_alarm_to_discord(
            {
                "alarm_type": "geofence_intrusion",
                "risk_level": "danger",
                "source_label": "위험구역",
                "summary": "진입",
                "worker_id": 3,
            }
        )
    body = _body_for(post, WORKER)
    assert body["content"] == "<@12345>"
    assert body["allowed_mentions"] == {"users": ["12345"]}


def test_geofence_without_discord_id_skips_worker(settings, monkeypatch):
    _enable(settings)
    monkeypatch.setattr(ds, "_get_worker_discord_id", lambda wid: "")
    with patch.object(ds.httpx, "post") as post:
        post.return_value.status_code = 204
        ds.send_alarm_to_discord(
            {
                "alarm_type": "geofence_intrusion",
                "risk_level": "danger",
                "source_label": "위험구역",
                "summary": "진입",
                "worker_id": 3,
            }
        )
    assert _urls(post) == [ADMIN]  # 관리자만, 작업자 멘션 대상 없음


def test_disabled_sends_nothing(settings):
    settings.DISCORD_ALARM_ENABLED = False
    settings.DISCORD_WEBHOOK_ADMIN = ADMIN
    settings.DISCORD_WEBHOOK_WORKER = WORKER
    with patch.object(ds.httpx, "post") as post:
        ds.send_alarm_to_discord(
            {
                "alarm_type": "gas_threshold",
                "risk_level": "danger",
                "source_label": "GS-001",
                "summary": "x",
            }
        )
    post.assert_not_called()
