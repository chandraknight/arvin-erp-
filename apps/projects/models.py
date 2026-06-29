"""
apps/projects/models.py
=======================
Project tracking and cost-centre module.

Enabled per-company via Company.enable_project_tracking = True.
Automatically enabled when Company.organisation_type = 'PROJECT'.

Models
------
CostCentre      - A named budget/reporting unit.
Project         - A time-bounded initiative with a budget.
ProjectTask     - A task or milestone within a project.
ProjectMilestone- A key deliverable with a target date.
ProjectTimeLog  - Time tracking per employee per project.
ProjectRisk     - Risk register entry.
ProjectDocument - File attachment on a project.
ProjectExpense  - An expense line tagged to a project.
ProjectRevenue  - Revenue recognised against a project.
Budget          - A period budget for a cost centre or project.
BudgetRevision  - Audit trail for budget revisions.
Forecast        - A monthly revenue/expense/cashflow forecast line.
"""

from decimal import Decimal
from apps.utils.baseModel import BaseModel
from django.db import models
from django.utils import timezone


# ─────────────────────────────────────────────────────────────────────────────
# Cost Centre
# ─────────────────────────────────────────────────────────────────────────────

class CostCentre(BaseModel):
    company = models.ForeignKey(
        'company.Company', on_delete=models.CASCADE, related_name='cost_centres'
    )
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=20, blank=True, null=True,
                            help_text='Short code for reports (e.g. CC-001)')
    description = models.TextField(blank=True, null=True)
    parent = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='children',
        help_text='Parent cost centre for hierarchical rollup.'
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('company', 'name')
        ordering = ['name']

    def __str__(self):
        return f"{self.code} — {self.name}" if self.code else self.name


# ─────────────────────────────────────────────────────────────────────────────
# Project
# ─────────────────────────────────────────────────────────────────────────────

PROJECT_STATUS_CHOICES = [
    ('PLANNING',    'Planning'),
    ('ACTIVE',      'Active'),
    ('ON_HOLD',     'On Hold'),
    ('COMPLETED',   'Completed'),
    ('CANCELLED',   'Cancelled'),
]

PRIORITY_CHOICES = [
    ('LOW',    'Low'),
    ('MEDIUM', 'Medium'),
    ('HIGH',   'High'),
    ('URGENT', 'Urgent'),
]


class Project(BaseModel):
    company = models.ForeignKey(
        'company.Company', on_delete=models.CASCADE, related_name='projects'
    )
    cost_centre = models.ForeignKey(
        CostCentre, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='projects'
    )
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=30, blank=True, null=True,
                            help_text='Project code (e.g. PRJ-2081-001)')
    description = models.TextField(blank=True, null=True)
    client_name = models.CharField(max_length=255, blank=True, null=True)
    client_contact = models.CharField(max_length=150, blank=True, null=True)
    client_email = models.EmailField(blank=True, null=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=15, choices=PROJECT_STATUS_CHOICES, default='PLANNING')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='MEDIUM')
    budget_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00'),
        help_text='Total approved budget for this project.'
    )
    currency = models.CharField(max_length=5, default='NPR')
    # Project manager (optional link to HR employee)
    project_manager = models.ForeignKey(
        'hrpayroll.Employee', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='managed_projects',
        help_text='Employee responsible for this project.'
    )
    notes = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('company', 'code')
        ordering = ['-start_date', 'name']

    def __str__(self):
        return f"{self.code} — {self.name}" if self.code else self.name

    @property
    def total_expenses(self):
        return self.expenses.filter(is_deleted=False).aggregate(
            t=models.Sum('amount')
        )['t'] or Decimal('0.00')

    @property
    def total_revenue(self):
        return self.revenues.filter(is_deleted=False).aggregate(
            t=models.Sum('amount')
        )['t'] or Decimal('0.00')

    @property
    def net_position(self):
        return self.total_revenue - self.total_expenses

    @property
    def budget_utilisation_pct(self):
        if self.budget_amount and self.budget_amount > 0:
            return round((self.total_expenses / self.budget_amount) * 100, 1)
        return None

    @property
    def is_over_budget(self):
        return self.total_expenses > self.budget_amount

    @property
    def total_hours_logged(self):
        return self.time_logs.filter(is_deleted=False).aggregate(
            t=models.Sum('hours')
        )['t'] or Decimal('0.00')

    @property
    def completion_pct(self):
        tasks = self.tasks.filter(is_deleted=False)
        total = tasks.count()
        if total == 0:
            return 0
        done = tasks.filter(status='DONE').count()
        return round((done / total) * 100)


# ─────────────────────────────────────────────────────────────────────────────
# Project Task
# ─────────────────────────────────────────────────────────────────────────────

TASK_STATUS_CHOICES = [
    ('TODO',        'To Do'),
    ('IN_PROGRESS', 'In Progress'),
    ('REVIEW',      'In Review'),
    ('DONE',        'Done'),
    ('BLOCKED',     'Blocked'),
    ('CANCELLED',   'Cancelled'),
]


class ProjectTask(BaseModel):
    """A task or work item within a project."""
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='tasks')
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True, null=True)
    assignee = models.ForeignKey(
        'hrpayroll.Employee', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assigned_tasks'
    )
    status = models.CharField(max_length=15, choices=TASK_STATUS_CHOICES, default='TODO')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='MEDIUM')
    due_date = models.DateField(null=True, blank=True)
    estimated_hours = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    parent_task = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='subtasks',
        help_text='Parent task for sub-task hierarchy.'
    )
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'due_date', 'title']

    def __str__(self):
        return f"{self.project.name} — {self.title}"

    @property
    def hours_logged(self):
        return self.time_logs.filter(is_deleted=False).aggregate(
            t=models.Sum('hours')
        )['t'] or Decimal('0.00')


# ─────────────────────────────────────────────────────────────────────────────
# Project Milestone
# ─────────────────────────────────────────────────────────────────────────────

class ProjectMilestone(BaseModel):
    """A key deliverable or checkpoint in a project."""
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='milestones')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    target_date = models.DateField()
    completed_date = models.DateField(null=True, blank=True)
    is_completed = models.BooleanField(default=False)
    deliverable = models.CharField(
        max_length=500, blank=True, null=True,
        help_text='What is delivered at this milestone.'
    )

    class Meta:
        ordering = ['target_date']

    def __str__(self):
        return f"{self.project.name} — {self.title}"


# ─────────────────────────────────────────────────────────────────────────────
# Project Time Log
# ─────────────────────────────────────────────────────────────────────────────

class ProjectTimeLog(BaseModel):
    """Time tracking entry — hours worked on a project/task by an employee."""
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='time_logs')
    task = models.ForeignKey(
        ProjectTask, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='time_logs'
    )
    employee = models.ForeignKey(
        'hrpayroll.Employee', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='time_logs'
    )
    log_date = models.DateField(default=timezone.now)
    hours = models.DecimalField(max_digits=6, decimal_places=2)
    description = models.CharField(max_length=500, blank=True, null=True)
    is_billable = models.BooleanField(
        default=True,
        help_text='Whether these hours are billable to the client.'
    )
    hourly_rate = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text='Override hourly rate for billing. Leave blank to use employee rate.'
    )

    class Meta:
        ordering = ['-log_date']

    def __str__(self):
        emp = self.employee.full_name if self.employee else 'Unknown'
        return f"{self.project.name} — {emp} {self.hours}h on {self.log_date}"

    @property
    def billable_amount(self):
        if not self.is_billable:
            return Decimal('0.00')
        rate = self.hourly_rate
        if not rate and self.employee and self.employee.hourly_rate:
            rate = self.employee.hourly_rate
        if rate:
            return (self.hours * rate).quantize(Decimal('0.01'))
        return Decimal('0.00')


# ─────────────────────────────────────────────────────────────────────────────
# Project Risk
# ─────────────────────────────────────────────────────────────────────────────

RISK_STATUS_CHOICES = [
    ('OPEN',        'Open'),
    ('MITIGATED',   'Mitigated'),
    ('ACCEPTED',    'Accepted'),
    ('CLOSED',      'Closed'),
]

RISK_LEVEL_CHOICES = [
    (1, 'Very Low'),
    (2, 'Low'),
    (3, 'Medium'),
    (4, 'High'),
    (5, 'Critical'),
]


class ProjectRisk(BaseModel):
    """Risk register entry for a project."""
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='risks')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    probability = models.PositiveSmallIntegerField(
        choices=RISK_LEVEL_CHOICES, default=3,
        help_text='Likelihood of the risk occurring (1=Very Low, 5=Critical).'
    )
    impact = models.PositiveSmallIntegerField(
        choices=RISK_LEVEL_CHOICES, default=3,
        help_text='Impact if the risk occurs (1=Very Low, 5=Critical).'
    )
    mitigation = models.TextField(blank=True, null=True, help_text='Mitigation plan.')
    owner = models.ForeignKey(
        'hrpayroll.Employee', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='owned_risks'
    )
    status = models.CharField(max_length=10, choices=RISK_STATUS_CHOICES, default='OPEN')

    class Meta:
        ordering = ['-impact', '-probability']

    def __str__(self):
        return f"{self.project.name} — {self.title}"

    @property
    def risk_score(self):
        return self.probability * self.impact

    @property
    def risk_level_label(self):
        score = self.risk_score
        if score >= 20:
            return 'Critical'
        elif score >= 12:
            return 'High'
        elif score >= 6:
            return 'Medium'
        else:
            return 'Low'


# ─────────────────────────────────────────────────────────────────────────────
# Project Document
# ─────────────────────────────────────────────────────────────────────────────

PROJECT_DOC_TYPE_CHOICES = [
    ('PROPOSAL',    'Proposal'),
    ('CONTRACT',    'Contract'),
    ('SOW',         'Statement of Work'),
    ('REPORT',      'Progress Report'),
    ('INVOICE',     'Invoice'),
    ('DRAWING',     'Drawing / Design'),
    ('MINUTES',     'Meeting Minutes'),
    ('OTHER',       'Other'),
]


class ProjectDocument(BaseModel):
    """File attachment on a project."""
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='documents')
    document_type = models.CharField(max_length=15, choices=PROJECT_DOC_TYPE_CHOICES, default='OTHER')
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to='project_documents/')
    version = models.CharField(max_length=20, blank=True, null=True, help_text='e.g. v1.0, Rev 2')
    notes = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        ordering = ['document_type', '-created_at']

    def __str__(self):
        return f"{self.project.name} — {self.title}"


# ─────────────────────────────────────────────────────────────────────────────
# Project Expense
# ─────────────────────────────────────────────────────────────────────────────

class ProjectExpense(BaseModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='expenses')
    cost_centre = models.ForeignKey(
        CostCentre, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='expenses'
    )
    ledger_account = models.ForeignKey(
        'bookkeeping.LedgerAccount', on_delete=models.PROTECT,
        help_text='Expense account this cost is charged to.'
    )
    vendor_bill = models.ForeignKey(
        'billing.VendorBill', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='project_expenses'
    )
    payment = models.ForeignKey(
        'payments.Payment', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='project_expenses'
    )
    description = models.CharField(max_length=500)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    expense_date = models.DateField(default=timezone.now)
    reference = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-expense_date']

    def __str__(self):
        return f"{self.project.name} — {self.description} ({self.amount})"


# ─────────────────────────────────────────────────────────────────────────────
# Project Revenue
# ─────────────────────────────────────────────────────────────────────────────

class ProjectRevenue(BaseModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='revenues')
    invoice = models.ForeignKey(
        'billing.Invoice', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='project_revenues'
    )
    description = models.CharField(max_length=500)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    revenue_date = models.DateField(default=timezone.now)
    reference = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-revenue_date']

    def __str__(self):
        return f"{self.project.name} — {self.description} ({self.amount})"


# ─────────────────────────────────────────────────────────────────────────────
# Budget
# ─────────────────────────────────────────────────────────────────────────────

BUDGET_TYPE_CHOICES = [
    ('REVENUE', 'Revenue Budget'),
    ('EXPENSE', 'Expense Budget'),
    ('CAPEX',   'Capital Expenditure'),
]


class Budget(BaseModel):
    company = models.ForeignKey(
        'company.Company', on_delete=models.CASCADE, related_name='budgets'
    )
    fiscal_year = models.ForeignKey(
        'company.FiscalYear', on_delete=models.CASCADE, related_name='budgets'
    )
    cost_centre = models.ForeignKey(
        CostCentre, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='budgets'
    )
    project = models.ForeignKey(
        Project, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='budgets'
    )
    ledger_account = models.ForeignKey(
        'bookkeeping.LedgerAccount', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='budgets'
    )
    budget_type = models.CharField(max_length=10, choices=BUDGET_TYPE_CHOICES, default='EXPENSE')
    name = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    period_start = models.DateField()
    period_end = models.DateField()
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['period_start', 'name']

    def __str__(self):
        return f"{self.name} ({self.period_start} – {self.period_end}): {self.amount}"

    @property
    def actual_amount(self):
        from apps.bookkeeping.models import JournalEntryLine
        from django.db.models import Sum
        if not self.ledger_account:
            return Decimal('0.00')
        entry_type = 'DEBIT' if self.budget_type == 'EXPENSE' else 'CREDIT'
        return JournalEntryLine.objects.filter(
            account=self.ledger_account,
            entry_type=entry_type,
            journal_entry__company=self.company,
            journal_entry__date__gte=self.period_start,
            journal_entry__date__lte=self.period_end,
            journal_entry__is_deleted=False,
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

    @property
    def variance(self):
        return self.amount - self.actual_amount

    @property
    def utilisation_pct(self):
        if self.amount and self.amount > 0:
            return round((self.actual_amount / self.amount) * 100, 1)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Budget Revision
# ─────────────────────────────────────────────────────────────────────────────

class BudgetRevision(BaseModel):
    """Audit trail when a budget line is revised."""
    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name='revisions')
    original_amount = models.DecimalField(max_digits=14, decimal_places=2)
    revised_amount = models.DecimalField(max_digits=14, decimal_places=2)
    reason = models.TextField()
    approved_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approved_budget_revisions'
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Revision of {self.budget.name}: {self.original_amount} → {self.revised_amount}"


# ─────────────────────────────────────────────────────────────────────────────
# Forecast
# ─────────────────────────────────────────────────────────────────────────────

FORECAST_TYPE_CHOICES = [
    ('REVENUE',  'Revenue Forecast'),
    ('EXPENSE',  'Expense Forecast'),
    ('CASHFLOW', 'Cash Flow Forecast'),
]


class Forecast(BaseModel):
    company = models.ForeignKey(
        'company.Company', on_delete=models.CASCADE, related_name='forecasts'
    )
    fiscal_year = models.ForeignKey(
        'company.FiscalYear', on_delete=models.CASCADE, related_name='forecasts'
    )
    cost_centre = models.ForeignKey(
        CostCentre, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='forecasts'
    )
    project = models.ForeignKey(
        Project, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='forecasts'
    )
    ledger_account = models.ForeignKey(
        'bookkeeping.LedgerAccount', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='forecasts'
    )
    forecast_type = models.CharField(max_length=10, choices=FORECAST_TYPE_CHOICES, default='REVENUE')
    name = models.CharField(max_length=255)
    year = models.PositiveIntegerField(help_text='AD year (e.g. 2025)')
    month = models.PositiveSmallIntegerField(help_text='Month 1–12')
    forecast_amount = models.DecimalField(max_digits=14, decimal_places=2)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('company', 'fiscal_year', 'forecast_type', 'ledger_account',
                           'cost_centre', 'project', 'year', 'month')
        ordering = ['year', 'month']

    def __str__(self):
        return f"{self.name} {self.year}/{self.month:02d}: {self.forecast_amount}"

    @property
    def actual_amount(self):
        from apps.bookkeeping.models import JournalEntryLine
        from django.db.models import Sum
        import datetime, calendar
        if not self.ledger_account:
            return Decimal('0.00')
        entry_type = 'DEBIT' if self.forecast_type == 'EXPENSE' else 'CREDIT'
        month_start = datetime.date(self.year, self.month, 1)
        last_day = calendar.monthrange(self.year, self.month)[1]
        month_end = datetime.date(self.year, self.month, last_day)
        return JournalEntryLine.objects.filter(
            account=self.ledger_account,
            entry_type=entry_type,
            journal_entry__company=self.company,
            journal_entry__date__gte=month_start,
            journal_entry__date__lte=month_end,
            journal_entry__is_deleted=False,
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

    @property
    def variance(self):
        return self.forecast_amount - self.actual_amount


