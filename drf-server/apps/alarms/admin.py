# Register your models here.
from django.contrib import admin
from .models import AlarmRecord, Notification, SafetyCheckItem, SafetyStatus, SystemLog

admin.site.register(AlarmRecord)
admin.site.register(Notification)
admin.site.register(SafetyCheckItem)
admin.site.register(SafetyStatus)
admin.site.register(SystemLog)