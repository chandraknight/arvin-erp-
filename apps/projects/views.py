"""
apps/projects/views.py
======================
Views for Projects, Cost Centres, Budgets, and Forecasts.

All views are protected with @login_required or AuthMixin.
All querysets are scoped to request.user_company for non-superusers.
Feature-flag guard: redirect to dashboard if the module is not enabled.
"""

import json
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView
)
from django.db.models import Sum, Q
from decimal import Decimal
import pandas as pd
from apps.utils.htmx import is_htmx, toast_trigger

from apps.reports.services.pdf_export import render_pdf_response
from apps.utils.mixins import AuthMixin, ModuleRequiredMixin, module_required
from .models import (
    CostCentre, Project, ProjectTask, ProjectMilestone, ProjectTimeLog,
    ProjectRisk, ProjectDocument, ProjectExpense, ProjectRevenue,
    Budget, BudgetRevision, Forecast, PROJECT_STATUS_CHOICES,
)
from .forms import (
    CostCentreForm, ProjectForm, ProjectTaskForm, ProjectMilestoneForm,
    ProjectTimeLogForm, ProjectRiskForm, ProjectDocumentForm,
    ProjectExpenseForm, ProjectRevenueForm,
    BudgetForm, BudgetRevisionForm, ForecastForm,
)
from .services import get_dashboard_stats, get_budget_vs_actual, get_forecast_vs_actual, get_project_pnl


def _require_project_tracking(request):
    """Return None if enabled, else an HttpResponse redirect."""
    company = request.user_company
    if company and not company.enable_project_tracking:
        messages.warning(request, "Project tracking is not enabled for your company.")
        return redirect('accounts:user_dashboard')
    return None


def _require_forecasting(request):
    company = request.user_company
    if company and not company.enable_forecasting:
        messages.warning(request, "Forecasting is not enabled for your company.")
        return redirect('accounts:user_dashboard')
    return None


def _get_active_fiscal_year(request, company):
    from apps.company.models import FiscalYear
    fiscal_year_id = request.session.get('active_fiscal_year_id')
    if fiscal_year_id:
        return FiscalYear.objects.filter(id=fiscal_year_id, company=company).first()
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@module_required('enable_project_tracking')
def project_dashboard(request):
    guard = _require_project_tracking(request)
    if guard:
        return guard

    data = get_dashboard_stats(request.user_company)
    context = {
        'projects': data['projects'].order_by('status', 'name'),
        'stats': data['stats'],
        'recent_expenses': data['recent_expenses'],
        'upcoming_milestones': data['upcoming_milestones'],
    }
    return render(request, 'projects/dashboard.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# Cost Centre
# ─────────────────────────────────────────────────────────────────────────────

class CostCentreListView(AuthMixin, ModuleRequiredMixin, ListView):
    model = CostCentre
    module_flag = 'enable_project_tracking'
    template_name = 'projects/costcentre_list.html'
    context_object_name = 'cost_centres'
    permission_required = ['projects.view_costcentre']

    def get_queryset(self):
        return CostCentre.active_objects.filter(
            company=self.request.user_company
        ).select_related('parent').order_by('name')


class CostCentreCreateView(AuthMixin, ModuleRequiredMixin, CreateView):
    model = CostCentre
    module_flag = 'enable_project_tracking'
    form_class = CostCentreForm
    template_name = 'projects/costcentre_form.html'
    success_url = reverse_lazy('projects:costcentre_list')
    permission_required = ['projects.add_costcentre']

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def form_valid(self, form):
        form.instance.company = self.request.user_company
        form.instance.created_by = self.request.user
        messages.success(self.request, "Cost centre created.")
        return super().form_valid(form)


class CostCentreUpdateView(AuthMixin, ModuleRequiredMixin, UpdateView):
    model = CostCentre
    module_flag = 'enable_project_tracking'
    form_class = CostCentreForm
    template_name = 'projects/costcentre_form.html'
    success_url = reverse_lazy('projects:costcentre_list')
    permission_required = ['projects.change_costcentre']

    def get_queryset(self):
        return CostCentre.active_objects.filter(company=self.request.user_company)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, "Cost centre updated.")
        return super().form_valid(form)


class CostCentreDeleteView(AuthMixin, ModuleRequiredMixin, DeleteView):
    model = CostCentre
    module_flag = 'enable_project_tracking'
    template_name = 'projects/confirm_delete.html'
    success_url = reverse_lazy('projects:costcentre_list')
    permission_required = ['projects.delete_costcentre']

    def get_queryset(self):
        return CostCentre.active_objects.filter(company=self.request.user_company)

    def form_valid(self, form):
        self.object.soft_delete(deleted_by=self.request.user)
        if is_htmx(self.request):
            response = HttpResponse(status=200, content='')
            response['HX-Trigger'] = json.dumps(toast_trigger('success', 'Cost centre deleted.'))
            return response
        messages.success(self.request, "Cost centre deleted.")
        return redirect(self.success_url)


# ─────────────────────────────────────────────────────────────────────────────
# Project
# ─────────────────────────────────────────────────────────────────────────────

class ProjectListView(AuthMixin, ModuleRequiredMixin, ListView):
    model = Project
    module_flag = 'enable_project_tracking'
    template_name = 'projects/project_list.html'
    context_object_name = 'projects'
    permission_required = ['projects.view_project']
    paginate_by = 20

    def get_queryset(self):
        qs = Project.active_objects.filter(
            company=self.request.user_company
        ).select_related('cost_centre')
        status = self.request.GET.get('status', '').strip()
        if status:
            qs = qs.filter(status=status)
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q) | Q(client_name__icontains=q))
        return qs.order_by('status', 'name')

    def get_template_names(self):
        from apps.utils.htmx import is_htmx
        if is_htmx(self.request):
            return ['projects/partials/project_table.html']
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['q'] = self.request.GET.get('q', '')
        context['status'] = self.request.GET.get('status', '')
        return context


class ProjectDetailView(AuthMixin, ModuleRequiredMixin, DetailView):
    model = Project
    module_flag = 'enable_project_tracking'
    template_name = 'projects/project_detail.html'
    context_object_name = 'project'
    permission_required = ['projects.view_project']

    def get_queryset(self):
        return Project.active_objects.filter(company=self.request.user_company)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.object
        context['expenses'] = project.expenses.filter(is_deleted=False).select_related(
            'ledger_account', 'cost_centre'
        ).order_by('-expense_date')
        context['revenues'] = project.revenues.filter(is_deleted=False).order_by('-revenue_date')
        context['budgets'] = project.budgets.filter(is_deleted=False)
        context['tasks'] = project.tasks.filter(is_deleted=False, parent_task__isnull=True).order_by('sort_order', 'due_date')
        context['milestones'] = project.milestones.filter(is_deleted=False).order_by('target_date')
        context['risks'] = project.risks.filter(is_deleted=False).order_by('-impact', '-probability')
        context['documents'] = project.documents.filter(is_deleted=False).order_by('document_type')
        context['time_logs'] = project.time_logs.filter(is_deleted=False).select_related('employee', 'task').order_by('-log_date')[:20]
        context['expense_form'] = ProjectExpenseForm(request=self.request)
        context['revenue_form'] = ProjectRevenueForm(request=self.request)
        context['task_form'] = ProjectTaskForm(request=self.request, project=project)
        context['milestone_form'] = ProjectMilestoneForm(request=self.request)
        context['timelog_form'] = ProjectTimeLogForm(request=self.request, project=project)
        context['risk_form'] = ProjectRiskForm(request=self.request)
        context['document_form'] = ProjectDocumentForm()
        return context


class ProjectCreateView(AuthMixin, ModuleRequiredMixin, CreateView):
    model = Project
    module_flag = 'enable_project_tracking'
    form_class = ProjectForm
    template_name = 'projects/project_form.html'
    success_url = reverse_lazy('projects:project_list')
    permission_required = ['projects.add_project']

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def form_valid(self, form):
        form.instance.company = self.request.user_company
        form.instance.created_by = self.request.user
        messages.success(self.request, f"Project '{form.instance.name}' created.")
        return super().form_valid(form)


class ProjectUpdateView(AuthMixin, ModuleRequiredMixin, UpdateView):
    model = Project
    module_flag = 'enable_project_tracking'
    form_class = ProjectForm
    template_name = 'projects/project_form.html'
    permission_required = ['projects.change_project']

    def get_queryset(self):
        return Project.active_objects.filter(company=self.request.user_company)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def get_success_url(self):
        return reverse_lazy('projects:project_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, "Project updated.")
        return super().form_valid(form)


class ProjectDeleteView(AuthMixin, ModuleRequiredMixin, DeleteView):
    model = Project
    module_flag = 'enable_project_tracking'
    template_name = 'projects/confirm_delete.html'
    success_url = reverse_lazy('projects:project_list')
    permission_required = ['projects.delete_project']

    def get_queryset(self):
        return Project.active_objects.filter(company=self.request.user_company)

    def form_valid(self, form):
        project = self.object
        expense_count = project.expenses.filter(is_deleted=False).count()
        revenue_count = project.revenues.filter(is_deleted=False).count()
        if expense_count or revenue_count:
            messages.error(
                self.request,
                f"Cannot delete project with {expense_count} expense(s) and {revenue_count} revenue(s). "
                "Cancel or remove all transactions first."
            )
            return redirect('projects:project_detail', pk=project.pk)
        project.soft_delete(deleted_by=self.request.user)
        messages.success(self.request, "Project deleted.")
        return redirect(self.success_url)


# ─────────────────────────────────────────────────────────────────────────────
# Project Expense
# ─────────────────────────────────────────────────────────────────────────────

class ProjectExpenseListView(AuthMixin, ModuleRequiredMixin, ListView):
    model = ProjectExpense
    module_flag = 'enable_project_tracking'
    template_name = 'projects/expense_list.html'
    context_object_name = 'expenses'
    permission_required = ['projects.view_projectexpense']
    paginate_by = 30

    def get_queryset(self):
        return ProjectExpense.active_objects.filter(
            project__company=self.request.user_company
        ).select_related('project', 'ledger_account', 'cost_centre').order_by('-expense_date')


class ProjectExpenseCreateView(AuthMixin, ModuleRequiredMixin, CreateView):
    model = ProjectExpense
    module_flag = 'enable_project_tracking'
    form_class = ProjectExpenseForm
    template_name = 'projects/expense_form.html'
    success_url = reverse_lazy('projects:expense_list')
    permission_required = ['projects.add_projectexpense']

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, "Expense recorded.")
        return super().form_valid(form)


class ProjectExpenseUpdateView(AuthMixin, ModuleRequiredMixin, UpdateView):
    model = ProjectExpense
    module_flag = 'enable_project_tracking'
    form_class = ProjectExpenseForm
    template_name = 'projects/expense_form.html'
    success_url = reverse_lazy('projects:expense_list')
    permission_required = ['projects.change_projectexpense']

    def get_queryset(self):
        return ProjectExpense.active_objects.filter(project__company=self.request.user_company)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, "Expense updated.")
        return super().form_valid(form)


class ProjectExpenseDeleteView(AuthMixin, ModuleRequiredMixin, DeleteView):
    model = ProjectExpense
    module_flag = 'enable_project_tracking'
    template_name = 'projects/confirm_delete.html'
    success_url = reverse_lazy('projects:expense_list')
    permission_required = ['projects.delete_projectexpense']

    def get_queryset(self):
        return ProjectExpense.active_objects.filter(project__company=self.request.user_company)

    def form_valid(self, form):
        self.object.soft_delete(deleted_by=self.request.user)
        if is_htmx(self.request):
            response = HttpResponse(status=200, content='')
            response['HX-Trigger'] = json.dumps(toast_trigger('success', 'Expense deleted.'))
            return response
        messages.success(self.request, "Expense deleted.")
        return redirect(self.success_url)


# ─────────────────────────────────────────────────────────────────────────────
# Project Revenue
# ─────────────────────────────────────────────────────────────────────────────

class ProjectRevenueCreateView(AuthMixin, ModuleRequiredMixin, CreateView):
    model = ProjectRevenue
    module_flag = 'enable_project_tracking'
    form_class = ProjectRevenueForm
    template_name = 'projects/revenue_form.html'
    success_url = reverse_lazy('projects:project_list')
    permission_required = ['projects.add_projectrevenue']

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, "Revenue recorded.")
        return super().form_valid(form)


class ProjectRevenueDeleteView(AuthMixin, ModuleRequiredMixin, DeleteView):
    model = ProjectRevenue
    module_flag = 'enable_project_tracking'
    template_name = 'projects/confirm_delete.html'
    success_url = reverse_lazy('projects:project_list')
    permission_required = ['projects.delete_projectrevenue']

    def get_queryset(self):
        return ProjectRevenue.active_objects.filter(project__company=self.request.user_company)

    def form_valid(self, form):
        self.object.soft_delete(deleted_by=self.request.user)
        messages.success(self.request, "Revenue entry deleted.")
        return redirect(self.success_url)


# ─────────────────────────────────────────────────────────────────────────────
# Budget
# ─────────────────────────────────────────────────────────────────────────────

class BudgetListView(AuthMixin, ModuleRequiredMixin, ListView):
    model = Budget
    module_flag = 'enable_project_tracking'
    template_name = 'projects/budget_list.html'
    context_object_name = 'budgets'
    permission_required = ['projects.view_budget']
    paginate_by = 20

    def get_queryset(self):
        return Budget.active_objects.filter(
            company=self.request.user_company
        ).select_related('fiscal_year', 'cost_centre', 'project', 'ledger_account').order_by(
            'period_start', 'name'
        )


class BudgetCreateView(AuthMixin, ModuleRequiredMixin, CreateView):
    model = Budget
    module_flag = 'enable_project_tracking'
    form_class = BudgetForm
    template_name = 'projects/budget_form.html'
    success_url = reverse_lazy('projects:budget_list')
    permission_required = ['projects.add_budget']

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def form_valid(self, form):
        form.instance.company = self.request.user_company
        form.instance.created_by = self.request.user
        messages.success(self.request, "Budget line created.")
        return super().form_valid(form)


class BudgetUpdateView(AuthMixin, ModuleRequiredMixin, UpdateView):
    model = Budget
    module_flag = 'enable_project_tracking'
    form_class = BudgetForm
    template_name = 'projects/budget_form.html'
    success_url = reverse_lazy('projects:budget_list')
    permission_required = ['projects.change_budget']

    def get_queryset(self):
        return Budget.active_objects.filter(company=self.request.user_company)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def form_valid(self, form):
        original_amount = self.get_object().amount
        form.instance.updated_by = self.request.user
        response = super().form_valid(form)
        # Auto-create revision record if amount changed
        if form.cleaned_data.get('amount') != original_amount:
            BudgetRevision.objects.create(
                budget=self.object,
                original_amount=original_amount,
                revised_amount=self.object.amount,
                reason='Updated via budget edit form',
                approved_by=self.request.user,
                created_by=self.request.user,
            )
        messages.success(self.request, "Budget updated.")
        return response


class BudgetDeleteView(AuthMixin, ModuleRequiredMixin, DeleteView):
    model = Budget
    module_flag = 'enable_project_tracking'
    template_name = 'projects/confirm_delete.html'
    success_url = reverse_lazy('projects:budget_list')
    permission_required = ['projects.delete_budget']

    def get_queryset(self):
        return Budget.active_objects.filter(company=self.request.user_company)

    def form_valid(self, form):
        self.object.soft_delete(deleted_by=self.request.user)
        if is_htmx(self.request):
            response = HttpResponse(status=200, content='')
            response['HX-Trigger'] = json.dumps(toast_trigger('success', 'Budget deleted.'))
            return response
        messages.success(self.request, "Budget deleted.")
        return redirect(self.success_url)


@login_required
@module_required('enable_project_tracking')
def project_pnl_report(request):
    guard = _require_project_tracking(request)
    if guard:
        return guard

    company = request.user_company
    projects = Project.active_objects.filter(company=company).order_by('name')

    project = None
    project_id = request.GET.get('project')
    if project_id:
        project = projects.filter(pk=project_id).first()

    data = get_project_pnl(company, project=project)
    context = {'company': company, 'projects': projects, **data}
    return render(request, 'projects/project_pnl.html', context)


@login_required
@module_required('enable_project_tracking')
def budget_vs_actual_report(request):
    guard, context = _get_budget_vs_actual_context(request)
    if guard:
        return guard
    return render(request, 'projects/budget_vs_actual.html', context)


def _get_budget_vs_actual_context(request):
    guard = _require_forecasting(request)
    if guard:
        return guard, None

    company = request.user_company
    fiscal_year = _get_active_fiscal_year(request, company)
    data = get_budget_vs_actual(company, fiscal_year)
    return None, {'company': company, 'fiscal_year': fiscal_year, **data}


@login_required
@module_required('enable_forecasting')
def export_budget_vs_actual_excel(request):
    guard, context = _get_budget_vs_actual_context(request)
    if guard:
        return guard

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="budget_vs_actual.xlsx"'

    rows = [{
        'Budget Line': d['budget'].name,
        'Type': d['budget'].get_budget_type_display(),
        'Period Start': d['budget'].period_start,
        'Period End': d['budget'].period_end,
        'Budget': d['budget'].amount,
        'Actual': d['actual'],
        'Variance': d['variance'],
        'Utilisation %': d['utilisation'],
    } for d in context['budget_data']]
    df = pd.DataFrame(rows)
    df.to_excel(response, index=False, sheet_name='Budget vs Actual')
    return response


@login_required
@module_required('enable_forecasting')
def export_budget_vs_actual_pdf(request):
    guard, context = _get_budget_vs_actual_context(request)
    if guard:
        return guard
    return render_pdf_response(
        'projects/pdf/budget_vs_actual_pdf.html', context, 'budget_vs_actual.pdf')


# ─────────────────────────────────────────────────────────────────────────────
# Forecast
# ─────────────────────────────────────────────────────────────────────────────

class ForecastListView(AuthMixin, ModuleRequiredMixin, ListView):
    model = Forecast
    module_flag = 'enable_forecasting'
    template_name = 'projects/forecast_list.html'
    context_object_name = 'forecasts'
    permission_required = ['projects.view_forecast']
    paginate_by = 30

    def get_queryset(self):
        return Forecast.active_objects.filter(
            company=self.request.user_company
        ).select_related('fiscal_year', 'cost_centre', 'project', 'ledger_account').order_by(
            'year', 'month'
        )


class ForecastCreateView(AuthMixin, ModuleRequiredMixin, CreateView):
    model = Forecast
    module_flag = 'enable_forecasting'
    form_class = ForecastForm
    template_name = 'projects/forecast_form.html'
    success_url = reverse_lazy('projects:forecast_list')
    permission_required = ['projects.add_forecast']

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def form_valid(self, form):
        form.instance.company = self.request.user_company
        form.instance.created_by = self.request.user
        messages.success(self.request, "Forecast line created.")
        return super().form_valid(form)


class ForecastUpdateView(AuthMixin, ModuleRequiredMixin, UpdateView):
    model = Forecast
    module_flag = 'enable_forecasting'
    form_class = ForecastForm
    template_name = 'projects/forecast_form.html'
    success_url = reverse_lazy('projects:forecast_list')
    permission_required = ['projects.change_forecast']

    def get_queryset(self):
        return Forecast.active_objects.filter(company=self.request.user_company)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, "Forecast updated.")
        return super().form_valid(form)


class ForecastDeleteView(AuthMixin, ModuleRequiredMixin, DeleteView):
    model = Forecast
    module_flag = 'enable_forecasting'
    template_name = 'projects/confirm_delete.html'
    success_url = reverse_lazy('projects:forecast_list')
    permission_required = ['projects.delete_forecast']

    def get_queryset(self):
        return Forecast.active_objects.filter(company=self.request.user_company)

    def form_valid(self, form):
        self.object.soft_delete(deleted_by=self.request.user)
        if is_htmx(self.request):
            response = HttpResponse(status=200, content='')
            response['HX-Trigger'] = json.dumps(toast_trigger('success', 'Forecast deleted.'))
            return response
        messages.success(self.request, "Forecast deleted.")
        return redirect(self.success_url)


@login_required
@module_required('enable_forecasting')
def forecast_vs_actual_report(request):
    guard, context = _get_forecast_vs_actual_context(request)
    if guard:
        return guard
    return render(request, 'projects/forecast_vs_actual.html', context)


def _get_forecast_vs_actual_context(request):
    guard = _require_forecasting(request)
    if guard:
        return guard, None

    company = request.user_company
    fiscal_year = _get_active_fiscal_year(request, company)
    forecast_type = request.GET.get('type', 'REVENUE')
    data = get_forecast_vs_actual(company, fiscal_year, forecast_type)
    return None, {'company': company, 'fiscal_year': fiscal_year, **data}


@login_required
@module_required('enable_forecasting')
def export_forecast_vs_actual_excel(request):
    guard, context = _get_forecast_vs_actual_context(request)
    if guard:
        return guard

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="forecast_vs_actual.xlsx"'

    rows = [{
        'Name': d['forecast'].name,
        'Period': d['month_label'],
        'Account': d['forecast'].ledger_account.name if d['forecast'].ledger_account else '',
        'Forecast': d['forecast'].forecast_amount,
        'Actual': d['actual'],
        'Variance': d['variance'],
    } for d in context['forecast_data']]
    df = pd.DataFrame(rows)
    df.to_excel(response, index=False, sheet_name='Forecast vs Actual')
    return response


@login_required
@module_required('enable_forecasting')
def export_forecast_vs_actual_pdf(request):
    guard, context = _get_forecast_vs_actual_context(request)
    if guard:
        return guard
    return render_pdf_response(
        'projects/pdf/forecast_vs_actual_pdf.html', context, 'forecast_vs_actual.pdf')


@login_required
@module_required('enable_forecasting')
def print_forecast_vs_actual(request):
    guard, context = _get_forecast_vs_actual_context(request)
    if guard:
        return guard
    return render(request, 'projects/print/forecast_vs_actual_print.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# Project Tasks
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@module_required('enable_project_tracking')
def task_create(request, project_pk):
    project = get_object_or_404(Project, pk=project_pk, company=request.user_company)
    if request.method == 'POST':
        form = ProjectTaskForm(request.POST, request=request, project=project)
        if form.is_valid():
            task = form.save(commit=False)
            task.project = project
            task.created_by = request.user
            task.save()
            messages.success(request, f"Task '{task.title}' added.")
        else:
            messages.error(request, "Could not save task.")
    return redirect('projects:project_detail', pk=project_pk)


@login_required
@module_required('enable_project_tracking')
def task_update_status(request, pk):
    """HTMX quick-update for task status."""
    task = get_object_or_404(ProjectTask, pk=pk, project__company=request.user_company)
    if request.method == 'POST':
        new_status = request.POST.get('status')
        valid = [c[0] for c in ProjectTask._meta.get_field('status').choices]
        if new_status in valid:
            task.status = new_status
            task.updated_by = request.user
            task.save(update_fields=['status', 'updated_by'])
            messages.success(request, f"Task updated to {task.get_status_display()}.")
    return redirect('projects:project_detail', pk=task.project.pk)


@login_required
@module_required('enable_project_tracking')
def task_delete(request, pk):
    task = get_object_or_404(ProjectTask, pk=pk, project__company=request.user_company)
    project_pk = task.project.pk
    if request.method == 'POST':
        task.soft_delete(deleted_by=request.user)
        if is_htmx(request):
            response = HttpResponse(status=200, content='')
            response['HX-Trigger'] = json.dumps(toast_trigger('success', 'Task deleted.'))
            return response
        messages.success(request, "Task deleted.")
    return redirect('projects:project_detail', pk=project_pk)


# ─────────────────────────────────────────────────────────────────────────────
# Project Milestones
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@module_required('enable_project_tracking')
def milestone_create(request, project_pk):
    project = get_object_or_404(Project, pk=project_pk, company=request.user_company)
    if request.method == 'POST':
        form = ProjectMilestoneForm(request.POST, request=request)
        if form.is_valid():
            ms = form.save(commit=False)
            ms.project = project
            ms.created_by = request.user
            ms.save()
            messages.success(request, f"Milestone '{ms.title}' added.")
        else:
            messages.error(request, "Could not save milestone.")
    return redirect('projects:project_detail', pk=project_pk)


@login_required
@module_required('enable_project_tracking')
def milestone_complete(request, pk):
    ms = get_object_or_404(ProjectMilestone, pk=pk, project__company=request.user_company)
    if request.method == 'POST':
        from django.utils import timezone
        ms.is_completed = True
        ms.completed_date = timezone.now().date()
        ms.updated_by = request.user
        ms.save(update_fields=['is_completed', 'completed_date', 'updated_by'])
        messages.success(request, f"Milestone '{ms.title}' marked complete.")
    return redirect('projects:project_detail', pk=ms.project.pk)


@login_required
@module_required('enable_project_tracking')
def milestone_delete(request, pk):
    ms = get_object_or_404(ProjectMilestone, pk=pk, project__company=request.user_company)
    project_pk = ms.project.pk
    if request.method == 'POST':
        ms.soft_delete(deleted_by=request.user)
        if is_htmx(request):
            response = HttpResponse(status=200, content='')
            response['HX-Trigger'] = json.dumps(toast_trigger('success', 'Milestone deleted.'))
            return response
        messages.success(request, "Milestone deleted.")
    return redirect('projects:project_detail', pk=project_pk)


# ─────────────────────────────────────────────────────────────────────────────
# Time Logs
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@module_required('enable_project_tracking')
def timelog_create(request, project_pk):
    project = get_object_or_404(Project, pk=project_pk, company=request.user_company)
    if request.method == 'POST':
        form = ProjectTimeLogForm(request.POST, request=request, project=project)
        if form.is_valid():
            log = form.save(commit=False)
            log.project = project
            log.created_by = request.user
            log.save()
            messages.success(request, f"{log.hours}h logged.")
        else:
            messages.error(request, "Could not save time log.")
    return redirect('projects:project_detail', pk=project_pk)


@login_required
@module_required('enable_project_tracking')
def timelog_delete(request, pk):
    log = get_object_or_404(ProjectTimeLog, pk=pk, project__company=request.user_company)
    project_pk = log.project.pk
    if request.method == 'POST':
        log.soft_delete(deleted_by=request.user)
        if is_htmx(request):
            response = HttpResponse(status=200, content='')
            response['HX-Trigger'] = json.dumps(toast_trigger('success', 'Time log deleted.'))
            return response
        messages.success(request, "Time log deleted.")
    return redirect('projects:project_detail', pk=project_pk)


class TimeLogListView(AuthMixin, ModuleRequiredMixin, ListView):
    model = ProjectTimeLog
    module_flag = 'enable_project_tracking'
    template_name = 'projects/timelog_list.html'
    context_object_name = 'logs'
    permission_required = ['projects.view_projecttimelog']
    paginate_by = 30

    def get_queryset(self):
        qs = ProjectTimeLog.active_objects.filter(
            project__company=self.request.user_company
        ).select_related('project', 'employee', 'task').order_by('-log_date')
        project_pk = self.request.GET.get('project')
        if project_pk:
            qs = qs.filter(project_id=project_pk)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['projects'] = Project.active_objects.filter(company=self.request.user_company)
        ctx['selected_project'] = self.request.GET.get('project', '')
        ctx['total_hours'] = self.get_queryset().aggregate(t=Sum('hours'))['t'] or Decimal('0')
        return ctx


# ─────────────────────────────────────────────────────────────────────────────
# Risks
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@module_required('enable_project_tracking')
def risk_create(request, project_pk):
    project = get_object_or_404(Project, pk=project_pk, company=request.user_company)
    if request.method == 'POST':
        form = ProjectRiskForm(request.POST, request=request)
        if form.is_valid():
            risk = form.save(commit=False)
            risk.project = project
            risk.created_by = request.user
            risk.save()
            messages.success(request, f"Risk '{risk.title}' added.")
        else:
            messages.error(request, "Could not save risk.")
    return redirect('projects:project_detail', pk=project_pk)


@login_required
@module_required('enable_project_tracking')
def risk_update(request, pk):
    risk = get_object_or_404(ProjectRisk, pk=pk, project__company=request.user_company)
    if request.method == 'POST':
        form = ProjectRiskForm(request.POST, request=request, instance=risk)
        if form.is_valid():
            form.instance.updated_by = request.user
            form.save()
            messages.success(request, "Risk updated.")
    return redirect('projects:project_detail', pk=risk.project.pk)


@login_required
@module_required('enable_project_tracking')
def risk_delete(request, pk):
    risk = get_object_or_404(ProjectRisk, pk=pk, project__company=request.user_company)
    project_pk = risk.project.pk
    if request.method == 'POST':
        risk.soft_delete(deleted_by=request.user)
        if is_htmx(request):
            response = HttpResponse(status=200, content='')
            response['HX-Trigger'] = json.dumps(toast_trigger('success', 'Risk deleted.'))
            return response
        messages.success(request, "Risk deleted.")
    return redirect('projects:project_detail', pk=project_pk)


# ─────────────────────────────────────────────────────────────────────────────
# Documents
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@module_required('enable_project_tracking')
def document_upload(request, project_pk):
    project = get_object_or_404(Project, pk=project_pk, company=request.user_company)
    if request.method == 'POST':
        form = ProjectDocumentForm(request.POST, request.FILES)
        if form.is_valid():
            doc = form.save(commit=False)
            doc.project = project
            doc.created_by = request.user
            doc.save()
            messages.success(request, "Document uploaded.")
        else:
            messages.error(request, "Upload failed.")
    return redirect('projects:project_detail', pk=project_pk)


@login_required
@module_required('enable_project_tracking')
def document_delete(request, pk):
    doc = get_object_or_404(ProjectDocument, pk=pk, project__company=request.user_company)
    project_pk = doc.project.pk
    if request.method == 'POST':
        doc.soft_delete(deleted_by=request.user)
        if is_htmx(request):
            response = HttpResponse(status=200, content='')
            response['HX-Trigger'] = json.dumps(toast_trigger('success', 'Document removed.'))
            return response
        messages.success(request, "Document removed.")
    return redirect('projects:project_detail', pk=project_pk)


# ─────────────────────────────────────────────────────────────────────────────
# Budget Revision
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@module_required('enable_project_tracking')
def budget_revise(request, pk):
    """Record a budget revision — saves original amount, updates budget.amount."""
    budget = get_object_or_404(Budget, pk=pk, company=request.user_company)
    if request.method == 'POST':
        form = BudgetRevisionForm(request.POST)
        if form.is_valid():
            revised = form.cleaned_data['revised_amount']
            if revised == budget.amount:
                messages.warning(request, "Revised amount is the same as the current budget — no change made.")
            else:
                from django.db import transaction as db_tx
                with db_tx.atomic():
                    revision = form.save(commit=False)
                    revision.budget = budget
                    revision.original_amount = budget.amount
                    revision.approved_by = request.user
                    revision.created_by = request.user
                    revision.save()
                    budget.amount = revised
                    budget.updated_by = request.user
                    budget.save(update_fields=['amount', 'updated_by'])
                import logging
                logging.getLogger('audit').info(
                    'BUDGET_REVISED budget=%s from=%s to=%s actor=%s company=%s',
                    budget.name, revision.original_amount, revised,
                    request.user.email, budget.company,
                )
                messages.success(request, f"Budget revised from {revision.original_amount} to {revised}.")
        else:
            messages.error(request, "Could not save revision.")
    return redirect('projects:budget_list')


# ─────────────────────────────────────────────────────────────────────────────
# Project Status Change
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@module_required('enable_project_tracking')
def project_change_status(request, pk):
    project = get_object_or_404(Project, pk=pk, company=request.user_company)
    if request.method == 'POST':
        new_status = request.POST.get('status')
        valid = [c[0] for c in PROJECT_STATUS_CHOICES]
        if new_status in valid:
            project.status = new_status
            project.updated_by = request.user
            project.save(update_fields=['status', 'updated_by'])
            messages.success(request, f"Project status changed to {project.get_status_display()}.")
    return redirect('projects:project_detail', pk=pk)
