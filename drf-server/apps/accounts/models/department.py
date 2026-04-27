from django.db import models


class Department(models.Model):
    name = models.CharField(max_length=50, unique=True, verbose_name="부서명")
    code = models.CharField(max_length=20, unique=True, verbose_name="부서 코드")
    is_active = models.BooleanField(default=True, verbose_name="사용 여부")

    class Meta:
        db_table = "department"
        ordering = ["code"]
        verbose_name = "부서"

    def __str__(self):
        return self.name
