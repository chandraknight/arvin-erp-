"""
Migration 0025 — restore DB-level defaults for columns that raw-SQL
PL/pgSQL journal-posting functions don't set explicitly.

Same root cause as migration 0016: Django's add-NOT-NULL-column procedure
adds a temporary DEFAULT, backfills, then DROPs it — fine for the ORM (which
always sends every field) but not for fn_post_invoice_journal,
fn_post_payment_journal, and fn_close_period_journal (see migration 0009),
whose INSERT INTO bookkeeping_journalentry / bookkeeping_journalentryline
column lists predate these columns:

  - bookkeeping_journalentry.source_type      (added after 0009/0015/0018 were written)
  - bookkeeping_journalentryline.is_reconciled (added in migration 0023, this session)

Symptom without this fix: any invoice/payment/period-close journal posting
through those functions fails with
  IntegrityError: null value in column "source_type" / "is_reconciled" ...

Fix: DB-level defaults so those raw-SQL INSERTs succeed without having to
touch three separate PL/pgSQL function bodies.
"""
from django.db import migrations


def add_db_defaults(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute(
        "ALTER TABLE bookkeeping_journalentry ALTER COLUMN source_type SET DEFAULT 'OTHER';",
        params=None,
    )
    schema_editor.execute(
        "ALTER TABLE bookkeeping_journalentryline ALTER COLUMN is_reconciled SET DEFAULT FALSE;",
        params=None,
    )


def remove_db_defaults(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute(
        "ALTER TABLE bookkeeping_journalentry ALTER COLUMN source_type DROP DEFAULT;",
        params=None,
    )
    schema_editor.execute(
        "ALTER TABLE bookkeeping_journalentryline ALTER COLUMN is_reconciled DROP DEFAULT;",
        params=None,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('bookkeeping', '0024_fn_invoice_journal_delivery_charge'),
    ]

    operations = [
        migrations.RunPython(add_db_defaults, remove_db_defaults),
    ]
