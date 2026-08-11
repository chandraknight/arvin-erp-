from django.db import migrations

# Tags year-end closing entries with journal_type='CLOSING' so they're
# distinguishable in the journal list/filters. PostgreSQL only — MySQL uses
# the ORM-based close path in company/services which sets journal_type directly.

_FORWARD_SQL = """
CREATE OR REPLACE FUNCTION fn_close_period_journal(
    p_company_id     UUID,
    p_fiscal_year_id UUID,
    p_closed_by_id   UUID DEFAULT NULL
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_fy            RECORD;
    v_entry_id      UUID;
    v_retained_id   UUID;
    v_net_income    NUMERIC(14,2) := 0;
    v_total_revenue NUMERIC(14,2) := 0;
    v_total_expense NUMERIC(14,2) := 0;
    v_acc           RECORD;
    v_acc_balance   NUMERIC(14,2);
BEGIN
    SELECT * INTO v_fy FROM company_fiscalyear
    WHERE id = p_fiscal_year_id AND company_id = p_company_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'FiscalYear % not found for company %', p_fiscal_year_id, p_company_id
            USING ERRCODE = 'P0002';
    END IF;

    IF v_fy.is_closed THEN
        SELECT je.id INTO v_entry_id
        FROM bookkeeping_journalentry je
        WHERE je.company_id  = p_company_id
          AND je.description LIKE 'Year-End Closing%'
          AND je.date        = v_fy.end_date
          AND je.is_deleted  = FALSE
        ORDER BY je.created_at DESC LIMIT 1;
        RETURN v_entry_id;
    END IF;

    SELECT id INTO v_retained_id FROM bookkeeping_ledgeraccount
    WHERE company_id = p_company_id AND name = 'Retained Earnings' AND is_deleted = FALSE LIMIT 1;

    IF v_retained_id IS NULL THEN
        INSERT INTO bookkeeping_ledgeraccount
            (id, company_id, name, account_type, code, system_created, is_deleted, created_at, updated_at)
        VALUES
            (gen_random_uuid(), p_company_id, 'Retained Earnings', 'EQUITY', '3100', TRUE, FALSE, NOW(), NOW())
        RETURNING id INTO v_retained_id;
    END IF;

    INSERT INTO bookkeeping_journalentry
        (id, company_id, date, description, journal_type, is_deleted, created_at, updated_at)
    VALUES
        (gen_random_uuid(), p_company_id, v_fy.end_date,
         'Year-End Closing Entry for ' || v_fy.name,
         'CLOSING',
         FALSE, NOW(), NOW())
    RETURNING id INTO v_entry_id;

    FOR v_acc IN
        SELECT id FROM bookkeeping_ledgeraccount
        WHERE company_id = p_company_id AND account_type = 'REVENUE' AND is_deleted = FALSE
    LOOP
        v_acc_balance := fn_get_account_balance(v_acc.id, v_fy.end_date);
        IF v_acc_balance > 0 THEN
            INSERT INTO bookkeeping_journalentryline
                (id, journal_entry_id, account_id, entry_type, amount, is_deleted, created_at, updated_at)
            VALUES (gen_random_uuid(), v_entry_id, v_acc.id, 'DEBIT', v_acc_balance, FALSE, NOW(), NOW());
            v_total_revenue := v_total_revenue + v_acc_balance;
        END IF;
    END LOOP;

    FOR v_acc IN
        SELECT id FROM bookkeeping_ledgeraccount
        WHERE company_id = p_company_id AND account_type = 'EXPENSE' AND is_deleted = FALSE
    LOOP
        v_acc_balance := fn_get_account_balance(v_acc.id, v_fy.end_date);
        IF v_acc_balance > 0 THEN
            INSERT INTO bookkeeping_journalentryline
                (id, journal_entry_id, account_id, entry_type, amount, is_deleted, created_at, updated_at)
            VALUES (gen_random_uuid(), v_entry_id, v_acc.id, 'CREDIT', v_acc_balance, FALSE, NOW(), NOW());
            v_total_expense := v_total_expense + v_acc_balance;
        END IF;
    END LOOP;

    v_net_income := v_total_revenue - v_total_expense;
    IF v_net_income > 0 THEN
        INSERT INTO bookkeeping_journalentryline
            (id, journal_entry_id, account_id, entry_type, amount, is_deleted, created_at, updated_at)
        VALUES (gen_random_uuid(), v_entry_id, v_retained_id, 'CREDIT', v_net_income, FALSE, NOW(), NOW());
    ELSIF v_net_income < 0 THEN
        INSERT INTO bookkeeping_journalentryline
            (id, journal_entry_id, account_id, entry_type, amount, is_deleted, created_at, updated_at)
        VALUES (gen_random_uuid(), v_entry_id, v_retained_id, 'DEBIT', ABS(v_net_income), FALSE, NOW(), NOW());
    END IF;

    RETURN v_entry_id;
END;
$$;
COMMENT ON FUNCTION fn_close_period_journal(UUID, UUID, UUID) IS
    'Year-end P&L closing: zeroes REVENUE and EXPENSE into Retained Earnings. Idempotent. Tags entry journal_type=CLOSING.';
"""

_REVERSE_SQL = """
CREATE OR REPLACE FUNCTION fn_close_period_journal(
    p_company_id     UUID,
    p_fiscal_year_id UUID,
    p_closed_by_id   UUID DEFAULT NULL
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_fy            RECORD;
    v_entry_id      UUID;
    v_retained_id   UUID;
    v_net_income    NUMERIC(14,2) := 0;
    v_total_revenue NUMERIC(14,2) := 0;
    v_total_expense NUMERIC(14,2) := 0;
    v_acc           RECORD;
    v_acc_balance   NUMERIC(14,2);
BEGIN
    SELECT * INTO v_fy FROM company_fiscalyear
    WHERE id = p_fiscal_year_id AND company_id = p_company_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'FiscalYear % not found for company %', p_fiscal_year_id, p_company_id
            USING ERRCODE = 'P0002';
    END IF;

    IF v_fy.is_closed THEN
        SELECT je.id INTO v_entry_id
        FROM bookkeeping_journalentry je
        WHERE je.company_id  = p_company_id
          AND je.description LIKE 'Year-End Closing%'
          AND je.date        = v_fy.end_date
          AND je.is_deleted  = FALSE
        ORDER BY je.created_at DESC LIMIT 1;
        RETURN v_entry_id;
    END IF;

    SELECT id INTO v_retained_id FROM bookkeeping_ledgeraccount
    WHERE company_id = p_company_id AND name = 'Retained Earnings' AND is_deleted = FALSE LIMIT 1;

    IF v_retained_id IS NULL THEN
        INSERT INTO bookkeeping_ledgeraccount
            (id, company_id, name, account_type, code, system_created, is_deleted, created_at, updated_at)
        VALUES
            (gen_random_uuid(), p_company_id, 'Retained Earnings', 'EQUITY', '3100', TRUE, FALSE, NOW(), NOW())
        RETURNING id INTO v_retained_id;
    END IF;

    INSERT INTO bookkeeping_journalentry
        (id, company_id, date, description, is_deleted, created_at, updated_at)
    VALUES
        (gen_random_uuid(), p_company_id, v_fy.end_date,
         'Year-End Closing Entry for ' || v_fy.name,
         FALSE, NOW(), NOW())
    RETURNING id INTO v_entry_id;

    FOR v_acc IN
        SELECT id FROM bookkeeping_ledgeraccount
        WHERE company_id = p_company_id AND account_type = 'REVENUE' AND is_deleted = FALSE
    LOOP
        v_acc_balance := fn_get_account_balance(v_acc.id, v_fy.end_date);
        IF v_acc_balance > 0 THEN
            INSERT INTO bookkeeping_journalentryline
                (id, journal_entry_id, account_id, entry_type, amount, is_deleted, created_at, updated_at)
            VALUES (gen_random_uuid(), v_entry_id, v_acc.id, 'DEBIT', v_acc_balance, FALSE, NOW(), NOW());
            v_total_revenue := v_total_revenue + v_acc_balance;
        END IF;
    END LOOP;

    FOR v_acc IN
        SELECT id FROM bookkeeping_ledgeraccount
        WHERE company_id = p_company_id AND account_type = 'EXPENSE' AND is_deleted = FALSE
    LOOP
        v_acc_balance := fn_get_account_balance(v_acc.id, v_fy.end_date);
        IF v_acc_balance > 0 THEN
            INSERT INTO bookkeeping_journalentryline
                (id, journal_entry_id, account_id, entry_type, amount, is_deleted, created_at, updated_at)
            VALUES (gen_random_uuid(), v_entry_id, v_acc.id, 'CREDIT', v_acc_balance, FALSE, NOW(), NOW());
            v_total_expense := v_total_expense + v_acc_balance;
        END IF;
    END LOOP;

    v_net_income := v_total_revenue - v_total_expense;
    IF v_net_income > 0 THEN
        INSERT INTO bookkeeping_journalentryline
            (id, journal_entry_id, account_id, entry_type, amount, is_deleted, created_at, updated_at)
        VALUES (gen_random_uuid(), v_entry_id, v_retained_id, 'CREDIT', v_net_income, FALSE, NOW(), NOW());
    ELSIF v_net_income < 0 THEN
        INSERT INTO bookkeeping_journalentryline
            (id, journal_entry_id, account_id, entry_type, amount, is_deleted, created_at, updated_at)
        VALUES (gen_random_uuid(), v_entry_id, v_retained_id, 'DEBIT', ABS(v_net_income), FALSE, NOW(), NOW());
    END IF;

    RETURN v_entry_id;
END;
$$;
COMMENT ON FUNCTION fn_close_period_journal(UUID, UUID, UUID) IS
    'Year-end P&L closing: zeroes REVENUE and EXPENSE into Retained Earnings. Idempotent.';
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
        ('bookkeeping', '0028_journalentry_db_defaults_for_raw_sql_inserts'),
    ]

    operations = [
        migrations.RunPython(apply_fix, revert_fix),
    ]
