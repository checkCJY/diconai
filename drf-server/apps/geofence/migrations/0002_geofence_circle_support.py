from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("geofence", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="geofence",
            name="shape_type",
            field=models.CharField(
                choices=[("polygon", "다각형"), ("circle", "원형")],
                default="polygon",
                max_length=10,
                verbose_name="형태",
            ),
        ),
        migrations.AddField(
            model_name="geofence",
            name="circle_cx",
            field=models.FloatField(
                blank=True, null=True, verbose_name="원 중심 x (px)"
            ),
        ),
        migrations.AddField(
            model_name="geofence",
            name="circle_cy",
            field=models.FloatField(
                blank=True, null=True, verbose_name="원 중심 y (px)"
            ),
        ),
        migrations.AddField(
            model_name="geofence",
            name="circle_radius",
            field=models.FloatField(blank=True, null=True, verbose_name="반지름 (px)"),
        ),
    ]
