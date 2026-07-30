"""
Migration 0016 — restore database-level defaults on the NOT NULL columns
migration 0014 added to bookkeeping_journalentry (is_reversed, reversed_reason).

Why: migration 0014 added is_reversed (NOT NULL, default=False) and
reversed_reason (NOT NULL, default='') at the Django model level. Django's
standard procedure for adding a NOT NULL column to an existing table is to
add it WITH a temporary DEFAULT, backfill existing rows, then DROP the
DEFAULT — leaving both columns NOT NULL with no server-side default. That's
normally fine for ORM-driven inserts (Django always sends every field), but
this project also posts journal entries via raw SQL in PL/pgSQL functions
(fn_post_invoice_journal, fn_post_payment_journal, fn_close_period_journal —
see migration 0009) which INSERT INTO bookkeeping_journalentry with an
explicit column list that predates these columns and does not include them.

Effect before this fix: every POS checkout / payment / invoice journal
posting failed with
  IntegrityError: null value in column "is_reversed" / "reversed_reason" ...
because Postgres had no default to fall back on.

Fix: re-add DB-level defaults so the existing raw-SQL INSERTs (which this
migration does not touch) work again, without having to reproduce and risk
introducing typos in three large PL/pgSQL function bodies.
"""
from django.db import migrations


def add_db_defaults(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute(
        "ALTER TABLE bookkeeping_journalentry ALTER COLUMN is_reversed SET DEFAULT FALSE;",
        params=None,
    )
    schema_editor.execute(
        "ALTER TABLE bookkeeping_journalentry ALTER COLUMN reversed_reason SET DEFAULT '';",
        params=None,
    )


def remove_db_defaults(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute(
        "ALTER TABLE bookkeeping_journalentry ALTER COLUMN is_reversed DROP DEFAULT;",
        params=None,
    )
    schema_editor.execute(
        "ALTER TABLE bookkeeping_journalentry ALTER COLUMN reversed_reason DROP DEFAULT;",
        params=None,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('bookkeeping', '0015_payment_journal_uses_bank_account'),
    ]

    operations = [
        migrations.RunPython(add_db_defaults, remove_db_defaults),
    ]
