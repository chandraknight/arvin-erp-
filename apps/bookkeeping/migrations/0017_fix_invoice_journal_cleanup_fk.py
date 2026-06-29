"""
Migration 0017 — fn_post_invoice_journal: delete journalentryline rows before
deleting the stale parent journalentry row, to avoid a deferred FK violation.

Why: fn_post_invoice_journal (migration 0009) makes itself idempotent by
deleting any prior journal entry for the same invoice (matched by
company_id + description = 'Invoice <number>') that isn't yet linked to a
Payment, then inserting a fresh one. That DELETE only ever targeted
bookkeeping_journalentry — it never deleted the matching
bookkeeping_journalentryline rows first. The FK from journalentryline to
journalentry is DEFERRABLE INITIALLY DEFERRED (so normal posting works
inside one transaction), which means this orphaning bug doesn't fail
immediately — it fails at COMMIT with:
  IntegrityError: update or delete on table "bookkeeping_journalentry"
  violates foreign key constraint ... still referenced from table
  "bookkeeping_journalentryline"
any time an invoice's journal entry needs to be re-posted before a Payment
has linked to it (e.g. POS checkout calls invoice.save(update_fields=[...])
after creating the invoice, which re-fires the journal-posting signal).

Fix: delete the lines for the entries about to be removed, in the same
statement group, before deleting the entries themselves. No other logic in
the function changes.
"""
from django.db import migrations

_FORWARD_SQL = """
CREATE OR REPLACE FUNCTION fn_post_invoice_journal(p_invoice_id UUID)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_inv              RECORD;
    v_entry_id         UUID;
    v_debit_account_id UUID;
    v_sales_account_id UUID;
    v_tax_account_id   UUID;
    v_disc_account_id  UUID;
    v_calc_sales       NUMERIC(14,2);
BEGIN
    SELECT
        i.id, i.company_id, i.invoice_number, i.transaction_date,
        i.total, i.discount_amount, i.tax_amount,
        i.customer_id,
        c.related_ledger_account_id AS customer_ledger_id
    INTO v_inv
    FROM billing_invoice    i
    LEFT JOIN customers_customer c ON c.id = i.customer_id
    WHERE i.id = p_invoice_id AND i.is_deleted = FALSE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Invoice % not found', p_invoice_id USING ERRCODE = 'P0002';
    END IF;

    IF v_inv.total IS NULL OR v_inv.total <= 0 THEN
        RETURN NULL;
    END IF;

    IF v_inv.customer_id IS NULL THEN
        SELECT id INTO v_debit_account_id FROM bookkeeping_ledgeraccount
        WHERE company_id = v_inv.company_id AND name = 'Cash' AND is_deleted = FALSE LIMIT 1;
    ELSIF v_inv.customer_ledger_id IS NOT NULL THEN
        v_debit_account_id := v_inv.customer_ledger_id;
    ELSE
        SELECT id INTO v_debit_account_id FROM bookkeeping_ledgeraccount
        WHERE company_id = v_inv.company_id AND name = 'Accounts Receivable' AND is_deleted = FALSE LIMIT 1;
    END IF;

    SELECT id INTO v_sales_account_id FROM bookkeeping_ledgeraccount
    WHERE company_id = v_inv.company_id AND name = 'Sales Revenue' AND is_deleted = FALSE LIMIT 1;
    SELECT id INTO v_tax_account_id FROM bookkeeping_ledgeraccount
    WHERE company_id = v_inv.company_id AND name = 'Tax Payable' AND is_deleted = FALSE LIMIT 1;
    SELECT id INTO v_disc_account_id FROM bookkeeping_ledgeraccount
    WHERE company_id = v_inv.company_id AND name = 'Discount Given' AND is_deleted = FALSE LIMIT 1;

    IF v_debit_account_id IS NULL OR v_sales_account_id IS NULL
       OR v_tax_account_id IS NULL OR v_disc_account_id IS NULL THEN
        RAISE EXCEPTION 'Missing default ledger accounts for company %', v_inv.company_id
            USING ERRCODE = 'P0001';
    END IF;

    DELETE FROM bookkeeping_journalentryline
    WHERE journal_entry_id IN (
        SELECT id FROM bookkeeping_journalentry
        WHERE company_id  = v_inv.company_id
          AND description = 'Invoice ' || v_inv.invoice_number
          AND id NOT IN (
              SELECT journal_entry_id FROM payments_payment
              WHERE journal_entry_id IS NOT NULL
          )
    );

    DELETE FROM bookkeeping_journalentry
    WHERE company_id  = v_inv.company_id
      AND description = 'Invoice ' || v_inv.invoice_number
      AND id NOT IN (
          SELECT journal_entry_id FROM payments_payment
          WHERE journal_entry_id IS NOT NULL
      );

    INSERT INTO bookkeeping_journalentry
        (id, company_id, date, description, is_deleted, created_at, updated_at)
    VALUES
        (gen_random_uuid(), v_inv.company_id,
         COALESCE(v_inv.transaction_date, CURRENT_DATE),
         'Invoice ' || v_inv.invoice_number,
         FALSE, NOW(), NOW())
    RETURNING id INTO v_entry_id;

    v_calc_sales := v_inv.total + COALESCE(v_inv.discount_amount, 0)
                    - COALESCE(v_inv.tax_amount, 0);

    INSERT INTO bookkeeping_journalentryline
        (id, journal_entry_id, account_id, entry_type, amount, is_deleted, created_at, updated_at)
    VALUES (gen_random_uuid(), v_entry_id, v_debit_account_id, 'DEBIT', v_inv.total, FALSE, NOW(), NOW());

    INSERT INTO bookkeeping_journalentryline
        (id, journal_entry_id, account_id, entry_type, amount, is_deleted, created_at, updated_at)
    VALUES (gen_random_uuid(), v_entry_id, v_sales_account_id, 'CREDIT', v_calc_sales, FALSE, NOW(), NOW());

    IF COALESCE(v_inv.tax_amount, 0) > 0 THEN
        INSERT INTO bookkeeping_journalentryline
            (id, journal_entry_id, account_id, entry_type, amount, is_deleted, created_at, updated_at)
        VALUES (gen_random_uuid(), v_entry_id, v_tax_account_id, 'CREDIT', v_inv.tax_amount, FALSE, NOW(), NOW());
    END IF;

    IF COALESCE(v_inv.discount_amount, 0) > 0 THEN
        INSERT INTO bookkeeping_journalentryline
            (id, journal_entry_id, account_id, entry_type, amount, is_deleted, created_at, updated_at)
        VALUES (gen_random_uuid(), v_entry_id, v_disc_account_id, 'DEBIT', v_inv.discount_amount, FALSE, NOW(), NOW());
    END IF;

    RETURN v_entry_id;
END;
$$;
COMMENT ON FUNCTION fn_post_invoice_journal(UUID) IS
    'Atomically creates/replaces the double-entry journal for an invoice.';
"""

_REVERSE_SQL = """
CREATE OR REPLACE FUNCTION fn_post_invoice_journal(p_invoice_id UUID)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_inv              RECORD;
    v_entry_id         UUID;
    v_debit_account_id UUID;
    v_sales_account_id UUID;
    v_tax_account_id   UUID;
    v_disc_account_id  UUID;
    v_calc_sales       NUMERIC(14,2);
BEGIN
    SELECT
        i.id, i.company_id, i.invoice_number, i.transaction_date,
        i.total, i.discount_amount, i.tax_amount,
        i.customer_id,
        c.related_ledger_account_id AS customer_ledger_id
    INTO v_inv
    FROM billing_invoice    i
    LEFT JOIN customers_customer c ON c.id = i.customer_id
    WHERE i.id = p_invoice_id AND i.is_deleted = FALSE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Invoice % not found', p_invoice_id USING ERRCODE = 'P0002';
    END IF;

    IF v_inv.total IS NULL OR v_inv.total <= 0 THEN
        RETURN NULL;
    END IF;

    IF v_inv.customer_id IS NULL THEN
        SELECT id INTO v_debit_account_id FROM bookkeeping_ledgeraccount
        WHERE company_id = v_inv.company_id AND name = 'Cash' AND is_deleted = FALSE LIMIT 1;
    ELSIF v_inv.customer_ledger_id IS NOT NULL THEN
        v_debit_account_id := v_inv.customer_ledger_id;
    ELSE
        SELECT id INTO v_debit_account_id FROM bookkeeping_ledgeraccount
        WHERE company_id = v_inv.company_id AND name = 'Accounts Receivable' AND is_deleted = FALSE LIMIT 1;
    END IF;

    SELECT id INTO v_sales_account_id FROM bookkeeping_ledgeraccount
    WHERE company_id = v_inv.company_id AND name = 'Sales Revenue' AND is_deleted = FALSE LIMIT 1;
    SELECT id INTO v_tax_account_id FROM bookkeeping_ledgeraccount
    WHERE company_id = v_inv.company_id AND name = 'Tax Payable' AND is_deleted = FALSE LIMIT 1;
    SELECT id INTO v_disc_account_id FROM bookkeeping_ledgeraccount
    WHERE company_id = v_inv.company_id AND name = 'Discount Given' AND is_deleted = FALSE LIMIT 1;

    IF v_debit_account_id IS NULL OR v_sales_account_id IS NULL
       OR v_tax_account_id IS NULL OR v_disc_account_id IS NULL THEN
        RAISE EXCEPTION 'Missing default ledger accounts for company %', v_inv.company_id
            USING ERRCODE = 'P0001';
    END IF;

    DELETE FROM bookkeeping_journalentry
    WHERE company_id  = v_inv.company_id
      AND description = 'Invoice ' || v_inv.invoice_number
      AND id NOT IN (
          SELECT journal_entry_id FROM payments_payment
          WHERE journal_entry_id IS NOT NULL
      );

    INSERT INTO bookkeeping_journalentry
        (id, company_id, date, description, is_deleted, created_at, updated_at)
    VALUES
        (gen_random_uuid(), v_inv.company_id,
         COALESCE(v_inv.transaction_date, CURRENT_DATE),
         'Invoice ' || v_inv.invoice_number,
         FALSE, NOW(), NOW())
    RETURNING id INTO v_entry_id;

    v_calc_sales := v_inv.total + COALESCE(v_inv.discount_amount, 0)
                    - COALESCE(v_inv.tax_amount, 0);

    INSERT INTO bookkeeping_journalentryline
        (id, journal_entry_id, account_id, entry_type, amount, is_deleted, created_at, updated_at)
    VALUES (gen_random_uuid(), v_entry_id, v_debit_account_id, 'DEBIT', v_inv.total, FALSE, NOW(), NOW());

    INSERT INTO bookkeeping_journalentryline
        (id, journal_entry_id, account_id, entry_type, amount, is_deleted, created_at, updated_at)
    VALUES (gen_random_uuid(), v_entry_id, v_sales_account_id, 'CREDIT', v_calc_sales, FALSE, NOW(), NOW());

    IF COALESCE(v_inv.tax_amount, 0) > 0 THEN
        INSERT INTO bookkeeping_journalentryline
            (id, journal_entry_id, account_id, entry_type, amount, is_deleted, created_at, updated_at)
        VALUES (gen_random_uuid(), v_entry_id, v_tax_account_id, 'CREDIT', v_inv.tax_amount, FALSE, NOW(), NOW());
    END IF;

    IF COALESCE(v_inv.discount_amount, 0) > 0 THEN
        INSERT INTO bookkeeping_journalentryline
            (id, journal_entry_id, account_id, entry_type, amount, is_deleted, created_at, updated_at)
        VALUES (gen_random_uuid(), v_entry_id, v_disc_account_id, 'DEBIT', v_inv.discount_amount, FALSE, NOW(), NOW());
    END IF;

    RETURN v_entry_id;
END;
$$;
COMMENT ON FUNCTION fn_post_invoice_journal(UUID) IS
    'Atomically creates/replaces the double-entry journal for an invoice.';
"""


def apply_fix(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute(_FORWARD_SQL, params=None)


def revert_fix(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute(_REVERSE_SQL, params=None)


class Migration(migrations.Migration):

    dependencies = [
        ('bookkeeping', '0016_journalentry_is_reversed_db_default'),
    ]

    operations = [
        migrations.RunPython(apply_fix, revert_fix),
    ]
