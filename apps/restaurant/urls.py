from django.urls import path
from . import views

app_name = 'restaurant'

urlpatterns = [
    # Dashboard / floor plan
    path('', views.restaurant_dashboard, name='dashboard'),

    # Tables
    path('tables/', views.TableListView.as_view(), name='table_list'),
    path('tables/create/', views.TableCreateView.as_view(), name='table_create'),
    path('tables/<uuid:pk>/update/', views.TableUpdateView.as_view(), name='table_update'),
    path('tables/<uuid:table_pk>/set-available/', views.table_set_available, name='table_set_available'),

    # Sections
    path('sections/create/', views.SectionCreateView.as_view(), name='section_create'),
    path('sections/<uuid:pk>/update/', views.SectionUpdateView.as_view(), name='section_update'),

    # Printer stations
    path('printers/', views.PrinterListView.as_view(), name='printer_list'),
    path('printers/create/', views.PrinterCreateView.as_view(), name='printer_create'),
    path('printers/<uuid:pk>/update/', views.PrinterUpdateView.as_view(), name='printer_update'),

    # Dining orders
    path('orders/', views.order_list, name='order_list'),
    path('orders/open/<uuid:table_pk>/', views.order_open, name='order_open'),
    path('orders/<uuid:pk>/', views.order_detail, name='order_detail'),
    path('orders/<uuid:pk>/add-item/', views.order_add_item, name='order_add_item'),
    path('orders/<uuid:pk>/remove-item/<uuid:item_pk>/', views.order_remove_item, name='order_remove_item'),

    # KOT / BOT — send new items
    path('orders/<uuid:pk>/kot/', views.print_kot_view, name='print_kot'),
    path('orders/<uuid:pk>/bot/', views.print_bot_view, name='print_bot'),
    path('orders/<uuid:pk>/kot-bot/', views.send_kot_bot_view, name='send_kot_bot'),

    # KOT / BOT — reprint (force duplicate for kitchen/bar)
    path('orders/<uuid:pk>/kot/reprint/', views.reprint_kot_view, name='reprint_kot'),
    path('orders/<uuid:pk>/bot/reprint/', views.reprint_bot_view, name='reprint_bot'),

    # Bill
    path('orders/<uuid:pk>/bill/', views.issue_bill_view, name='issue_bill'),
    path('orders/<uuid:pk>/paid/', views.mark_order_paid_view, name='mark_paid'),

    # Void order
    path('orders/<uuid:pk>/void/', views.void_order_view, name='void_order'),

    # Item status updates (kitchen/bar → READY / SERVED)
    path('orders/<uuid:pk>/items/<uuid:item_pk>/status/', views.item_status_update_view, name='item_status_update'),

    # Table transfer
    path('orders/<uuid:pk>/transfer/', views.table_transfer_view, name='table_transfer'),

    # Print job dashboard + retry
    path('print-jobs/', views.print_job_dashboard, name='print_job_dashboard'),
    path('print-jobs/<uuid:job_pk>/retry/', views.retry_print_job, name='retry_print_job'),

    # Print agent API
    path('api/print-jobs/', views.print_jobs_api, name='print_jobs_api'),
    path('api/print-jobs/<uuid:job_pk>/fail/', views.print_job_fail, name='print_job_fail'),

    # Menu management
    path('menus/', views.menu_list, name='menu_list'),
    path('menus/create/', views.menu_create, name='menu_create'),
    path('menus/<uuid:pk>/', views.menu_detail, name='menu_detail'),
    path('menus/<uuid:pk>/edit/', views.menu_edit, name='menu_edit'),
    path('menus/<uuid:pk>/publish/', views.menu_publish_toggle, name='menu_publish_toggle'),
    path('menus/<uuid:menu_pk>/categories/add/', views.menu_category_add, name='menu_category_add'),
    path('menus/<uuid:menu_pk>/categories/<uuid:category_pk>/items/add/', views.menu_item_add, name='menu_item_add'),
    path('menus/<uuid:menu_pk>/items/<uuid:item_pk>/toggle/', views.menu_item_toggle, name='menu_item_toggle'),

    # Room types
    path('room-types/', views.RoomTypeListView.as_view(), name='room_type_list'),
    path('room-types/create/', views.RoomTypeCreateView.as_view(), name='room_type_create'),
    path('room-types/<uuid:pk>/update/', views.RoomTypeUpdateView.as_view(), name='room_type_update'),

    # Rooms
    path('rooms/', views.RoomListView.as_view(), name='room_list'),
    path('rooms/board/', views.room_board, name='room_board'),
    path('rooms/create/', views.RoomCreateView.as_view(), name='room_create'),
    path('rooms/<uuid:pk>/update/', views.RoomUpdateView.as_view(), name='room_update'),
    path('rooms/<uuid:pk>/set-available/', views.room_set_available, name='room_set_available'),

    # Room bookings
    path('rooms/bookings/', views.room_booking_list, name='room_booking_list'),
    path('rooms/bookings/new/', views.room_booking_create, name='room_booking_create'),
    path('rooms/bookings/<uuid:pk>/', views.room_booking_detail, name='room_booking_detail'),
    path('rooms/bookings/<uuid:pk>/check-in/', views.room_check_in, name='room_check_in'),
    path('rooms/bookings/<uuid:pk>/check-out/', views.room_check_out, name='room_check_out'),
    path('rooms/bookings/<uuid:pk>/charge/', views.room_add_charge, name='room_add_charge'),
    path('rooms/bookings/<uuid:pk>/cancel/', views.room_booking_cancel, name='room_booking_cancel'),
]
