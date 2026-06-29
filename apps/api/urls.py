from django.urls import path

from apps.api.views.auth_views import TokenListView, TokenObtainView, TokenRevokeView
from apps.api.views.company_views import CompanyDetailView
from apps.api.views.customer_views import CustomerCreateView, CustomerDetailView, CustomerListView
from apps.api.views.dashboard_views import DashboardView
from apps.api.views.invoice_views import InvoiceCreateView, InvoiceDetailView, InvoiceListView
from apps.api.views.payment_views import PaymentDetailView, PaymentListView
from apps.api.views.product_views import ProductDetailView, ProductListView

app_name = 'api'

urlpatterns = [
    # Auth
    path('v1/auth/token/', TokenObtainView.as_view(), name='token_obtain'),
    path('v1/auth/token/revoke/', TokenRevokeView.as_view(), name='token_revoke'),
    path('v1/auth/tokens/', TokenListView.as_view(), name='token_list'),

    # Company
    path('v1/company/', CompanyDetailView.as_view(), name='company_detail'),

    # Customers
    path('v1/customers/', CustomerListView.as_view(), name='customer_list'),
    path('v1/customers/create/', CustomerCreateView.as_view(), name='customer_create'),
    path('v1/customers/<uuid:pk>/', CustomerDetailView.as_view(), name='customer_detail'),

    # Products
    path('v1/products/', ProductListView.as_view(), name='product_list'),
    path('v1/products/<uuid:pk>/', ProductDetailView.as_view(), name='product_detail'),

    # Invoices
    path('v1/invoices/', InvoiceListView.as_view(), name='invoice_list'),
    path('v1/invoices/create/', InvoiceCreateView.as_view(), name='invoice_create'),
    path('v1/invoices/<uuid:pk>/', InvoiceDetailView.as_view(), name='invoice_detail'),

    # Payments
    path('v1/payments/', PaymentListView.as_view(), name='payment_list'),
    path('v1/payments/<uuid:pk>/', PaymentDetailView.as_view(), name='payment_detail'),

    # Dashboard
    path('v1/dashboard/', DashboardView.as_view(), name='dashboard'),
]
