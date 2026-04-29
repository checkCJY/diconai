from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("facilities", "0002_facility_map_coords_positionnode"),
    ]

    operations = [
        migrations.AddField(
            model_name="facility",
            name="notes",
            field=models.TextField(blank=True, default="", verbose_name="비고"),
        ),
    ]
