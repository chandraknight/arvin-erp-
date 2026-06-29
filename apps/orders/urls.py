from django.urls import path
from . import views

app_name = 'orders'

urlpatterns = [
    path('', views.order_dashboard, name='dashboard'),

    # Sales Orders
    path('sales-orders/', views.SalesOrderListView.as_view(), name='order_list'),
    path('sales-orders/create/', views.SalesOrderCreateView.as_view(), name='order_create'),
    path('sales-orders/<uuid:pk>/', views.SalesOrderDetailView.as_view(), name='order_detail'),
    path('sales-orders/<uuid:pk>/update/', views.SalesOrderUpdateView.as_view(), name='order_update'),
    path('sales-orders/<uuid:pk>/delete/', views.SalesOrderDeleteView.as_view(), name='order_delete'),
    path('sales-orders/<uuid:pk>/confirm/', views.confirm_order, name='order_confirm'),
    path('sales-orders/<uuid:pk>/cancel/', views.cancel_order, name='order_cancel'),
    path('sales-orders/<uuid:pk>/convert-invoice/', views.convert_to_invoice, name='order_to_invoice'),

    # Delivery Notes
    path('delivery-notes/', views.DeliveryNoteListView.as_view(), name='delivery_list'),
    path('delivery-notes/create/<uuid:order_pk>/', views.DeliveryNoteCreateView.as_view(), name='delivery_create'),
    path('delivery-notes/<uuid:pk>/', views.DeliveryNoteDetailView.as_view(), name='delivery_detail'),
    path('delivery-notes/<uuid:pk>/update/', views.DeliveryNoteUpdateView.as_view(), name='delivery_update'),
    path('delivery-notes/<uuid:pk>/mark-delivered/', views.mark_delivered, name='delivery_mark_delivered'),
    path('delivery-notes/<uuid:pk>/cancel/', views.cancel_delivery, name='delivery_cancel'),

    # Tracking
    path('delivery-notes/<uuid:pk>/track/', views.delivery_tracking_view, name='delivery_track'),
    path('delivery-notes/<uuid:pk>/add-event/', views.add_tracking_event, name='delivery_add_event'),

    # Print receipt
    path('sales-orders/<uuid:pk>/print/', views.order_print_receipt, name='order_print_receipt'),

    # HTMX partials
    path('htmx/order-items/<uuid:order_pk>/', views.htmx_order_items, name='htmx_order_items'),
]
