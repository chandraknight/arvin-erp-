from django.urls import path
from . import views

app_name = 'products'

urlpatterns = [
    path('inventory/', views.inventory_management, name='inventory_management'),
    path('inventory/all-products/', views.all_products, name='all_products'),
    path('inventory/add-item/', views.add_item, name='add_item'),
    path('inventory/edit-item/<uuid:id>/', views.edit_item, name='edit_item'),

    path('inventory/add-category-type/', views.create_categorytype, name='add_category_type'),
    path('inventory/update-stock/<uuid:item_id>/', views.update_stock, name='update_stock'),
    path('inventory/add-category/', views.add_category, name='add_category'),
    path('inventory/edit-category/<uuid:category_id>/', views.edit_category, name='edit_category'),

    path('inventory/edit-category-type/<uuid:id>/', views.edit_category_type, name='edit_category_type'),
    path('inventory/add-package/', views.create_package, name='create_package'),
    path('inventory/edit-package/<uuid:package_id>/', views.update_package, name='edit_package'),
    path('inventory/delete-package/<uuid:package_id>/', views.delete_package, name='delete_package'),
    path('api/search-products/', views.search_items_by_barcode, name='search_products_api'),
    # path('reports/stock-movement/', views.stock_movement_report, name='stock_movement_report'), # This has been migrated to the reports app
    path('advanced-inventory-analytics/', views.advanced_inventory_analytics, name='advanced_inventory_analytics'),

    # Bulk product upload
    path('inventory/bulk-upload/', views.bulk_product_upload, name='bulk_product_upload'),
    path('inventory/bulk-upload/sample/', views.bulk_product_sample_csv, name='bulk_product_sample_csv'),
    path('inventory/bulk-upload/export/', views.bulk_product_export, name='bulk_product_export'),
    path('inventory/print-labels/', views.print_labels_selector, name='print_labels'),
    path('inventory/print-labels/generate/', views.print_labels, name='print_labels_generate'),

    # Units of Measure
    path('inventory/units/', views.uom_list, name='uom_list'),
    path('inventory/units/create/', views.uom_create, name='uom_create'),
    path('inventory/units/<uuid:pk>/delete/', views.uom_delete, name='uom_delete'),

    # Product Variants
    path('inventory/<uuid:product_id>/variants/', views.variant_list, name='variant_list'),
    path('inventory/<uuid:product_id>/variants/create/', views.variant_create, name='variant_create'),
    path('inventory/variants/<uuid:variant_id>/stock/', views.variant_update_stock, name='variant_update_stock'),
    path('inventory/variants/<uuid:variant_id>/delete/', views.variant_delete, name='variant_delete'),
]