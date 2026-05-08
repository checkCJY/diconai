from django.core.management import call_command
from django.db import migrations


def load_fixture(apps, schema_editor):
    call_command("loaddata", "risk_level_standard", app_label="core")


def revert_fixture(apps, schema_editor):
    apps.get_model("core", "RiskLevelStandard").objects.filter(
        code__in=["normal", "warning", "danger"]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_systemlog_result_systemlog_target_menu_and_more"),
    ]

    operations = [
        migrations.RunPython(load_fixture, revert_fixture),
    ]
