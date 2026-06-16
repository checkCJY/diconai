from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reference", "0003_remove_lel"),
    ]

    operations = [
        # CodeGroup.scope — Figma "관리범위" 필드. blank=True, default="" 이므로 기존 레코드에 영향 없음.
        migrations.AddField(
            model_name="codegroup",
            name="scope",
            field=models.CharField(
                blank=True,
                default="",
                max_length=200,
                verbose_name="관리 범위",
            ),
        ),
    ]
