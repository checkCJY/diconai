from django.core.management import call_command
from django.db import migrations


def load_fixture(apps, schema_editor):
    call_command("loaddata", "gas_type", app_label="reference")


def revert_fixture(apps, schema_editor):
    apps.get_model("reference", "CommonCode").objects.filter(
        group__code="GAS_TYPE"
    ).delete()
    apps.get_model("reference", "CodeGroup").objects.filter(code="GAS_TYPE").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("reference", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(load_fixture, revert_fixture),
    ]
