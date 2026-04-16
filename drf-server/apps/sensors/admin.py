# Register your models here.
from django.contrib import admin
from .models import Facility, GasSensor, PowerDevice, GasData, PowerData, PowerEvent

admin.site.register(Facility)
admin.site.register(GasSensor)
admin.site.register(PowerDevice)
admin.site.register(GasData)
admin.site.register(PowerData)
admin.site.register(PowerEvent)
