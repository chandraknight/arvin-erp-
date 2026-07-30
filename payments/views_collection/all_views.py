from ..forms import *
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.db import transaction as db_transaction
from decimal import Decimal, InvalidOperation
from apps.bookkeeping.models import LedgerAccount
from apps.utils.constant import PAYMENT_TYPE_CHOICES
from ..models import Payment
from ..services.payment_number_service import generate_payment_number
from ..services.payment_services import consolidate_split_payment_journals
from apps.company.fiscal_year_guard import fiscal_year_open_required
from apps.vendors.models import Vendor
from apps.billing.models import VendorBill as BillingVendorBill, Invoice
from apps.customers.models import Customer
from apps.utils.amount_words import amount_in_words


def _parse_splits(post):
    """Extract split rows from POST. Returns list of {method, amount} or []."""
    splits = []
    i = 0
    while True:
        method = post.get(f'split_method_{i}', '').strip()
        raw = post.get(f'split_amount_{i}', '').strip()
        if not method or not raw:
            break
        try:
            splits.append({'method': method, 'amount': Decimal(raw)})
        except InvalidOperation:
            break
        i += 1
    return splits


def _stamp_payment(payment, request):
    """Assign company, branch, and creator from the request."""
    payment.created_by = request.user
    if hasattr(request.user, 'company') and request.user.company:
        payment.company = request.user.company
        user_branch = getattr(request, 'user_branch', None)
        if user_branch is not None:
            payment.branch = user_branch
        elif payment.invoice and payment.invoice.branch:
            payment.branch = payment.invoice.branch


@login_required
@fiscal_year_open_required
def payment_create(request):
    if request.method == 'POST':
        is_split = request.POST.get('split_enabled') == 'true'

        if is_split:
            splits = _parse_splits(request.POST)
            if not splits:
                messages.error(request, "Split payment enabled but no splits were provided.")
                form = PaymentForm(request.POST, user=request.user, request=request)
            else:
                # Validate base form using first split's method/amount
                post_data = request.POST.copy()
                post_data['method'] = splits[0]['method']
                post_data['amount'] = str(splits[0]['amount'])
                form = PaymentForm(post_data, user=request.user, request=request)

                if form.is_valid():
                    try:
                        with db_transaction.atomic():
                            company = getattr(request.user, 'company', None)
                            created_payments = []

                            for split in splits:
                                p = form.save(commit=False)
                                p.pk = None  # new record each time
                                p.method = split['method']
                                p.amount = split['amount']
                                _stamp_payment(p, request)
                                if company:
                                    ref, seq, fy = generate_payment_number(company.id, p.payment_type)
                                    p.reference_number = ref
                                    p.sequence_number = seq
                                    p.fiscal_year = fy
                                p.save()

                                if p.invoice:
                                    p.amount_applied = split['amount']
                                    p.save(update_fields=['amount_applied'])

                                created_payments.append(p)

                            # Update invoice outstanding balance once with total split amount
                            if form.cleaned_data.get('invoice'):
                                invoice = form.cleaned_data['invoice']
                                invoice.refresh_from_db()
                                total_paid = sum(s['amount'] for s in splits)
                                invoice.outstanding_balance = max(Decimal('0'), invoice.outstanding_balance - total_paid)
                                invoice.save(update_fields=['outstanding_balance'])

                            consolidate_split_payment_journals(created_payments)

                        messages.success(request, f"Split payment recorded ({len(splits)} methods).")
                        return redirect('payments:payment_list')
                    except Exception as e:
                        messages.error(request, f"Error recording split payment: {e}")
                else:
                    messages.error(request, "Please correct the errors below.")
        else:
            form = PaymentForm(request.POST, user=request.user, request=request)
            if form.is_valid():
                try:
                    payment = form.save(commit=False)
                    _stamp_payment(payment, request)
                    if not payment.reference_number and getattr(payment, 'company', None):
                        ref, seq, fy = generate_payment_number(payment.company.id, payment.payment_type)
                        payment.reference_number = ref
                        payment.sequence_number = seq
                        payment.fiscal_year = fy
                    payment.save()

                    if payment.invoice:
                        invoice = payment.invoice
                        invoice.outstanding_balance = max(Decimal('0'), invoice.outstanding_balance - payment.amount)
                        invoice.save(update_fields=['outstanding_balance'])
                        payment.amount_applied = payment.amount
                        payment.save(update_fields=['amount_applied'])

                    messages.success(request, "Payment recorded successfully.")
                    return redirect('payments:payment_list')
                except Exception as e:
                    messages.error(request, f"An error occurred while recording the payment: {e}")
            else:
                messages.error(request, "Please correct the errors below.")

        auto_payment_number = None
        if hasattr(request.user, 'company') and request.user.company:
            auto_payment_number, _, _fy = generate_payment_number(request.user.company.id, 'CUSTOMER')
    else:
        form = PaymentForm(user=request.user, request=request)
        auto_payment_number = None
        if hasattr(request.user, 'company') and request.user.company:
            auto_payment_number, _, _fy = generate_payment_number(request.user.company.id, 'CUSTOMER')
    
    company = getattr(request.user, 'company', None)
    vendors = Vendor.objects.filter(company=company).order_by('name') if company else Vendor.objects.none()
    unpaid_bills = (
        BillingVendorBill.objects.filter(company=company, status='UNPAID')
        .select_related('vendor')
        .order_by('-bill_date')
        if company else BillingVendorBill.objects.none()
    )
    customers = Customer.objects.filter(company=company).order_by('name') if company else Customer.objects.none()
    outstanding_invoices = (
        Invoice.objects.filter(company=company, status='ISSUED', outstanding_balance__gt=0)
        .select_related('customer')
        .order_by('-transaction_date')
        if company else Invoice.objects.none()
    )
    context = {
        'form': form,
        'auto_payment_number': auto_payment_number,
        'vendors': vendors,
        'unpaid_bills': unpaid_bills,
        'customers': customers,
        'outstanding_invoices': outstanding_invoices,
    }
    return render(request, 'payments/add_payment.html', context)

@login_required
def payment_list(request):
    from django.db.models import Q
    from apps.utils.htmx import is_htmx

    # Company scoping
    company = request.user_company if hasattr(request, 'user_company') else getattr(request.user, 'company', None)
    if company:
        payments = Payment.active_objects.filter(company=company).order_by('-date', '-created_at')
        # Branch isolation — restrict to the user's branch when assigned
        user_branch = getattr(request, 'user_branch', None)
        if user_branch is not None:
            payments = payments.filter(branch=user_branch)
    else:
        payments = Payment.objects.none()

    # Payment type filter
    payment_type = request.GET.get('payment_type', '').strip()
    if payment_type:
        payments = payments.filter(payment_type=payment_type)

    # Live search — reference number, invoice number, description
    q = request.GET.get('q', '').strip()
    if q:
        payments = payments.filter(
            Q(reference_number__icontains=q) |
            Q(invoice__invoice_number__icontains=q) |
            Q(description__icontains=q)
        )

    # Pagination
    from django.core.paginator import Paginator
    paginate_by = int(request.GET.get('paginate_by', 20))
    paginator = Paginator(payments, paginate_by)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    from django.db.models import Sum
    total = payments.aggregate(t=Sum('amount'))['t'] or 0

    context = {
        'payments': page_obj,
        'page_obj': page_obj,
        'payment_types': PAYMENT_TYPE_CHOICES,
        'selected_payment_type': payment_type,
        'q': q,
        'paginate_by': paginate_by,
        'total': total,
        'total_count': paginator.count,
    }

    # HTMX request — return only the table partial
    if is_htmx(request):
        return render(request, 'payments/partials/payment_table.html', context)

    return render(request, 'payments/payment_list.html', context)

@login_required
def payment_detail(request, pk):
    payment = get_object_or_404(Payment, pk=pk)

    # Company isolation
    if hasattr(request.user, 'company') and request.user.company:
        if payment.company != request.user.company:
            messages.error(request, "You don't have access to this payment.")
            return redirect('payments:payment_list')

    # Branch isolation
    if not request.user.is_superuser:
        user_branch = getattr(request, 'user_branch', None)
        if user_branch is not None and payment.branch != user_branch:
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied('You do not have access to this payment.')

    context = {
        'payment': payment,
        'journal_entry': payment.journal_entry,
    }
    return render(request, 'payments/payment_detail.html', context)

@login_required
def payment_update(request, pk):
    """
    Payments are immutable once recorded.
    Editing a payment is not permitted — cancel it and record a new one instead.
    """
    payment = get_object_or_404(Payment, pk=pk)

    # Company isolation
    if not request.user.is_superuser:
        company = request.user_company if hasattr(request, 'user_company') else getattr(request.user, 'company', None)
        if company and payment.company != company:
            raise PermissionDenied("You do not have access to this payment.")

    messages.error(
        request,
        f"Payment {payment.payment_number} cannot be edited once recorded. "
        "Cancel it and record a new payment to make corrections.",
    )
    return redirect('payments:payment_detail', pk=pk)

@login_required
def get_ledger_accounts(request):
    """API endpoint to get ledger accounts for the user's company"""
    if not hasattr(request.user, 'company') or not request.user.company:
        return JsonResponse({'accounts': []})
    
    accounts = LedgerAccount.objects.filter(company=request.user.company).values('id', 'name', 'account_type')
    return JsonResponse({'accounts': list(accounts)})


@login_required
def payment_cancel(request, pk):
    """
    Cancel (soft-delete) a payment.
    GET  → confirmation page.
    POST → calls Payment.cancel(), restores invoice outstanding balance if applicable.
    """
    import logging as _logging
    _audit = _logging.getLogger('audit')

    payment = get_object_or_404(Payment, pk=pk)

    # Company isolation
    if not request.user.is_superuser:
        company = request.user_company if hasattr(request, 'user_company') else getattr(request.user, 'company', None)
        if company and payment.company != company:
            raise PermissionDenied("You do not have access to this payment.")

    if payment.is_deleted:
        messages.warning(request, f"Payment {payment.payment_number} is already cancelled.")
        return redirect('payments:payment_list')

    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        if not reason:
            messages.error(request, "A cancellation reason is required.")
            return render(request, 'payments/payment_cancel_confirm.html', {'payment': payment})

        try:
            payment.cancel(cancelled_by=request.user, reason=reason)
            _audit.info(
                'PAYMENT_CANCELLED payment=%s actor=%s company=%s reason=%s',
                payment.payment_number, request.user.email,
                getattr(request, 'user_company', None), reason,
            )
            messages.success(
                request,
                f"Payment {payment.payment_number} has been cancelled. "
                "Record a new payment to replace it.",
            )
        except ValueError as exc:
            messages.error(request, str(exc))

        return redirect('payments:payment_list')

    return render(request, 'payments/payment_cancel_confirm.html', {'payment': payment})


@login_required
def payment_receipt(request, pk):
    payment = get_object_or_404(Payment, pk=pk)

    # Company isolation
    if hasattr(request.user, 'company') and request.user.company:
        if payment.company != request.user.company:
            messages.error(request, "You don't have access to this payment.")
            return redirect('payments:payment_list')

    # Branch isolation
    if not request.user.is_superuser:
        user_branch = getattr(request, 'user_branch', None)
        if user_branch is not None and payment.branch != user_branch:
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied('You do not have access to this payment.')

    context = {
        'payment': payment,
        'amount_in_words': amount_in_words(payment.amount),
    }
    return render(request, 'payments/payment_receipt.html', context)
