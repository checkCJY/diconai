from django.core.management import call_command
from django.db import migrations


def load_fixture(apps, schema_editor):
    call_command("loaddata", "hazard_type", app_label="alerts")


def revert_fixture(apps, schema_editor):
    apps.get_model("alerts", "HazardType").objects.all().delete()
    apps.get_model("alerts", "HazardTypeGroup").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("alerts", "0004_hazardtypegroup_hazardtype_alertpolicy"),
    ]

    operations = [
        migrations.RunPython(load_fixture, revert_fixture),
    ]
