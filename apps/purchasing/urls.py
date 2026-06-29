from django.urls import path
from . import views
from .view_collections.update_view import PurchaseOrderUpdateView

app_name = 'purchasing'

urlpatterns = [
    # ── Hub ───────────────────────────────────────────────────────────────
    path('', views.purchasing_hub, name='purchasing_hub'),

    # ── Purchase Orders ───────────────────────────────────────────────────
    path('purchase-orders/', views.purchase_order_dashboard, name='purchase_dashboard'),
    path('purchase-orders/create/', views.PurchaseOrderCreateView.as_view(), name='purchase_order_create'),
    path('purchase-orders/<uuid:pk>/', views.purchase_order_detail, name='purchase_order_detail'),
    path('purchase-orders/<uuid:pk>/edit/', PurchaseOrderUpdateView.as_view(), name='purchase_order_update'),
    path('purchase-orders/<uuid:pk>/receive/', views.receive_purchase_order, name='receive_purchase_order'),

    # ── Vendor Bills ──────────────────────────────────────────────────────
    path('vendor-bills/', views.vendor_bill_list, name='vendor_bill_list'),
    path('vendor-bills/create/', views.vendor_bill_create, name='vendor_bill_create'),

    # ── Vendor Payments ───────────────────────────────────────────────────
    path('vendor-payments/', views.vendor_payment_list, name='vendor_payment_list'),
    path('vendor-payments/create/', views.vendor_payment_create, name='vendor_payment_create'),

    # ── HTMX ─────────────────────────────────────────────────────────────
    path('htmx/vendor-bill-item-form/', views.htmx_vendor_bill_item_form, name='htmx_vendor_bill_item_form'),
    path('htmx/vendor-bill-summary/', views.htmx_vendor_bill_summary, name='htmx_vendor_bill_summary'),
]
