from django.urls import path
from . import views

app_name = 'billing'

urlpatterns = [
    # ── Dashboard & Lists ──────────────────────────────────────────────────
    path('', views.billing_dashboard, name='billing_dashboard'),
    path('invoices/', views.invoice_list, name='invoice_list'),
    path('invoices/<uuid:pk>/', views.invoice_detail, name='view_invoice_detail'),
    path('credit-notes/', views.credit_note_list, name='credit_note_list'),
    path('debit-notes/', views.debit_note_list, name='debit_note_list'),

    # ── Invoice CRUD ───────────────────────────────────────────────────────
    path('invoice/create/', views.InvoiceCreateView.as_view(), name='invoice_create'),
    path('invoice/update/<uuid:pk>/', views.InvoiceUpdateView.as_view(), name='invoice_update'),
    path('invoice/<uuid:pk>/pdf/', views.invoice_pdf_view, name='invoice_pdf'),
    path('invoice/<uuid:pk>/cancel/', views.invoice_cancel, name='invoice_cancel'),
    path('invoice/<uuid:pk>/delete/', views.invoice_delete, name='invoice_delete'),

    # ── HTMX endpoints ─────────────────────────────────────────────────────
    path('htmx/invoice-item-form/', views.InvoiceItemFormRowView.as_view(), name='htmx_invoice_item_form'),
    path('htmx/invoice-item-products/', views.InvoiceItemProductsView.as_view(), name='htmx_invoice_item_products'),
    path('htmx/invoice/<uuid:pk>/collect-payment/', views.CollectPaymentHtmxView.as_view(), name='htmx_collect_payment'),

    # ── Vendor Bills ───────────────────────────────────────────────────────
    path('vendor-bills/create/', views.VendorBillCreateView.as_view(), name='vendor_bill_create'),
    path('vendor-bills/update/<uuid:pk>/', views.VendorBillUpdateView.as_view(), name='vendor_bill_update'),
    path('vendor-bills/<uuid:pk>/cancel/', views.vendor_bill_cancel, name='vendor_bill_cancel'),

    path('api/invoice/<uuid:pk>/summary/', views.invoice_summary_api, name='invoice_summary_api'),

    # ── Credit / Debit Notes ───────────────────────────────────────────────
    path('credit-notes/create/', views.CreditNoteCreateView.as_view(), name='credit_note_create'),
    path('credit-notes/update/<uuid:pk>/', views.CreditNoteUpdateView.as_view(), name='credit_note_update'),
    path('debit-notes/create/', views.DebitNoteCreateView.as_view(), name='debit_note_create'),
    path('debit-notes/update/<uuid:pk>/', views.DebitNoteUpdateView.as_view(), name='debit_note_update'),
]
