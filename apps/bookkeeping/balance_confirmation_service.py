"""
Party balance confirmation letters — snapshot a customer/vendor ledger
balance as of a date so it can be sent out for written audit confirmation.
"""
from decimal import Decimal


def generate_confirmation(company, party, as_of_date):
    """
    party: a Customer or Vendor instance with related_ledger_account set.
    Returns the created BalanceConfirmationRequest.
    """
    from apps.customers.models import Customer
    from apps.reports.views import build_ledger_statement
    from .models import BalanceConfirmationRequest

    if not party.related_ledger_account:
        raise ValueError(f"'{party}' has no ledger account — cannot confirm balance.")

    statement = build_ledger_statement(party.related_ledger_account, date_to=as_of_date)
    balance = statement['closing_balance']

    kwargs = {'company': company, 'as_of_date': as_of_date, 'balance': balance}
    if isinstance(party, Customer):
        kwargs['customer'] = party
    else:
        kwargs['vendor'] = party

    return BalanceConfirmationRequest.objects.create(**kwargs)
