"""
Migration 0028 — DB-level default for is_cleared so raw-SQL PL/pgSQL
journal-posting functions that don't set it explicitly still succeed.

Same root cause as migration 0016: Django's add-NOT-NULL-column procedure
adds a temporary DEFAULT, backfills, then DROPs it — fine for the ORM but
not for fn_post_invoice_journal / fn_post_payment_journal / fn_close_period_journal,
whose INSERT INTO bookkeeping_journalentryline column lists predate this
column.
"""
from django.db import migrations


def add_db_defaults(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute(
        "ALTER TABLE bookkeeping_journalentryline ALTER COLUMN is_cleared SET DEFAULT FALSE;",
        params=None,
    )


def remove_db_defaults(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute(
        "ALTER TABLE bookkeeping_journalentryline ALTER COLUMN is_cleared DROP DEFAULT;",
        params=None,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('bookkeeping', '0027_journalentryline_is_cleared_and_more'),
    ]

    operations = [
        migrations.RunPython(add_db_defaults, remove_db_defaults),
    ]
