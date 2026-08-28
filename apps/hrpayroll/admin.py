from django.contrib import admin
from .models import (
    Department, Employee, Earning, Deduction,
    PayrollRun, Payslip, PayslipEarning, PayslipDeduction,
    Attendance, JobPosition, JobApplication, Interview,
    LeaveType, LeaveBalance, LeaveRequest, EmployeeDocument,
    PerformanceReview, EmployeeNote, Separation, IncomeTaxSlab,
    SSFContribution,
)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company')
    list_filter = ('company',)


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company')
    list_filter = ('company',)


@admin.register(Earning)
class EarningAdmin(admin.ModelAdmin):
    list_display = ('__str__',)


@admin.register(Deduction)
class DeductionAdmin(admin.ModelAdmin):
    list_display = ('__str__',)


@admin.register(PayrollRun)
class PayrollRunAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company', 'fiscal_year')
    list_filter = ('company', 'fiscal_year')


@admin.register(Payslip)
class PayslipAdmin(admin.ModelAdmin):
    list_display = ('__str__',)


@admin.register(PayslipEarning)
class PayslipEarningAdmin(admin.ModelAdmin):
    list_display = ('__str__',)


@admin.register(PayslipDeduction)
class PayslipDeductionAdmin(admin.ModelAdmin):
    list_display = ('__str__',)


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('__str__',)


@admin.register(JobPosition)
class JobPositionAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company')
    list_filter = ('company',)


@admin.register(JobApplication)
class JobApplicationAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company')
    list_filter = ('company',)


@admin.register(Interview)
class InterviewAdmin(admin.ModelAdmin):
    list_display = ('__str__',)


@admin.register(LeaveType)
class LeaveTypeAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company')
    list_filter = ('company',)


@admin.register(LeaveBalance)
class LeaveBalanceAdmin(admin.ModelAdmin):
    list_display = ('__str__',)


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ('__str__',)


@admin.register(EmployeeDocument)
class EmployeeDocumentAdmin(admin.ModelAdmin):
    list_display = ('__str__',)


@admin.register(PerformanceReview)
class PerformanceReviewAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company')
    list_filter = ('company',)


@admin.register(EmployeeNote)
class EmployeeNoteAdmin(admin.ModelAdmin):
    list_display = ('__str__',)


@admin.register(Separation)
class SeparationAdmin(admin.ModelAdmin):
    list_display = ('__str__',)


@admin.register(IncomeTaxSlab)
class IncomeTaxSlabAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company', 'fiscal_year')
    list_filter = ('company', 'fiscal_year')


@admin.register(SSFContribution)
class SSFContributionAdmin(admin.ModelAdmin):
    list_display = ('__str__',)
