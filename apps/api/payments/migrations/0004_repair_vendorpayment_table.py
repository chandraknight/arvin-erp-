from django.db import migrations


POSTGRESQL_SQL = """
CREATE TABLE IF NOT EXISTS payments_vendorpayment (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    is_deleted      BOOLEAN      NOT NULL DEFAULT FALSE,
    amount          NUMERIC(10,2) NOT NULL,
    payment_date    DATE         NOT NULL DEFAULT CURRENT_DATE,
    payment_method  VARCHAR(20)  NOT NULL,
    transaction_id  VARCHAR(100),
    vendor_bill_id  BIGINT       NOT NULL
        REFERENCES billing_vendorbill(id) ON DELETE CASCADE,
    created_by_id   UUID
        REFERENCES accounts_user(id) ON DELETE SET NULL,
    updated_by_id   UUID
        REFERENCES accounts_user(id) ON DELETE SET NULL,
    deleted_by_id   UUID
        REFERENCES accounts_user(id) ON DELETE SET NULL
);
COMMENT ON TABLE payments_vendorpayment IS
    'Vendor payments against vendor bills. Recreated by repair migration 0004.';
"""


def repair_table(apps, schema_editor):
    # Only needed for PostgreSQL — MySQL creates the table correctly via 0001_initial ORM migration
    if schema_editor.connection.vendor == 'postgresql':
        schema_editor.execute(POSTGRESQL_SQL)


class Migration(migrations.Migration):
    """
    Repair migration: recreates payments_vendorpayment table which was missing
    from the database despite 0001_initial being recorded as applied.
    PostgreSQL only — MySQL handles this via the ORM in 0001_initial.
    """

    dependencies = [
        ("payments", "0003_alter_payment_reference_number"),
        ("billing", "0008_invoice_transaction_date"),
    ]

    operations = [
        migrations.RunPython(repair_table, migrations.RunPython.noop),
    ]
