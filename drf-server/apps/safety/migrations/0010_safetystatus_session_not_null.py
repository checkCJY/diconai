"""
3c 마이그 (e) — SafetyStatus.session nullable → NOT NULL.

선행 (b) 백필이 모든 row의 session을 채웠으므로 NOT NULL 안전.
단, check_item이 NULL인 row는 session=NULL로 남음 (탈퇴/삭제된 항목 이력).
이런 row는 운영자가 수동 정리하거나 보존 가치 있음 — 학습 환경에서는 사실상 0건.

본 마이그가 적용되어 NOT NULL 전환되려면 모든 row에 session이 채워져야 함.
만약 (b) 백필 후에도 남은 NULL row가 있으면 IntegrityError 발생 → 별도 정리 필요.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("safety", "0009_add_new_status_unique"),
    ]

    operations = [
        migrations.AlterField(
            model_name="safetystatus",
            name="session",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="statuses",
                to="safety.safetychecksession",
            ),
        ),
    ]
