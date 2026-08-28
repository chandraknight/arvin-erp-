from django.contrib import admin
from .models import (
    Vendor,
)


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company')
    list_filter = ('company',)
