from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from ..models import BankAccount, BankReconciliation
from apps.bookkeeping.models import JournalEntryLine


@login_required
def bank_reconciliation(request, pk):
    """
    NFRS bank reconciliation: mark ledger lines for this bank account as
    reconciled/unreconciled against a bank statement, then record the
    reconciled book vs statement balance as of a chosen date.
    """
    company = getattr(request.user, 'company', None)
    bank_account = get_object_or_404(BankAccount, pk=pk, company=company)

    if not bank_account.ledger_account:
        messages.error(request, "This bank account has no linked ledger account.")
        return redirect('payments:bank_account_list')

    if request.method == 'POST':
        if request.POST.get('action') == 'toggle_cleared':
            line_id = request.POST.get('line_id')
            line = get_object_or_404(
                JournalEntryLine, pk=line_id, account=bank_account.ledger_account)
            line.is_cleared = not line.is_cleared
            from django.utils import timezone
            line.cleared_date = timezone.now().date() if line.is_cleared else None
            line.save(update_fields=['is_cleared', 'cleared_date'])
            return redirect('payments:bank_reconciliation', pk=pk)

        if request.POST.get('action') == 'save_reconciliation':
            statement_date_str = request.POST.get('statement_date')
            statement_balance_str = request.POST.get('statement_balance', '0')
            try:
                from datetime import date as _date
                statement_date = _date.fromisoformat(statement_date_str) if statement_date_str else _date.today()
                statement_balance = Decimal(statement_balance_str or '0')

                def _dec(field_name):
                    return Decimal(request.POST.get(field_name) or '0')

                deposits_in_transit = _dec('deposits_in_transit')
                unpresented_cheques = _dec('unpresented_cheques')
                bank_charges_not_recorded = _dec('bank_charges_not_recorded')
                interest_not_recorded = _dec('interest_not_recorded')
                other_adjustments = _dec('other_adjustments')
            except (ValueError, TypeError):
                messages.error(request, "Invalid statement date or balance.")
                return redirect('payments:bank_reconciliation', pk=pk)

            book_balance = _cleared_balance(bank_account.ledger_account)
            BankReconciliation.objects.create(
                bank_account=bank_account,
                statement_date=statement_date,
                statement_balance=statement_balance,
                book_balance=book_balance,
                reconciled_by=request.user,
                notes=request.POST.get('notes', ''),
                deposits_in_transit=deposits_in_transit,
                unpresented_cheques=unpresented_cheques,
                bank_charges_not_recorded=bank_charges_not_recorded,
                interest_not_recorded=interest_not_recorded,
                other_adjustments=other_adjustments,
            )
            messages.success(request, f"Reconciliation saved for {statement_date}.")
            return redirect('payments:bank_reconciliation', pk=pk)

    lines = JournalEntryLine.objects.filter(
        account=bank_account.ledger_account, journal_entry__is_deleted=False,
    ).select_related('journal_entry').order_by('-journal_entry__date', '-id')

    uncleared_lines = lines.filter(is_cleared=False)
    cleared_balance = _cleared_balance(bank_account.ledger_account)
    book_balance = _account_balance(bank_account.ledger_account)

    history = bank_account.reconciliations.select_related('reconciled_by')[:10]

    context = {
        'bank_account': bank_account,
        'lines': lines,
        'uncleared_lines': uncleared_lines,
        'cleared_balance': cleared_balance,
        'book_balance': book_balance,
        'uncleared_difference': book_balance - cleared_balance,
        'history': history,
    }
    return render(request, 'payments/bank_accounts/bank_reconciliation.html', context)


def _account_balance(ledger_account):
    from django.db.models import Sum, Q
    from django.db.models.functions import Coalesce
    agg = JournalEntryLine.objects.filter(
        account=ledger_account, journal_entry__is_deleted=False,
    ).aggregate(
        debit=Coalesce(Sum('amount', filter=Q(entry_type='DEBIT')), Decimal('0')),
        credit=Coalesce(Sum('amount', filter=Q(entry_type='CREDIT')), Decimal('0')),
    )
    return agg['debit'] - agg['credit']


def _cleared_balance(ledger_account):
    from django.db.models import Sum, Q
    from django.db.models.functions import Coalesce
    agg = JournalEntryLine.objects.filter(
        account=ledger_account, journal_entry__is_deleted=False, is_cleared=True,
    ).aggregate(
        debit=Coalesce(Sum('amount', filter=Q(entry_type='DEBIT')), Decimal('0')),
        credit=Coalesce(Sum('amount', filter=Q(entry_type='CREDIT')), Decimal('0')),
    )
    return agg['debit'] - agg['credit']
