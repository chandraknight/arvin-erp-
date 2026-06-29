from django.urls import path
from . import views

app_name = 'manufacturing'

urlpatterns = [
    path('', views.manufacturing_dashboard, name='dashboard'),

    # Bill of Materials
    path('bom/', views.BOMListView.as_view(), name='bom_list'),
    path('bom/create/', views.BOMCreateView.as_view(), name='bom_create'),
    path('bom/<uuid:pk>/', views.BOMDetailView.as_view(), name='bom_detail'),
    path('bom/<uuid:pk>/update/', views.BOMUpdateView.as_view(), name='bom_update'),
    path('bom/<uuid:pk>/delete/', views.BOMDeleteView.as_view(), name='bom_delete'),

    # Work Orders
    path('work-orders/', views.WorkOrderListView.as_view(), name='workorder_list'),
    path('work-orders/create/', views.WorkOrderCreateView.as_view(), name='workorder_create'),
    path('work-orders/<uuid:pk>/', views.WorkOrderDetailView.as_view(), name='workorder_detail'),
    path('work-orders/<uuid:pk>/update/', views.WorkOrderUpdateView.as_view(), name='workorder_update'),
    path('work-orders/<uuid:pk>/start/', views.start_work_order, name='workorder_start'),
    path('work-orders/<uuid:pk>/complete/', views.complete_work_order, name='workorder_complete'),
    path('work-orders/<uuid:pk>/cancel/', views.cancel_work_order, name='workorder_cancel'),
    path('work-orders/<uuid:pk>/materials/', views.update_material_consumption, name='workorder_materials'),

    # Production Runs
    path('production-runs/create/<uuid:wo_pk>/', views.ProductionRunCreateView.as_view(), name='run_create'),
    path('production-runs/<uuid:pk>/', views.ProductionRunDetailView.as_view(), name='run_detail'),

    # Quality Control
    path('quality-checks/create/<uuid:run_pk>/', views.QualityCheckCreateView.as_view(), name='qc_create'),

    # Machines
    path('machines/', views.MachineListView.as_view(), name='machine_list'),
    path('machines/create/', views.MachineCreateView.as_view(), name='machine_create'),
    path('machines/<uuid:pk>/', views.MachineDetailView.as_view(), name='machine_detail'),
    path('machines/<uuid:pk>/update/', views.MachineUpdateView.as_view(), name='machine_update'),
    path('machines/<uuid:pk>/log/', views.MachineLogCreateView.as_view(), name='machine_log'),

    # Reports
    path('reports/production/', views.production_report, name='production_report'),
    path('reports/material-consumption/', views.material_consumption_report, name='material_report'),
]
