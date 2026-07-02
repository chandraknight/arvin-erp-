from decimal import Decimal
from django.db import transaction as db_transaction

from apps.bookkeeping.models import JournalEntry, JournalEntryLine, reverse_journal
from apps.utils.nepali_date import bs_str_to_ad
from ..models import Expense


@db_transaction.atomic
def create_expense_batch(expense_rows: list, payment_rows: list, date_bs, company, user) -> list:
    """
    Create multiple Expense records sharing one balanced journal entry.

    expense_rows: [{'title', 'expense_account', 'amount', 'reference', 'description', 'payment_method'}]
    payment_rows: [{'payment_account', 'payment_method', 'amount'}]
      - payment_rows drives the CR side; their amounts must sum == sum of expense_rows amounts.
      - If payment_rows is empty, payment_account / method come from expense_rows individually
        (single-row simple mode, one journal per expense).
    """
    ad_date = bs_str_to_ad(str(date_bs)) if isinstance(date_bs, str) else date_bs

    def _auto_expense_ref():
        """Generate sequential EXP reference if caller didn't supply one."""
        try:
            from apps.payments.services.payment_number_service import generate_payment_number
            ref, _, _fy = generate_payment_number(str(company.id), 'EXPENSE')
            return ref
        except Exception:
            return ''

    # ── Batch mode: shared journal, split payment ──────────────────────
    if payment_rows:
        description = ", ".join(r['title'] for r in expense_rows[:3])
        if len(expense_rows) > 3:
            description += f" +{len(expense_rows) - 3} more"

        je = JournalEntry.objects.create(
            company=company,
            date=ad_date,
            description=f"Expenses: {description}",
            created_by=user,
        )

        # DR each expense line
        debit_lines = []
        for row in expense_rows:
            debit_lines.append(JournalEntryLine(
                journal_entry=je,
                account=row['expense_account'],
                entry_type='DEBIT',
                narration=row['title'],
                amount=row['amount'],
            ))
        JournalEntryLine.objects.bulk_create(debit_lines)

        # CR each payment split
        credit_lines = []
        for pay in payment_rows:
            credit_lines.append(JournalEntryLine(
                journal_entry=je,
                account=pay['payment_account'],
                entry_type='CREDIT',
                narration=f"Paid via {pay['payment_method']}",
                amount=pay['amount'],
            ))
        JournalEntryLine.objects.bulk_create(credit_lines)

        # Use first payment row's account/method for Expense records (for display)
        primary_pay = payment_rows[0]
        expenses = []
        for row in expense_rows:
            exp = Expense.objects.create(
                company=company,
                date=ad_date,
                title=row['title'],
                expense_account=row['expense_account'],
                payment_account=primary_pay['payment_account'],
                amount=row['amount'],
                payment_method=primary_pay['payment_method'],
                reference_number=row.get('reference') or _auto_expense_ref(),
                description=row.get('description', '') or '',
                status='RECORDED',
                journal_entry=je,
                created_by=user,
            )
            expenses.append(exp)
        return expenses

    # ── Per-row mode: one journal per expense, CR side may be split ───
    expenses = []
    for row in expense_rows:
        je = JournalEntry.objects.create(
            company=company,
            date=ad_date,
            description=f"Expense: {row['title']}",
            created_by=user,
        )

        # DR the expense account
        JournalEntryLine.objects.create(
            journal_entry=je,
            account=row['expense_account'],
            entry_type='DEBIT',
            narration=row['title'],
            amount=row['amount'],
        )

        splits = row.get('payment_splits') or []
        if splits:
            # CR each payment split
            credit_lines = [
                JournalEntryLine(
                    journal_entry=je,
                    account=pay['payment_account'],
                    entry_type='CREDIT',
                    narration=f"Paid via {pay['payment_method']}",
                    amount=pay['amount'],
                )
                for pay in splits
            ]
            JournalEntryLine.objects.bulk_create(credit_lines)
            primary = splits[0]
            pay_account = primary['payment_account']
            pay_method = primary['payment_method']
        else:
            JournalEntryLine.objects.create(
                journal_entry=je,
                account=row['payment_account'],
                entry_type='CREDIT',
                narration=f"Paid via {row['payment_method']}",
                amount=row['amount'],
            )
            pay_account = row['payment_account']
            pay_method = row['payment_method']

        exp = Expense.objects.create(
            company=company,
            date=ad_date,
            title=row['title'],
            expense_account=row['expense_account'],
            payment_account=pay_account,
            amount=row['amount'],
            payment_method=pay_method,
            reference_number=row.get('reference') or _auto_expense_ref(),
            description=row.get('description', '') or '',
            status='RECORDED',
            journal_entry=je,
            created_by=user,
        )
        expenses.append(exp)
    return expenses


@db_transaction.atomic
def cancel_expense(expense: Expense, user) -> Expense:
    if expense.status == 'CANCELLED':
        raise ValueError("Expense is already cancelled.")

    if expense.journal_entry:
        # Only reverse the journal if this is the last non-cancelled expense using it
        siblings = expense.journal_entry.expenses.exclude(pk=expense.pk).filter(status='RECORDED')
        if not siblings.exists():
            reverse_journal(
                expense.journal_entry,
                reason=f'Expense cancelled: {expense.title}',
                user=user,
            )

    expense.status = 'CANCELLED'
    expense.updated_by = user
    expense.save(update_fields=['status', 'updated_by'])
    return expense
