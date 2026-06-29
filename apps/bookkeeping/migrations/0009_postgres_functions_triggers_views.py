from django.db import migrations

# PostgreSQL enterprise layer: functions, triggers, stored procedures, views.
#
# WHAT THIS INSTALLS
# ==================
# Audit table : bookkeeping_journalentry_audit
# Functions   : fn_get_account_balance, fn_get_trial_balance, fn_get_ar_aging,
#               fn_post_invoice_journal, fn_post_payment_journal,
#               fn_close_period_journal
# Triggers    : trg_journal_entry_balance_check  (enforces DR=CR at DB level)
#               trg_invoice_outstanding_balance  (recalcs invoice totals)
#               trg_vendor_bill_total            (recalcs vendor bill total)
#               trg_payroll_run_totals           (recalcs payroll run totals)
#               trg_audit_journal_entry          (immutable audit trail)
# Views       : vw_trial_balance, vw_ar_aging, vw_income_statement,
#               vw_balance_sheet_summary, vw_outstanding_invoices,
#               vw_vendor_payables, vw_payroll_summary
# Indexes     : 11 partial indexes for report query performance
#
# MySQL/MariaDB: this entire migration is a no-op — Django signals handle the
# same business logic in Python, and MySQL does not support PL/pgSQL.

_POSTGRESQL_STATEMENTS = [
    # Audit table
    """CREATE TABLE IF NOT EXISTS bookkeeping_journalentry_audit (
        id               BIGSERIAL    PRIMARY KEY,
        journal_entry_id UUID         NOT NULL,
        company_id       UUID,
        changed_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
        operation        CHAR(1)      NOT NULL CHECK (operation IN ('U','D')),
        old_date         DATE,
        old_description  VARCHAR(700),
        old_is_deleted   BOOLEAN,
        changed_by       TEXT
    );
    COMMENT ON TABLE bookkeeping_journalentry_audit IS
        'Immutable append-only audit trail for every mutation of a posted journal entry.';""",

    # fn_get_account_balance
    """CREATE OR REPLACE FUNCTION fn_get_account_balance(
        p_account_id UUID,
        p_as_of_date  DATE DEFAULT CURRENT_DATE
    )
    RETURNS NUMERIC(14,2)
    LANGUAGE plpgsql
    STABLE
    SECURITY DEFINER
    AS $$
    DECLARE
        v_account_type  VARCHAR(10);
        v_debit_total   NUMERIC(14,2) := 0;
        v_credit_total  NUMERIC(14,2) := 0;
        v_opening_bal   NUMERIC(14,2) := 0;
        v_opening_type  VARCHAR(10)   := 'DEBIT';
    BEGIN
        SELECT account_type INTO v_account_type
        FROM   bookkeeping_ledgeraccount
        WHERE  id = p_account_id AND is_deleted = FALSE;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'LedgerAccount % not found', p_account_id
                USING ERRCODE = 'P0002';
        END IF;

        SELECT COALESCE(lob.amount, 0), COALESCE(lob.opening_type, 'DEBIT')
        INTO   v_opening_bal, v_opening_type
        FROM   bookkeeping_ledgeropeningbalance lob
        JOIN   company_fiscalyear fy ON fy.id = lob.fiscal_year_id
        WHERE  lob.account_id = p_account_id
          AND  fy.start_date  <= p_as_of_date
        ORDER BY fy.start_date DESC
        LIMIT 1;

        SELECT
            COALESCE(SUM(jel.amount) FILTER (WHERE jel.entry_type = 'DEBIT'),  0),
            COALESCE(SUM(jel.amount) FILTER (WHERE jel.entry_type = 'CREDIT'), 0)
        INTO v_debit_total, v_credit_total
        FROM bookkeeping_journalentryline jel
        JOIN bookkeeping_journalentry     je  ON je.id = jel.journal_entry_id
        WHERE jel.account_id    = p_account_id
          AND jel.is_deleted    = FALSE
          AND je.is_deleted     = FALSE
          AND je.date           <= p_as_of_date;

        IF v_opening_type = 'DEBIT' THEN
            v_debit_total := v_debit_total + v_opening_bal;
        ELSE
            v_credit_total := v_credit_total + v_opening_bal;
        END IF;

        IF v_account_type IN ('ASSET', 'EXPENSE') THEN
            RETURN v_debit_total - v_credit_total;
        ELSE
            RETURN v_credit_total - v_debit_total;
        END IF;
    END;
    $$;
    COMMENT ON FUNCTION fn_get_account_balance(UUID, DATE) IS
        'Returns the net balance of a ledger account up to a given date, sign-corrected for account type.';""",

    # fn_get_trial_balance
    """CREATE OR REPLACE FUNCTION fn_get_trial_balance(
        p_company_id  UUID,
        p_as_of_date  DATE DEFAULT CURRENT_DATE
    )
    RETURNS TABLE (
        account_id     UUID,
        account_code   VARCHAR(50),
        account_name   VARCHAR(255),
        account_type   VARCHAR(10),
        debit_balance  NUMERIC(14,2),
        credit_balance NUMERIC(14,2)
    )
    LANGUAGE plpgsql
    STABLE
    SECURITY DEFINER
    AS $$
    BEGIN
        RETURN QUERY
        WITH line_totals AS (
            SELECT
                jel.account_id,
                COALESCE(SUM(jel.amount) FILTER (WHERE jel.entry_type = 'DEBIT'),  0) AS total_debit,
                COALESCE(SUM(jel.amount) FILTER (WHERE jel.entry_type = 'CREDIT'), 0) AS total_credit
            FROM bookkeeping_journalentryline jel
            JOIN bookkeeping_journalentry     je  ON je.id = jel.journal_entry_id
            WHERE je.company_id  = p_company_id
              AND je.is_deleted  = FALSE
              AND jel.is_deleted = FALSE
              AND je.date        <= p_as_of_date
            GROUP BY jel.account_id
        ),
        opening_totals AS (
            SELECT
                lob.account_id,
                CASE WHEN lob.opening_type = 'DEBIT'  THEN lob.amount ELSE 0 END AS ob_debit,
                CASE WHEN lob.opening_type = 'CREDIT' THEN lob.amount ELSE 0 END AS ob_credit
            FROM bookkeeping_ledgeropeningbalance lob
            JOIN company_fiscalyear fy ON fy.id = lob.fiscal_year_id
            WHERE fy.company_id   = p_company_id
              AND fy.start_date   <= p_as_of_date
              AND fy.id = (
                  SELECT fy2.id FROM company_fiscalyear fy2
                  WHERE fy2.company_id = p_company_id
                    AND fy2.start_date <= p_as_of_date
                  ORDER BY fy2.start_date DESC LIMIT 1
              )
        )
        SELECT
            la.id,
            la.code,
            la.name,
            la.account_type,
            CASE
                WHEN la.account_type IN ('ASSET','EXPENSE') THEN
                    GREATEST(0, (COALESCE(lt.total_debit,0)  + COALESCE(ot.ob_debit,0))
                               - (COALESCE(lt.total_credit,0) + COALESCE(ot.ob_credit,0)))
                ELSE
                    GREATEST(0, (COALESCE(lt.total_credit,0) + COALESCE(ot.ob_credit,0))
                               - (COALESCE(lt.total_debit,0)  + COALESCE(ot.ob_debit,0)))
            END AS debit_balance,
            CASE
                WHEN la.account_type NOT IN ('ASSET','EXPENSE') THEN
                    GREATEST(0, (COALESCE(lt.total_credit,0) + COALESCE(ot.ob_credit,0))
                               - (COALESCE(lt.total_debit,0)  + COALESCE(ot.ob_debit,0)))
                ELSE
                    GREATEST(0, (COALESCE(lt.total_debit,0)  + COALESCE(ot.ob_debit,0))
                               - (COALESCE(lt.total_credit,0) + COALESCE(ot.ob_credit,0)))
            END AS credit_balance
        FROM bookkeeping_ledgeraccount la
        LEFT JOIN line_totals    lt ON lt.account_id = la.id
        LEFT JOIN opening_totals ot ON ot.account_id = la.id
        WHERE la.company_id  = p_company_id
          AND la.is_deleted  = FALSE
          AND (lt.account_id IS NOT NULL OR ot.account_id IS NOT NULL)
        ORDER BY la.account_type, la.code NULLS LAST, la.name;
    END;
    $$;
    COMMENT ON FUNCTION fn_get_trial_balance(UUID, DATE) IS
        'Returns trial balance rows for a company up to a given date.';""",

    # fn_get_ar_aging
    """CREATE OR REPLACE FUNCTION fn_get_ar_aging(
        p_company_id  UUID,
        p_as_of_date  DATE DEFAULT CURRENT_DATE
    )
    RETURNS TABLE (
        customer_id       UUID,
        customer_name     VARCHAR(255),
        current_amount    NUMERIC(14,2),
        days_1_30         NUMERIC(14,2),
        days_31_60        NUMERIC(14,2),
        days_61_90        NUMERIC(14,2),
        days_90_plus      NUMERIC(14,2),
        total_outstanding NUMERIC(14,2)
    )
    LANGUAGE plpgsql
    STABLE
    SECURITY DEFINER
    AS $$
    BEGIN
        RETURN QUERY
        SELECT
            c.id,
            c.name,
            COALESCE(SUM(i.outstanding_balance)
                FILTER (WHERE (p_as_of_date - i.due_date) <= 0),  0)             AS current_amount,
            COALESCE(SUM(i.outstanding_balance)
                FILTER (WHERE (p_as_of_date - i.due_date) BETWEEN 1  AND 30), 0) AS days_1_30,
            COALESCE(SUM(i.outstanding_balance)
                FILTER (WHERE (p_as_of_date - i.due_date) BETWEEN 31 AND 60), 0) AS days_31_60,
            COALESCE(SUM(i.outstanding_balance)
                FILTER (WHERE (p_as_of_date - i.due_date) BETWEEN 61 AND 90), 0) AS days_61_90,
            COALESCE(SUM(i.outstanding_balance)
                FILTER (WHERE (p_as_of_date - i.due_date) > 90),  0)             AS days_90_plus,
            COALESCE(SUM(i.outstanding_balance), 0)                              AS total_outstanding
        FROM customers_customer c
        JOIN billing_invoice    i  ON i.customer_id = c.id
        WHERE i.company_id          = p_company_id
          AND i.is_deleted          = FALSE
          AND i.outstanding_balance > 0
          AND i.due_date            IS NOT NULL
        GROUP BY c.id, c.name
        HAVING COALESCE(SUM(i.outstanding_balance), 0) > 0
        ORDER BY total_outstanding DESC;
    END;
    $$;
    COMMENT ON FUNCTION fn_get_ar_aging(UUID, DATE) IS
        'Returns AR aging buckets per customer for a company.';""",

    # fn_post_invoice_journal
    """CREATE OR REPLACE FUNCTION fn_post_invoice_journal(p_invoice_id UUID)
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
        'Atomically creates/replaces the double-entry journal for an invoice.';""",

    # fn_post_payment_journal
    """CREATE OR REPLACE FUNCTION fn_post_payment_journal(p_payment_id UUID)
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
        'Atomically creates the double-entry journal for a payment.';""",

    # fn_close_period_journal
    """CREATE OR REPLACE FUNCTION fn_close_period_journal(
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
        'Year-end P&L closing: zeroes REVENUE and EXPENSE into Retained Earnings. Idempotent.';""",

    # trigger function: balance check
    """CREATE OR REPLACE FUNCTION trg_fn_journal_balance_check()
    RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER AS $$
    DECLARE
        v_debit_total  NUMERIC(14,2);
        v_credit_total NUMERIC(14,2);
        v_line_count   INTEGER;
    BEGIN
        SELECT
            COALESCE(SUM(amount) FILTER (WHERE entry_type = 'DEBIT'),  0),
            COALESCE(SUM(amount) FILTER (WHERE entry_type = 'CREDIT'), 0),
            COUNT(*)
        INTO v_debit_total, v_credit_total, v_line_count
        FROM bookkeeping_journalentryline
        WHERE journal_entry_id = NEW.journal_entry_id AND is_deleted = FALSE;

        IF v_line_count >= 2 AND ABS(v_debit_total - v_credit_total) > 0.01 THEN
            RAISE EXCEPTION
                'Journal entry % is unbalanced: debits=% credits=% diff=%',
                NEW.journal_entry_id, v_debit_total, v_credit_total,
                ABS(v_debit_total - v_credit_total)
                USING ERRCODE = 'P0001';
        END IF;
        RETURN NEW;
    END; $$;""",

    """DROP TRIGGER IF EXISTS trg_journal_entry_balance_check ON bookkeeping_journalentryline;
    CREATE TRIGGER trg_journal_entry_balance_check
        AFTER INSERT OR UPDATE ON bookkeeping_journalentryline
        FOR EACH ROW EXECUTE FUNCTION trg_fn_journal_balance_check();
    COMMENT ON TRIGGER trg_journal_entry_balance_check ON bookkeeping_journalentryline IS
        'Enforces double-entry balance at DB level.';""",

    # trigger function: invoice recalc
    """CREATE OR REPLACE FUNCTION trg_fn_invoice_recalc_totals()
    RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER AS $$
    DECLARE
        v_invoice_id UUID;
        v_subtotal   NUMERIC(14,2);
        v_discount   NUMERIC(14,2);
        v_tax_pct    NUMERIC(5,2);
        v_tax_amt    NUMERIC(14,2);
        v_total      NUMERIC(14,2);
        v_paid       NUMERIC(14,2);
    BEGIN
        v_invoice_id := CASE TG_OP WHEN 'DELETE' THEN OLD.invoice_id ELSE NEW.invoice_id END;

        SELECT
            COALESCE(SUM(ii.quantity * ii.price), 0),
            COALESCE(SUM(
                CASE
                    WHEN ii.discount_amount > 0 THEN ii.discount_amount
                    WHEN ii.discount_percent > 0 THEN
                        ROUND((ii.quantity * ii.price * ii.discount_percent / 100), 2)
                    ELSE 0
                END
            ), 0)
        INTO v_subtotal, v_discount
        FROM billing_invoiceitem ii
        WHERE ii.invoice_id = v_invoice_id;

        SELECT COALESCE(tax_percent, 0) INTO v_tax_pct
        FROM billing_invoice WHERE id = v_invoice_id;

        v_tax_amt := ROUND(((v_subtotal - v_discount) * v_tax_pct / 100), 2);
        v_total   := v_subtotal - v_discount + v_tax_amt;

        SELECT COALESCE(SUM(amount_applied), 0) INTO v_paid
        FROM payments_payment WHERE invoice_id = v_invoice_id AND is_deleted = FALSE;

        UPDATE billing_invoice
        SET subtotal            = v_subtotal,
            discount_amount     = v_discount,
            tax_amount          = v_tax_amt,
            total               = v_total,
            outstanding_balance = GREATEST(0, v_total - v_paid),
            updated_at          = NOW()
        WHERE id = v_invoice_id;

        RETURN NULL;
    END; $$;""",

    """DROP TRIGGER IF EXISTS trg_invoice_outstanding_balance ON billing_invoiceitem;
    CREATE TRIGGER trg_invoice_outstanding_balance
        AFTER INSERT OR UPDATE OR DELETE ON billing_invoiceitem
        FOR EACH ROW EXECUTE FUNCTION trg_fn_invoice_recalc_totals();""",

    # trigger function: vendor bill recalc
    """CREATE OR REPLACE FUNCTION trg_fn_vendor_bill_recalc_total()
    RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER AS $$
    DECLARE
        v_bill_id UUID;
        v_total   NUMERIC(14,2);
    BEGIN
        v_bill_id := CASE TG_OP WHEN 'DELETE' THEN OLD.vendor_bill_id ELSE NEW.vendor_bill_id END;
        SELECT COALESCE(SUM(quantity * price), 0) INTO v_total
        FROM billing_vendorbillitem WHERE vendor_bill_id = v_bill_id AND is_deleted = FALSE;
        UPDATE billing_vendorbill SET total_amount = v_total, updated_at = NOW() WHERE id = v_bill_id;
        RETURN NULL;
    END; $$;""",

    """DROP TRIGGER IF EXISTS trg_vendor_bill_total ON billing_vendorbillitem;
    CREATE TRIGGER trg_vendor_bill_total
        AFTER INSERT OR UPDATE OR DELETE ON billing_vendorbillitem
        FOR EACH ROW EXECUTE FUNCTION trg_fn_vendor_bill_recalc_total();""",

    # trigger function: payroll run recalc
    """CREATE OR REPLACE FUNCTION trg_fn_payroll_run_recalc_totals()
    RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER AS $$
    DECLARE
        v_run_id UUID;
    BEGIN
        v_run_id := CASE TG_OP WHEN 'DELETE' THEN OLD.payroll_run_id ELSE NEW.payroll_run_id END;
        UPDATE hrpayroll_payrollrun
        SET
            total_gross_pay = (SELECT COALESCE(SUM(gross_pay), 0) FROM hrpayroll_payslip
                               WHERE payroll_run_id = v_run_id AND is_deleted = FALSE),
            total_net_pay   = (SELECT COALESCE(SUM(net_pay),   0) FROM hrpayroll_payslip
                               WHERE payroll_run_id = v_run_id AND is_deleted = FALSE),
            updated_at      = NOW()
        WHERE id = v_run_id;
        RETURN NULL;
    END; $$;""",

    """DROP TRIGGER IF EXISTS trg_payroll_run_totals ON hrpayroll_payslip;
    CREATE TRIGGER trg_payroll_run_totals
        AFTER INSERT OR UPDATE OR DELETE ON hrpayroll_payslip
        FOR EACH ROW EXECUTE FUNCTION trg_fn_payroll_run_recalc_totals();""",

    # trigger function: audit journal entry
    """CREATE OR REPLACE FUNCTION trg_fn_audit_journal_entry()
    RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER AS $$
    BEGIN
        INSERT INTO bookkeeping_journalentry_audit
            (journal_entry_id, company_id, operation, old_date, old_description, old_is_deleted, changed_by)
        VALUES (
            OLD.id, OLD.company_id,
            CASE TG_OP WHEN 'UPDATE' THEN 'U' ELSE 'D' END,
            OLD.date, OLD.description, OLD.is_deleted,
            current_user
        );
        RETURN NULL;
    END; $$;""",

    """DROP TRIGGER IF EXISTS trg_audit_journal_entry ON bookkeeping_journalentry;
    CREATE TRIGGER trg_audit_journal_entry
        AFTER UPDATE OR DELETE ON bookkeeping_journalentry
        FOR EACH ROW EXECUTE FUNCTION trg_fn_audit_journal_entry();""",

    # Views
    """CREATE OR REPLACE VIEW vw_trial_balance AS
    SELECT
        la.company_id,
        la.id                                                           AS account_id,
        la.code                                                         AS account_code,
        la.name                                                         AS account_name,
        la.account_type,
        COALESCE(SUM(jel.amount) FILTER (WHERE jel.entry_type='DEBIT'),  0) AS total_debits,
        COALESCE(SUM(jel.amount) FILTER (WHERE jel.entry_type='CREDIT'), 0) AS total_credits,
        CASE
            WHEN la.account_type IN ('ASSET','EXPENSE') THEN
                COALESCE(SUM(jel.amount) FILTER (WHERE jel.entry_type='DEBIT'),  0) -
                COALESCE(SUM(jel.amount) FILTER (WHERE jel.entry_type='CREDIT'), 0)
            ELSE
                COALESCE(SUM(jel.amount) FILTER (WHERE jel.entry_type='CREDIT'), 0) -
                COALESCE(SUM(jel.amount) FILTER (WHERE jel.entry_type='DEBIT'),  0)
        END AS net_balance
    FROM bookkeeping_ledgeraccount la
    LEFT JOIN bookkeeping_journalentryline jel ON jel.account_id=la.id AND jel.is_deleted=FALSE
    LEFT JOIN bookkeeping_journalentry     je  ON je.id=jel.journal_entry_id AND je.is_deleted=FALSE
    WHERE la.is_deleted=FALSE
    GROUP BY la.company_id, la.id, la.code, la.name, la.account_type
    ORDER BY la.company_id, la.account_type, la.code NULLS LAST, la.name;""",

    """CREATE OR REPLACE VIEW vw_ar_aging AS
    SELECT
        i.company_id,
        c.id                                                                    AS customer_id,
        c.name                                                                  AS customer_name,
        COALESCE(SUM(i.outstanding_balance)
            FILTER (WHERE (CURRENT_DATE - i.due_date) <= 0),  0)               AS current_amount,
        COALESCE(SUM(i.outstanding_balance)
            FILTER (WHERE (CURRENT_DATE - i.due_date) BETWEEN 1  AND 30), 0)   AS days_1_30,
        COALESCE(SUM(i.outstanding_balance)
            FILTER (WHERE (CURRENT_DATE - i.due_date) BETWEEN 31 AND 60), 0)   AS days_31_60,
        COALESCE(SUM(i.outstanding_balance)
            FILTER (WHERE (CURRENT_DATE - i.due_date) BETWEEN 61 AND 90), 0)   AS days_61_90,
        COALESCE(SUM(i.outstanding_balance)
            FILTER (WHERE (CURRENT_DATE - i.due_date) > 90),  0)               AS days_90_plus,
        COALESCE(SUM(i.outstanding_balance), 0)                                AS total_outstanding
    FROM billing_invoice    i
    JOIN customers_customer c ON c.id = i.customer_id
    WHERE i.is_deleted=FALSE AND i.outstanding_balance > 0 AND i.due_date IS NOT NULL
    GROUP BY i.company_id, c.id, c.name
    ORDER BY i.company_id, total_outstanding DESC;""",

    """CREATE OR REPLACE VIEW vw_income_statement AS
    SELECT
        je.company_id,
        la.account_type,
        la.id   AS account_id,
        la.name AS account_name,
        la.code AS account_code,
        COALESCE(SUM(jel.amount) FILTER (WHERE jel.entry_type='CREDIT'), 0) AS credit_total,
        COALESCE(SUM(jel.amount) FILTER (WHERE jel.entry_type='DEBIT'),  0) AS debit_total,
        CASE la.account_type
            WHEN 'REVENUE' THEN
                COALESCE(SUM(jel.amount) FILTER (WHERE jel.entry_type='CREDIT'), 0) -
                COALESCE(SUM(jel.amount) FILTER (WHERE jel.entry_type='DEBIT'),  0)
            WHEN 'EXPENSE' THEN
                COALESCE(SUM(jel.amount) FILTER (WHERE jel.entry_type='DEBIT'),  0) -
                COALESCE(SUM(jel.amount) FILTER (WHERE jel.entry_type='CREDIT'), 0)
            ELSE 0
        END AS net_amount,
        je.date
    FROM bookkeeping_journalentryline jel
    JOIN bookkeeping_journalentry  je  ON je.id=jel.journal_entry_id AND je.is_deleted=FALSE
    JOIN bookkeeping_ledgeraccount la  ON la.id=jel.account_id       AND la.is_deleted=FALSE
    WHERE jel.is_deleted=FALSE AND la.account_type IN ('REVENUE','EXPENSE')
    GROUP BY je.company_id, la.account_type, la.id, la.name, la.code, je.date
    ORDER BY je.company_id, je.date, la.account_type, la.name;""",

    """CREATE OR REPLACE VIEW vw_balance_sheet_summary AS
    SELECT
        la.company_id,
        la.account_type,
        COALESCE(SUM(jel.amount) FILTER (WHERE jel.entry_type='DEBIT'),  0) AS total_debits,
        COALESCE(SUM(jel.amount) FILTER (WHERE jel.entry_type='CREDIT'), 0) AS total_credits,
        CASE la.account_type
            WHEN 'ASSET' THEN
                COALESCE(SUM(jel.amount) FILTER (WHERE jel.entry_type='DEBIT'),  0) -
                COALESCE(SUM(jel.amount) FILTER (WHERE jel.entry_type='CREDIT'), 0)
            ELSE
                COALESCE(SUM(jel.amount) FILTER (WHERE jel.entry_type='CREDIT'), 0) -
                COALESCE(SUM(jel.amount) FILTER (WHERE jel.entry_type='DEBIT'),  0)
        END AS net_balance
    FROM bookkeeping_ledgeraccount la
    LEFT JOIN bookkeeping_journalentryline jel ON jel.account_id=la.id AND jel.is_deleted=FALSE
    LEFT JOIN bookkeeping_journalentry     je  ON je.id=jel.journal_entry_id AND je.is_deleted=FALSE
    WHERE la.is_deleted=FALSE AND la.account_type IN ('ASSET','LIABILITY','EQUITY')
    GROUP BY la.company_id, la.account_type
    ORDER BY la.company_id, la.account_type;""",

    """CREATE OR REPLACE VIEW vw_outstanding_invoices AS
    SELECT
        i.company_id,
        i.id              AS invoice_id,
        i.invoice_number,
        i.transaction_date,
        i.due_date,
        CURRENT_DATE - i.due_date AS days_overdue,
        c.id              AS customer_id,
        c.name            AS customer_name,
        i.total,
        i.outstanding_balance
    FROM billing_invoice    i
    LEFT JOIN customers_customer c ON c.id = i.customer_id
    WHERE i.is_deleted=FALSE AND i.outstanding_balance > 0 AND i.invoice_number IS NOT NULL
    ORDER BY i.company_id, i.due_date NULLS LAST;""",

    """CREATE OR REPLACE VIEW vw_vendor_payables AS
    SELECT
        COALESCE(po.company_id, v.company_id)          AS company_id,
        vb.id                                          AS vendor_bill_id,
        vb.bill_number,
        vb.bill_date,
        vb.due_date,
        CURRENT_DATE - vb.due_date                    AS days_overdue,
        v.id                                           AS vendor_id,
        v.name                                         AS vendor_name,
        vb.total_amount,
        COALESCE(SUM(vp.amount), 0)                    AS total_paid,
        vb.total_amount - COALESCE(SUM(vp.amount), 0) AS outstanding_amount
    FROM billing_vendorbill     vb
    JOIN vendors_vendor          v  ON v.id  = vb.vendor_id
    LEFT JOIN purchasing_purchaseorder po ON po.id = vb.purchase_order_id
    LEFT JOIN payments_vendorpayment   vp ON vp.vendor_bill_id = vb.id AND vp.is_deleted = FALSE
    WHERE vb.status NOT IN ('PAID','CANCELLED')
    GROUP BY COALESCE(po.company_id, v.company_id), vb.id, vb.bill_number,
             vb.bill_date, vb.due_date, v.id, v.name, vb.total_amount
    HAVING vb.total_amount - COALESCE(SUM(vp.amount), 0) > 0
    ORDER BY COALESCE(po.company_id, v.company_id), vb.due_date NULLS LAST;""",

    """CREATE OR REPLACE VIEW vw_payroll_summary AS
    SELECT
        pr.company_id,
        pr.id                         AS payroll_run_id,
        pr.period_start_date,
        pr.period_end_date,
        pr.payroll_date,
        pr.status,
        COUNT(ps.id)                  AS employee_count,
        COALESCE(SUM(ps.gross_pay), 0)        AS total_gross_pay,
        COALESCE(SUM(ps.total_deductions), 0) AS total_deductions,
        COALESCE(SUM(ps.net_pay), 0)          AS total_net_pay
    FROM hrpayroll_payrollrun pr
    LEFT JOIN hrpayroll_payslip ps ON ps.payroll_run_id=pr.id AND ps.is_deleted=FALSE
    WHERE pr.is_deleted=FALSE
    GROUP BY pr.company_id, pr.id, pr.period_start_date, pr.period_end_date, pr.payroll_date, pr.status
    ORDER BY pr.company_id, pr.period_start_date DESC;""",

    # Indexes
    """CREATE INDEX IF NOT EXISTS idx_jel_account_date
        ON bookkeeping_journalentryline (account_id)
        WHERE is_deleted = FALSE;

    CREATE INDEX IF NOT EXISTS idx_je_company_date
        ON bookkeeping_journalentry (company_id, date)
        WHERE is_deleted = FALSE;

    CREATE INDEX IF NOT EXISTS idx_jel_journal_entry
        ON bookkeeping_journalentryline (journal_entry_id)
        WHERE is_deleted = FALSE;

    CREATE INDEX IF NOT EXISTS idx_invoice_company_outstanding
        ON billing_invoice (company_id, outstanding_balance)
        WHERE is_deleted = FALSE AND outstanding_balance > 0;

    CREATE INDEX IF NOT EXISTS idx_invoice_due_date
        ON billing_invoice (company_id, due_date)
        WHERE is_deleted = FALSE;

    CREATE INDEX IF NOT EXISTS idx_payment_invoice
        ON payments_payment (invoice_id)
        WHERE is_deleted = FALSE;

    CREATE INDEX IF NOT EXISTS idx_vendorbill_vendor
        ON billing_vendorbill (vendor_id);

    CREATE INDEX IF NOT EXISTS idx_payslip_payroll_run
        ON hrpayroll_payslip (payroll_run_id)
        WHERE is_deleted = FALSE;

    CREATE INDEX IF NOT EXISTS idx_ledgeraccount_company_type
        ON bookkeeping_ledgeraccount (company_id, account_type)
        WHERE is_deleted = FALSE;

    CREATE INDEX IF NOT EXISTS idx_je_audit_entry_id
        ON bookkeeping_journalentry_audit (journal_entry_id);

    CREATE INDEX IF NOT EXISTS idx_je_audit_changed_at
        ON bookkeeping_journalentry_audit (changed_at DESC);""",
]


def install_postgres_layer(apps, schema_editor):
    # MySQL/MariaDB: Django signals handle the same logic — skip entirely
    if schema_editor.connection.vendor != 'postgresql':
        return
    # Use raw cursor to avoid Django's mogrify path, which misinterprets
    # % signs in PL/pgSQL RAISE EXCEPTION strings as SQL parameter placeholders.
    with schema_editor.connection.cursor() as cursor:
        for sql in _POSTGRESQL_STATEMENTS:
            cursor.execute(sql)


def remove_postgres_layer(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute("""
        DROP INDEX IF EXISTS idx_je_audit_changed_at;
        DROP INDEX IF EXISTS idx_je_audit_entry_id;
        DROP INDEX IF EXISTS idx_ledgeraccount_company_type;
        DROP INDEX IF EXISTS idx_payslip_payroll_run;
        DROP INDEX IF EXISTS idx_vendorbill_vendor;
        DROP INDEX IF EXISTS idx_payment_invoice;
        DROP INDEX IF EXISTS idx_invoice_due_date;
        DROP INDEX IF EXISTS idx_invoice_company_outstanding;
        DROP INDEX IF EXISTS idx_jel_journal_entry;
        DROP INDEX IF EXISTS idx_je_company_date;
        DROP INDEX IF EXISTS idx_jel_account_date;

        DROP VIEW IF EXISTS vw_payroll_summary;
        DROP VIEW IF EXISTS vw_vendor_payables;
        DROP VIEW IF EXISTS vw_outstanding_invoices;
        DROP VIEW IF EXISTS vw_balance_sheet_summary;
        DROP VIEW IF EXISTS vw_income_statement;
        DROP VIEW IF EXISTS vw_ar_aging;
        DROP VIEW IF EXISTS vw_trial_balance;

        DROP TRIGGER IF EXISTS trg_audit_journal_entry ON bookkeeping_journalentry;
        DROP FUNCTION IF EXISTS trg_fn_audit_journal_entry();
        DROP TRIGGER IF EXISTS trg_payroll_run_totals ON hrpayroll_payslip;
        DROP FUNCTION IF EXISTS trg_fn_payroll_run_recalc_totals();
        DROP TRIGGER IF EXISTS trg_vendor_bill_total ON billing_vendorbillitem;
        DROP FUNCTION IF EXISTS trg_fn_vendor_bill_recalc_total();
        DROP TRIGGER IF EXISTS trg_invoice_outstanding_balance ON billing_invoiceitem;
        DROP FUNCTION IF EXISTS trg_fn_invoice_recalc_totals();
        DROP TRIGGER IF EXISTS trg_journal_entry_balance_check ON bookkeeping_journalentryline;
        DROP FUNCTION IF EXISTS trg_fn_journal_balance_check();
        DROP FUNCTION IF EXISTS fn_close_period_journal(UUID, UUID, UUID);
        DROP FUNCTION IF EXISTS fn_post_payment_journal(UUID);
        DROP FUNCTION IF EXISTS fn_post_invoice_journal(UUID);
        DROP FUNCTION IF EXISTS fn_get_ar_aging(UUID, DATE);
        DROP FUNCTION IF EXISTS fn_get_trial_balance(UUID, DATE);
        DROP FUNCTION IF EXISTS fn_get_account_balance(UUID, DATE);
        DROP TABLE IF EXISTS bookkeeping_journalentry_audit CASCADE;
    """)


class Migration(migrations.Migration):

    dependencies = [
        ("bookkeeping", "0008_remove_ledgeraccount_opening_type"),
        ("billing", "0008_invoice_transaction_date"),
        ("payments", "0004_repair_vendorpayment_table"),
        ("hrpayroll", "0001_initial"),
        ("company", "0005_fiscalyear_closed_at_fiscalyear_closed_by_and_more"),
        ("customers", "0002_customer_text"),
        ("vendors", "0003_vendor_related_ledger_account"),
        ("purchasing", "0003_purchaseorderitem_hscode"),
    ]

    operations = [
        migrations.RunPython(install_postgres_layer, remove_postgres_layer),
    ]
