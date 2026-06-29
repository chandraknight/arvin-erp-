from django.urls import path
from . import views

app_name = 'vendors'

urlpatterns = [
    path('create/', views.vendor_create, name='vendor_create'),
    path('dashboard/', views.vendor_dashboard, name='vendor_dashboard'),
    path('update/<uuid:pk>/', views.vendor_update, name='vendor_update'),
    path('delete/<uuid:pk>/', views.vendor_delete, name='vendor_delete'),
    path('detail/<uuid:pk>/', views.vendor_detail, name='vendor_detail'),
    path('api/<uuid:pk>/json/', views.vendor_json, name='vendor_json'),
    path('htmx/quick-create/', views.vendor_quick_create, name='vendor_quick_create'),
]
