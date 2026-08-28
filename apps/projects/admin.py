from django.contrib import admin
from .models import (
    CostCentre, Project, ProjectTask, ProjectMilestone,
    ProjectTimeLog, ProjectRisk, ProjectDocument, ProjectExpense,
    ProjectRevenue, Budget, BudgetRevision, Forecast,
)


@admin.register(CostCentre)
class CostCentreAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company')
    list_filter = ('company',)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company')
    list_filter = ('company',)


@admin.register(ProjectTask)
class ProjectTaskAdmin(admin.ModelAdmin):
    list_display = ('__str__',)


@admin.register(ProjectMilestone)
class ProjectMilestoneAdmin(admin.ModelAdmin):
    list_display = ('__str__',)


@admin.register(ProjectTimeLog)
class ProjectTimeLogAdmin(admin.ModelAdmin):
    list_display = ('__str__',)


@admin.register(ProjectRisk)
class ProjectRiskAdmin(admin.ModelAdmin):
    list_display = ('__str__',)


@admin.register(ProjectDocument)
class ProjectDocumentAdmin(admin.ModelAdmin):
    list_display = ('__str__',)


@admin.register(ProjectExpense)
class ProjectExpenseAdmin(admin.ModelAdmin):
    list_display = ('__str__',)


@admin.register(ProjectRevenue)
class ProjectRevenueAdmin(admin.ModelAdmin):
    list_display = ('__str__',)


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company', 'fiscal_year')
    list_filter = ('company', 'fiscal_year')


@admin.register(BudgetRevision)
class BudgetRevisionAdmin(admin.ModelAdmin):
    list_display = ('__str__',)


@admin.register(Forecast)
class ForecastAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company', 'fiscal_year')
    list_filter = ('company', 'fiscal_year')
