from django.contrib import admin
from .models import (
    SalesOrder, SalesOrderItem, DeliveryNote, DeliveryNoteItem,
    DeliveryTracking,
)


@admin.register(SalesOrder)
class SalesOrderAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company', 'fiscal_year')
    list_filter = ('company', 'fiscal_year')


@admin.register(SalesOrderItem)
class SalesOrderItemAdmin(admin.ModelAdmin):
    list_display = ('__str__',)


@admin.register(DeliveryNote)
class DeliveryNoteAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company', 'fiscal_year')
    list_filter = ('company', 'fiscal_year')


@admin.register(DeliveryNoteItem)
class DeliveryNoteItemAdmin(admin.ModelAdmin):
    list_display = ('__str__',)


@admin.register(DeliveryTracking)
class DeliveryTrackingAdmin(admin.ModelAdmin):
    list_display = ('__str__',)
