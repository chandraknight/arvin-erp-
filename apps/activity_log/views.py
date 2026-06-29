from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from apps.utils.nepali_date import bs_str_to_ad

from .models import ActivityLog


@login_required
def activity_log_list(request):
    """
    Main activity log browser.
    Superusers see all logs; regular users see only their company's logs.
    """
    qs = ActivityLog.objects.select_related('user').order_by('-timestamp')

    # Company scoping for non-superusers
    if not request.user.is_superuser:
        company_name = getattr(getattr(request.user, 'company', None), 'name', None)
        if company_name:
            qs = qs.filter(company_name=company_name)
        else:
            qs = qs.none()

    # ── Filters ───────────────────────────────────────────────────────────────
    search = request.GET.get('search', '').strip()
    action = request.GET.get('action', '').strip()
    model = request.GET.get('model', '').strip()
    user_filter = request.GET.get('user', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    if search:
        qs = qs.filter(
            Q(object_repr__icontains=search) |
            Q(user_email__icontains=search) |
            Q(model_name__icontains=search) |
            Q(object_id__icontains=search)
        )
    if action:
        qs = qs.filter(action=action)
    if model:
        qs = qs.filter(model_name__icontains=model)
    if user_filter:
        qs = qs.filter(user_email__icontains=user_filter)
    if date_from:
        d = bs_str_to_ad(date_from)
        if d:
            qs = qs.filter(timestamp__date__gte=d)
    if date_to:
        d = bs_str_to_ad(date_to)
        if d:
            qs = qs.filter(timestamp__date__lte=d)

    # ── Distinct model names for filter dropdown ───────────────────────────────
    model_names = (
        ActivityLog.objects.values_list('model_name', flat=True)
        .distinct().order_by('model_name')
    )

    # ── Pagination ─────────────────────────────────────────────────────────────
    paginator = Paginator(qs, 50)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'page_obj': page_obj,
        'action_choices': ActivityLog.ACTION_CHOICES,
        'model_names': model_names,
        'filters': {
            'search': search,
            'action': action,
            'model': model,
            'user': user_filter,
            'date_from': date_from,
            'date_to': date_to,
        },
        'total_count': qs.count(),
    }
    return render(request, 'activity_log/log_list.html', context)


@login_required
def activity_log_detail(request, pk):
    """Detail view for a single log entry — shows full change diff."""
    log = get_object_or_404(ActivityLog, pk=pk)

    # Non-superusers can only see their company's logs
    if not request.user.is_superuser:
        company_name = getattr(getattr(request.user, 'company', None), 'name', None)
        if log.company_name != company_name:
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied

    # Build a readable diff table
    diff_rows = []
    if log.changes and log.action == ActivityLog.ACTION_UPDATE:
        for field, vals in log.changes.items():
            diff_rows.append({
                'field': field.replace('_id', '').replace('_', ' ').title(),
                'old': vals.get('old'),
                'new': vals.get('new'),
            })
    elif log.changes and log.action == ActivityLog.ACTION_CREATE:
        for field, val in log.changes.items():
            diff_rows.append({
                'field': field.replace('_id', '').replace('_', ' ').title(),
                'old': '—',
                'new': val,
            })

    context = {
        'log': log,
        'diff_rows': diff_rows,
    }
    return render(request, 'activity_log/log_detail.html', context)


@login_required
def object_history(request, model_name, object_id):
    """Show all activity log entries for a specific object."""
    qs = ActivityLog.objects.filter(
        model_name=model_name,
        object_id=object_id,
    ).order_by('-timestamp')

    if not request.user.is_superuser:
        company_name = getattr(getattr(request.user, 'company', None), 'name', None)
        if company_name:
            qs = qs.filter(company_name=company_name)

    context = {
        'logs': qs,
        'model_name': model_name,
        'object_id': object_id,
    }
    return render(request, 'activity_log/object_history.html', context)
