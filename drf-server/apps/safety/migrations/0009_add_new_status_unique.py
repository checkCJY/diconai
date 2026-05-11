"""
3c 마이그 (d) — SafetyStatus에 UNIQUE(session, check_item) 추가.

이전 (c)에서 (worker, check_item) UNIQUE 제거 + (b)에서 (session, check_item)
조합이 worker별 1세션 매핑으로 이미 UNIQUE 보장 → 안전하게 추가.

reverse: 새 UNIQUE 제거.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("safety", "0008_drop_old_status_unique"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="safetystatus",
            constraint=models.UniqueConstraint(
                fields=["session", "check_item"], name="uq_safety_session_item"
            ),
        ),
    ]
