"""
Migration 0010 — Fix journal balance check trigger to be DEFERRABLE INITIALLY DEFERRED.

The trigger previously fired FOR EACH ROW after every INSERT, which caused
fn_post_invoice_journal to fail when inserting multi-line entries (e.g. with tax):
  - After DEBIT line + Sales Revenue CREDIT line: debits ≠ credits → trigger raised.
  - Tax Payable CREDIT line never got inserted.

Fix: make the constraint trigger DEFERRABLE INITIALLY DEFERRED so it only
fires at transaction commit, after all lines are inserted.
"""
from django.db import migrations


def fix_trigger_deferrable(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute("""
        -- Drop the old per-row trigger
        DROP TRIGGER IF EXISTS trg_journal_entry_balance_check ON bookkeeping_journalentryline;

        -- Recreate as a CONSTRAINT trigger (supports DEFERRABLE)
        -- Fires AFTER INSERT OR UPDATE, deferred to end of transaction
        CREATE CONSTRAINT TRIGGER trg_journal_entry_balance_check
            AFTER INSERT OR UPDATE ON bookkeeping_journalentryline
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION trg_fn_journal_balance_check();

        COMMENT ON TRIGGER trg_journal_entry_balance_check ON bookkeeping_journalentryline IS
            'Enforces double-entry balance at DB level — deferred to transaction end.';
    """)


def reverse_fix_trigger_deferrable(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute("""
        DROP TRIGGER IF EXISTS trg_journal_entry_balance_check ON bookkeeping_journalentryline;
        CREATE TRIGGER trg_journal_entry_balance_check
            AFTER INSERT OR UPDATE ON bookkeeping_journalentryline
            FOR EACH ROW EXECUTE FUNCTION trg_fn_journal_balance_check();
    """)


class Migration(migrations.Migration):

    dependencies = [
        ('bookkeeping', '0009_postgres_functions_triggers_views'),
    ]

    operations = [
        migrations.RunPython(fix_trigger_deferrable, reverse_fix_trigger_deferrable),
    ]
