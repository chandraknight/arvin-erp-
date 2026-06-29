from apps.bookkeeping.models import LedgerAccount
from apps.company.models import Company
from apps.utils.constant import DEFAULT_ACCOUNTS
import datetime
import uuid


def setup_default_ledger_accounts(company: Company):
    created = []
    for acc in DEFAULT_ACCOUNTS:
        obj, is_created = LedgerAccount.objects.get_or_create(
            company=company,
            name=acc["name"],
            defaults={
                "account_type": acc["account_type"],
                "code": acc["code"],
                "system_created": True,
            }
        )
        if is_created:
            created.append(obj.name)
    return created
