from django.db import migrations, models


def _column_exists(cursor, vendor, table, column):
    # MySQL uses DATABASE() scalar function; PostgreSQL uses current_database().
    if vendor == 'mysql':
        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() "
            "AND TABLE_NAME = %s AND COLUMN_NAME = %s",
            [table, column],
        )
    else:
        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_catalog = current_database() "
            "AND table_name = %s AND column_name = %s",
            [table, column],
        )
    (count,) = cursor.fetchone()
    return bool(count)


def add_status_if_missing(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    with schema_editor.connection.cursor() as cursor:
        if not _column_exists(cursor, vendor, 'billing_invoice', 'status'):
            schema_editor.execute(
                "ALTER TABLE billing_invoice "
                "ADD COLUMN status VARCHAR(10) NOT NULL DEFAULT 'DRAFT'"
            )


def remove_status_if_present(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    with schema_editor.connection.cursor() as cursor:
        if _column_exists(cursor, vendor, 'billing_invoice', 'status'):
            schema_editor.execute(
                "ALTER TABLE billing_invoice DROP COLUMN status"
            )


class Migration(migrations.Migration):
    """
    Migration 0012 assumed billing_invoice.status still existed in the DB
    (removed from Django state in 0003 but assumed physically present).
    On servers where 0003 actually dropped the column this left it missing.
    This migration adds the column when absent, and is a no-op when present.
    """

    dependencies = [
        ('billing', '0012_invoice_status_cancellation_vendorbill_cancellation'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[],
            database_operations=[
                migrations.RunPython(
                    add_status_if_missing,
                    reverse_code=remove_status_if_present,
                ),
            ],
        ),
    ]
