from django.core.management import call_command
from django.db import migrations


def load_fixture(apps, schema_editor):
    call_command("loaddata", "menu", app_label="dashboard")


def revert_fixture(apps, schema_editor):
    apps.get_model("dashboard", "Menu").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("dashboard", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(load_fixture, revert_fixture),
    ]
