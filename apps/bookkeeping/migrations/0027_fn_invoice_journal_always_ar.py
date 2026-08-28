"""
Migration 0027 — fn_post_invoice_journal: always debit Accounts Receivable,
never Cash, for walk-in (no customer) sales.

Root cause: the invoice journal function special-cased "no customer" to
debit Cash directly, on the assumption a walk-in sale is always paid on
the spot. That assumption breaks the moment a Payment is recorded
separately (which POS and every other flow in this app do) — the invoice
posts DR Cash / CR Sales, then the payment posts DR Cash / CR Accounts
Receivable again, double-counting the cash received and leaving a
phantom AR credit that's never offset by a debit.

Correct double-entry: a sale always creates a receivable (DR AR / CR
Sales), and payment is a separate event that clears it (DR Cash / CR AR).
Walk-in customers now debit the company's shared 'Accounts Receivable'
ledger account instead of 'Cash' — identical to the existing fallback
already used when a customer exists but has no dedicated ledger account.

Only the customer_id IS NULL branch changes; everything else is
unchanged from migration 0026.
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

    IF v_inv.customer_id IS NOT NULL AND v_inv.customer_ledger_id IS NOT NULL THEN
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
        (id, company_id, date, description, journal_type, source_type, is_deleted, created_at, updated_at)
    VALUES
        (gen_random_uuid(), v_inv.company_id,
         COALESCE(v_inv.transaction_date, CURRENT_DATE),
         'Invoice ' || v_inv.invoice_number,
         'GENERAL', 'SALES_INVOICE', FALSE, NOW(), NOW())
    RETURNING id INTO v_entry_id;

    v_calc_sales := v_inv.total + COALESCE(v_inv.discount_amount, 0)
                    - COALESCE(v_inv.tax_amount, 0);

    INSERT INTO bookkeeping_journalentryline
        (id, journal_entry_id, account_id, entry_type, amount, is_cleared, is_deleted, created_at, updated_at)
    VALUES (gen_random_uuid(), v_entry_id, v_debit_account_id, 'DEBIT', v_inv.total, FALSE, FALSE, NOW(), NOW());

    INSERT INTO bookkeeping_journalentryline
        (id, journal_entry_id, account_id, entry_type, amount, is_cleared, is_deleted, created_at, updated_at)
    VALUES (gen_random_uuid(), v_entry_id, v_sales_account_id, 'CREDIT', v_calc_sales, FALSE, FALSE, NOW(), NOW());

    IF COALESCE(v_inv.tax_amount, 0) > 0 THEN
        INSERT INTO bookkeeping_journalentryline
            (id, journal_entry_id, account_id, entry_type, amount, is_cleared, is_deleted, created_at, updated_at)
        VALUES (gen_random_uuid(), v_entry_id, v_tax_account_id, 'CREDIT', v_inv.tax_amount, FALSE, FALSE, NOW(), NOW());
    END IF;

    IF COALESCE(v_inv.discount_amount, 0) > 0 THEN
        INSERT INTO bookkeeping_journalentryline
            (id, journal_entry_id, account_id, entry_type, amount, is_cleared, is_deleted, created_at, updated_at)
        VALUES (gen_random_uuid(), v_entry_id, v_disc_account_id, 'DEBIT', v_inv.discount_amount, FALSE, FALSE, NOW(), NOW());
    END IF;

    RETURN v_entry_id;
END;
$$;
COMMENT ON FUNCTION fn_post_invoice_journal(UUID) IS
    'Atomically creates/replaces the double-entry journal for an invoice. '
    'Always debits Accounts Receivable (customer-specific ledger when set) '
    '— payment settlement is a separate journal event, never assumed here. '
    'Prior draft entries are soft-deleted (never hard-deleted) for NFRS audit immutability.';
"""


def apply_fix(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute(_FORWARD_SQL, params=None)


class Migration(migrations.Migration):

    dependencies = [
        ('bookkeeping', '0026_fn_journal_functions_set_journal_type'),
    ]

    operations = [
        migrations.RunPython(apply_fix, migrations.RunPython.noop),
    ]
