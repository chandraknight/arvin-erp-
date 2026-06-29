from django.urls import path
from . import views

app_name = 'backup'

urlpatterns = [
    path('', views.backup_list, name='backup_list'),
    path('create/', views.backup_create, name='backup_create'),
    path('<uuid:pk>/download/', views.backup_download, name='backup_download'),
    path('<uuid:pk>/restore/', views.backup_confirm_restore, name='backup_confirm_restore'),
    path('<uuid:pk>/restore/confirm/', views.backup_restore, name='backup_restore'),
    path('<uuid:pk>/delete/', views.backup_delete, name='backup_delete'),
]
