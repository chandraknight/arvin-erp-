from django.urls import path
from . import views

app_name = 'customers'

urlpatterns = [
    path('contacts/', views.contacts_dashboard, name='contacts_dashboard'),
    path('', views.customer_dashboard, name='customer_dashboard'),
    path('create/', views.create_customer, name='create_customer'),
    path('htmx/quick-create/', views.customer_quick_create, name='customer_quick_create'),
    path('api/<uuid:pk>/json/', views.customer_json, name='customer_json'),
    path('update/<uuid:id>/', views.update_customer, name='update_customer'),
    path('delete/<uuid:id>/', views.delete_customer, name='delete_customer'),
    path('referrers/', views.referrer_list, name='referrer_list'),
    path('referrers/create/', views.referrer_create, name='referrer_create'),
    path('referrers/update/<uuid:pk>/', views.referrer_update, name='referrer_update'),
    path('referrers/delete/<uuid:pk>/', views.referrer_delete, name='referrer_delete'),
]