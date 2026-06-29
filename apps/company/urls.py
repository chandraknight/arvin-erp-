from django.urls import path
from django.views.generic import RedirectView
from .services.all_services import FiscalYearListView,FiscalYearCreateView,select_fiscal_year
from . import views
app_name = 'company'

urlpatterns = [
    path('', RedirectView.as_view(pattern_name='company:company_list', permanent=False)),
    path('companies/', views.CompanyListView.as_view(), name='company_list'),
    path('companies/create/', views.CompanyCreateAndAssignView.as_view(), name='company_create'),
    path('companies/detail/<uuid:id>/', views.CompanyDetailView.as_view(), name='company_detail'),
    path('companies/update/<uuid:id>/', views.CompanyUpdateView.as_view(), name='company_update'),
    path('companies/delete/<uuid:id>/', views.company_delete_view, name='company_delete'),

    path('branches/', views.BranchListView.as_view(), name='branch_list'),
    path('companies/branches/create/', views.BranchCreateView.as_view(), name='branch_create'),
    path('companies/<uuid:company_pk>/branches/create/', views.BranchCreateView.as_view(), name='company_branch_create'),
    path('branches/detail/<uuid:id>/', views.BranchDetailView.as_view(), name='branch_detail'),
    path('branches/update/<uuid:id>/', views.BranchUpdateView.as_view(), name='branch_update'),
    path('companies/branches/update/<uuid:id>/', views.BranchUpdateView.as_view(), name='company_branch_update'),
    path('branches/delete/<uuid:id>/', views.BranchDeleteView.as_view(), name='branch_delete'),

    path('fiscalyears/', FiscalYearListView.as_view(), name='fiscalyear_list'),
    path('fiscalyears/create/',FiscalYearCreateView.as_view(), name='fiscalyear_create'),
    path('fiscalyears/select/<uuid:id>/',select_fiscal_year, name='select_fiscal_year'),
    path('fiscalyears/close/<uuid:pk>/', views.close_fiscal_year, name='fiscalyear_close'),
] 