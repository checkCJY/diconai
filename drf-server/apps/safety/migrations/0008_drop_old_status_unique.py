"""
3c 마이그 (c) — SafetyStatus의 UNIQUE(worker, check_item) 제거.

이전 단계 (b)에서 모든 row가 default Session에 매핑됐으므로 새 UNIQUE
(session, check_item)이 보장됨. 본 단계는 기존 UNIQUE만 제거 — 새 UNIQUE는
다음 단계 (d)에서 추가.

reverse: 기존 UNIQUE를 다시 추가.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("safety", "0007_backfill_default_session"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="safetystatus",
            name="uq_safety_worker_item",
        ),
    ]
