from django.contrib import admin
from .models import (
    BillOfMaterials, BOMItem, WorkOrder, WorkOrderMaterial,
    ProductionRun, QualityCheck, Machine, MachineLog,
)


@admin.register(BillOfMaterials)
class BillOfMaterialsAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company')
    list_filter = ('company',)


@admin.register(BOMItem)
class BOMItemAdmin(admin.ModelAdmin):
    list_display = ('__str__',)


@admin.register(WorkOrder)
class WorkOrderAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company', 'fiscal_year')
    list_filter = ('company', 'fiscal_year')


@admin.register(WorkOrderMaterial)
class WorkOrderMaterialAdmin(admin.ModelAdmin):
    list_display = ('__str__',)


@admin.register(ProductionRun)
class ProductionRunAdmin(admin.ModelAdmin):
    list_display = ('__str__',)


@admin.register(QualityCheck)
class QualityCheckAdmin(admin.ModelAdmin):
    list_display = ('__str__',)


@admin.register(Machine)
class MachineAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company')
    list_filter = ('company',)


@admin.register(MachineLog)
class MachineLogAdmin(admin.ModelAdmin):
    list_display = ('__str__',)
