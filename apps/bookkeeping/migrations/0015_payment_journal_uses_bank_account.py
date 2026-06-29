"""
Migration 0015 — fn_post_payment_journal: prefer the payment's selected
BankAccount ledger over the single shared 'Bank' ledger account.

Why: apps.payments.models.BankAccount lets a company register multiple bank
accounts, each with its own auto-created LedgerAccount. Payment.bank_account
records which one was used. Previously this function only ever looked up the
generic ledger account named 'Cash' or 'Bank', ignoring which specific bank
account (if any) was selected on the payment — so all bank transfers posted
to one shared ledger no matter which real bank they went through.

This migration only changes how the cash/bank leg's ledger account is
resolved. It does not touch the (pre-existing, unrelated) DEBIT/CREDIT
direction logic for VENDOR/SALARY/EXPENSE/OTHER payment types — that is
out of scope for this change and is left exactly as it was.

Forward: if payment.bank_account_id is set and that BankAccount has a
ledger_account, use it. Otherwise fall back to the previous generic
'Cash' / 'Bank' lookup by name — fully backward compatible with existing
payments that have no bank_account set.

Reverse: restores the exact fn_post_payment_journal body from migration 0009.
"""
from django.db import migrations

_FORWARD_SQL = """
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
        (id, company_id, date, description, is_deleted, created_at, updated_at)
    VALUES
        (gen_random_uuid(), v_pay.company_id, v_pay.date, v_description, FALSE, NOW(), NOW())
    RETURNING id INTO v_entry_id;

    INSERT INTO bookkeeping_journalentryline
        (id, journal_entry_id, account_id, entry_type, amount, is_deleted, created_at, updated_at)
    VALUES (gen_random_uuid(), v_entry_id, v_cash_bank_id, 'DEBIT', v_pay.amount, FALSE, NOW(), NOW());

    INSERT INTO bookkeeping_journalentryline
        (id, journal_entry_id, account_id, entry_type, amount, is_deleted, created_at, updated_at)
    VALUES (gen_random_uuid(), v_entry_id, v_dest_account_id, 'CREDIT', v_pay.amount, FALSE, NOW(), NOW());

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

_REVERSE_SQL = """
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
        p.payment_type, p.invoice_id, p.ledger_account_id,
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

    IF v_pay.method = 'CASH' THEN
        SELECT id INTO v_cash_bank_id FROM bookkeeping_ledgeraccount
        WHERE company_id = v_pay.company_id AND name = 'Cash' AND is_deleted = FALSE LIMIT 1;
    ELSE
        SELECT id INTO v_cash_bank_id FROM bookkeeping_ledgeraccount
        WHERE company_id = v_pay.company_id AND name = 'Bank' AND is_deleted = FALSE LIMIT 1;
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
        (id, company_id, date, description, is_deleted, created_at, updated_at)
    VALUES
        (gen_random_uuid(), v_pay.company_id, v_pay.date, v_description, FALSE, NOW(), NOW())
    RETURNING id INTO v_entry_id;

    INSERT INTO bookkeeping_journalentryline
        (id, journal_entry_id, account_id, entry_type, amount, is_deleted, created_at, updated_at)
    VALUES (gen_random_uuid(), v_entry_id, v_cash_bank_id, 'DEBIT', v_pay.amount, FALSE, NOW(), NOW());

    INSERT INTO bookkeeping_journalentryline
        (id, journal_entry_id, account_id, entry_type, amount, is_deleted, created_at, updated_at)
    VALUES (gen_random_uuid(), v_entry_id, v_dest_account_id, 'CREDIT', v_pay.amount, FALSE, NOW(), NOW());

    UPDATE payments_payment
    SET    journal_entry_id = v_entry_id,
           amount_applied   = v_pay.amount,
           updated_at       = NOW()
    WHERE  id = p_payment_id;

    RETURN v_entry_id;
END;
$$;
COMMENT ON FUNCTION fn_post_payment_journal(UUID) IS
    'Atomically creates the double-entry journal for a payment.';
"""


def apply_bank_account_lookup(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    # params=None — otherwise Django's postgres schema editor mogrifies the
    # SQL client-side and chokes on the literal '%' inside RAISE EXCEPTION
    # messages (e.g. 'Payment % not found') when given an empty params tuple.
    schema_editor.execute(_FORWARD_SQL, params=None)


def revert_bank_account_lookup(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute(_REVERSE_SQL, params=None)


class Migration(migrations.Migration):

    dependencies = [
        ('bookkeeping', '0014_journal_entry_reversal_fields'),
        ('payments', '0011_bankaccount_payment_bank_account_and_more'),
    ]

    operations = [
        migrations.RunPython(apply_bank_account_lookup, revert_bank_account_lookup),
    ]
