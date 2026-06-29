from django.urls import path
from . import views

app_name = 'activity_log'

urlpatterns = [
    path('', views.activity_log_list, name='log_list'),
    path('<uuid:pk>/', views.activity_log_detail, name='log_detail'),
    path('history/<str:model_name>/<str:object_id>/', views.object_history, name='object_history'),
]
