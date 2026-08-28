from django.contrib import admin
from .models import (
    TableSection, RestaurantTable, TableReservation, PrinterStation,
    DiningOrder, DiningOrderItem, PrintJob, Menu,
    MenuCategory, MenuItem, RoomType, Room,
    RoomBooking, RoomCharge,
)


@admin.register(TableSection)
class TableSectionAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company')
    list_filter = ('company',)


@admin.register(RestaurantTable)
class RestaurantTableAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company')
    list_filter = ('company',)


@admin.register(TableReservation)
class TableReservationAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company')
    list_filter = ('company',)


@admin.register(PrinterStation)
class PrinterStationAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company')
    list_filter = ('company',)


@admin.register(DiningOrder)
class DiningOrderAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company', 'fiscal_year')
    list_filter = ('company', 'fiscal_year')


@admin.register(DiningOrderItem)
class DiningOrderItemAdmin(admin.ModelAdmin):
    list_display = ('__str__',)


@admin.register(PrintJob)
class PrintJobAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company')
    list_filter = ('company',)


@admin.register(Menu)
class MenuAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company')
    list_filter = ('company',)


@admin.register(MenuCategory)
class MenuCategoryAdmin(admin.ModelAdmin):
    list_display = ('__str__',)


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ('__str__',)


@admin.register(RoomType)
class RoomTypeAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company')
    list_filter = ('company',)


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company')
    list_filter = ('company',)


@admin.register(RoomBooking)
class RoomBookingAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company')
    list_filter = ('company',)


@admin.register(RoomCharge)
class RoomChargeAdmin(admin.ModelAdmin):
    list_display = ('__str__',)
