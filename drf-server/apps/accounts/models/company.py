from django.db import models
from apps.core.models.base import BaseModel


class Company(BaseModel):
    name = models.CharField(max_length=100, unique=True, verbose_name="회사명")
    is_active = models.BooleanField(default=True, verbose_name="사용 여부")

    class Meta:
        db_table = "company"
        verbose_name = "회사"

    def __str__(self):
        return self.name
