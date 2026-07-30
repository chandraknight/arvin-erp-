from django.db import migrations

ACCOUNT_TYPE_NORMAL_BALANCE = {
    'ASSET': 'DEBIT',
    'EXPENSE': 'DEBIT',
    'LIABILITY': 'CREDIT',
    'EQUITY': 'CREDIT',
    'REVENUE': 'CREDIT',
}


def backfill_normal_balance(apps, schema_editor):
    LedgerAccount = apps.get_model('bookkeeping', 'LedgerAccount')
    for account_type, normal_balance in ACCOUNT_TYPE_NORMAL_BALANCE.items():
        LedgerAccount.objects.filter(
            account_type=account_type, normal_balance=''
        ).update(normal_balance=normal_balance)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('bookkeeping', '0019_ledgeraccount_normal_balance'),
    ]

    operations = [
        migrations.RunPython(backfill_normal_balance, noop_reverse),
    ]
