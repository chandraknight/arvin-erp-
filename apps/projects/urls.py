from django.urls import path
from . import views

app_name = 'projects'

urlpatterns = [
    # Dashboard
    path('', views.project_dashboard, name='dashboard'),

    # Cost Centres
    path('cost-centres/', views.CostCentreListView.as_view(), name='costcentre_list'),
    path('cost-centres/create/', views.CostCentreCreateView.as_view(), name='costcentre_create'),
    path('cost-centres/<uuid:pk>/update/', views.CostCentreUpdateView.as_view(), name='costcentre_update'),
    path('cost-centres/<uuid:pk>/delete/', views.CostCentreDeleteView.as_view(), name='costcentre_delete'),

    # Projects
    path('projects/', views.ProjectListView.as_view(), name='project_list'),
    path('projects/create/', views.ProjectCreateView.as_view(), name='project_create'),
    path('projects/<uuid:pk>/', views.ProjectDetailView.as_view(), name='project_detail'),
    path('projects/<uuid:pk>/update/', views.ProjectUpdateView.as_view(), name='project_update'),
    path('projects/<uuid:pk>/delete/', views.ProjectDeleteView.as_view(), name='project_delete'),
    path('projects/<uuid:pk>/status/', views.project_change_status, name='project_change_status'),

    # Tasks
    path('projects/<uuid:project_pk>/tasks/create/', views.task_create, name='task_create'),
    path('tasks/<uuid:pk>/status/', views.task_update_status, name='task_update_status'),
    path('tasks/<uuid:pk>/delete/', views.task_delete, name='task_delete'),

    # Milestones
    path('projects/<uuid:project_pk>/milestones/create/', views.milestone_create, name='milestone_create'),
    path('milestones/<uuid:pk>/complete/', views.milestone_complete, name='milestone_complete'),
    path('milestones/<uuid:pk>/delete/', views.milestone_delete, name='milestone_delete'),

    # Time Logs
    path('projects/<uuid:project_pk>/timelogs/create/', views.timelog_create, name='timelog_create'),
    path('timelogs/', views.TimeLogListView.as_view(), name='timelog_list'),
    path('timelogs/<uuid:pk>/delete/', views.timelog_delete, name='timelog_delete'),

    # Risks
    path('projects/<uuid:project_pk>/risks/create/', views.risk_create, name='risk_create'),
    path('risks/<uuid:pk>/update/', views.risk_update, name='risk_update'),
    path('risks/<uuid:pk>/delete/', views.risk_delete, name='risk_delete'),

    # Documents
    path('projects/<uuid:project_pk>/documents/upload/', views.document_upload, name='document_upload'),
    path('documents/<uuid:pk>/delete/', views.document_delete, name='document_delete'),

    # Project Expenses
    path('expenses/', views.ProjectExpenseListView.as_view(), name='expense_list'),
    path('expenses/create/', views.ProjectExpenseCreateView.as_view(), name='expense_create'),
    path('expenses/<uuid:pk>/update/', views.ProjectExpenseUpdateView.as_view(), name='expense_update'),
    path('expenses/<uuid:pk>/delete/', views.ProjectExpenseDeleteView.as_view(), name='expense_delete'),

    # Project Revenue
    path('revenues/create/', views.ProjectRevenueCreateView.as_view(), name='revenue_create'),
    path('revenues/<uuid:pk>/delete/', views.ProjectRevenueDeleteView.as_view(), name='revenue_delete'),

    # Budgets
    path('budgets/', views.BudgetListView.as_view(), name='budget_list'),
    path('budgets/create/', views.BudgetCreateView.as_view(), name='budget_create'),
    path('budgets/<uuid:pk>/update/', views.BudgetUpdateView.as_view(), name='budget_update'),
    path('budgets/<uuid:pk>/delete/', views.BudgetDeleteView.as_view(), name='budget_delete'),
    path('budgets/<uuid:pk>/revise/', views.budget_revise, name='budget_revise'),
    path('budgets/vs-actual/', views.budget_vs_actual_report, name='budget_vs_actual'),

    # Forecasts
    path('forecasts/', views.ForecastListView.as_view(), name='forecast_list'),
    path('forecasts/create/', views.ForecastCreateView.as_view(), name='forecast_create'),
    path('forecasts/<uuid:pk>/update/', views.ForecastUpdateView.as_view(), name='forecast_update'),
    path('forecasts/<uuid:pk>/delete/', views.ForecastDeleteView.as_view(), name='forecast_delete'),
    path('forecasts/vs-actual/', views.forecast_vs_actual_report, name='forecast_vs_actual'),
]
