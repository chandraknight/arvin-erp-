from django import forms
from .models import (
    CostCentre, Project, ProjectTask, ProjectMilestone, ProjectTimeLog,
    ProjectRisk, ProjectDocument, ProjectExpense, ProjectRevenue,
    Budget, BudgetRevision, Forecast,
)
from apps.utils.nepali_date import NepaliDateWidget, NepaliDateField, FiscalYearDateMixin


class CostCentreForm(forms.ModelForm):
    class Meta:
        model = CostCentre
        fields = ['name', 'code', 'description', 'parent', 'is_active']
        widgets = {'description': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if self.request and not self.request.user.is_superuser:
            company = self.request.user_company
            self.fields['parent'].queryset = CostCentre.active_objects.filter(
                company=company, parent__isnull=True
            )


class ProjectForm(FiscalYearDateMixin, forms.ModelForm):
    start_date = NepaliDateField(widget=NepaliDateWidget(), required=False, label='Start Date (BS)')
    end_date   = NepaliDateField(widget=NepaliDateWidget(), required=False, label='End Date (BS)')

    class Meta:
        model = Project
        fields = [
            'name', 'code', 'description', 'client_name', 'client_contact', 'client_email',
            'cost_centre', 'project_manager', 'start_date', 'end_date',
            'status', 'priority', 'budget_amount', 'currency', 'notes',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if self.request and not self.request.user.is_superuser:
            from apps.hrpayroll.models import Employee
            company = self.request.user_company
            self.fields['cost_centre'].queryset = CostCentre.active_objects.filter(company=company)
            self.fields['project_manager'].queryset = Employee.active_objects.filter(
                company=company, is_active=True
            )
        self.inject_fiscal_year(self.request)


class ProjectTaskForm(FiscalYearDateMixin, forms.ModelForm):
    due_date = NepaliDateField(widget=NepaliDateWidget(), required=False, label='Due Date (BS)')

    class Meta:
        model = ProjectTask
        fields = ['title', 'description', 'assignee', 'status', 'priority',
                  'due_date', 'estimated_hours', 'parent_task']
        widgets = {'description': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        self.project = kwargs.pop('project', None)
        super().__init__(*args, **kwargs)
        if self.request and not self.request.user.is_superuser:
            from apps.hrpayroll.models import Employee
            company = self.request.user_company
            self.fields['assignee'].queryset = Employee.active_objects.filter(
                company=company, is_active=True
            )
        if self.project:
            self.fields['parent_task'].queryset = ProjectTask.active_objects.filter(
                project=self.project, parent_task__isnull=True
            )
        self.inject_fiscal_year(self.request)

    def clean_due_date(self):
        due_date = self.cleaned_data.get('due_date')
        if due_date and self.project and self.project.end_date:
            if due_date > self.project.end_date:
                raise forms.ValidationError(
                    f"Due date cannot be after project end date ({self.project.end_date})."
                )
        return due_date


class ProjectMilestoneForm(FiscalYearDateMixin, forms.ModelForm):
    target_date    = NepaliDateField(widget=NepaliDateWidget(), required=True, label='Target Date (BS)')
    completed_date = NepaliDateField(widget=NepaliDateWidget(), required=False, label='Completed Date (BS)')

    class Meta:
        model = ProjectMilestone
        fields = ['title', 'description', 'target_date', 'completed_date', 'is_completed', 'deliverable']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
            'deliverable': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        self.inject_fiscal_year(self.request)


class ProjectTimeLogForm(FiscalYearDateMixin, forms.ModelForm):
    log_date = NepaliDateField(widget=NepaliDateWidget(), required=True, label='Date (BS)')

    class Meta:
        model = ProjectTimeLog
        fields = ['task', 'employee', 'log_date', 'hours', 'description', 'is_billable', 'hourly_rate']

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        self.project = kwargs.pop('project', None)
        super().__init__(*args, **kwargs)
        if self.request and not self.request.user.is_superuser:
            from apps.hrpayroll.models import Employee
            company = self.request.user_company
            self.fields['employee'].queryset = Employee.active_objects.filter(
                company=company, is_active=True
            )
        if self.project:
            self.fields['task'].queryset = ProjectTask.active_objects.filter(
                project=self.project
            )
        self.inject_fiscal_year(self.request)


class ProjectRiskForm(forms.ModelForm):
    class Meta:
        model = ProjectRisk
        fields = ['title', 'description', 'probability', 'impact', 'mitigation', 'owner', 'status']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
            'mitigation':  forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if self.request and not self.request.user.is_superuser:
            from apps.hrpayroll.models import Employee
            company = self.request.user_company
            self.fields['owner'].queryset = Employee.active_objects.filter(
                company=company, is_active=True
            )


class ProjectDocumentForm(forms.ModelForm):
    class Meta:
        model = ProjectDocument
        fields = ['document_type', 'title', 'file', 'version', 'notes']


class ProjectExpenseForm(FiscalYearDateMixin, forms.ModelForm):
    expense_date = NepaliDateField(widget=NepaliDateWidget(), required=True, label='Date (BS)')

    class Meta:
        model = ProjectExpense
        fields = ['project', 'cost_centre', 'ledger_account', 'description',
                  'amount', 'expense_date', 'reference', 'notes',
                  'vendor_bill', 'payment']
        widgets = {'notes': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if self.request and not self.request.user.is_superuser:
            from apps.bookkeeping.models import LedgerAccount
            from apps.billing.models import VendorBill
            from apps.payments.models import Payment
            company = self.request.user_company
            self.fields['project'].queryset = Project.active_objects.filter(company=company)
            self.fields['cost_centre'].queryset = CostCentre.active_objects.filter(company=company)
            self.fields['ledger_account'].queryset = LedgerAccount.active_objects.filter(
                company=company, account_type='EXPENSE'
            )
            self.fields['vendor_bill'].queryset = VendorBill.objects.filter(vendor__company=company)
            self.fields['payment'].queryset = Payment.active_objects.filter(company=company)
        self.inject_fiscal_year(self.request)


class ProjectRevenueForm(FiscalYearDateMixin, forms.ModelForm):
    revenue_date = NepaliDateField(widget=NepaliDateWidget(), required=True, label='Date (BS)')

    class Meta:
        model = ProjectRevenue
        fields = ['project', 'invoice', 'description', 'amount', 'revenue_date', 'reference', 'notes']
        widgets = {'notes': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if self.request and not self.request.user.is_superuser:
            from apps.billing.models import Invoice
            company = self.request.user_company
            self.fields['project'].queryset = Project.active_objects.filter(company=company)
            self.fields['invoice'].queryset = Invoice.active_objects.filter(company=company)
        self.inject_fiscal_year(self.request)


class BudgetForm(FiscalYearDateMixin, forms.ModelForm):
    period_start = NepaliDateField(widget=NepaliDateWidget(), required=True, label='Period Start (BS)')
    period_end   = NepaliDateField(widget=NepaliDateWidget(), required=True, label='Period End (BS)')

    class Meta:
        model = Budget
        fields = ['fiscal_year', 'cost_centre', 'project', 'ledger_account',
                  'budget_type', 'name', 'amount', 'period_start', 'period_end', 'notes']
        widgets = {'notes': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if self.request and not self.request.user.is_superuser:
            from apps.bookkeeping.models import LedgerAccount
            from apps.company.models import FiscalYear
            company = self.request.user_company
            self.fields['fiscal_year'].queryset = FiscalYear.objects.filter(company=company)
            self.fields['cost_centre'].queryset = CostCentre.active_objects.filter(company=company)
            self.fields['project'].queryset = Project.active_objects.filter(company=company)
            self.fields['ledger_account'].queryset = LedgerAccount.active_objects.filter(company=company)
        self.inject_fiscal_year(self.request)


class BudgetRevisionForm(forms.ModelForm):
    class Meta:
        model = BudgetRevision
        fields = ['revised_amount', 'reason']
        widgets = {'reason': forms.Textarea(attrs={'rows': 2})}

    def clean_revised_amount(self):
        amount = self.cleaned_data.get('revised_amount')
        if amount is not None and amount <= 0:
            raise forms.ValidationError("Revised amount must be greater than zero.")
        return amount


class ForecastForm(forms.ModelForm):
    class Meta:
        model = Forecast
        fields = ['fiscal_year', 'cost_centre', 'project', 'ledger_account',
                  'forecast_type', 'name', 'year', 'month', 'forecast_amount', 'notes']
        widgets = {'notes': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if self.request and not self.request.user.is_superuser:
            from apps.bookkeeping.models import LedgerAccount
            from apps.company.models import FiscalYear
            company = self.request.user_company
            self.fields['fiscal_year'].queryset = FiscalYear.objects.filter(company=company)
            self.fields['cost_centre'].queryset = CostCentre.active_objects.filter(company=company)
            self.fields['project'].queryset = Project.active_objects.filter(company=company)
            self.fields['ledger_account'].queryset = LedgerAccount.active_objects.filter(company=company)
