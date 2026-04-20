from django.contrib import admin
from apps.alerts.models import AlarmRecord, Event, EventLog

admin.site.register(AlarmRecord)
admin.site.register(Event)
admin.site.register(EventLog)
