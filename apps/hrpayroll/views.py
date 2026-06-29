import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib import messages
from django.db import transaction
from decimal import Decimal
from datetime import timedelta
from django.http import HttpResponse
from django.template.loader import render_to_string
from apps.utils.htmx import is_htmx, toast_trigger
from django.core.exceptions import PermissionDenied

from .models import Department, Employee, Earning, Deduction, PayrollRun, Payslip, PayslipEarning, PayslipDeduction, Attendance
from .forms import DepartmentForm, EmployeeForm, EarningForm, DeductionForm, PayrollRunForm, AttendanceForm, PayslipForm

# Custom permission mixin for HR payroll views
class HRPayrollPermissionMixin:
    """
    Permission mixin for all HR/Payroll views.

    Access rules (in order):
      1. Unauthenticated → redirect to login
      2. Company has enable_hr_payroll=False → redirect to dashboard
      3. Superuser → always allowed
      4. is_company_admin → allowed
      5. Has the required Django permission → allowed
      6. Otherwise → 403
    """
    permission_required = None

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        # Module guard — block access if HR/Payroll is disabled for this company
        company = getattr(request, 'user_company', None)
        if company and not getattr(company, 'enable_hr_payroll', False):
            from django.contrib import messages
            from django.shortcuts import redirect
            messages.warning(request, "HR & Payroll module is not enabled for your company.")
            return redirect('accounts:user_dashboard')

        if request.user.is_superuser:
            return super().dispatch(request, *args, **kwargs)

        if getattr(request.user, 'is_company_admin', False):
            return super().dispatch(request, *args, **kwargs)

        if self.permission_required:
            perms = [self.permission_required] if isinstance(self.permission_required, str) else self.permission_required
            if request.user.has_perms(perms):
                return super().dispatch(request, *args, **kwargs)

        raise PermissionDenied

# Create your views here.

# Department Views
class DepartmentListView(LoginRequiredMixin, HRPayrollPermissionMixin, ListView):
    model = Department
    template_name = 'hrpayroll/department_list.html'
    context_object_name = 'departments'
    permission_required = 'hrpayroll.view_department'

    def get_queryset(self):
        if self.request.user.is_superuser:
            return Department.active_objects.all().order_by('name')
        return Department.active_objects.filter(
            company=self.request.user.company
        ).order_by('name')

class DepartmentCreateView(LoginRequiredMixin, HRPayrollPermissionMixin, CreateView):
    model = Department
    form_class = DepartmentForm
    template_name = 'hrpayroll/department_form.html'
    success_url = reverse_lazy('hrpayroll:department_list')
    permission_required = 'hrpayroll.add_department'

    def form_valid(self, form):
        messages.success(self.request, "Department created successfully.")
        return super().form_valid(form)

class DepartmentUpdateView(LoginRequiredMixin, HRPayrollPermissionMixin, UpdateView):
    model = Department
    form_class = DepartmentForm
    template_name = 'hrpayroll/department_form.html'
    context_object_name = 'department'
    permission_required = 'hrpayroll.change_department'
    success_url = reverse_lazy('hrpayroll:department_list')

    def form_valid(self, form):
        messages.success(self.request, "Department updated successfully.")
        return super().form_valid(form)

class DepartmentDeleteView(LoginRequiredMixin, HRPayrollPermissionMixin, DeleteView):
    model = Department
    template_name = 'hrpayroll/department_confirm_delete.html'
    context_object_name = 'department'
    success_url = reverse_lazy('hrpayroll:department_list')
    permission_required = 'hrpayroll.delete_department'

    def form_valid(self, form):
        messages.success(self.request, "Department deleted successfully.")
        return super().form_valid(form)

# Employee Views
class EmployeeListView(LoginRequiredMixin, HRPayrollPermissionMixin, ListView):
    model = Employee
    template_name = 'hrpayroll/employee_list.html'
    context_object_name = 'employees'
    permission_required = 'hrpayroll.view_employee'
    paginate_by = 20

    def get_queryset(self):
        from django.db.models import Q
        if self.request.user.is_superuser:
            qs = Employee.active_objects.all()
        else:
            qs = Employee.active_objects.filter(company=self.request.user.company)

        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(first_name__icontains=q) |
                Q(last_name__icontains=q) |
                Q(email__icontains=q) |
                Q(position__icontains=q)
            )

        dept = self.request.GET.get('department', '').strip()
        if dept:
            qs = qs.filter(department_id=dept)

        active = self.request.GET.get('is_active', '').strip()
        if active == '1':
            qs = qs.filter(is_active=True)
        elif active == '0':
            qs = qs.filter(is_active=False)

        return qs.select_related('department').order_by('first_name', 'last_name')

    def get_template_names(self):
        from apps.utils.htmx import is_htmx
        if is_htmx(self.request):
            return ['hrpayroll/partials/employee_table.html']
        return [self.template_name]

    def get_context_data(self, **kwargs):
        from apps.hrpayroll.models import Department
        context = super().get_context_data(**kwargs)
        context['q'] = self.request.GET.get('q', '')
        context['department'] = self.request.GET.get('department', '')
        context['is_active'] = self.request.GET.get('is_active', '')
        context['departments'] = Department.active_objects.all().order_by('name')
        return context

class EmployeeCreateView(LoginRequiredMixin, HRPayrollPermissionMixin, CreateView):
    model = Employee
    form_class = EmployeeForm
    template_name = 'hrpayroll/employee_form.html'
    success_url = reverse_lazy('hrpayroll:employee_list')
    permission_required = 'hrpayroll.add_employee'

    def form_valid(self, form):
        if not self.request.user.is_superuser:
            form.instance.company = self.request.user.company
        messages.success(self.request, "Employee created successfully.")
        return super().form_valid(form)

class EmployeeUpdateView(LoginRequiredMixin, HRPayrollPermissionMixin, UpdateView):
    model = Employee
    form_class = EmployeeForm
    template_name = 'hrpayroll/employee_form.html'
    context_object_name = 'employee'
    permission_required = 'hrpayroll.change_employee'
    success_url = reverse_lazy('hrpayroll:employee_list')

    def get_queryset(self):
        if self.request.user.is_superuser:
            return Employee.objects.all()
        return Employee.objects.filter(company=self.request.user.company)

    def form_valid(self, form):
        messages.success(self.request, "Employee updated successfully.")
        return super().form_valid(form)

class EmployeeDeleteView(LoginRequiredMixin, HRPayrollPermissionMixin, DeleteView):
    model = Employee
    template_name = 'hrpayroll/employee_confirm_delete.html'
    context_object_name = 'employee'
    success_url = reverse_lazy('hrpayroll:employee_list')
    permission_required = 'hrpayroll.delete_employee'

    def get_queryset(self):
        if self.request.user.is_superuser:
            return Employee.objects.all()
        return Employee.objects.filter(company=self.request.user.company)

    def form_valid(self, form):
        name = str(self.get_object())
        result = super().form_valid(form)
        if is_htmx(self.request):
            response = HttpResponse(status=200, content='')
            response['HX-Trigger'] = json.dumps(toast_trigger('success', f'Employee "{name}" deleted.'))
            return response
        messages.success(self.request, "Employee deleted successfully.")
        return result

# Earning Views
class EarningListView(LoginRequiredMixin, HRPayrollPermissionMixin, ListView):
    model = Earning
    template_name = 'hrpayroll/earning_list.html'
    context_object_name = 'earnings'
    permission_required = 'hrpayroll.view_earning'

class EarningCreateView(LoginRequiredMixin, HRPayrollPermissionMixin, CreateView):
    model = Earning
    form_class = EarningForm
    template_name = 'hrpayroll/earning_form.html'
    success_url = reverse_lazy('hrpayroll:earning_list')
    permission_required = 'hrpayroll.add_earning'

    def form_valid(self, form):
        messages.success(self.request, "Earning created successfully.")
        return super().form_valid(form)

class EarningUpdateView(LoginRequiredMixin, HRPayrollPermissionMixin, UpdateView):
    model = Earning
    form_class = EarningForm
    template_name = 'hrpayroll/earning_form.html'
    context_object_name = 'earning'
    permission_required = 'hrpayroll.change_earning'
    success_url = reverse_lazy('hrpayroll:earning_list')

    def form_valid(self, form):
        messages.success(self.request, "Earning updated successfully.")
        return super().form_valid(form)

class EarningDeleteView(LoginRequiredMixin, HRPayrollPermissionMixin, DeleteView):
    model = Earning
    template_name = 'hrpayroll/earning_confirm_delete.html'
    context_object_name = 'earning'
    success_url = reverse_lazy('hrpayroll:earning_list')
    permission_required = 'hrpayroll.delete_earning'

    def form_valid(self, form):
        messages.success(self.request, "Earning deleted successfully.")
        return super().form_valid(form)

# Deduction Views
class DeductionListView(LoginRequiredMixin, HRPayrollPermissionMixin, ListView):
    model = Deduction
    template_name = 'hrpayroll/deduction_list.html'
    context_object_name = 'deductions'
    permission_required = 'hrpayroll.view_deduction'

class DeductionCreateView(LoginRequiredMixin, HRPayrollPermissionMixin, CreateView):
    model = Deduction
    form_class = DeductionForm
    template_name = 'hrpayroll/deduction_form.html'
    success_url = reverse_lazy('hrpayroll:deduction_list')
    permission_required = 'hrpayroll.add_deduction'

    def form_valid(self, form):
        messages.success(self.request, "Deduction created successfully.")
        return super().form_valid(form)

class DeductionUpdateView(LoginRequiredMixin, HRPayrollPermissionMixin, UpdateView):
    model = Deduction
    form_class = DeductionForm
    template_name = 'hrpayroll/deduction_form.html'
    context_object_name = 'deduction'
    permission_required = 'hrpayroll.change_deduction'
    success_url = reverse_lazy('hrpayroll:deduction_list')

    def form_valid(self, form):
        messages.success(self.request, "Deduction updated successfully.")
        return super().form_valid(form)

class DeductionDeleteView(LoginRequiredMixin, HRPayrollPermissionMixin, DeleteView):
    model = Deduction
    template_name = 'hrpayroll/deduction_confirm_delete.html'
    context_object_name = 'deduction'
    success_url = reverse_lazy('hrpayroll:deduction_list')
    permission_required = 'hrpayroll.delete_deduction'

    def form_valid(self, form):
        messages.success(self.request, "Deduction deleted successfully.")
        return super().form_valid(form)

# Payroll Run Views
class PayrollRunListView(LoginRequiredMixin, HRPayrollPermissionMixin, ListView):
    model = PayrollRun
    template_name = 'hrpayroll/payrollrun_list.html'
    context_object_name = 'payroll_runs'
    permission_required = 'hrpayroll.view_payrollrun'
    paginate_by = 20

    def get_queryset(self):
        if self.request.user.is_superuser:
            qs = PayrollRun.active_objects.all()
        else:
            qs = PayrollRun.active_objects.filter(company=self.request.user.company)

        status = self.request.GET.get('status', '').strip()
        if status:
            qs = qs.filter(status=status)

        return qs.select_related('company').order_by('-period_start_date')

    def get_template_names(self):
        from apps.utils.htmx import is_htmx
        if is_htmx(self.request):
            return ['hrpayroll/partials/payrollrun_table.html']
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status'] = self.request.GET.get('status', '')
        return context

class PayrollRunCreateView(LoginRequiredMixin, HRPayrollPermissionMixin, CreateView):
    model = PayrollRun
    form_class = PayrollRunForm
    template_name = 'hrpayroll/payrollrun_form.html'
    success_url = reverse_lazy('hrpayroll:payrollrun_list')
    permission_required = 'hrpayroll.add_payrollrun'

    def form_valid(self, form):
        if not self.request.user.is_superuser:
            form.instance.company = self.request.user.company
        messages.success(self.request, "Payroll run created successfully.")
        return super().form_valid(form)

class PayrollRunUpdateView(LoginRequiredMixin, HRPayrollPermissionMixin, UpdateView):
    model = PayrollRun
    form_class = PayrollRunForm
    template_name = 'hrpayroll/payrollrun_form.html'
    context_object_name = 'payroll_run'
    permission_required = 'hrpayroll.change_payrollrun'
    success_url = reverse_lazy('hrpayroll:payrollrun_list')

    def get_queryset(self):
        if self.request.user.is_superuser:
            return PayrollRun.objects.all()
        return PayrollRun.objects.filter(company=self.request.user.company)

    def form_valid(self, form):
        messages.success(self.request, "Payroll run updated successfully.")
        return super().form_valid(form)

class PayrollRunDeleteView(LoginRequiredMixin, HRPayrollPermissionMixin, DeleteView):
    model = PayrollRun
    template_name = 'hrpayroll/payrollrun_confirm_delete.html'
    context_object_name = 'payroll_run'
    success_url = reverse_lazy('hrpayroll:payrollrun_list')
    permission_required = 'hrpayroll.delete_payrollrun'

    def get_queryset(self):
        if self.request.user.is_superuser:
            return PayrollRun.objects.all()
        return PayrollRun.objects.filter(company=self.request.user.company)

    def form_valid(self, form):
        result = super().form_valid(form)
        if is_htmx(self.request):
            response = HttpResponse(status=200, content='')
            response['HX-Trigger'] = json.dumps(toast_trigger('success', 'Payroll run deleted.'))
            return response
        messages.success(self.request, "Payroll run deleted successfully.")
        return result

# Payslip Views
class PayslipListView(LoginRequiredMixin, HRPayrollPermissionMixin, ListView):
    model = Payslip
    template_name = 'hrpayroll/payslip_list.html'
    context_object_name = 'payslips'
    permission_required = 'hrpayroll.view_payslip'
    paginate_by = 20

    def get_queryset(self):
        from django.db.models import Q
        if self.request.user.is_superuser:
            qs = Payslip.active_objects.all()
        else:
            qs = Payslip.active_objects.filter(
                payroll_run__company=self.request.user.company
            )

        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(employee__first_name__icontains=q) |
                Q(employee__last_name__icontains=q) |
                Q(employee__email__icontains=q)
            )

        return qs.select_related('employee', 'payroll_run').order_by('-payroll_run__period_start_date')

    def get_template_names(self):
        from apps.utils.htmx import is_htmx
        if is_htmx(self.request):
            return ['hrpayroll/partials/payslip_table.html']
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['q'] = self.request.GET.get('q', '')
        return context

class PayslipDetailView(LoginRequiredMixin, HRPayrollPermissionMixin, DetailView):
    model = Payslip
    template_name = 'hrpayroll/payslip_detail.html'
    context_object_name = 'payslip'
    permission_required = 'hrpayroll.view_payslip'

    def get_queryset(self):
        if self.request.user.is_superuser:
            return Payslip.objects.all()
        return Payslip.objects.filter(payroll_run__company=self.request.user.company).select_related('employee', 'payroll_run')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['earnings'] = self.object.payslip_earnings.all()
        context['deductions'] = self.object.payslip_deductions.all()
        return context

class PayslipCreateView(LoginRequiredMixin, HRPayrollPermissionMixin, CreateView):
    model = Payslip
    form_class = PayslipForm
    template_name = 'hrpayroll/payslip_form.html'
    success_url = reverse_lazy('hrpayroll:payslip_list')
    permission_required = 'hrpayroll.add_payslip'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if not self.request.user.is_superuser:
            kwargs['payroll_run_queryset'] = PayrollRun.objects.filter(company=self.request.user.company)
            kwargs['employee_queryset'] = Employee.objects.filter(company=self.request.user.company)
        return kwargs

    def form_valid(self, form):
        # Validate company isolation — non-superusers cannot create payslips for other companies
        if not self.request.user.is_superuser:
            run_company = form.instance.payroll_run.company if form.instance.payroll_run else None
            if run_company != self.request.user.company:
                from django.core.exceptions import PermissionDenied
                raise PermissionDenied

        employee_salary = form.instance.employee.salary if form.instance.employee.salary else Decimal('0.00')
        form.instance.gross_pay = employee_salary
        form.instance.total_deductions = Decimal('0.00')
        form.instance.net_pay = form.instance.gross_pay - form.instance.total_deductions

        messages.success(self.request, "Payslip created successfully.")
        return super().form_valid(form)

class PayslipUpdateView(LoginRequiredMixin, HRPayrollPermissionMixin, UpdateView):
    model = Payslip
    form_class = PayslipForm
    template_name = 'hrpayroll/payslip_form.html'
    context_object_name = 'payslip'
    success_url = reverse_lazy('hrpayroll:payslip_list')
    permission_required = 'hrpayroll.change_payslip'

    def get_queryset(self):
        if self.request.user.is_superuser:
            return Payslip.objects.all()
        return Payslip.objects.filter(payroll_run__company=self.request.user.company)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if not self.request.user.is_superuser:
            kwargs['payroll_run_queryset'] = PayrollRun.objects.filter(company=self.request.user.company)
            kwargs['employee_queryset'] = Employee.objects.filter(company=self.request.user.company)
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Payslip updated successfully.")
        return super().form_valid(form)

class PayslipDeleteView(LoginRequiredMixin, HRPayrollPermissionMixin, DeleteView):
    model = Payslip
    template_name = 'hrpayroll/payslip_confirm_delete.html'
    context_object_name = 'payslip'
    success_url = reverse_lazy('hrpayroll:payslip_list')
    permission_required = 'hrpayroll.delete_payslip'

    def get_queryset(self):
        if self.request.user.is_superuser:
            return Payslip.objects.all()
        return Payslip.objects.filter(payroll_run__company=self.request.user.company)

    def form_valid(self, form):
        messages.success(self.request, "Payslip deleted successfully.")
        return super().form_valid(form)

# Attendance Views
class AttendanceListView(LoginRequiredMixin, HRPayrollPermissionMixin, ListView):
    model = Attendance
    template_name = 'hrpayroll/attendance_list.html'
    context_object_name = 'attendance_records'
    permission_required = 'hrpayroll.view_attendance'
    paginate_by = 30

    def get_queryset(self):
        from django.db.models import Q
        if self.request.user.is_superuser:
            qs = Attendance.active_objects.all()
        else:
            qs = Attendance.active_objects.filter(employee__company=self.request.user.company)

        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(employee__first_name__icontains=q) |
                Q(employee__last_name__icontains=q)
            )

        status = self.request.GET.get('status', '').strip()
        if status:
            qs = qs.filter(status=status)

        return qs.select_related('employee').order_by('-date')

    def get_template_names(self):
        from apps.utils.htmx import is_htmx
        if is_htmx(self.request):
            return ['hrpayroll/partials/attendance_table.html']
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['q'] = self.request.GET.get('q', '')
        context['status'] = self.request.GET.get('status', '')
        return context

class AttendanceCreateView(LoginRequiredMixin, HRPayrollPermissionMixin, CreateView):
    model = Attendance
    form_class = AttendanceForm
    template_name = 'hrpayroll/attendance_form.html'
    success_url = reverse_lazy('hrpayroll:attendance_list')
    permission_required = 'hrpayroll.add_attendance'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if not self.request.user.is_superuser:
            kwargs['queryset'] = Employee.objects.filter(company=self.request.user.company)
        return kwargs

    def form_valid(self, form):
        # For non-superusers, ensure employee selected belongs to their company
        if not self.request.user.is_superuser and form.instance.employee.company != self.request.user.company:
            messages.error(self.request, "You can only create attendance for employees in your company.")
            return self.form_invalid(form)
        messages.success(self.request, "Attendance record created successfully.")
        return super().form_valid(form)

class AttendanceUpdateView(LoginRequiredMixin, HRPayrollPermissionMixin, UpdateView):
    model = Attendance
    form_class = AttendanceForm
    template_name = 'hrpayroll/attendance_form.html'
    context_object_name = 'attendance_record'
    permission_required = 'hrpayroll.change_attendance'
    success_url = reverse_lazy('hrpayroll:attendance_list')

    def get_queryset(self):
        if self.request.user.is_superuser:
            return Attendance.objects.all()
        return Attendance.objects.filter(employee__company=self.request.user.company)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if not self.request.user.is_superuser:
            kwargs['queryset'] = Employee.objects.filter(company=self.request.user.company)
        return kwargs

    def form_valid(self, form):
        # For non-superusers, ensure employee selected belongs to their company
        if not self.request.user.is_superuser and form.instance.employee.company != self.request.user.company:
            messages.error(self.request, "You can only update attendance for employees in your company.")
            return self.form_invalid(form)
        messages.success(self.request, "Attendance record updated successfully.")
        return super().form_valid(form)

class AttendanceDeleteView(LoginRequiredMixin, HRPayrollPermissionMixin, DeleteView):
    model = Attendance
    template_name = 'hrpayroll/attendance_confirm_delete.html'
    context_object_name = 'attendance_record'
    success_url = reverse_lazy('hrpayroll:attendance_list')
    permission_required = 'hrpayroll.delete_attendance'

    def get_queryset(self):
        if self.request.user.is_superuser:
            return Attendance.objects.all()
        return Attendance.objects.filter(employee__company=self.request.user.company)

    def form_valid(self, form):
        result = super().form_valid(form)
        if is_htmx(self.request):
            response = HttpResponse(status=200, content='')
            response['HX-Trigger'] = json.dumps(toast_trigger('success', 'Attendance record deleted.'))
            return response
        messages.success(self.request, "Attendance record deleted successfully.")
        return result

def _post_payroll_journal(payroll_run, user):
    """
    Payroll accounting entry when a run is processed:
      DR Salary Expense     (gross payroll cost)
      CR Salary Payable     (liability until disbursed)
    When salaries are actually paid via Payment(payment_type='SALARY'),
    handle_other_payment_journal posts:
      DR Salary Payable / CR Cash/Bank (clearing the liability).
    """
    if not payroll_run.total_gross_pay or payroll_run.total_gross_pay <= 0:
        return
    from apps.bookkeeping.models import JournalEntry, JournalEntryLine
    from apps.company.services.company_services import setup_default_ledger_accounts
    from apps.bookkeeping.models import LedgerAccount

    company = payroll_run.company
    setup_default_ledger_accounts(company)

    salary_expense = LedgerAccount.objects.filter(company=company, name='Salary Expense').first()
    salary_payable = LedgerAccount.objects.filter(company=company, name='Salary Payable').first()

    if not salary_expense or not salary_payable:
        import logging
        logging.getLogger(__name__).error(
            "Missing 'Salary Expense' or 'Salary Payable' ledger for company %s — payroll journal skipped",
            company,
        )
        return

    entry = JournalEntry.objects.create(
        company=company,
        date=payroll_run.payroll_date,
        description=f"Payroll: {payroll_run.period_start_date} – {payroll_run.period_end_date}",
        created_by=user,
    )
    JournalEntryLine.objects.bulk_create([
        JournalEntryLine(journal_entry=entry, account=salary_expense, entry_type='DEBIT',
                         amount=payroll_run.total_gross_pay, narration='Gross payroll cost'),
        JournalEntryLine(journal_entry=entry, account=salary_payable, entry_type='CREDIT',
                         amount=payroll_run.total_gross_pay, narration='Salary payable to employees'),
    ])

    from apps.activity_log.models import ActivityLog
    ActivityLog.log(
        user=user,
        action=ActivityLog.ACTION_CREATE,
        instance=entry,
        object_repr=str(entry),
        changes={'payroll_run_id': str(payroll_run.pk), 'amount': str(payroll_run.total_gross_pay)},
    )


@login_required
@transaction.atomic
def generate_payslips(request, pk):
    # Lock the run row to prevent concurrent double-generation
    payroll_run = PayrollRun.objects.select_for_update().filter(pk=pk).first()
    if not payroll_run:
        messages.error(request, "Payroll run not found.")
        return redirect('hrpayroll:payrollrun_list')

    # Security check: Ensure user can access this payroll run
    if not request.user.is_superuser and payroll_run.company != request.user.company:
        messages.error(request, "You do not have permission to generate payslips for this payroll run.")
        return redirect('hrpayroll:payrollrun_list')

    # Prevent re-generation once approved, processed, or paid
    if payroll_run.status in ['Approved', 'Processed', 'Paid']:
        messages.warning(request, f"Payroll run is already {payroll_run.status}. Cannot re-generate.")
        return redirect('hrpayroll:payrollrun_list')

    # Soft-delete existing payslips so audit trail is preserved
    Payslip.objects.filter(payroll_run=payroll_run).update(is_deleted=True)

    total_gross_pay_run = Decimal('0.00')
    total_net_pay_run = Decimal('0.00')

    employees = list(Employee.objects.filter(company=payroll_run.company, is_active=True))
    employee_ids = [e.id for e in employees]
    total_days_in_period = (payroll_run.period_end_date - payroll_run.period_start_date).days + 1

    # Bulk-fetch all attendance for the period — replaces N per-employee queries
    from django.db.models import Count, Q
    att_counts = (
        Attendance.objects
        .filter(
            employee_id__in=employee_ids,
            date__range=(payroll_run.period_start_date, payroll_run.period_end_date),
        )
        .values('employee_id', 'status')
        .annotate(cnt=Count('id'))
    )
    att_map: dict = {}  # {employee_id: {status: count}}
    for row in att_counts:
        att_map.setdefault(row['employee_id'], {})[row['status']] = row['cnt']

    absent_deduction, _ = Deduction.objects.get_or_create(name='Absent Day Deduction', defaults={'is_pre_tax': False})
    basic_earning, _ = Earning.objects.get_or_create(name='Basic Salary', defaults={'is_taxable': True})

    payslip_deductions_to_create = []
    payslip_earnings_to_create = []

    for employee in employees:
        gross_pay = employee.salary if employee.salary else Decimal('0.00')
        total_deductions = Decimal('0.00')

        statuses = att_map.get(employee.id, {})
        absent_days = statuses.get('Absent', 0)

        daily_rate = Decimal('0.00')
        if employee.salary and total_days_in_period > 0:
            daily_rate = employee.salary / Decimal(str(total_days_in_period))

        absent_amount = Decimal('0.00')
        if absent_days > 0 and daily_rate > 0:
            absent_amount = absent_days * daily_rate
            total_deductions += absent_amount

        net_pay = gross_pay - total_deductions

        payslip = Payslip.objects.create(
            payroll_run=payroll_run,
            employee=employee,
            gross_pay=gross_pay,
            total_deductions=total_deductions,
            net_pay=net_pay,
            issue_date=payroll_run.payroll_date,
            is_finalized=False,
        )

        if absent_amount > 0:
            payslip_deductions_to_create.append(
                PayslipDeduction(payslip=payslip, deduction=absent_deduction, amount=absent_amount)
            )

        payslip_earnings_to_create.append(
            PayslipEarning(payslip=payslip, earning=basic_earning, amount=gross_pay)
        )

        total_gross_pay_run += gross_pay
        total_net_pay_run += net_pay

    PayslipDeduction.objects.bulk_create(payslip_deductions_to_create)
    PayslipEarning.objects.bulk_create(payslip_earnings_to_create)

    payroll_run.total_gross_pay = total_gross_pay_run
    payroll_run.total_net_pay = total_net_pay_run
    payroll_run.status = 'Processed'
    payroll_run.save(update_fields=['total_gross_pay', 'total_net_pay', 'status'])

    # Post payroll journal: DR Salary Expense / CR Salary Payable
    _post_payroll_journal(payroll_run, request.user)

    messages.success(request, f"Payslips generated successfully for Payroll Run: {payroll_run}.")
    return redirect('hrpayroll:payslip_list')

# Reports Views
class PayrollSummaryReportView(LoginRequiredMixin, HRPayrollPermissionMixin, ListView):
    model = PayrollRun
    template_name = 'hrpayroll/payroll_summary_report.html'
    context_object_name = 'payroll_runs'
    permission_required = 'hrpayroll.view_payrollrun' # Reusing this permission for now

    def get_queryset(self):
        queryset = super().get_queryset()
        if not self.request.user.is_superuser:
            queryset = queryset.filter(company=self.request.user.company)

        # Optional: Add filtering by year/month if needed for large datasets
        return queryset.order_by('-period_start_date')

class MonthlyAttendanceReportView(LoginRequiredMixin, HRPayrollPermissionMixin, ListView):
    model = Attendance
    template_name = 'hrpayroll/monthly_attendance_report.html'
    context_object_name = 'attendance_summary'
    permission_required = 'hrpayroll.view_attendance'

    def get_queryset(self):
        queryset = Attendance.objects.all()
        if not self.request.user.is_superuser:
            queryset = queryset.filter(employee__company=self.request.user.company)

        employee_id = self.request.GET.get('employee')
        month = self.request.GET.get('month')
        year = self.request.GET.get('year')

        if employee_id:
            queryset = queryset.filter(employee__id=employee_id)
        if month and year:
            queryset = queryset.filter(date__year=year, date__month=month)

        # Group by employee and month/year to get summary
        # This requires more complex aggregation, so for simplicity initially, 
        # we'll return raw attendance records and process in template or a helper.
        # A better approach for true summary would involve annotations or custom managers.
        return queryset.order_by('employee__last_name', 'date')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add employees for the filter dropdown
        if self.request.user.is_superuser:
            context['employees'] = Employee.objects.all()
        else:
            context['employees'] = Employee.objects.filter(company=self.request.user.company)
        
        # Add current year for the year input default
        from datetime import datetime
        context['current_year'] = datetime.now().year
        
        return context

@login_required
def download_payslip_pdf(request, pk):
    # payslip = get_object_or_404(Payslip, pk=pk)
    #
    # # Security check
    # if not request.user.is_superuser and payslip.payroll_run.company != request.user.company and payslip.employee.id != request.user.employee.id:
    #     messages.error(request, "You do not have permission to view this payslip.")
    #     return redirect('hrpayroll:payslip_list')
    #
    # # Render the HTML template with payslip data
    # html_string = render_to_string('hrpayroll/payslip_pdf_template.html', {'payslip': payslip})
    #
    # # Generate PDF using WeasyPrint
    # # html = HTML(string=html_string)
    # # pdf = html.write_pdf()
    #
    # # response = HttpResponse(pdf, content_type='application/pdf')
    # response['Content-Disposition'] = f'inline; filename="payslip_{payslip.employee.last_name}_{payslip.issue_date}.pdf"'
    # return response
    from django.http import HttpResponse
    return HttpResponse("PDF generation not yet implemented.", status=501)


# ── New imports for extended HR ───────────────────────────────────────────────
from .models import (
    JobPosition, JobApplication, Interview,
    LeaveType, LeaveRequest, LeaveBalance,
    EmployeeDocument, PerformanceReview, EmployeeNote, Separation,
    JOB_STATUS_CHOICES,
)
from .forms import (
    JobPositionForm, JobApplicationForm, InterviewForm,
    LeaveTypeForm, LeaveRequestForm,
    EmployeeDocumentForm, PerformanceReviewForm, EmployeeNoteForm, SeparationForm,
)


# ── Employee Detail (profile page) ───────────────────────────────────────────

class EmployeeDetailView(LoginRequiredMixin, HRPayrollPermissionMixin, DetailView):
    model = Employee
    template_name = 'hrpayroll/employee_detail.html'
    context_object_name = 'employee'
    permission_required = 'hrpayroll.view_employee'

    def get_queryset(self):
        if self.request.user.is_superuser:
            return Employee.objects.all()
        return Employee.objects.filter(company=self.request.user.company)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        emp = self.object
        context['documents'] = emp.documents.filter(is_deleted=False).order_by('document_type')
        context['hr_notes'] = emp.hr_notes.filter(is_deleted=False).order_by('-created_at')
        context['reviews'] = emp.performance_reviews.filter(is_deleted=False).order_by('-review_period_end')
        context['leave_requests'] = emp.leave_requests.filter(is_deleted=False).order_by('-start_date')[:10]
        context['leave_balances'] = emp.leave_balances.filter(is_deleted=False).select_related('leave_type')
        context['separation'] = getattr(emp, 'separation', None)
        context['recent_attendance'] = emp.attendance_records.filter(
            is_deleted=False
        ).order_by('-date')[:30]
        return context


# ── Recruitment — Job Positions ───────────────────────────────────────────────

class JobPositionListView(LoginRequiredMixin, HRPayrollPermissionMixin, ListView):
    model = JobPosition
    template_name = 'hrpayroll/recruitment/job_position_list.html'
    context_object_name = 'positions'
    permission_required = 'hrpayroll.view_jobposition'
    paginate_by = 20

    def get_queryset(self):
        from django.db.models import Count, Q
        qs = JobPosition.active_objects.all() if self.request.user.is_superuser \
            else JobPosition.active_objects.filter(company=self.request.user.company)
        status = self.request.GET.get('status', '').strip()
        if status:
            qs = qs.filter(status=status)
        # Annotate counts to avoid N+1 on template property access
        return qs.select_related('department').annotate(
            app_count=Count('applications', distinct=True),
            hired_count_db=Count('applications', filter=Q(applications__status='HIRED'), distinct=True),
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['status'] = self.request.GET.get('status', '')
        ctx['job_status_choices'] = JOB_STATUS_CHOICES
        return ctx


class JobPositionCreateView(LoginRequiredMixin, HRPayrollPermissionMixin, CreateView):
    model = JobPosition
    form_class = JobPositionForm
    template_name = 'hrpayroll/recruitment/job_position_form.html'
    permission_required = 'hrpayroll.add_jobposition'
    success_url = reverse_lazy('hrpayroll:job_position_list')

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['request'] = self.request
        return kw

    def form_valid(self, form):
        if not self.request.user.is_superuser:
            form.instance.company = self.request.user.company
        form.instance.created_by = self.request.user
        messages.success(self.request, "Job position created.")
        return super().form_valid(form)


class JobPositionUpdateView(LoginRequiredMixin, HRPayrollPermissionMixin, UpdateView):
    model = JobPosition
    form_class = JobPositionForm
    template_name = 'hrpayroll/recruitment/job_position_form.html'
    permission_required = 'hrpayroll.change_jobposition'
    success_url = reverse_lazy('hrpayroll:job_position_list')

    def get_queryset(self):
        if self.request.user.is_superuser:
            return JobPosition.objects.all()
        return JobPosition.objects.filter(company=self.request.user.company)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['request'] = self.request
        return kw

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, "Job position updated.")
        return super().form_valid(form)


# ── Recruitment — Applications ────────────────────────────────────────────────

class JobApplicationListView(LoginRequiredMixin, HRPayrollPermissionMixin, ListView):
    model = JobApplication
    template_name = 'hrpayroll/recruitment/application_list.html'
    context_object_name = 'applications'
    permission_required = 'hrpayroll.view_jobapplication'
    paginate_by = 20

    def get_queryset(self):
        qs = JobApplication.active_objects.all() if self.request.user.is_superuser \
            else JobApplication.active_objects.filter(company=self.request.user.company)
        status = self.request.GET.get('status', '').strip()
        if status:
            qs = qs.filter(status=status)
        position = self.request.GET.get('position', '').strip()
        if position:
            qs = qs.filter(position_id=position)
        return qs.select_related('position')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['status'] = self.request.GET.get('status', '')
        if self.request.user.is_superuser:
            ctx['positions'] = JobPosition.active_objects.all()
        else:
            ctx['positions'] = JobPosition.active_objects.filter(company=self.request.user.company)
        return ctx


class JobApplicationCreateView(LoginRequiredMixin, HRPayrollPermissionMixin, CreateView):
    model = JobApplication
    form_class = JobApplicationForm
    template_name = 'hrpayroll/recruitment/application_form.html'
    permission_required = 'hrpayroll.add_jobapplication'
    success_url = reverse_lazy('hrpayroll:application_list')

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['request'] = self.request
        return kw

    def form_valid(self, form):
        if not self.request.user.is_superuser:
            form.instance.company = self.request.user.company
        form.instance.created_by = self.request.user
        messages.success(self.request, "Application recorded.")
        return super().form_valid(form)


class JobApplicationDetailView(LoginRequiredMixin, HRPayrollPermissionMixin, DetailView):
    model = JobApplication
    template_name = 'hrpayroll/recruitment/application_detail.html'
    context_object_name = 'application'
    permission_required = 'hrpayroll.view_jobapplication'

    def get_queryset(self):
        if self.request.user.is_superuser:
            return JobApplication.objects.all()
        return JobApplication.objects.filter(company=self.request.user.company)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['interviews'] = self.object.interviews.filter(is_deleted=False).order_by('scheduled_at')
        ctx['interview_form'] = InterviewForm()
        return ctx


class JobApplicationUpdateView(LoginRequiredMixin, HRPayrollPermissionMixin, UpdateView):
    model = JobApplication
    form_class = JobApplicationForm
    template_name = 'hrpayroll/recruitment/application_form.html'
    permission_required = 'hrpayroll.change_jobapplication'

    def get_queryset(self):
        if self.request.user.is_superuser:
            return JobApplication.objects.all()
        return JobApplication.objects.filter(company=self.request.user.company)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['request'] = self.request
        return kw

    def get_success_url(self):
        return reverse_lazy('hrpayroll:application_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, "Application updated.")
        return super().form_valid(form)


@login_required
def application_move_stage(request, pk):
    """Quick HTMX action to advance/change application status."""
    if request.method == 'POST':
        app = get_object_or_404(JobApplication, pk=pk)
        if not request.user.is_superuser and app.company != request.user.company:
            raise PermissionDenied
        new_status = request.POST.get('status')
        valid = [c[0] for c in JobApplication._meta.get_field('status').choices]
        if new_status in valid:
            app.status = new_status
            app.updated_by = request.user
            app.save(update_fields=['status', 'updated_by'])
            messages.success(request, f"Application moved to {app.get_status_display()}.")
        return redirect('hrpayroll:application_detail', pk=pk)
    return redirect('hrpayroll:application_list')


@login_required
def hire_applicant(request, pk):
    """Convert a HIRED application into an Employee record."""
    app = get_object_or_404(JobApplication, pk=pk)
    if not request.user.is_superuser and app.company != request.user.company:
        raise PermissionDenied

    if app.hired_employee:
        messages.info(request, "This applicant is already an employee.")
        return redirect('hrpayroll:employee_detail', pk=app.hired_employee.pk)

    if request.method == 'POST':
        from django.utils import timezone
        from django.db import transaction as db_transaction
        with db_transaction.atomic():
            position = app.position.__class__.objects.select_for_update().get(pk=app.position.pk)
            employee = Employee.objects.create(
                company=app.company,
                first_name=app.candidate_name.split()[0],
                last_name=' '.join(app.candidate_name.split()[1:]) or '-',
                email=app.candidate_email,
                phone_number=app.candidate_phone or '',
                hire_date=timezone.now().date(),
                position=position.title,
                department=position.department,
                employment_type=position.employment_type,
                is_active=True,
                created_by=request.user,
            )
            app.hired_employee = employee
            app.status = 'HIRED'
            app.updated_by = request.user
            app.save(update_fields=['hired_employee', 'status', 'updated_by'])

            # Close the position if headcount is filled
            if position.hired_count >= position.headcount:
                position.status = 'FILLED'
                position.save(update_fields=['status'])

        import logging
        logging.getLogger('audit').info(
            'EMPLOYEE_HIRED actor=%s candidate=%s employee_id=%s company=%s',
            request.user.email, app.candidate_name, employee.pk, app.company,
        )
        messages.success(request, f"{employee.full_name} has been added as an employee.")
        return redirect('hrpayroll:employee_detail', pk=employee.pk)

    return render(request, 'hrpayroll/recruitment/confirm_hire.html', {'application': app})


# ── Interviews ────────────────────────────────────────────────────────────────

@login_required
def interview_create(request, application_pk):
    app = get_object_or_404(JobApplication, pk=application_pk)
    if not request.user.is_superuser and app.company != request.user.company:
        raise PermissionDenied

    if request.method == 'POST':
        form = InterviewForm(request.POST)
        if form.is_valid():
            interview = form.save(commit=False)
            interview.application = app
            interview.created_by = request.user
            interview.save()
            messages.success(request, "Interview scheduled.")
        else:
            messages.error(request, "Please correct the errors.")
    return redirect('hrpayroll:application_detail', pk=application_pk)


@login_required
def interview_update_result(request, pk):
    interview = get_object_or_404(Interview, pk=pk)
    if not request.user.is_superuser and interview.application.company != request.user.company:
        raise PermissionDenied

    if request.method == 'POST':
        form = InterviewForm(request.POST, instance=interview)
        if form.is_valid():
            form.save()
            messages.success(request, "Interview updated.")
    return redirect('hrpayroll:application_detail', pk=interview.application.pk)


# ── Leave Management ──────────────────────────────────────────────────────────

class LeaveTypeListView(LoginRequiredMixin, HRPayrollPermissionMixin, ListView):
    model = LeaveType
    template_name = 'hrpayroll/leave/leave_type_list.html'
    context_object_name = 'leave_types'
    permission_required = 'hrpayroll.view_leavetype'

    def get_queryset(self):
        if self.request.user.is_superuser:
            return LeaveType.active_objects.all()
        return LeaveType.active_objects.filter(company=self.request.user.company)


class LeaveTypeCreateView(LoginRequiredMixin, HRPayrollPermissionMixin, CreateView):
    model = LeaveType
    form_class = LeaveTypeForm
    template_name = 'hrpayroll/leave/leave_type_form.html'
    permission_required = 'hrpayroll.add_leavetype'
    success_url = reverse_lazy('hrpayroll:leave_type_list')

    def form_valid(self, form):
        if not self.request.user.is_superuser:
            form.instance.company = self.request.user.company
        form.instance.created_by = self.request.user
        messages.success(self.request, "Leave type created.")
        return super().form_valid(form)


class LeaveTypeUpdateView(LoginRequiredMixin, HRPayrollPermissionMixin, UpdateView):
    model = LeaveType
    form_class = LeaveTypeForm
    template_name = 'hrpayroll/leave/leave_type_form.html'
    permission_required = 'hrpayroll.change_leavetype'
    success_url = reverse_lazy('hrpayroll:leave_type_list')

    def get_queryset(self):
        if self.request.user.is_superuser:
            return LeaveType.objects.all()
        return LeaveType.objects.filter(company=self.request.user.company)

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, "Leave type updated.")
        return super().form_valid(form)


class LeaveRequestListView(LoginRequiredMixin, HRPayrollPermissionMixin, ListView):
    model = LeaveRequest
    template_name = 'hrpayroll/leave/leave_request_list.html'
    context_object_name = 'leave_requests'
    permission_required = 'hrpayroll.view_leaverequest'
    paginate_by = 20

    def get_queryset(self):
        qs = LeaveRequest.active_objects.filter(
            employee__company=self.request.user.company
        ) if not self.request.user.is_superuser else LeaveRequest.active_objects.all()

        status = self.request.GET.get('status', '').strip()
        if status:
            qs = qs.filter(status=status)
        return qs.select_related('employee', 'leave_type').order_by('-start_date')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['status'] = self.request.GET.get('status', '')
        return ctx


class LeaveRequestCreateView(LoginRequiredMixin, HRPayrollPermissionMixin, CreateView):
    model = LeaveRequest
    form_class = LeaveRequestForm
    template_name = 'hrpayroll/leave/leave_request_form.html'
    permission_required = 'hrpayroll.add_leaverequest'
    success_url = reverse_lazy('hrpayroll:leave_request_list')

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['request'] = self.request
        return kw

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, "Leave request submitted.")
        return super().form_valid(form)


@login_required
def leave_request_approve(request, pk):
    """Approve or reject a leave request."""
    lr = get_object_or_404(LeaveRequest, pk=pk)
    if not request.user.is_superuser and lr.employee.company != request.user.company:
        raise PermissionDenied

    if request.method == 'POST':
        from django.utils import timezone
        action = request.POST.get('action')
        if action == 'approve':
            lr.status = 'APPROVED'
            lr.approved_by = request.user
            lr.approved_at = timezone.now()
            lr.save(update_fields=['status', 'approved_by', 'approved_at'])
            # Update leave balance
            year = lr.start_date.year
            balance, _ = LeaveBalance.objects.get_or_create(
                employee=lr.employee, leave_type=lr.leave_type, year=year,
                defaults={'allocated': lr.leave_type.days_allowed_per_year}
            )
            from django.db.models import F
            LeaveBalance.objects.filter(pk=balance.pk).update(used=F('used') + lr.days_requested)
            messages.success(request, f"Leave approved for {lr.employee.full_name}.")
        elif action == 'reject':
            lr.status = 'REJECTED'
            lr.rejection_reason = request.POST.get('rejection_reason', '')
            lr.save(update_fields=['status', 'rejection_reason'])
            messages.warning(request, f"Leave rejected for {lr.employee.full_name}.")

    return redirect('hrpayroll:leave_request_list')


# ── Employee Documents ────────────────────────────────────────────────────────

@login_required
def employee_document_create(request, employee_pk):
    employee = get_object_or_404(Employee, pk=employee_pk)
    if not request.user.is_superuser and employee.company != request.user.company:
        raise PermissionDenied

    if request.method == 'POST':
        form = EmployeeDocumentForm(request.POST, request.FILES)
        if form.is_valid():
            doc = form.save(commit=False)
            doc.employee = employee
            doc.created_by = request.user
            doc.save()
            messages.success(request, "Document uploaded.")
        else:
            messages.error(request, "Upload failed. Check the form.")
    return redirect('hrpayroll:employee_detail', pk=employee_pk)


@login_required
def employee_document_delete(request, pk):
    doc = get_object_or_404(EmployeeDocument, pk=pk)
    if not request.user.is_superuser and doc.employee.company != request.user.company:
        raise PermissionDenied
    employee_pk = doc.employee.pk
    if request.method == 'POST':
        doc.soft_delete(deleted_by=request.user)
        messages.success(request, "Document removed.")
    return redirect('hrpayroll:employee_detail', pk=employee_pk)


# ── Performance Reviews ───────────────────────────────────────────────────────

class PerformanceReviewListView(LoginRequiredMixin, HRPayrollPermissionMixin, ListView):
    model = PerformanceReview
    template_name = 'hrpayroll/performance/review_list.html'
    context_object_name = 'reviews'
    permission_required = 'hrpayroll.view_performancereview'
    paginate_by = 20

    def get_queryset(self):
        qs = PerformanceReview.active_objects.all() if self.request.user.is_superuser \
            else PerformanceReview.active_objects.filter(company=self.request.user.company)
        return qs.select_related('employee').order_by('-review_period_end')


class PerformanceReviewCreateView(LoginRequiredMixin, HRPayrollPermissionMixin, CreateView):
    model = PerformanceReview
    form_class = PerformanceReviewForm
    template_name = 'hrpayroll/performance/review_form.html'
    permission_required = 'hrpayroll.add_performancereview'
    success_url = reverse_lazy('hrpayroll:review_list')

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['request'] = self.request
        return kw

    def form_valid(self, form):
        if not self.request.user.is_superuser:
            form.instance.company = self.request.user.company
        form.instance.reviewer = self.request.user
        form.instance.created_by = self.request.user
        messages.success(self.request, "Performance review saved.")
        return super().form_valid(form)


class PerformanceReviewUpdateView(LoginRequiredMixin, HRPayrollPermissionMixin, UpdateView):
    model = PerformanceReview
    form_class = PerformanceReviewForm
    template_name = 'hrpayroll/performance/review_form.html'
    permission_required = 'hrpayroll.change_performancereview'
    success_url = reverse_lazy('hrpayroll:review_list')

    def get_queryset(self):
        if self.request.user.is_superuser:
            return PerformanceReview.objects.all()
        return PerformanceReview.objects.filter(company=self.request.user.company)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['request'] = self.request
        return kw

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, "Review updated.")
        return super().form_valid(form)


# ── HR Notes ──────────────────────────────────────────────────────────────────

@login_required
def employee_note_create(request, employee_pk):
    employee = get_object_or_404(Employee, pk=employee_pk)
    if not request.user.is_superuser and employee.company != request.user.company:
        raise PermissionDenied

    if request.method == 'POST':
        form = EmployeeNoteForm(request.POST)
        if form.is_valid():
            note = form.save(commit=False)
            note.employee = employee
            note.recorded_by = request.user
            note.created_by = request.user
            note.save()
            messages.success(request, "Note added.")
        else:
            messages.error(request, "Could not save note.")
    return redirect('hrpayroll:employee_detail', pk=employee_pk)


@login_required
def employee_note_delete(request, pk):
    note = get_object_or_404(EmployeeNote, pk=pk)
    if not request.user.is_superuser and note.employee.company != request.user.company:
        raise PermissionDenied
    employee_pk = note.employee.pk
    if request.method == 'POST':
        note.soft_delete(deleted_by=request.user)
        messages.success(request, "Note removed.")
    return redirect('hrpayroll:employee_detail', pk=employee_pk)


# ── Separation / Offboarding ──────────────────────────────────────────────────

@login_required
def employee_separate(request, employee_pk):
    """Initiate offboarding — create a Separation record and deactivate the employee."""
    employee = get_object_or_404(Employee, pk=employee_pk)
    if not request.user.is_superuser and employee.company != request.user.company:
        raise PermissionDenied

    if hasattr(employee, 'separation'):
        messages.info(request, "This employee already has a separation record.")
        return redirect('hrpayroll:employee_detail', pk=employee_pk)

    if request.method == 'POST':
        form = SeparationForm(request.POST, request=request)
        if form.is_valid():
            sep = form.save(commit=False)
            sep.employee = employee
            sep.processed_by = request.user
            sep.created_by = request.user
            sep.save()

            # Deactivate employee
            employee.is_active = False
            employee.termination_date = sep.effective_date
            employee.termination_reason = sep.reason or sep.get_separation_type_display()
            employee.updated_by = request.user
            employee.save(update_fields=['is_active', 'termination_date', 'termination_reason', 'updated_by'])

            import logging
            logging.getLogger('audit').info(
                'EMPLOYEE_SEPARATED actor=%s employee=%s type=%s company=%s',
                request.user.email, employee.full_name,
                sep.separation_type, employee.company,
            )
            messages.success(request, f"{employee.full_name} has been separated ({sep.get_separation_type_display()}).")
            return redirect('hrpayroll:employee_detail', pk=employee_pk)
    else:
        form = SeparationForm(request=request)

    return render(request, 'hrpayroll/separation/separation_form.html', {
        'form': form,
        'employee': employee,
    })


# ── Modern HR Dashboard ───────────────────────────────────────────────────────

@login_required
def hrpayroll_dashboard(request):
    from django.db.models import Count, Q
    from django.utils import timezone

    company = getattr(request.user, 'company', None)
    today = timezone.now().date()
    context = {}

    if company:
        employees = Employee.active_objects.filter(company=company)
        context.update({
            'total_employees': employees.count(),
            'active_employees': employees.filter(is_active=True).count(),
            'on_probation': employees.filter(
                is_active=True,
                probation_end_date__gte=today
            ).count(),
            'open_positions': JobPosition.active_objects.filter(
                company=company, status='OPEN'
            ).count(),
            'pending_applications': JobApplication.active_objects.filter(
                company=company,
                status__in=['APPLIED', 'SCREENING', 'INTERVIEW']
            ).count(),
            'pending_leaves': LeaveRequest.active_objects.filter(
                employee__company=company, status='PENDING'
            ).count(),
            'pending_reviews': PerformanceReview.active_objects.filter(
                company=company, status='DRAFT'
            ).count(),
            'recent_hires': employees.filter(
                hire_date__gte=today.replace(day=1)
            ).order_by('-hire_date')[:5],
            'pending_leave_requests': LeaveRequest.active_objects.filter(
                employee__company=company, status='PENDING'
            ).select_related('employee', 'leave_type').order_by('start_date')[:5],
            'open_jobs': JobPosition.active_objects.filter(
                company=company, status='OPEN'
            ).select_related('department').order_by('-created_at')[:5],
        })

    return render(request, 'hrpayroll/hrpayroll_dashboard.html', context)


# ── Bulk Attendance Upload ─────────────────────────────────────────────────────

@login_required
def attendance_bulk_upload(request):
    if request.method == 'GET':
        employees = Employee.active_objects.filter(
            company=request.user.company
        ).order_by('last_name', 'first_name') if not request.user.is_superuser \
            else Employee.active_objects.all().order_by('last_name', 'first_name')
        return render(request, 'hrpayroll/attendance/bulk_upload.html', {'employees': employees})

    import csv
    import io
    from datetime import datetime

    uploaded_file = request.FILES.get('csv_file')
    if not uploaded_file:
        messages.error(request, "No file uploaded.")
        return redirect('hrpayroll:attendance_bulk_upload')

    if not uploaded_file.name.endswith('.csv'):
        messages.error(request, "Only CSV files are supported.")
        return redirect('hrpayroll:attendance_bulk_upload')

    content = uploaded_file.read().decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(content))

    required_cols = {'employee_id', 'date', 'status'}
    if not required_cols.issubset({c.strip().lower() for c in (reader.fieldnames or [])}):
        messages.error(request, "CSV must have columns: employee_id, date, status (check_in, check_out optional).")
        return redirect('hrpayroll:attendance_bulk_upload')

    STATUS_CHOICES = {'Present', 'Absent', 'Leave', 'Holiday'}
    created, skipped, errors = 0, 0, []

    company = request.user.company if not request.user.is_superuser else None

    for i, row in enumerate(reader, start=2):
        emp_id = row.get('employee_id', '').strip()
        date_str = row.get('date', '').strip()
        status = row.get('status', '').strip().title()
        check_in_str = row.get('check_in', '').strip()
        check_out_str = row.get('check_out', '').strip()

        if not emp_id or not date_str or not status:
            errors.append(f"Row {i}: missing required field.")
            continue

        if status not in STATUS_CHOICES:
            errors.append(f"Row {i}: invalid status '{status}'. Use Present/Absent/Leave/Holiday.")
            continue

        try:
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            errors.append(f"Row {i}: invalid date '{date_str}'. Use YYYY-MM-DD.")
            continue

        try:
            qs = Employee.objects.filter(pk=emp_id)
            if company:
                qs = qs.filter(company=company)
            employee = qs.get()
        except (Employee.DoesNotExist, ValueError):
            errors.append(f"Row {i}: employee '{emp_id}' not found.")
            continue

        def parse_time(t, date):
            if not t:
                return None
            try:
                from django.utils import timezone as tz
                import pytz
                naive = datetime.strptime(f"{date} {t}", '%Y-%m-%d %H:%M')
                return tz.make_aware(naive)
            except ValueError:
                return None

        check_in = parse_time(check_in_str, date_str)
        check_out = parse_time(check_out_str, date_str)

        obj, was_created = Attendance.objects.update_or_create(
            employee=employee,
            date=date,
            defaults={
                'status': status,
                'check_in_time': check_in,
                'check_out_time': check_out,
                'created_by': request.user,
            },
        )
        if was_created:
            created += 1
        else:
            skipped += 1

    msg_parts = [f"{created} record(s) created"]
    if skipped:
        msg_parts.append(f"{skipped} updated (already existed)")
    if errors:
        msg_parts.append(f"{len(errors)} error(s)")

    messages.success(request, " | ".join(msg_parts) + ".")
    if errors:
        for e in errors[:10]:
            messages.warning(request, e)

    return redirect('hrpayroll:attendance_list')
