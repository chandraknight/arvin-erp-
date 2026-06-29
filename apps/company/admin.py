from django.contrib import admin
from .models import Company, Branch, FiscalYear


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'organisation_type',
        'enable_pos', 'enable_inventory', 'enable_hr_payroll',
        'enable_purchasing', 'enable_order_management',
        'enable_restaurant', 'enable_manufacturing', 'enable_tours',
        'enable_project_tracking',
    )
    list_editable = (
        'enable_pos', 'enable_inventory', 'enable_hr_payroll',
        'enable_purchasing', 'enable_order_management',
        'enable_restaurant', 'enable_manufacturing', 'enable_tours',
        'enable_project_tracking',
    )
    list_filter = ('organisation_type',)
    search_fields = ('name',)
    fieldsets = (
        (None, {
            'fields': ('name', 'organisation_type'),
        }),
        ('Modules', {
            'fields': (
                'enable_pos',
                'enable_inventory',
                'enable_hr_payroll',
                'enable_purchasing',
                'enable_order_management',
                'enable_restaurant',
                'enable_manufacturing',
                'enable_tours',
                'enable_project_tracking',
                'enable_forecasting',
                'enable_branch_accounting',
            ),
        }),
    )


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ('name', 'company')
    list_filter = ('company',)
    search_fields = ('name',)


@admin.register(FiscalYear)
class FiscalYearAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company', 'start_date', 'end_date', 'is_active')
    list_filter = ('company', 'is_active')
