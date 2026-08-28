from django.contrib import admin
from .models import (
    TourDestination, TourPackage, TourEnquiry, TourBooking, TourBookingItem,
    IATAAirline, IATAAirport, AirTicket, IATASourceFile, IATAReconciliationItem,
)

@admin.register(TourDestination)
class TourDestinationAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company')
    list_filter = ('company',)


@admin.register(TourPackage)
class TourPackageAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company')
    list_filter = ('company',)


@admin.register(TourEnquiry)
class TourEnquiryAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company', 'fiscal_year')
    list_filter = ('company', 'fiscal_year')


@admin.register(TourBooking)
class TourBookingAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company', 'fiscal_year')
    list_filter = ('company', 'fiscal_year')


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
    list_display = ['ticket_number', 'passenger_name', 'company', 'issue_date', 'validating_carrier', 'routing', 'gross_fare', 'status']
    search_fields = ['ticket_number', 'passenger_name', 'pnr']
    list_filter = ['company', 'status', 'trip_type', 'cabin']
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
