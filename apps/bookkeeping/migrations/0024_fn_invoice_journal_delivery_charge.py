"""
Migration 0024 — fn_post_invoice_journal: post delivery_charge to its own
'Delivery Income' revenue account instead of folding it into Sales Revenue.

NFRS presentation: delivery/shipping income is not part of product sales
revenue (it isn't tied to inventory/COGS), so it needs its own P&L line to
avoid overstating product Sales Revenue and to let ratio analysis (gross
margin) compute correctly against product sales alone.

v_calc_sales previously derived Sales Revenue as (total + discount - tax).
Now that Invoice.total includes delivery_charge, Sales Revenue must first
have delivery_charge backed out: (total - delivery_charge + discount - tax).
"""
from django.db import migrations

_FORWARD_SQL = """
CREATE OR REPLACE FUNCTION fn_post_invoice_journal(p_invoice_id UUID)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_inv                  RECORD;
    v_entry_id             UUID;
    v_debit_account_id     UUID;
    v_sales_account_id     UUID;
    v_tax_account_id       UUID;
    v_disc_account_id      UUID;
    v_delivery_account_id  UUID;
    v_calc_sales           NUMERIC(14,2);
BEGIN
    SELECT
        i.id, i.company_id, i.invoice_number, i.transaction_date,
        i.total, i.discount_amount, i.tax_amount, i.delivery_charge,
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
    SELECT id INTO v_delivery_account_id FROM bookkeeping_ledgeraccount
    WHERE company_id = v_inv.company_id AND name = 'Delivery Income' AND is_deleted = FALSE LIMIT 1;

    IF v_debit_account_id IS NULL OR v_sales_account_id IS NULL
       OR v_tax_account_id IS NULL OR v_disc_account_id IS NULL THEN
        RAISE EXCEPTION 'Missing default ledger accounts for company %', v_inv.company_id
            USING ERRCODE = 'P0001';
    END IF;

    IF COALESCE(v_inv.delivery_charge, 0) > 0 AND v_delivery_account_id IS NULL THEN
        RAISE EXCEPTION 'Missing Delivery Income ledger account for company %', v_inv.company_id
            USING ERRCODE = 'P0001';
    END IF;

    -- Soft-delete (never hard-delete) prior draft entries for this invoice
    -- that are not yet linked to a confirmed payment.
    UPDATE bookkeeping_journalentry
    SET    is_deleted       = TRUE,
           is_reversed      = TRUE,
           reversed_reason  = 'Replaced by re-post of invoice ' || v_inv.invoice_number,
           reversed_at      = NOW(),
           updated_at       = NOW()
    WHERE  company_id  = v_inv.company_id
      AND  description = 'Invoice ' || v_inv.invoice_number
      AND  is_deleted  = FALSE
      AND  id NOT IN (
               SELECT journal_entry_id FROM payments_payment
               WHERE  journal_entry_id IS NOT NULL
           );

    INSERT INTO bookkeeping_journalentry
        (id, company_id, date, description, source_type, is_deleted, created_at, updated_at)
    VALUES
        (gen_random_uuid(), v_inv.company_id,
         COALESCE(v_inv.transaction_date, CURRENT_DATE),
         'Invoice ' || v_inv.invoice_number,
         'SALES_INVOICE',
         FALSE, NOW(), NOW())
    RETURNING id INTO v_entry_id;

    v_calc_sales := v_inv.total - COALESCE(v_inv.delivery_charge, 0)
                    + COALESCE(v_inv.discount_amount, 0)
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

    IF COALESCE(v_inv.delivery_charge, 0) > 0 THEN
        INSERT INTO bookkeeping_journalentryline
            (id, journal_entry_id, account_id, entry_type, amount, is_deleted, created_at, updated_at)
        VALUES (gen_random_uuid(), v_entry_id, v_delivery_account_id, 'CREDIT', v_inv.delivery_charge, FALSE, NOW(), NOW());
    END IF;

    RETURN v_entry_id;
END;
$$;
COMMENT ON FUNCTION fn_post_invoice_journal(UUID) IS
    'Atomically creates/replaces the double-entry journal for an invoice, '
    'booking delivery_charge to Delivery Income separately from Sales Revenue. '
    'Prior draft entries are soft-deleted (never hard-deleted) for NFRS audit immutability.';
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

    UPDATE bookkeeping_journalentry
    SET    is_deleted       = TRUE,
           is_reversed      = TRUE,
           reversed_reason  = 'Replaced by re-post of invoice ' || v_inv.invoice_number,
           reversed_at      = NOW(),
           updated_at       = NOW()
    WHERE  company_id  = v_inv.company_id
      AND  description = 'Invoice ' || v_inv.invoice_number
      AND  is_deleted  = FALSE
      AND  id NOT IN (
               SELECT journal_entry_id FROM payments_payment
               WHERE  journal_entry_id IS NOT NULL
           );

    INSERT INTO bookkeeping_journalentry
        (id, company_id, date, description, source_type, is_deleted, created_at, updated_at)
    VALUES
        (gen_random_uuid(), v_inv.company_id,
         COALESCE(v_inv.transaction_date, CURRENT_DATE),
         'Invoice ' || v_inv.invoice_number,
         'SALES_INVOICE',
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
    'Atomically creates/replaces the double-entry journal for an invoice. '
    'Prior draft entries are soft-deleted (never hard-deleted) for NFRS audit immutability.';
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
        ('bookkeeping', '0023_journalentryline_is_reconciled_and_more'),
        ('billing', '0032_invoice_delivery_charge'),
    ]

    operations = [
        migrations.RunPython(apply_fix, revert_fix),
    ]
