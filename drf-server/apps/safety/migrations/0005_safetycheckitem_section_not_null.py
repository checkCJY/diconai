"""
3b 마이그 3단계 — SafetyCheckItem.section NOT NULL 전환.

선행 0004 백필 마이그가 모든 row의 section을 채웠으므로 NOT NULL 안전.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("safety", "0004_backfill_default_section"),
    ]

    operations = [
        migrations.AlterField(
            model_name="safetycheckitem",
            name="section",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="items",
                to="safety.safetychecksection",
            ),
        ),
    ]
