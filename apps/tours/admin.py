from django.contrib import admin
from .models import (
    TourDestination, TourPackage, TourEnquiry, TourBooking, TourBookingItem,
    IATAAirline, IATAAirport, AirTicket, IATASourceFile, IATAReconciliationItem,
)

admin.site.register(TourDestination)
admin.site.register(TourPackage)
admin.site.register(TourEnquiry)
admin.site.register(TourBooking)
admin.site.register(TourBookingItem)


@admin.register(IATAAirline)
class IATAAirlineAdmin(admin.ModelAdmin):
    list_display = ['iata_code', 'icao_code', 'name', 'country', 'is_active']
    search_fields = ['iata_code', 'name', 'country']
    list_filter = ['is_active']


@admin.register(IATAAirport)
class IATAAirportAdmin(admin.ModelAdmin):
    list_display = ['iata_code', 'icao_code', 'name', 'city', 'country', 'is_active']
    search_fields = ['iata_code', 'name', 'city', 'country']
    list_filter = ['is_active', 'country_code']


@admin.register(AirTicket)
class AirTicketAdmin(admin.ModelAdmin):
    list_display = ['ticket_number', 'passenger_name', 'issue_date', 'validating_carrier', 'routing', 'gross_fare', 'status']
    search_fields = ['ticket_number', 'passenger_name', 'pnr']
    list_filter = ['status', 'trip_type', 'cabin']
    date_hierarchy = 'issue_date'


@admin.register(IATASourceFile)
class IATASourceFileAdmin(admin.ModelAdmin):
    list_display = ['original_filename', 'company', 'status', 'rows_total', 'rows_matched', 'rows_unmatched', 'created_at']
    list_filter = ['status']


@admin.register(IATAReconciliationItem)
class IATAReconciliationItemAdmin(admin.ModelAdmin):
    list_display = ['raw_ticket_number', 'raw_passenger_name', 'raw_gross', 'match_status', 'source_file']
    list_filter = ['match_status']
    search_fields = ['raw_ticket_number', 'raw_passenger_name']
