from django.urls import path
from . import views
from .view_collections.create_view import (
    FixedAssetCreateView, FixedAssetListView, FixedAssetDetailView,
    FixedAssetUpdateView, fixed_asset_dispose,
)

app_name = 'bookkeeping'
urlpatterns = [
    # Ledger accounts
    path('ledger_accounts/', views.LedgerAccountListView.as_view(), name='ledger_account_list'),
    path('ledger/create/', views.LedgerAccountCreateView.as_view(), name='ledger_account_create'),
    path('ledger/<uuid:pk>/edit/', views.LedgerAccountUpdateView.as_view(), name='ledger_account_update'),
    path('ledger-report/<uuid:account_id>/', views.LedgerReportView.as_view(), name='ledger_report'),
    path('ledger-report/<uuid:account_id>/set-opening-balance/', views.LedgerReportView.as_view(), name='set_opening_balance'),

    # Journal entries
    path('journal-entries/', views.JournalEntryListView.as_view(), name='journal_entry_list'),
    path('journal-entries/<uuid:pk>/', views.JournalEntryDetailView.as_view(), name='journal_entry_detail'),
    path('journal-entries/<uuid:pk>/pdf/', views.JournalEntryPdfView.as_view(), name='journal_entry_pdf'),
    path('journal-entries/<uuid:pk>/reverse/', views.JournalEntryReverseView.as_view(), name='journal_entry_reverse'),
    path('journal/create/', views.JournalEntryCreateView.as_view(), name='journal_entry_create'),

    # Superadmin — immutable journal audit trail
    path('journal-audit-log/', views.JournalAuditLogView.as_view(), name='journal_audit_log'),

    # NFRS 13 Fixed Assets
    path('fixed-assets/', FixedAssetListView.as_view(), name='fixed_asset_list'),
    path('fixed-assets/create/', FixedAssetCreateView.as_view(), name='fixed_asset_create'),
    path('fixed-assets/<uuid:pk>/', FixedAssetDetailView.as_view(), name='fixed_asset_detail'),
    path('fixed-assets/<uuid:pk>/edit/', FixedAssetUpdateView.as_view(), name='fixed_asset_update'),
    path('fixed-assets/<uuid:pk>/dispose/', fixed_asset_dispose, name='fixed_asset_dispose'),
]
