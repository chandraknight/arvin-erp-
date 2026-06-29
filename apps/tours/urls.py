from django.urls import path
from . import views

app_name = 'tours'

urlpatterns = [
    # Dashboard
    path('', views.tours_dashboard, name='dashboard'),

    # Destinations
    path('destinations/', views.destination_list, name='destination_list'),
    path('destinations/new/', views.destination_create, name='destination_create'),
    path('destinations/<uuid:pk>/edit/', views.destination_edit, name='destination_edit'),

    # Packages
    path('packages/', views.package_list, name='package_list'),
    path('packages/new/', views.package_create, name='package_create'),
    path('packages/<uuid:pk>/edit/', views.package_edit, name='package_edit'),

    # Enquiries
    path('enquiries/', views.enquiry_list, name='enquiry_list'),
    path('enquiries/new/', views.enquiry_create, name='enquiry_create'),
    path('enquiries/<uuid:pk>/', views.enquiry_detail, name='enquiry_detail'),
    path('enquiries/<uuid:pk>/edit/', views.enquiry_edit, name='enquiry_edit'),
    path('enquiries/<uuid:pk>/status/', views.enquiry_update_status, name='enquiry_update_status'),
    path('enquiries/<uuid:pk>/convert/', views.enquiry_convert_to_booking, name='enquiry_convert'),

    # Bookings
    path('bookings/', views.booking_list, name='booking_list'),
    path('bookings/new/', views.booking_create, name='booking_create'),
    path('bookings/<uuid:pk>/', views.booking_detail, name='booking_detail'),
    path('bookings/<uuid:pk>/edit/', views.booking_edit, name='booking_edit'),
    path('bookings/<uuid:pk>/status/', views.booking_update_status, name='booking_update_status'),
    path('bookings/<uuid:pk>/invoice/', views.booking_issue_invoice, name='booking_issue_invoice'),

    # Air Tickets
    path('tickets/', views.ticket_list, name='ticket_list'),
    path('tickets/new/', views.ticket_create, name='ticket_create'),
    path('tickets/<uuid:pk>/', views.ticket_detail, name='ticket_detail'),
    path('tickets/<uuid:pk>/edit/', views.ticket_edit, name='ticket_edit'),

    # IATA Reference — Airlines
    path('iata/airlines/', views.airline_list, name='airline_list'),
    path('iata/airlines/add/', views.airline_create, name='airline_create'),
    path('iata/airlines/import/', views.airline_import, name='airline_import'),

    # IATA Reference — Airports
    path('iata/airports/', views.airport_list, name='airport_list'),
    path('iata/airports/import/', views.airport_import, name='airport_import'),

    # BSP Reconciliation
    path('reconciliation/', views.reconciliation_list, name='reconciliation_list'),
    path('reconciliation/upload/', views.reconciliation_upload, name='reconciliation_upload'),
    path('reconciliation/<uuid:pk>/', views.reconciliation_detail, name='reconciliation_detail'),
    path('reconciliation/<uuid:pk>/process/', views.reconciliation_process, name='reconciliation_process'),

    # AIR File (Agency Invoice Report) & Payment Reconciliation
    path('air/', views.air_file_list, name='air_file_list'),
    path('air/upload/', views.air_file_upload, name='air_file_upload'),
    path('air/<uuid:pk>/', views.air_file_detail, name='air_file_detail'),
    path('air/<uuid:pk>/payment/add/', views.air_payment_add, name='air_payment_add'),
    path('air/<uuid:pk>/payment/<uuid:payment_pk>/delete/', views.air_payment_delete, name='air_payment_delete'),
    path('air/<uuid:pk>/dispute/', views.air_file_mark_disputed, name='air_file_mark_disputed'),
]
