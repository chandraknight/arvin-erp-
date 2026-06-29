"""
apps/bookkeeping/db_functions.py
================================
Python interface to the PostgreSQL functions, views, and stored procedures
installed by migration 0009_postgres_functions_triggers_views.

Usage pattern
-------------
All public functions accept a Django database connection alias (default='default').
They return plain Python dicts / lists of dicts so callers never touch raw cursors.

Security
--------
Every SQL call uses parameterised queries (%s placeholders).
No user-supplied strings are ever interpolated into SQL.
All PostgreSQL functions are defined with SECURITY DEFINER — they run with the
privileges of the function owner, not the calling DB role.
"""

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
