from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render

from apps.bookkeeping.models import LedgerAccount
from apps.company.fiscal_year_guard import fiscal_year_open_required
from ..models import Expense
from ..services.expense_service import cancel_expense, create_expense_batch


def _get_accounts(company):
    if not company:
        return LedgerAccount.objects.none(), LedgerAccount.objects.none()
    exp = LedgerAccount.objects.filter(company=company, account_type='EXPENSE').order_by('name')
    ast = LedgerAccount.objects.filter(company=company, account_type='ASSET').order_by('name')
    return exp, ast


def _parse_expense_rows(post, expense_qs, asset_qs):
    """Return (rows, errors). Each row may have a 'payment_splits' list for multi-payment."""
    rows = []
    errors = []
    i = 0
    while True:
        title = post.get(f'row_title_{i}', '').strip()
        if not title and i > 0:
            break
        if not title and i == 0:
            errors.append("At least one expense line is required.")
            break

        expense_id = post.get(f'row_expense_account_{i}', '').strip()
        amount_raw = post.get(f'row_amount_{i}', '').strip()

        try:
            amount = Decimal(amount_raw)
            if amount <= 0:
                raise ValueError()
        except (InvalidOperation, ValueError):
            errors.append(f"Row {i+1}: valid positive amount required.")
            i += 1
            continue

        exp_acc = expense_qs.filter(pk=expense_id).first()
        if not exp_acc:
            errors.append(f"Row {i+1}: select an expense account.")
            i += 1
            continue

        # Detect multi-payment mode for this line (pay_multi_account_i_0 exists)
        payment_splits = []
        pi = 0
        while True:
            acc_id = post.get(f'pay_multi_account_{i}_{pi}', '').strip()
            if not acc_id:
                break
            method_m = post.get(f'pay_multi_method_{i}_{pi}', 'CASH').strip()
            amount_m_raw = post.get(f'pay_multi_amount_{i}_{pi}', '').strip()
            try:
                amount_m = Decimal(amount_m_raw)
            except InvalidOperation:
                amount_m = Decimal('0')
            acc = asset_qs.filter(pk=acc_id).first()
            if acc and amount_m > 0:
                payment_splits.append({'payment_account': acc, 'payment_method': method_m, 'amount': amount_m})
            pi += 1

        # Validate multi-payment balance
        if payment_splits:
            split_total = sum(p['amount'] for p in payment_splits)
            if abs(split_total - amount) >= Decimal('0.01'):
                errors.append(f"Row {i+1}: payment total ({split_total:.2f}) must equal expense amount ({amount:.2f}).")
                i += 1
                continue

        # Single payment mode
        pay_acc = None
        method = 'CASH'
        if not payment_splits:
            payment_account_id = post.get(f'row_payment_account_{i}', '').strip()
            method = post.get(f'row_payment_method_{i}', '').strip()
            pay_acc = asset_qs.filter(pk=payment_account_id).first() if payment_account_id else None

        rows.append({
            'title':            title,
            'expense_account':  exp_acc,
            'payment_account':  pay_acc,
            'amount':           amount,
            'payment_method':   method,
            'payment_splits':   payment_splits,  # non-empty = multi-payment per line
            'reference':        post.get(f'row_reference_{i}', '').strip(),
            'description':      post.get(f'row_description_{i}', '').strip(),
        })
        i += 1
    return rows, errors


@login_required
def expense_list(request):
    company = getattr(request.user, 'company', None)
    qs = Expense.active_objects.filter(company=company).select_related('expense_account', 'payment_account')

    q = request.GET.get('q', '').strip()
    account_id = request.GET.get('account', '')
    method = request.GET.get('method', '')

    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(reference_number__icontains=q))
    if account_id:
        qs = qs.filter(expense_account_id=account_id)
    if method:
        qs = qs.filter(payment_method=method)

    total = qs.filter(status='RECORDED').aggregate(t=Sum('amount'))['t'] or 0
    expense_accounts, _ = _get_accounts(company)
    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'payments/expense_list.html', {
        'page_obj': page_obj, 'total': total,
        'expense_accounts': expense_accounts,
        'q': q, 'account_id': account_id, 'method': method,
    })


@login_required
@fiscal_year_open_required
def expense_create(request):
    company = getattr(request.user, 'company', None)
    expense_accounts, asset_accounts = _get_accounts(company)

    if request.method == 'POST':
        date_bs = request.POST.get('batch_date', '').strip()
        if not date_bs:
            messages.error(request, "Date is required.")
        else:
            expense_rows, row_errors = _parse_expense_rows(request.POST, expense_accounts, asset_accounts)

            # Validate single-payment rows have an account+method
            for idx, row in enumerate(expense_rows):
                if not row['payment_splits'] and not row['payment_account']:
                    row_errors.append(f"Row {idx+1}: select a payment account.")
                if not row['payment_splits'] and not row['payment_method']:
                    row_errors.append(f"Row {idx+1}: select a payment method.")

            if row_errors:
                for e in row_errors:
                    messages.error(request, e)
            elif expense_rows:
                try:
                    created = create_expense_batch(expense_rows, [], date_bs, company, request.user)
                    messages.success(request, f"{len(created)} expense(s) recorded successfully.")
                    return redirect('payments:expense_list')
                except Exception as exc:
                    messages.error(request, f"Error: {exc}")

    from apps.utils.nepali_date import today_bs
    return render(request, 'payments/expense_form.html', {
        'expense_accounts': expense_accounts,
        'asset_accounts':   asset_accounts,
        'today_bs':         today_bs(),
    })


@login_required
def expense_detail(request, pk):
    company = getattr(request.user, 'company', None)
    expense = get_object_or_404(
        Expense.objects.select_related('expense_account', 'payment_account', 'journal_entry'),
        pk=pk, company=company,
    )
    journal_lines = expense.journal_entry.lines.select_related('account').all() if expense.journal_entry else []
    return render(request, 'payments/expense_detail.html', {
        'expense': expense, 'journal_lines': journal_lines,
    })


@login_required
@fiscal_year_open_required
def expense_cancel(request, pk):
    company = getattr(request.user, 'company', None)
    expense = get_object_or_404(Expense, pk=pk, company=company)
    if request.method == 'POST':
        try:
            cancel_expense(expense, request.user)
            messages.success(request, f'Expense "{expense.title}" cancelled.')
        except ValueError as exc:
            messages.error(request, str(exc))
        return redirect('payments:expense_detail', pk=expense.pk)
    return render(request, 'payments/expense_cancel_confirm.html', {'expense': expense})
