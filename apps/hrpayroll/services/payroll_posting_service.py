"""
Posts the payroll journal entry for a single finalized Payslip.

Complements the existing run-level _post_payroll_journal() in
apps/hrpayroll/views.py (DR Salary Expense / CR Salary Payable, posted when
a run's payslips are generated). This posts the detailed per-payslip
breakdown — income tax, SSF, and net pay — once a payslip is finalized.
"""
import logging
from decimal import Decimal

from django.db import transaction

logger = logging.getLogger(__name__)


@transaction.atomic
def post_payslip_journal(payslip):
    from apps.bookkeeping.models import (
        JournalEntry, JournalEntryLine, assert_balanced,
        get_or_create_system_account, reverse_journal,
    )
    from apps.company.services.company_services import setup_default_ledger_accounts
    from apps.hrpayroll.models import SSFContribution
    from apps.hrpayroll.services.payroll_tax_service import calculate_ssf

    if not payslip.is_finalized:
        return

    company = payslip.payroll_run.company
    setup_default_ledger_accounts(company)

    for old_entry in JournalEntry.objects.filter(
        company=company,
        description=f"Payslip {payslip.pk}",
        is_reversed=False,
        is_deleted=False,
    ):
        reverse_journal(old_entry, reason=f'Payslip {payslip.pk} re-finalized')

    employee_ssf = Decimal('0.00')
    employer_ssf = Decimal('0.00')
    if company.enable_ssf:
        basic_salary = payslip.employee.salary or Decimal('0.00')
        employee_ssf, employer_ssf = calculate_ssf(basic_salary)

    income_tax_amount = payslip.income_tax_amount or Decimal('0.00')
    net_pay = payslip.gross_pay - income_tax_amount - employee_ssf - (payslip.total_deductions or Decimal('0.00'))

    salary_expense = get_or_create_system_account(company, "Salary Expense", "EXPENSE", code="5300")
    income_tax_payable = get_or_create_system_account(company, "Income Tax Payable", "LIABILITY", code="2160")
    ssf_payable = get_or_create_system_account(company, "SSF Payable", "LIABILITY", code="2170")
    net_salary_payable = get_or_create_system_account(company, "Net Salary Payable", "LIABILITY", code="2180")

    entry = JournalEntry.objects.create(
        company=company,
        date=payslip.issue_date,
        description=f"Payslip {payslip.pk}",
        source_type='PAYROLL',
    )

    lines = []
    debit_expense = payslip.gross_pay + (employer_ssf if company.enable_ssf else Decimal('0.00'))
    lines.append(JournalEntryLine(journal_entry=entry, account=salary_expense, entry_type='DEBIT', amount=debit_expense))

    if income_tax_amount > Decimal('0.00'):
        lines.append(JournalEntryLine(journal_entry=entry, account=income_tax_payable, entry_type='CREDIT', amount=income_tax_amount))

    total_ssf = employee_ssf + employer_ssf
    if company.enable_ssf and total_ssf > Decimal('0.00'):
        lines.append(JournalEntryLine(journal_entry=entry, account=ssf_payable, entry_type='CREDIT', amount=total_ssf))

    lines.append(JournalEntryLine(journal_entry=entry, account=net_salary_payable, entry_type='CREDIT', amount=net_pay))

    JournalEntryLine.objects.bulk_create(lines)
    assert_balanced(entry)

    if company.enable_ssf and total_ssf > Decimal('0.00'):
        SSFContribution.objects.update_or_create(
            payslip=payslip,
            defaults={'employee_amount': employee_ssf, 'employer_amount': employer_ssf, 'journal_entry': entry},
        )

    from apps.hrpayroll.models import Payslip
    Payslip.objects.filter(pk=payslip.pk).update(journal_entry=entry, net_pay=net_pay)
