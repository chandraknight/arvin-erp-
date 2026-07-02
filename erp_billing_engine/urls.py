from django.conf import settings
from django.urls import path, include
from apps.accounts.views import home_redirect_view
from rest_framework.authtoken.views import obtain_auth_token
from django.conf.urls.static import static
from django.views.static import serve
from django.urls import re_path
from django.contrib.auth.decorators import login_required
from . import views
from apps.products.api.get import *


urlpatterns = [
    path('', home_redirect_view, name='home'),
    path('health/', views.health_check, name='health_check'),
    path('search/', views.search_results, name='search_results'),
    path('accounts/', include('apps.accounts.urls')),
    path('company/', include('apps.company.urls')),
    path('billing/', include('apps.billing.urls')),
    path('products/', include('apps.products.urls')),
    path('customers/', include('apps.customers.urls')),
    path('purchasing/', include('apps.purchasing.urls')),
    path('vendors/', include('apps.vendors.urls')),
    path('bookkeeping/', include('apps.bookkeeping.urls')),
    path('hrpayroll/', include('apps.hrpayroll.urls')),
    path('reports/', include('apps.reports.urls')),
    path('payments/', include('apps.payments.urls')),
    path('projects/', include('apps.projects.urls')),
    path('orders/', include('apps.orders.urls')),
    path('manufacturing/', include('apps.manufacturing.urls')),
    path('activity/', include('apps.activity_log.urls')),
    path('restaurant/', include('apps.restaurant.urls')),
    path('pos/', include('apps.pos.urls')),
    path('tours/', include('apps.tours.urls', namespace='tours')),
    path('store/', include('apps.ecom.urls', namespace='ecom')),
    path('social/', include('social_django.urls', namespace='social')),
    path('backup/', include('apps.backup.urls', namespace='backup')),

    path('api/products/<uuid:product_id>/price/', get_product_price, name='product_price'),
    path('api/packages/<uuid:package_id>/detail/', get_package_detail, name='package_detail'),

    path('api/products/user-category/', get_user_categories, name='user_categories'),
    path('api/products/user-products/', get_user_products, name='user_products'),

    path('api/products/user-product-packages/', get_user_product_packages, name='user_product_packages'),

    path('api/', include('apps.api.urls', namespace='api')),
]

handler404 = 'apps.ecom.views.storefront.custom_404'

urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
# Backup files require login — registered BEFORE the wildcard so it takes priority
urlpatterns += [
    re_path(
        r'^media/backups/(?P<path>.*)$',
        login_required(serve),
        {'document_root': settings.MEDIA_ROOT + '/backups'},
    ),
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]
