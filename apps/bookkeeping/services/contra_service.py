from decimal import Decimal

from django.core.exceptions import ValidationError

from ..models import post_journal_entry

CONTRA_ELIGIBLE_TYPES = {'ASSET', 'LIABILITY'}


def post_contra_entry(company, date, from_account, to_account, amount, description, created_by=None):
    """
    NFRS contra entry: transfer between the entity's own accounts (cash<->bank,
    bank<->bank). Never touches INCOME/EXPENSE/EQUITY — both legs must be the
    same NFRS account type (ASSET-to-ASSET or LIABILITY-to-LIABILITY).
    """
    if from_account.account_type not in CONTRA_ELIGIBLE_TYPES:
        raise ValidationError(
            f"'{from_account.name}' is a {from_account.get_account_type_display()} account — "
            "contra entries may only move between ASSET or LIABILITY accounts."
        )
    if to_account.account_type != from_account.account_type:
        raise ValidationError(
            f"Both accounts must be the same type for a contra entry "
            f"('{from_account.name}' is {from_account.account_type}, "
            f"'{to_account.name}' is {to_account.account_type})."
        )
    if from_account.pk == to_account.pk:
        raise ValidationError("Source and destination accounts must be different.")
    if amount <= Decimal('0'):
        raise ValidationError("Contra entry amount must be greater than zero.")

    return post_journal_entry(
        company=company,
        date=date,
        description=description,
        lines=[
            {'account': to_account, 'entry_type': 'DEBIT', 'amount': amount, 'narration': description},
            {'account': from_account, 'entry_type': 'CREDIT', 'amount': amount, 'narration': description},
        ],
        created_by=created_by,
        source_type='OTHER',
        journal_type='TRANSFER',
    )
