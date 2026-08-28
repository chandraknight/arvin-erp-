"""
Migration 0026 — fn_post_invoice_journal / fn_post_payment_journal: set
journal_type, source_type, is_cleared.

Migrations 0021 (journal_type), 0023 (is_cleared), and 0025 (source_type)
added NOT NULL columns to JournalEntry / JournalEntryLine with Django-side
defaults only — the raw INSERT statements inside these two PL/pgSQL
functions were never updated to include them. Any invoice or payment
journal posted through these functions on PostgreSQL has been failing
with a NOT NULL constraint violation ever since — silently breaking
bookkeeping for POS, orders, restaurant, and any other flow that posts
through post_invoice_journal / post_payment_journal.

Only the affected INSERT statements change (journal_type='GENERAL',
source_type='SALES_INVOICE'/'PAYMENT', is_cleared=FALSE added); all other
logic is unchanged from the most recent prior definitions (0018 for
invoices, 0015 for payments).
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
    'Prior draft entries are soft-deleted (never hard-deleted) for NFRS audit immutability.';

CREATE OR REPLACE FUNCTION fn_post_payment_journal(p_payment_id UUID)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_pay              RECORD;
    v_entry_id         UUID;
    v_cash_bank_id     UUID;
    v_dest_account_id  UUID;
    v_description      TEXT;
BEGIN
    SELECT
        p.id, p.company_id, p.date, p.amount, p.method,
        p.payment_type, p.invoice_id, p.ledger_account_id, p.bank_account_id,
        i.invoice_number,
        CASE
            WHEN p.payment_type = 'CUSTOMER' AND c.related_ledger_account_id IS NOT NULL
                THEN c.related_ledger_account_id
            ELSE NULL
        END AS customer_ledger_id
    INTO v_pay
    FROM payments_payment p
    LEFT JOIN billing_invoice    i ON i.id = p.invoice_id
    LEFT JOIN customers_customer c ON c.id = i.customer_id
    WHERE p.id = p_payment_id AND p.is_deleted = FALSE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Payment % not found', p_payment_id USING ERRCODE = 'P0002';
    END IF;

    IF v_pay.bank_account_id IS NOT NULL THEN
        SELECT ledger_account_id INTO v_cash_bank_id
        FROM payments_bankaccount
        WHERE id = v_pay.bank_account_id AND is_deleted = FALSE;
    END IF;

    IF v_cash_bank_id IS NULL THEN
        IF v_pay.method = 'CASH' THEN
            SELECT id INTO v_cash_bank_id FROM bookkeeping_ledgeraccount
            WHERE company_id = v_pay.company_id AND name = 'Cash' AND is_deleted = FALSE LIMIT 1;
        ELSE
            SELECT id INTO v_cash_bank_id FROM bookkeeping_ledgeraccount
            WHERE company_id = v_pay.company_id AND name = 'Bank' AND is_deleted = FALSE LIMIT 1;
        END IF;
    END IF;

    IF v_cash_bank_id IS NULL THEN
        RAISE EXCEPTION 'Cash/Bank ledger account not found for company %', v_pay.company_id
            USING ERRCODE = 'P0001';
    END IF;

    IF v_pay.payment_type = 'CUSTOMER' THEN
        IF v_pay.customer_ledger_id IS NOT NULL THEN
            v_dest_account_id := v_pay.customer_ledger_id;
        ELSE
            SELECT id INTO v_dest_account_id FROM bookkeeping_ledgeraccount
            WHERE company_id = v_pay.company_id AND name = 'Accounts Receivable' AND is_deleted = FALSE LIMIT 1;
        END IF;
        v_description := 'Payment for Invoice ' || COALESCE(v_pay.invoice_number, p_payment_id::TEXT);
    ELSIF v_pay.payment_type = 'VENDOR' THEN
        SELECT id INTO v_dest_account_id FROM bookkeeping_ledgeraccount
        WHERE company_id = v_pay.company_id AND name = 'Accounts Payable' AND is_deleted = FALSE LIMIT 1;
        v_description := 'Vendor Payment';
    ELSIF v_pay.payment_type = 'SALARY' THEN
        SELECT id INTO v_dest_account_id FROM bookkeeping_ledgeraccount
        WHERE company_id = v_pay.company_id AND name = 'Salary Expense' AND is_deleted = FALSE LIMIT 1;
        v_description := 'Salary Payment';
    ELSE
        v_dest_account_id := v_pay.ledger_account_id;
        v_description := CASE v_pay.payment_type WHEN 'EXPENSE' THEN 'Expense Payment' ELSE 'Other Payment' END;
    END IF;

    IF v_dest_account_id IS NULL THEN
        RAISE EXCEPTION 'Destination ledger account not found for payment % (type=%)',
            p_payment_id, v_pay.payment_type USING ERRCODE = 'P0001';
    END IF;

    INSERT INTO bookkeeping_journalentry
        (id, company_id, date, description, journal_type, source_type, is_deleted, created_at, updated_at)
    VALUES
        (gen_random_uuid(), v_pay.company_id, v_pay.date, v_description, 'GENERAL', 'PAYMENT', FALSE, NOW(), NOW())
    RETURNING id INTO v_entry_id;

    INSERT INTO bookkeeping_journalentryline
        (id, journal_entry_id, account_id, entry_type, amount, is_cleared, is_deleted, created_at, updated_at)
    VALUES (gen_random_uuid(), v_entry_id, v_cash_bank_id, 'DEBIT', v_pay.amount, FALSE, FALSE, NOW(), NOW());

    INSERT INTO bookkeeping_journalentryline
        (id, journal_entry_id, account_id, entry_type, amount, is_cleared, is_deleted, created_at, updated_at)
    VALUES (gen_random_uuid(), v_entry_id, v_dest_account_id, 'CREDIT', v_pay.amount, FALSE, FALSE, NOW(), NOW());

    UPDATE payments_payment
    SET    journal_entry_id = v_entry_id,
           amount_applied   = v_pay.amount,
           updated_at       = NOW()
    WHERE  id = p_payment_id;

    RETURN v_entry_id;
END;
$$;
COMMENT ON FUNCTION fn_post_payment_journal(UUID) IS
    'Atomically creates the double-entry journal for a payment. Uses the payment''s bank_account ledger when set.';
"""


def apply_fix(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute(_FORWARD_SQL, params=None)


class Migration(migrations.Migration):

    dependencies = [
        ('bookkeeping', '0025_journalentry_source_type'),
    ]

    operations = [
        migrations.RunPython(apply_fix, migrations.RunPython.noop),
    ]
