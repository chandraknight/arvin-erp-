from django.urls import reverse
from decimal import Decimal
from apps.utils.baseModel import *
import nepali_datetime

ORGANISATION_TYPE_CHOICES = [
    ('TRADING',          'Trading / Retail'),
    ('SERVICE',          'Service'),
    ('PROJECT',          'Project-Based'),
    ('NGO',              'NGO / Non-Profit'),
    ('MANUFACTURING',    'Manufacturing'),
    ('RESTAURANT',       'Restaurant / F&B'),
    ('SMALL_ENTERPRISE', 'Small Enterprise'),
    ('TOUR_OPERATOR',    'Tour & Ticketing Operator'),
    ('OTHER',            'Other'),
]

class Company(BaseModel):
    name = models.CharField(max_length=255, unique=True)
    address = models.TextField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    logo = models.ImageField(upload_to='company_logos/', blank=True, null=True)
    tax_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('13.00'),
        help_text='Default VAT/tax rate for this company (e.g., 13.00 for 13%)'
    )
    # Organisation type — drives feature flags
    organisation_type = models.CharField(
        max_length=20, choices=ORGANISATION_TYPE_CHOICES, default='TRADING',
        help_text='Nature of the organisation — drives which modules are available.'
    )
    # VAT configuration
    vat_registered = models.BooleanField(
        default=False, help_text='Is this company registered for VAT/PAN?'
    )
    vat_number = models.CharField(
        max_length=50, blank=True, null=True,
        help_text='PAN / VAT registration number.'
    )
    vat_inclusive = models.BooleanField(
        default=False,
        help_text='If True, listed prices already include VAT (tax-inclusive pricing).'
    )
    # NFRS 12 — Corporate Income Tax
    cit_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('25.00'),
        help_text='NFRS 12: Corporate Income Tax rate (%). Nepal standard = 25%. Special industries may use 15%.',
    )
    # Feature flags
    enable_branch_accounting = models.BooleanField(
        default=False,
        help_text='Enable branch-wise reporting and transaction tagging.'
    )
    enable_project_tracking = models.BooleanField(
        default=False,
        help_text='Enable project / cost-centre module.'
    )
    enable_forecasting = models.BooleanField(
        default=False,
        help_text='Enable budget and revenue/expense forecasting module.'
    )
    enable_order_management = models.BooleanField(
        default=False,
        help_text='Enable Sales Orders and Delivery Management module.'
    )
    enable_manufacturing = models.BooleanField(
        default=False,
        help_text='Enable Manufacturing module (BOM, Work Orders, Production Runs).'
    )
    enable_hr_payroll = models.BooleanField(
        default=False,
        help_text='Enable HR & Payroll module (Employees, Attendance, Payroll Runs).'
    )
    enable_purchasing = models.BooleanField(
        default=False,
        help_text='Enable Purchasing module (Purchase Orders, Vendor Bills).'
    )
    enable_inventory = models.BooleanField(
        default=False,
        help_text='Enable Inventory / Product management module.'
    )
    enable_restaurant = models.BooleanField(
        default=False,
        help_text='Enable Restaurant module (Tables, KOT/BOT, Dining Orders, Printer Stations).'
    )
    enable_pos = models.BooleanField(
        default=False,
        help_text='Enable Point of Sale (POS) module for quick retail/counter sales.'
    )
    enable_tours = models.BooleanField(
        default=False,
        help_text='Enable Tours & Ticketing module (Enquiries, Bookings, Invoicing).'
    )
    enable_ecom = models.BooleanField(
        default=False,
        help_text='Enable E-Commerce storefront (/store/). Customers can browse products and place COD orders online.'
    )

    # CBMS / IRD e-Billing integration
    enable_ebilling = models.BooleanField(
        default=False,
        help_text='Enable real-time bill submission to Nepal IRD CBMS. Requires vat_number, cbms_username, and cbms_password.'
    )
    cbms_username = models.CharField(
        max_length=100, blank=True, null=True,
        help_text='IRD Taxpayer Login UserID for CBMS API.'
    )
    cbms_password = models.CharField(
        max_length=255, blank=True, null=True,
        help_text='IRD Taxpayer Login Password for CBMS API.'
    )

    class Meta:
        verbose_name_plural = "Companies"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('company:company_detail', kwargs={'pk': self.pk})

    def save(self, *args, **kwargs):
        # Only reset feature flags when organisation_type changes.
        # On subsequent saves the superadmin's manual toggles are preserved.
        org_type_changed = False
        if self.pk:
            try:
                prev = Company.objects.get(pk=self.pk)
                org_type_changed = prev.organisation_type != self.organisation_type
            except Company.DoesNotExist:
                org_type_changed = True
        else:
            org_type_changed = True  # new record — apply defaults

        if org_type_changed:
            self._apply_org_type_defaults()

        super().save(*args, **kwargs)

    def _apply_org_type_defaults(self):
        """Set feature flags to sensible defaults for the chosen organisation type."""
        # Baseline: all off — org-type blocks below enable what is needed
        self.enable_branch_accounting = False
        self.enable_project_tracking = False
        self.enable_forecasting = False
        self.enable_order_management = False
        self.enable_manufacturing = False
        self.enable_hr_payroll = False
        self.enable_purchasing = False
        self.enable_inventory = False
        self.enable_restaurant = False
        self.enable_pos = False
        self.enable_tours = False
        self.enable_ecom = False

        if self.organisation_type == 'TRADING':
            self.enable_inventory = True
            self.enable_purchasing = True
            self.enable_order_management = True
            self.enable_pos = True

        elif self.organisation_type == 'SERVICE':
            self.enable_order_management = True
            self.enable_inventory = False
            self.enable_purchasing = False
            self.enable_pos = True

        elif self.organisation_type == 'PROJECT':
            self.enable_project_tracking = True
            self.enable_forecasting = True
            self.enable_purchasing = True   # project firms procure materials/subcontractors
            self.enable_inventory = False
            self.enable_order_management = False

        elif self.organisation_type == 'NGO':
            self.enable_project_tracking = True
            self.enable_forecasting = True
            self.enable_purchasing = True
            self.enable_inventory = False

        elif self.organisation_type == 'MANUFACTURING':
            self.enable_manufacturing = True
            self.enable_order_management = True
            self.enable_inventory = True
            self.enable_purchasing = True

        elif self.organisation_type == 'RESTAURANT':
            self.enable_order_management = True
            self.enable_inventory = True
            self.enable_purchasing = True
            self.enable_hr_payroll = True
            self.enable_restaurant = True
            self.enable_pos = True

        elif self.organisation_type == 'SMALL_ENTERPRISE':
            self.enable_inventory = False
            self.enable_purchasing = False
            self.enable_hr_payroll = False
            self.enable_order_management = False
            self.enable_pos = True

        elif self.organisation_type == 'TOUR_OPERATOR':
            self.enable_tours = True
            self.enable_order_management = False
            self.enable_inventory = False
            self.enable_purchasing = True
            self.enable_hr_payroll = True
            self.enable_pos = False

        # OTHER: baseline defaults apply

class Branch(BaseModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='branches')
    name = models.CharField(max_length=255)
    address = models.TextField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    is_main_branch = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "Branches"
        unique_together = ('company', 'name') # A company cannot have two branches with the same name

    def __str__(self):
        return f"{self.name} ({self.company.name})"

    @property
    def company_name(self):
        return self.company.name

class FiscalYear(BaseModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='fiscal_years')
    start_date = models.DateField()
    end_date = models.DateField()
    start_date_bs = models.CharField(max_length=255, blank=True, null=True)
    end_date_bs = models.CharField(max_length=255, blank=True, null=True)
    name = models.CharField(max_length=20, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_closed = models.BooleanField(default=False, help_text='Closed years are read-only. No new transactions allowed.')
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        'accounts.User', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='closed_fiscal_years'
    )

    class Meta:
        unique_together = ('company', 'start_date', 'end_date')
        ordering = ['start_date']

    def save(self, *args, **kwargs):
        if not self.name and self.start_date_bs and self.end_date_bs:
            start_year = self.start_date_bs.split("-")[0]
            end_year = self.end_date_bs.split("-")[0]
            self.name = f"{start_year}/{end_year[-2:]}"
        super().save(*args, **kwargs)

    @property
    def company_name(self):
        return self.company.name

    def __str__(self):
        return f"{self.company.name} ({self.start_date.year}-{self.end_date.year})"

    @staticmethod
    def get_current(company, today=None):
        from datetime import date as dt_date
        if today is None:
            today = dt_date.today()
        return FiscalYear.objects.filter(company=company, start_date__lte=today, end_date__gte=today).first()

    @property
    def created_date_str(self):
        return self.created_at.strftime('%Y-%m-%d') if self.created_at else ''

    @property
    def start_date_ad(self):
        return self.start_date.strftime('%Y-%m-%d') if self.start_date else ''

    @property
    def end_date_ad(self):
        return self.end_date.strftime('%Y-%m-%d') if self.end_date else ''


    @property
    def bs_date(self):
        return f"{self.start_date_bs} ~ {self.end_date_bs}"

    @property
    def ad_date(self):
        return f"{self.start_date_ad} ~ {self.end_date_ad}"

    def get_close_validation(self):
        """
        Run pre-close checks and return a dict with:
          - errors: list of blocking issues (must fix before closing)
          - warnings: list of non-blocking advisories
          - stats: summary counts for display
        """
        from datetime import date as dt_date
        from apps.billing.models import Invoice
        from apps.bookkeeping.models import JournalEntry
        from decimal import Decimal

        today = dt_date.today()
        errors = []
        warnings = []
        stats = {}

        # 1. End date must have passed
        if self.end_date > today:
            errors.append(
                f"Fiscal year end date ({self.end_date_ad}) has not yet passed "
                f"(today is {today.strftime('%Y-%m-%d')}). "
                "You can only close a completed fiscal year."
            )

        # 2. Already closed
        if self.is_closed:
            errors.append("This fiscal year is already closed.")

        # 3. Outstanding invoices within the year
        outstanding_qs = Invoice.objects.filter(
            company=self.company,
            is_deleted=False,
            outstanding_balance__gt=0,
            created_at__date__gte=self.start_date,
            created_at__date__lte=self.end_date,
        ).exclude(status='CANCELLED')
        outstanding_count = outstanding_qs.count()
        from django.db.models import Sum
        outstanding_total = outstanding_qs.aggregate(
            t=Sum('outstanding_balance'))['t'] or Decimal('0')
        stats['outstanding_invoices'] = outstanding_count
        stats['outstanding_total'] = outstanding_total
        if outstanding_count > 0:
            warnings.append(
                f"{outstanding_count} invoice(s) with outstanding balance "
                f"NPR {outstanding_total:,.2f} exist in this period. "
                "These will remain as receivables after closing."
            )

        # 4. Total invoices and payments in the year
        stats['total_invoices'] = Invoice.objects.filter(
            company=self.company,
            is_deleted=False,
            created_at__date__gte=self.start_date,
            created_at__date__lte=self.end_date,
        ).count()

        stats['total_journal_entries'] = JournalEntry.objects.filter(
            company=self.company,
            date__gte=self.start_date,
            date__lte=self.end_date,
        ).count()

        return {'errors': errors, 'warnings': warnings, 'stats': stats}

    def close(self, closed_by_user):
        """
        Year-end close — two steps:

        STEP 1 — P&L Closing Entry (Income Summary)
          • Debit all REVENUE accounts (zero them out)
          • Credit all EXPENSE accounts (zero them out)
          • Net difference → Retained Earnings (EQUITY)

        STEP 2 — Carry-forward opening balances for next fiscal year
          • For every ASSET / LIABILITY / EQUITY account, calculate the
            closing balance and write it as a LedgerOpeningBalance on the
            next fiscal year (creates the next FY if it doesn't exist yet).
          • Outstanding AR (from unpaid invoices) is included automatically
            because it lives in the AR ledger account.

        After both steps the year is marked is_closed=True, is_active=False.
        """
        from django.utils import timezone as tz
        from django.db.models import Sum
        from apps.bookkeeping.models import (
            JournalEntry, JournalEntryLine, LedgerAccount, LedgerOpeningBalance
        )
        from decimal import Decimal

        if self.is_closed:
            raise ValueError("Fiscal year is already closed.")

        company = self.company

        # ── helpers ──────────────────────────────────────────────────────────

        def period_net(account):
            """
            Net movement for an account during this fiscal year.
            Returns (net_amount, dominant_type) where dominant_type is
            'DEBIT' or 'CREDIT' depending on the account's normal balance.
            """
            qs = JournalEntryLine.objects.filter(
                account=account,
                journal_entry__date__gte=self.start_date,
                journal_entry__date__lte=self.end_date,
            )
            debits  = qs.filter(entry_type='DEBIT').aggregate(s=Sum('amount'))['s']  or Decimal('0')
            credits = qs.filter(entry_type='CREDIT').aggregate(s=Sum('amount'))['s'] or Decimal('0')
            return debits, credits

        def account_closing_balance(account):
            """
            Full closing balance = opening balance (from LedgerOpeningBalance)
            + all movements during the year.
            Returns (amount, 'DEBIT'|'CREDIT').
            """
            # Opening balance for THIS fiscal year
            ob = LedgerOpeningBalance.objects.filter(
                account=account, fiscal_year=self
            ).first()
            if ob:
                ob_amount = ob.amount if ob.opening_type == 'DEBIT' else -ob.amount
            else:
                ob_amount = Decimal('0')

            debits, credits = period_net(account)
            # Net in signed form: debit = positive, credit = negative
            net = ob_amount + debits - credits

            if net >= 0:
                return abs(net), 'DEBIT'
            else:
                return abs(net), 'CREDIT'

        # ── STEP 1: P&L closing entry ─────────────────────────────────────

        revenue_accounts = LedgerAccount.objects.filter(
            company=company, account_type='REVENUE', is_deleted=False
        )
        expense_accounts = LedgerAccount.objects.filter(
            company=company, account_type='EXPENSE', is_deleted=False
        )

        closing_lines = []
        total_revenue = Decimal('0')
        total_expense = Decimal('0')

        for acc in revenue_accounts:
            debits, credits = period_net(acc)
            net_credit = credits - debits          # revenue has credit-normal balance
            if net_credit > 0:
                closing_lines.append({'account': acc, 'entry_type': 'DEBIT', 'amount': net_credit})
                total_revenue += net_credit

        for acc in expense_accounts:
            debits, credits = period_net(acc)
            net_debit = debits - credits            # expense has debit-normal balance
            if net_debit > 0:
                closing_lines.append({'account': acc, 'entry_type': 'CREDIT', 'amount': net_debit})
                total_expense += net_debit

        net_income = total_revenue - total_expense

        # Retained Earnings
        retained_earnings = LedgerAccount.objects.filter(
            company=company, name__icontains='Retained Earnings'
        ).first()
        if not retained_earnings:
            retained_earnings, _ = LedgerAccount.objects.get_or_create(
                company=company,
                name='Retained Earnings',
                defaults={'account_type': 'EQUITY', 'system_created': True}
            )

        if net_income > 0:
            closing_lines.append({
                'account': retained_earnings, 'entry_type': 'CREDIT', 'amount': net_income
            })
        elif net_income < 0:
            closing_lines.append({
                'account': retained_earnings, 'entry_type': 'DEBIT', 'amount': abs(net_income)
            })

        if closing_lines:
            entry = JournalEntry.objects.create(
                company=company,
                date=self.end_date,
                description=f"Year-End Closing Entry — FY {self.name}",
                created_by=closed_by_user,
            )
            for line in closing_lines:
                JournalEntryLine.objects.create(
                    journal_entry=entry,
                    account=line['account'],
                    entry_type=line['entry_type'],
                    amount=line['amount'],
                    narration='Year-end closing',
                )

        # ── STEP 2: Carry-forward opening balances to next fiscal year ────

        # Find or create the next fiscal year
        import datetime
        next_start = self.end_date + datetime.timedelta(days=1)
        next_fy = FiscalYear.objects.filter(
            company=company,
            start_date=next_start,
        ).first()

        if not next_fy:
            # Auto-create next FY with same duration
            duration = self.end_date - self.start_date
            next_end = next_start + duration
            try:
                import nepali_datetime as npdt
                next_start_bs = npdt.date.from_datetime_date(next_start).strftime('%Y-%m-%d')
                next_end_bs   = npdt.date.from_datetime_date(next_end).strftime('%Y-%m-%d')
            except Exception:
                next_start_bs = next_start.strftime('%Y-%m-%d')
                next_end_bs   = next_end.strftime('%Y-%m-%d')

            next_fy = FiscalYear.objects.create(
                company=company,
                start_date=next_start,
                end_date=next_end,
                start_date_bs=next_start_bs,
                end_date_bs=next_end_bs,
                is_active=True,
            )

        # Balance-sheet accounts: ASSET, LIABILITY, EQUITY
        bs_accounts = LedgerAccount.objects.filter(
            company=company,
            account_type__in=['ASSET', 'LIABILITY', 'EQUITY'],
            is_deleted=False,
        )

        for acc in bs_accounts:
            # After P&L closing, retained earnings balance has changed — recalculate
            if acc == retained_earnings:
                # Include the closing entry we just created
                amount, ob_type = account_closing_balance(acc)
                # Add net_income to retained earnings closing balance
                if net_income >= 0:
                    signed = (amount if ob_type == 'DEBIT' else -amount) + net_income
                else:
                    signed = (amount if ob_type == 'DEBIT' else -amount) + net_income
                amount = abs(signed)
                ob_type = 'CREDIT' if signed >= 0 else 'DEBIT'
            else:
                amount, ob_type = account_closing_balance(acc)

            if amount == 0:
                continue  # skip zero-balance accounts

            LedgerOpeningBalance.objects.update_or_create(
                account=acc,
                fiscal_year=next_fy,
                defaults={'opening_type': ob_type, 'amount': amount},
            )

        # ── Mark closed ───────────────────────────────────────────────────
        self.is_closed = True
        self.is_active = False
        self.closed_at = tz.now()
        self.closed_by = closed_by_user
        self.save(update_fields=['is_closed', 'is_active', 'closed_at', 'closed_by'])