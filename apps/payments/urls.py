from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [
    path('', views.payment_list, name='payment_list'),
    path('add/', views.payment_create, name='payment_add'),
    path('<uuid:pk>/', views.payment_detail, name='payment_detail'),
    path('<uuid:pk>/edit/', views.payment_update, name='payment_update'),
    path('<uuid:pk>/receipt/', views.payment_receipt, name='payment_receipt'),
    path('<uuid:pk>/cancel/', views.payment_cancel, name='payment_cancel'),
    path('api/ledger-accounts/', views.get_ledger_accounts, name='api_ledger_accounts'),

    # Expense tracker
    path('expenses/', views.expense_list, name='expense_list'),
    path('expenses/add/', views.expense_create, name='expense_create'),
    path('expenses/<uuid:pk>/', views.expense_detail, name='expense_detail'),
    path('expenses/<uuid:pk>/cancel/', views.expense_cancel, name='expense_cancel'),

    # Bank accounts
    path('bank-accounts/', views.bank_account_list, name='bank_account_list'),
    path('bank-accounts/add/', views.bank_account_create, name='bank_account_create'),
    path('bank-accounts/<uuid:pk>/edit/', views.bank_account_update, name='bank_account_update'),
]
