from django.db import models


class PositionCategory(models.TextChoices):
    OFFICE = "office", "사무직"
    FIELD = "field", "현장직"
    EXECUTIVE = "executive", "임원진"


class Position(models.Model):
    name = models.CharField(max_length=30, unique=True, verbose_name="직급명")
    level = models.PositiveSmallIntegerField(verbose_name="정렬 레벨")
    category = models.CharField(
        max_length=20,
        choices=PositionCategory.choices,
        verbose_name="분류",
    )
    is_active = models.BooleanField(default=True, verbose_name="사용 여부")

    class Meta:
        db_table = "position"
        ordering = ["level"]
        verbose_name = "직급"

    def __str__(self):
        return self.name
