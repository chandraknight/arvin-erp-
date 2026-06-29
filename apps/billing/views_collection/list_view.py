from ...utils.global_models import *
from django.db.models import Sum, Count, Q
from django.utils import timezone
from decimal import Decimal


@auth_required('billing.view_invoice')
def billing_dashboard(request):
    company = request.user_company
    user_branch = getattr(request, 'user_branch', None)

    qs = Invoice.active_objects.exclude(status='CANCELLED')
    if not request.user.is_superuser:
        qs = qs.filter(company=company)
        if user_branch:
            qs = qs.filter(branch=user_branch)

    today = timezone.now().date()
    month_start = today.replace(day=1)

    stats = qs.aggregate(
        total_issued=Count('id', filter=Q(status='ISSUED')),
        total_outstanding=Sum('outstanding_balance', filter=Q(status='ISSUED', outstanding_balance__gt=0)),
        total_invoiced_month=Sum('total', filter=Q(status='ISSUED', transaction_date__gte=month_start)),
        count_paid=Count('id', filter=Q(status='ISSUED', outstanding_balance=0)),
        count_overdue=Count('id', filter=Q(status='ISSUED', outstanding_balance__gt=0, due_date__lt=today)),
    )

    recent_invoices = qs.filter(status='ISSUED').select_related(
        'customer', 'company'
    ).order_by('-transaction_date', '-created_at')[:10]

    draft_invoices = qs.filter(status='DRAFT').select_related(
        'customer'
    ).order_by('-created_at')[:5]

    context = {
        'stats': {
            'total_issued':         stats['total_issued'] or 0,
            'total_outstanding':    stats['total_outstanding'] or Decimal('0.00'),
            'total_invoiced_month': stats['total_invoiced_month'] or Decimal('0.00'),
            'count_paid':           stats['count_paid'] or 0,
            'count_overdue':        stats['count_overdue'] or 0,
        },
        'recent_invoices': recent_invoices,
        'draft_invoices':  draft_invoices,
        'today':           today,
        'rupee':           RUPEE,
    }
    return render(request, 'billing/billing_dashboard.html', context)


@auth_required('billing.view_invoice')
def invoice_list(request):
    company = request.user_company
    user_branch = getattr(request, 'user_branch', None)

    qs = Invoice.active_objects.select_related('customer', 'company', 'branch').order_by(
        '-transaction_date', '-created_at'
    )
    if not request.user.is_superuser:
        qs = qs.filter(company=company)
        if user_branch:
            qs = qs.filter(branch=user_branch)

    # Filters
    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    start = request.GET.get('start', '').strip()
    end   = request.GET.get('end', '').strip()

    if q:
        qs = qs.filter(
            Q(invoice_number__icontains=q) |
            Q(customer__name__icontains=q)
        )
    if status:
        if status == 'PAID':
            qs = qs.filter(status='ISSUED', outstanding_balance=0)
        elif status == 'OUTSTANDING':
            qs = qs.filter(status='ISSUED', outstanding_balance__gt=0)
        else:
            qs = qs.filter(status=status)
    if start:
        from apps.utils.nepali_date import bs_str_to_ad
        sd = bs_str_to_ad(start)
        if sd:
            qs = qs.filter(transaction_date__gte=sd)
    if end:
        from apps.utils.nepali_date import bs_str_to_ad
        ed = bs_str_to_ad(end)
        if ed:
            qs = qs.filter(transaction_date__lte=ed)

    try:
        paginate_by = int(request.GET.get('paginate_by', 20))
    except (ValueError, TypeError):
        paginate_by = 20

    paginator = Paginator(qs, paginate_by)
    page_obj  = paginator.get_page(request.GET.get('page', 1))

    totals = qs.aggregate(
        grand_total=Sum('total'),
        grand_outstanding=Sum('outstanding_balance'),
    )

    from apps.utils.htmx import is_htmx
    context = {
        'object_list':       page_obj.object_list,
        'page_obj':          page_obj,
        'paginate_by':       paginate_by,
        'q':                 q,
        'status':            status,
        'start':             start,
        'end':               end,
        'grand_total':       totals['grand_total'] or Decimal('0.00'),
        'grand_outstanding': totals['grand_outstanding'] or Decimal('0.00'),
        'today':             timezone.now().date(),
        'rupee':             RUPEE,
    }
    if is_htmx(request):
        return render(request, 'billing/partials/invoice_table.html', context)
    return render(request, 'billing/invoices/invoice_list.html', context)


@auth_required('billing.view_creditnote')
def credit_note_list(request):
    template_name = 'reports/billing/credit_note_list.html'
    base_queryset = CreditNote.active_objects.order_by('-created_at')

    if not request.user.is_superuser and hasattr(request.user, 'company'):
        base_queryset = base_queryset.filter(company=request.user.company)
        # Branch isolation — restrict to the user's branch when assigned
        user_branch = getattr(request, 'user_branch', None)
        if user_branch is not None:
            base_queryset = base_queryset.filter(branch=user_branch)

    try:
        paginate_by = int(request.GET.get('paginate_by', 10))
    except (ValueError, TypeError):
        paginate_by = 10

    paginator = Paginator(base_queryset, paginate_by)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, template_name, {
        'object_list': page_obj.object_list,
        'page_obj': page_obj,
        'paginate_by': paginate_by
    })

@auth_required('billing.view_debitnote')
def debit_note_list(request):
    template_name = 'reports/billing/debitnote_note_list.html'
    base_queryset = DebitNote.active_objects.order_by('-created_at')

    if not request.user.is_superuser and hasattr(request.user, 'company'):
        base_queryset = base_queryset.filter(company=request.user.company)
        # Branch isolation — restrict to the user's branch when assigned
        user_branch = getattr(request, 'user_branch', None)
        if user_branch is not None:
            base_queryset = base_queryset.filter(branch=user_branch)

    try:
        paginate_by = int(request.GET.get('paginate_by', 10))
    except (ValueError, TypeError):
        paginate_by = 10

    paginator = Paginator(base_queryset, paginate_by)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, template_name, {
        'object_list': page_obj.object_list,
        'page_obj': page_obj,
        'paginate_by': paginate_by
    })



