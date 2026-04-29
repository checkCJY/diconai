from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("facilities", "0001_initial"),
    ]

    operations = [
        # Facility에 도면 좌표/크기 추가
        migrations.AddField(
            model_name="facility",
            name="map_x",
            field=models.FloatField(
                blank=True, null=True, verbose_name="도면 x 좌표 (px)"
            ),
        ),
        migrations.AddField(
            model_name="facility",
            name="map_y",
            field=models.FloatField(
                blank=True, null=True, verbose_name="도면 y 좌표 (px)"
            ),
        ),
        migrations.AddField(
            model_name="facility",
            name="map_width",
            field=models.FloatField(
                blank=True, null=True, verbose_name="도면 너비 (px)"
            ),
        ),
        migrations.AddField(
            model_name="facility",
            name="map_height",
            field=models.FloatField(
                blank=True, null=True, verbose_name="도면 높이 (px)"
            ),
        ),
        # PositionNode 신규 모델
        migrations.CreateModel(
            name="PositionNode",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "device_id",
                    models.CharField(
                        max_length=50, unique=True, verbose_name="하드웨어 식별자"
                    ),
                ),
                (
                    "device_name",
                    models.CharField(max_length=100, verbose_name="사용자 정의 이름"),
                ),
                ("x", models.FloatField(verbose_name="도면 x 좌표 (px)")),
                ("y", models.FloatField(verbose_name="도면 y 좌표 (px)")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("normal", "정상"),
                            ("error", "오류"),
                            ("offline", "오프라인"),
                            ("inactive", "비활성"),
                        ],
                        default="normal",
                        max_length=20,
                    ),
                ),
                ("status_updated_at", models.DateTimeField(blank=True, null=True)),
                ("last_reading", models.DateTimeField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=True)),
                ("deactivated_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "facility",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="positionnodes",
                        to="facilities.facility",
                    ),
                ),
            ],
            options={"db_table": "position_node"},
        ),
        migrations.AddIndex(
            model_name="positionnode",
            index=models.Index(
                fields=["facility", "is_active"], name="idx_pos_node_facility_active"
            ),
        ),
    ]
