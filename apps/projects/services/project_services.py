import datetime
from decimal import Decimal
from django.db.models import Sum, Count, Q, F, OuterRef, Subquery, DecimalField
from django.db.models.functions import Coalesce

from apps.projects.models import (
    Project, ProjectTask, ProjectMilestone, ProjectRisk,
    ProjectExpense, ProjectRevenue, Budget, Forecast,
)

_ZERO = Decimal('0')

# Subquery that returns total active expenses for a project row
_expense_sq = Subquery(
    ProjectExpense.active_objects
    .filter(project=OuterRef('pk'))
    .values('project')
    .annotate(t=Sum('amount'))
    .values('t'),
    output_field=DecimalField(max_digits=14, decimal_places=2),
)

# Subquery that returns total active revenue for a project row
_revenue_sq = Subquery(
    ProjectRevenue.active_objects
    .filter(project=OuterRef('pk'))
    .values('project')
    .annotate(t=Sum('amount'))
    .values('t'),
    output_field=DecimalField(max_digits=14, decimal_places=2),
)


def get_dashboard_stats(company):
    today = datetime.date.today()

    # Annotate each project with aggregated totals in a single DB round-trip
    projects = Project.active_objects.filter(company=company).annotate(
        expense_total=Coalesce(_expense_sq, _ZERO),
        revenue_total=Coalesce(_revenue_sq, _ZERO),
    )

    agg = projects.aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(status='ACTIVE')),
        planning=Count('id', filter=Q(status='PLANNING')),
        completed=Count('id', filter=Q(status='COMPLETED')),
        on_hold=Count('id', filter=Q(status='ON_HOLD')),
        total_budget=Coalesce(Sum('budget_amount'), _ZERO),
        total_expenses=Coalesce(Sum('expense_total'), _ZERO),
        total_revenue=Coalesce(Sum('revenue_total'), _ZERO),
        # over_budget: annotated expense exceeds the project's own budget_amount
        over_budget=Count('id', filter=Q(expense_total__gt=F('budget_amount'), budget_amount__gt=0)),
    )

    return {
        'projects': projects,
        'stats': {
            'total_projects': agg['total'],
            'active': agg['active'],
            'planning': agg['planning'],
            'completed': agg['completed'],
            'on_hold': agg['on_hold'],
            'over_budget': agg['over_budget'],
            'total_budget': agg['total_budget'],
            'total_expenses': agg['total_expenses'],
            'total_revenue': agg['total_revenue'],
            'open_tasks': ProjectTask.active_objects.filter(
                project__company=company, status__in=['TODO', 'IN_PROGRESS', 'REVIEW']
            ).count(),
            'open_risks': ProjectRisk.active_objects.filter(
                project__company=company, status='OPEN'
            ).count(),
            'overdue_milestones': ProjectMilestone.active_objects.filter(
                project__company=company,
                is_completed=False,
                target_date__lt=today,
            ).count(),
        },
        'recent_expenses': ProjectExpense.active_objects.filter(
            project__company=company
        ).select_related('project', 'ledger_account').order_by('-expense_date')[:10],
        'upcoming_milestones': ProjectMilestone.active_objects.filter(
            project__company=company, is_completed=False
        ).select_related('project').order_by('target_date')[:5],
    }


def get_budget_vs_actual(company, fiscal_year=None):
    budgets = Budget.active_objects.filter(company=company)
    if fiscal_year:
        budgets = budgets.filter(fiscal_year=fiscal_year)

    budget_data = []
    total_budget = _ZERO
    total_actual = _ZERO

    for b in budgets.select_related('cost_centre', 'project', 'ledger_account'):
        actual = b.actual_amount
        budget_data.append({
            'budget': b,
            'actual': actual,
            'variance': b.amount - actual,
            'utilisation': b.utilisation_pct,
            'over_budget': actual > b.amount,
        })
        total_budget += b.amount
        total_actual += actual

    return {
        'budget_data': budget_data,
        'total_budget': total_budget,
        'total_actual': total_actual,
        'total_variance': total_budget - total_actual,
    }


def get_forecast_vs_actual(company, fiscal_year=None, forecast_type='REVENUE'):
    forecasts = Forecast.active_objects.filter(company=company, forecast_type=forecast_type)
    if fiscal_year:
        forecasts = forecasts.filter(fiscal_year=fiscal_year)

    forecast_data = []
    for f in forecasts.select_related('cost_centre', 'project', 'ledger_account').order_by('year', 'month'):
        actual = f.actual_amount
        forecast_data.append({
            'forecast': f,
            'actual': actual,
            'variance': f.forecast_amount - actual,
            'month_label': f"{f.year}/{f.month:02d}",
        })

    return {
        'forecast_data': forecast_data,
        'forecast_type': forecast_type,
        'total_forecast': sum(d['forecast'].forecast_amount for d in forecast_data),
        'total_actual': sum(d['actual'] for d in forecast_data),
    }
