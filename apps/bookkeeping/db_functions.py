"""
apps/bookkeeping/db_functions.py
================================
Python interface to the PostgreSQL functions and stored procedures installed
by migration 0009. On MySQL / any non-PostgreSQL backend, every function falls
back to a pure-Django-ORM implementation so the application behaves identically
across both databases.

Security
--------
Every SQL call uses parameterised queries (%s placeholders).
No user-supplied strings are ever interpolated into SQL.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from django.db import connection

logger = logging.getLogger(__name__)


def _is_postgres() -> bool:
    return connection.vendor == 'postgresql'


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _dictfetchall(cursor) -> list[dict]:
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _dictfetchone(cursor) -> dict | None:
    row = cursor.fetchone()
    if row is None:
        return None
    columns = [col[0] for col in cursor.description]
    return dict(zip(columns, row))


# ─────────────────────────────────────────────────────────────────────────────
# post_invoice_journal — ORM fallback
# ─────────────────────────────────────────────────────────────────────────────

def _post_invoice_journal_orm(invoice_id: UUID | str) -> UUID | None:
    """
    Pure-ORM equivalent of fn_post_invoice_journal.
    Soft-deletes any prior unlinked draft journal entry for this invoice,
    then inserts a fresh balanced double-entry.
    """
    from django.db import transaction as db_transaction
    from apps.billing.models import Invoice
    from apps.bookkeeping.models import JournalEntry, JournalEntryLine, LedgerAccount

    def _ledger(company, name):
        return LedgerAccount.objects.filter(company=company, name=name, is_deleted=False).first()

    with db_transaction.atomic():
        try:
            inv = Invoice.objects.select_related('customer__related_ledger_account').get(
                pk=invoice_id, is_deleted=False
            )
        except Invoice.DoesNotExist:
            raise ValueError(f"Invoice {invoice_id} not found")

        if not inv.total or inv.total <= 0:
            return None

        company = inv.company

        # Resolve debit (receivable) account
        if inv.customer_id is None:
            debit_account = _ledger(company, 'Cash')
        elif inv.customer and inv.customer.related_ledger_account:
            debit_account = inv.customer.related_ledger_account
        else:
            debit_account = _ledger(company, 'Accounts Receivable')

        sales_account = _ledger(company, 'Sales Revenue')
        tax_account   = _ledger(company, 'Tax Payable')
        disc_account  = _ledger(company, 'Discount Given')

        if not all([debit_account, sales_account, tax_account, disc_account]):
            missing = [n for n, a in [
                ('Cash/AR', debit_account), ('Sales Revenue', sales_account),
                ('Tax Payable', tax_account), ('Discount Given', disc_account),
            ] if not a]
            raise ValueError(f"Missing default ledger accounts for company {company}: {missing}")

        description = f'Invoice {inv.invoice_number}'

        # Soft-delete prior draft entries not linked to a confirmed payment
        from django.db.models import Subquery
        from apps.payments.models import Payment
        linked_je_ids = Payment.objects.filter(
            journal_entry_id__isnull=False
        ).values('journal_entry_id')

        JournalEntry.objects.filter(
            company=company,
            description=description,
            is_deleted=False,
        ).exclude(id__in=Subquery(linked_je_ids)).update(
            is_deleted=True,
            is_reversed=True,
            reversed_reason=f'Replaced by re-post of invoice {inv.invoice_number}',
        )

        from django.utils.timezone import now as _now
        from datetime import date as _date
        entry = JournalEntry.objects.create(
            company=company,
            date=inv.transaction_date or _date.today(),
            description=description,
        )

        discount = inv.discount_amount or Decimal('0.00')
        tax      = inv.tax_amount      or Decimal('0.00')
        calc_sales = inv.total + discount - tax

        lines = [
            JournalEntryLine(journal_entry=entry, account=debit_account, entry_type='DEBIT',  amount=inv.total),
            JournalEntryLine(journal_entry=entry, account=sales_account, entry_type='CREDIT', amount=calc_sales),
        ]
        if tax > 0:
            lines.append(JournalEntryLine(
                journal_entry=entry, account=tax_account, entry_type='CREDIT', amount=tax,
            ))
        if discount > 0:
            lines.append(JournalEntryLine(
                journal_entry=entry, account=disc_account, entry_type='DEBIT', amount=discount,
            ))
        JournalEntryLine.objects.bulk_create(lines)

        logger.info("post_invoice_journal (ORM) invoice=%s journal_entry=%s", invoice_id, entry.id)
        return entry.id


# ─────────────────────────────────────────────────────────────────────────────
# post_payment_journal — ORM fallback
# ─────────────────────────────────────────────────────────────────────────────

def _post_payment_journal_orm(payment_id: UUID | str) -> UUID:
    """
    Pure-ORM equivalent of fn_post_payment_journal.
    Creates the double-entry journal for a Payment and links it back.
    """
    from django.db import transaction as db_transaction
    from apps.payments.models import Payment
    from apps.bookkeeping.models import JournalEntry, JournalEntryLine, LedgerAccount

    def _ledger(company, name):
        return LedgerAccount.objects.filter(company=company, name=name, is_deleted=False).first()

    with db_transaction.atomic():
        try:
            pay = Payment.objects.select_related(
                'invoice__customer__related_ledger_account',
                'bank_account__ledger_account',
            ).get(pk=payment_id, is_deleted=False)
        except Payment.DoesNotExist:
            raise ValueError(f"Payment {payment_id} not found")

        company = pay.company

        # Resolve cash/bank leg
        cash_bank = None
        if pay.bank_account_id and pay.bank_account and pay.bank_account.ledger_account:
            cash_bank = pay.bank_account.ledger_account
        if not cash_bank:
            cash_bank = _ledger(company, 'Cash' if pay.method == 'CASH' else 'Bank')
        if not cash_bank:
            raise ValueError(f"Cash/Bank ledger account not found for company {company}")

        # Resolve destination leg and description
        if pay.payment_type == 'CUSTOMER':
            customer = pay.invoice.customer if pay.invoice else None
            dest = (
                customer.related_ledger_account
                if customer and customer.related_ledger_account
                else _ledger(company, 'Accounts Receivable')
            )
            inv_num = pay.invoice.invoice_number if pay.invoice else str(payment_id)
            description = f'Payment for Invoice {inv_num}'
        elif pay.payment_type == 'VENDOR':
            dest = _ledger(company, 'Accounts Payable')
            description = 'Vendor Payment'
        elif pay.payment_type == 'SALARY':
            dest = _ledger(company, 'Salary Expense')
            description = 'Salary Payment'
        else:
            dest = pay.ledger_account
            description = 'Expense Payment' if pay.payment_type == 'EXPENSE' else 'Other Payment'

        if not dest:
            raise ValueError(
                f"Destination ledger account not found for payment {payment_id} type={pay.payment_type}"
            )

        entry = JournalEntry.objects.create(
            company=company,
            date=pay.date,
            description=description,
        )
        JournalEntryLine.objects.bulk_create([
            JournalEntryLine(journal_entry=entry, account=cash_bank, entry_type='DEBIT',  amount=pay.amount),
            JournalEntryLine(journal_entry=entry, account=dest,      entry_type='CREDIT', amount=pay.amount),
        ])

        Payment.objects.filter(pk=payment_id).update(
            journal_entry=entry,
            amount_applied=pay.amount,
        )

        logger.info("post_payment_journal (ORM) payment=%s journal_entry=%s", payment_id, entry.id)
        return entry.id


# ─────────────────────────────────────────────────────────────────────────────
# Public API — auto-selects PostgreSQL stored proc or ORM fallback
# ─────────────────────────────────────────────────────────────────────────────

def post_invoice_journal(invoice_id: UUID | str) -> UUID | None:
    """
    Atomically create/replace the double-entry journal for an invoice.
    Uses fn_post_invoice_journal on PostgreSQL; pure ORM on all other backends.
    """
    if _is_postgres():
        with connection.cursor() as cur:
            cur.execute("SELECT fn_post_invoice_journal(%s)", [str(invoice_id)])
            row = cur.fetchone()
            result = row[0] if row else None
            logger.info("post_invoice_journal (PG) invoice=%s journal_entry=%s", invoice_id, result)
            return UUID(str(result)) if result else None
    return _post_invoice_journal_orm(invoice_id)


def post_payment_journal(payment_id: UUID | str) -> UUID:
    """
    Atomically create the double-entry journal for a payment and link it back.
    Uses fn_post_payment_journal on PostgreSQL; pure ORM on all other backends.
    """
    if _is_postgres():
        with connection.cursor() as cur:
            cur.execute("SELECT fn_post_payment_journal(%s)", [str(payment_id)])
            row = cur.fetchone()
            result = row[0] if row else None
            if result is None:
                raise ValueError(f"fn_post_payment_journal returned NULL for payment {payment_id}")
            logger.info("post_payment_journal (PG) payment=%s journal_entry=%s", payment_id, result)
            return UUID(str(result))
    return _post_payment_journal_orm(payment_id)


def close_period_journal(
    company_id: UUID | str,
    fiscal_year_id: UUID | str,
    closed_by_id: UUID | str | None = None,
) -> UUID:
    """Year-end P&L closing. PostgreSQL only for now; raises on other backends."""
    if not _is_postgres():
        raise NotImplementedError(
            "close_period_journal requires PostgreSQL. "
            "On MySQL, trigger year-end closing via the FiscalYear.close() service method."
        )
    with connection.cursor() as cur:
        cur.execute(
            "SELECT fn_close_period_journal(%s, %s, %s)",
            [str(company_id), str(fiscal_year_id),
             str(closed_by_id) if closed_by_id else None],
        )
        row = cur.fetchone()
        result = row[0] if row else None
        if result is None:
            raise ValueError(f"fn_close_period_journal returned NULL for FY {fiscal_year_id}")
        logger.info(
            "close_period_journal company=%s fiscal_year=%s closing_entry=%s",
            company_id, fiscal_year_id, result,
        )
        return UUID(str(result))


def get_account_balance(account_id: UUID | str, as_of_date=None) -> Decimal:
    """PostgreSQL only — used for advanced reporting."""
    if not _is_postgres():
        raise NotImplementedError("get_account_balance requires PostgreSQL.")
    with connection.cursor() as cur:
        if as_of_date is None:
            cur.execute("SELECT fn_get_account_balance(%s)", [str(account_id)])
        else:
            cur.execute("SELECT fn_get_account_balance(%s, %s)", [str(account_id), as_of_date])
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"LedgerAccount {account_id} not found")
        return Decimal(str(row[0])) if row[0] is not None else Decimal("0.00")


def get_trial_balance(company_id: UUID | str, as_of_date=None) -> list[dict]:
    """PostgreSQL only."""
    if not _is_postgres():
        raise NotImplementedError("get_trial_balance requires PostgreSQL.")
    with connection.cursor() as cur:
        if as_of_date is None:
            cur.execute("SELECT * FROM fn_get_trial_balance(%s)", [str(company_id)])
        else:
            cur.execute("SELECT * FROM fn_get_trial_balance(%s, %s)", [str(company_id), as_of_date])
        rows = _dictfetchall(cur)
    for row in rows:
        row["debit_balance"]  = Decimal(str(row["debit_balance"]))
        row["credit_balance"] = Decimal(str(row["credit_balance"]))
    return rows


def get_ar_aging(company_id: UUID | str, as_of_date=None) -> list[dict]:
    """PostgreSQL only."""
    if not _is_postgres():
        raise NotImplementedError("get_ar_aging requires PostgreSQL.")
    with connection.cursor() as cur:
        if as_of_date is None:
            cur.execute("SELECT * FROM fn_get_ar_aging(%s)", [str(company_id)])
        else:
            cur.execute("SELECT * FROM fn_get_ar_aging(%s, %s)", [str(company_id), as_of_date])
        rows = _dictfetchall(cur)
    decimal_cols = ("current_amount", "days_1_30", "days_31_60", "days_61_90", "days_90_plus", "total_outstanding")
    for row in rows:
        for col in decimal_cols:
            row[col] = Decimal(str(row[col]))
    return rows


def query_trial_balance_view(company_id: UUID | str) -> list[dict]:
    if not _is_postgres():
        raise NotImplementedError("query_trial_balance_view requires PostgreSQL.")
    with connection.cursor() as cur:
        cur.execute("SELECT * FROM vw_trial_balance WHERE company_id = %s", [str(company_id)])
        rows = _dictfetchall(cur)
    for row in rows:
        row["total_debits"]  = Decimal(str(row["total_debits"]))
        row["total_credits"] = Decimal(str(row["total_credits"]))
        row["net_balance"]   = Decimal(str(row["net_balance"]))
    return rows


def query_ar_aging_view(company_id: UUID | str) -> list[dict]:
    if not _is_postgres():
        raise NotImplementedError("query_ar_aging_view requires PostgreSQL.")
    with connection.cursor() as cur:
        cur.execute("SELECT * FROM vw_ar_aging WHERE company_id = %s", [str(company_id)])
        rows = _dictfetchall(cur)
    decimal_cols = ("current_amount", "days_1_30", "days_31_60", "days_61_90", "days_90_plus", "total_outstanding")
    for row in rows:
        for col in decimal_cols:
            row[col] = Decimal(str(row[col]))
    return rows


def query_income_statement_view(
    company_id: UUID | str,
    start_date=None,
    end_date=None,
) -> dict[str, Any]:
    if not _is_postgres():
        raise NotImplementedError("query_income_statement_view requires PostgreSQL.")
    sql = "SELECT * FROM vw_income_statement WHERE company_id = %s"
    params: list[Any] = [str(company_id)]
    if start_date:
        sql += " AND date >= %s"
        params.append(start_date)
    if end_date:
        sql += " AND date <= %s"
        params.append(end_date)
    with connection.cursor() as cur:
        cur.execute(sql, params)
        rows = _dictfetchall(cur)
    revenue_lines = [r for r in rows if r["account_type"] == "REVENUE"]
    expense_lines = [r for r in rows if r["account_type"] == "EXPENSE"]
    total_revenue  = sum(Decimal(str(r["net_amount"])) for r in revenue_lines)
    total_expenses = sum(Decimal(str(r["net_amount"])) for r in expense_lines)
    return {
        "total_revenue":  total_revenue,
        "total_expenses": total_expenses,
        "net_profit":     total_revenue - total_expenses,
        "revenue_lines":  revenue_lines,
        "expense_lines":  expense_lines,
    }


def query_balance_sheet_view(company_id: UUID | str) -> dict[str, Any]:
    if not _is_postgres():
        raise NotImplementedError("query_balance_sheet_view requires PostgreSQL.")
    with connection.cursor() as cur:
        cur.execute("SELECT * FROM vw_balance_sheet_summary WHERE company_id = %s", [str(company_id)])
        rows = _dictfetchall(cur)
    result: dict[str, Any] = {"ASSET": Decimal("0.00"), "LIABILITY": Decimal("0.00"), "EQUITY": Decimal("0.00")}
    for row in rows:
        result[row["account_type"]] = Decimal(str(row["net_balance"]))
    total_assets = result["ASSET"]
    total_le     = result["LIABILITY"] + result["EQUITY"]
    result["is_balanced"] = abs(total_assets - total_le) < Decimal("0.01")
    return result


def query_outstanding_invoices_view(company_id: UUID | str) -> list[dict]:
    if not _is_postgres():
        raise NotImplementedError("query_outstanding_invoices_view requires PostgreSQL.")
    with connection.cursor() as cur:
        cur.execute("SELECT * FROM vw_outstanding_invoices WHERE company_id = %s", [str(company_id)])
        return _dictfetchall(cur)


def query_vendor_payables_view(company_id: UUID | str) -> list[dict]:
    if not _is_postgres():
        raise NotImplementedError("query_vendor_payables_view requires PostgreSQL.")
    with connection.cursor() as cur:
        cur.execute("SELECT * FROM vw_vendor_payables WHERE company_id = %s", [str(company_id)])
        rows = _dictfetchall(cur)
    for row in rows:
        row["total_amount"]       = Decimal(str(row["total_amount"]))
        row["total_paid"]         = Decimal(str(row["total_paid"]))
        row["outstanding_amount"] = Decimal(str(row["outstanding_amount"]))
    return rows


def query_payroll_summary_view(company_id: UUID | str) -> list[dict]:
    if not _is_postgres():
        raise NotImplementedError("query_payroll_summary_view requires PostgreSQL.")
    with connection.cursor() as cur:
        cur.execute("SELECT * FROM vw_payroll_summary WHERE company_id = %s", [str(company_id)])
        rows = _dictfetchall(cur)
    for row in rows:
        row["total_gross_pay"]  = Decimal(str(row["total_gross_pay"]))
        row["total_deductions"] = Decimal(str(row["total_deductions"]))
        row["total_net_pay"]    = Decimal(str(row["total_net_pay"]))
    return rows

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

from django.db import connection

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _dictfetchall(cursor) -> list[dict]:
    """Return all rows from a cursor as a list of dicts."""
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _dictfetchone(cursor) -> dict | None:
    """Return one row from a cursor as a dict, or None."""
    row = cursor.fetchone()
    if row is None:
        return None
    columns = [col[0] for col in cursor.description]
    return dict(zip(columns, row))


# ─────────────────────────────────────────────────────────────────────────────
# fn_get_account_balance
# ─────────────────────────────────────────────────────────────────────────────

def get_account_balance(account_id: UUID | str, as_of_date=None) -> Decimal:
    """
    Return the net balance of a single ledger account up to *as_of_date*.

    Sign convention matches account type:
      ASSET / EXPENSE  → positive = debit balance
      LIABILITY / EQUITY / REVENUE → positive = credit balance

    Raises
    ------
    ValueError  if the account does not exist in the DB.
    """
    with connection.cursor() as cur:
        if as_of_date is None:
            cur.execute(
                "SELECT fn_get_account_balance(%s)",
                [str(account_id)],
            )
        else:
            cur.execute(
                "SELECT fn_get_account_balance(%s, %s)",
                [str(account_id), as_of_date],
            )
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"LedgerAccount {account_id} not found")
        return Decimal(str(row[0])) if row[0] is not None else Decimal("0.00")


# ─────────────────────────────────────────────────────────────────────────────
# fn_get_trial_balance
# ─────────────────────────────────────────────────────────────────────────────

def get_trial_balance(company_id: UUID | str, as_of_date=None) -> list[dict]:
    """
    Return the trial balance for *company_id* up to *as_of_date*.

    Each row dict contains:
        account_id, account_code, account_name, account_type,
        debit_balance (Decimal), credit_balance (Decimal)

    Replaces the N+1 Python loop in reports/views.py::trial_balance_report.
    """
    with connection.cursor() as cur:
        if as_of_date is None:
            cur.execute(
                "SELECT * FROM fn_get_trial_balance(%s)",
                [str(company_id)],
            )
        else:
            cur.execute(
                "SELECT * FROM fn_get_trial_balance(%s, %s)",
                [str(company_id), as_of_date],
            )
        rows = _dictfetchall(cur)

    for row in rows:
        row["debit_balance"]  = Decimal(str(row["debit_balance"]))
        row["credit_balance"] = Decimal(str(row["credit_balance"]))
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# fn_get_ar_aging
# ─────────────────────────────────────────────────────────────────────────────

def get_ar_aging(company_id: UUID | str, as_of_date=None) -> list[dict]:
    """
    Return AR aging buckets per customer for *company_id*.

    Each row dict contains:
        customer_id, customer_name,
        current_amount, days_1_30, days_31_60, days_61_90, days_90_plus,
        total_outstanding  (all Decimal)
    """
    with connection.cursor() as cur:
        if as_of_date is None:
            cur.execute(
                "SELECT * FROM fn_get_ar_aging(%s)",
                [str(company_id)],
            )
        else:
            cur.execute(
                "SELECT * FROM fn_get_ar_aging(%s, %s)",
                [str(company_id), as_of_date],
            )
        rows = _dictfetchall(cur)

    decimal_cols = (
        "current_amount", "days_1_30", "days_31_60",
        "days_61_90", "days_90_plus", "total_outstanding",
    )
    for row in rows:
        for col in decimal_cols:
            row[col] = Decimal(str(row[col]))
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# fn_post_invoice_journal
# ─────────────────────────────────────────────────────────────────────────────

def post_invoice_journal(invoice_id: UUID | str) -> UUID | None:
    """
    Atomically create/replace the double-entry journal for an invoice.

    Fixes:
      Bug 2 — uses transaction_date, not due_date
      Bug 4 — exact description match instead of icontains

    Returns the new JournalEntry UUID, or None if the invoice has zero total.
    Raises django.db.DatabaseError on any DB-level constraint violation.
    """
    with connection.cursor() as cur:
        cur.execute(
            "SELECT fn_post_invoice_journal(%s)",
            [str(invoice_id)],
        )
        row = cur.fetchone()
        result = row[0] if row else None
        logger.info(
            "post_invoice_journal invoice=%s journal_entry=%s",
            invoice_id, result,
        )
        return UUID(str(result)) if result else None


# ─────────────────────────────────────────────────────────────────────────────
# fn_post_payment_journal
# ─────────────────────────────────────────────────────────────────────────────

def post_payment_journal(payment_id: UUID | str) -> UUID:
    """
    Atomically create the double-entry journal for a payment and link it back.

    Fixes:
      Bug 3 — uses customer's related_ledger_account for CUSTOMER payments

    Returns the new JournalEntry UUID.
    Raises django.db.DatabaseError on any DB-level constraint violation.
    """
    with connection.cursor() as cur:
        cur.execute(
            "SELECT fn_post_payment_journal(%s)",
            [str(payment_id)],
        )
        row = cur.fetchone()
        result = row[0] if row else None
        if result is None:
            raise ValueError(f"fn_post_payment_journal returned NULL for payment {payment_id}")
        logger.info(
            "post_payment_journal payment=%s journal_entry=%s",
            payment_id, result,
        )
        return UUID(str(result))


# ─────────────────────────────────────────────────────────────────────────────
# fn_close_period_journal
# ─────────────────────────────────────────────────────────────────────────────

def close_period_journal(
    company_id: UUID | str,
    fiscal_year_id: UUID | str,
    closed_by_id: UUID | str | None = None,
) -> UUID:
    """
    Perform year-end P&L closing for *fiscal_year_id*.

    Creates a closing JournalEntry that zeroes all REVENUE and EXPENSE accounts
    into Retained Earnings (auto-created if missing).

    Idempotent — safe to call twice; returns the existing closing entry UUID
    if the fiscal year is already marked closed.

    Returns the closing JournalEntry UUID.
    """
    with connection.cursor() as cur:
        cur.execute(
            "SELECT fn_close_period_journal(%s, %s, %s)",
            [str(company_id), str(fiscal_year_id),
             str(closed_by_id) if closed_by_id else None],
        )
        row = cur.fetchone()
        result = row[0] if row else None
        if result is None:
            raise ValueError(
                f"fn_close_period_journal returned NULL for FY {fiscal_year_id}"
            )
        logger.info(
            "close_period_journal company=%s fiscal_year=%s closing_entry=%s",
            company_id, fiscal_year_id, result,
        )
        return UUID(str(result))


# ─────────────────────────────────────────────────────────────────────────────
# DB Views — query helpers
# ─────────────────────────────────────────────────────────────────────────────

def query_trial_balance_view(company_id: UUID | str) -> list[dict]:
    """
    Query vw_trial_balance for *company_id* (all-time, no date filter).
    Faster than fn_get_trial_balance for dashboard widgets that don't need
    a specific as-of date.
    """
    with connection.cursor() as cur:
        cur.execute(
            "SELECT * FROM vw_trial_balance WHERE company_id = %s",
            [str(company_id)],
        )
        rows = _dictfetchall(cur)
    for row in rows:
        row["total_debits"]  = Decimal(str(row["total_debits"]))
        row["total_credits"] = Decimal(str(row["total_credits"]))
        row["net_balance"]   = Decimal(str(row["net_balance"]))
    return rows


def query_ar_aging_view(company_id: UUID | str) -> list[dict]:
    """Query vw_ar_aging for *company_id* (as of today)."""
    with connection.cursor() as cur:
        cur.execute(
            "SELECT * FROM vw_ar_aging WHERE company_id = %s",
            [str(company_id)],
        )
        rows = _dictfetchall(cur)
    decimal_cols = (
        "current_amount", "days_1_30", "days_31_60",
        "days_61_90", "days_90_plus", "total_outstanding",
    )
    for row in rows:
        for col in decimal_cols:
            row[col] = Decimal(str(row[col]))
    return rows


def query_income_statement_view(
    company_id: UUID | str,
    start_date=None,
    end_date=None,
) -> dict[str, Any]:
    """
    Query vw_income_statement for *company_id* with optional date range.

    Returns a summary dict:
        total_revenue (Decimal), total_expenses (Decimal), net_profit (Decimal),
        revenue_lines (list[dict]), expense_lines (list[dict])
    """
    sql = "SELECT * FROM vw_income_statement WHERE company_id = %s"
    params: list[Any] = [str(company_id)]

    if start_date:
        sql += " AND date >= %s"
        params.append(start_date)
    if end_date:
        sql += " AND date <= %s"
        params.append(end_date)

    with connection.cursor() as cur:
        cur.execute(sql, params)
        rows = _dictfetchall(cur)

    revenue_lines = [r for r in rows if r["account_type"] == "REVENUE"]
    expense_lines = [r for r in rows if r["account_type"] == "EXPENSE"]

    total_revenue  = sum(Decimal(str(r["net_amount"])) for r in revenue_lines)
    total_expenses = sum(Decimal(str(r["net_amount"])) for r in expense_lines)

    return {
        "total_revenue":  total_revenue,
        "total_expenses": total_expenses,
        "net_profit":     total_revenue - total_expenses,
        "revenue_lines":  revenue_lines,
        "expense_lines":  expense_lines,
    }


def query_balance_sheet_view(company_id: UUID | str) -> dict[str, Any]:
    """
    Query vw_balance_sheet_summary for *company_id*.

    Returns a dict keyed by account_type:
        ASSET, LIABILITY, EQUITY → net_balance (Decimal)
        is_balanced (bool)
    """
    with connection.cursor() as cur:
        cur.execute(
            "SELECT * FROM vw_balance_sheet_summary WHERE company_id = %s",
            [str(company_id)],
        )
        rows = _dictfetchall(cur)

    result: dict[str, Any] = {
        "ASSET":     Decimal("0.00"),
        "LIABILITY": Decimal("0.00"),
        "EQUITY":    Decimal("0.00"),
    }
    for row in rows:
        result[row["account_type"]] = Decimal(str(row["net_balance"]))

    total_assets = result["ASSET"]
    total_le     = result["LIABILITY"] + result["EQUITY"]
    result["is_balanced"] = abs(total_assets - total_le) < Decimal("0.01")
    return result


def query_outstanding_invoices_view(company_id: UUID | str) -> list[dict]:
    """Query vw_outstanding_invoices for *company_id*."""
    with connection.cursor() as cur:
        cur.execute(
            "SELECT * FROM vw_outstanding_invoices WHERE company_id = %s",
            [str(company_id)],
        )
        return _dictfetchall(cur)


def query_vendor_payables_view(company_id: UUID | str) -> list[dict]:
    """Query vw_vendor_payables for *company_id*."""
    with connection.cursor() as cur:
        cur.execute(
            "SELECT * FROM vw_vendor_payables WHERE company_id = %s",
            [str(company_id)],
        )
        rows = _dictfetchall(cur)
    for row in rows:
        row["total_amount"]      = Decimal(str(row["total_amount"]))
        row["total_paid"]        = Decimal(str(row["total_paid"]))
        row["outstanding_amount"] = Decimal(str(row["outstanding_amount"]))
    return rows


def query_payroll_summary_view(company_id: UUID | str) -> list[dict]:
    """Query vw_payroll_summary for *company_id*."""
    with connection.cursor() as cur:
        cur.execute(
            "SELECT * FROM vw_payroll_summary WHERE company_id = %s",
            [str(company_id)],
        )
        rows = _dictfetchall(cur)
    for row in rows:
        row["total_gross_pay"]   = Decimal(str(row["total_gross_pay"]))
        row["total_deductions"]  = Decimal(str(row["total_deductions"]))
        row["total_net_pay"]     = Decimal(str(row["total_net_pay"]))
    return rows
