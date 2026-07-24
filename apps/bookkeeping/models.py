from apps.company.models import Company, FiscalYear
from apps.utils.baseModel import *
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from decimal import Decimal

BALANCE_TOLERANCE = Decimal('0.01')

class LedgerAccount(BaseModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='ledger_accounts', null=True, blank=True)
    name = models.CharField(max_length=255)
    account_type = models.CharField(max_length=10, choices=LEGENDRE_ACCOUNT_TYPES)
    code = models.CharField(max_length=50, blank=True, null=True)
    system_created = models.BooleanField(default=False)
    is_current = models.BooleanField(
        default=True,
        help_text=(
            'NFRS: True = Current asset/liability (≤12 months). '
            'False = Non-current. Used for Balance Sheet classification.'
        ),
    )
    # For hierarchical accounts
    parent_account = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='child_accounts',
        help_text="The parent ledger account if this is a sub-account (e.g., Accounts Receivable for a customer)"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['company', 'name'], name='unique_ledgeraccount_name_per_company'),
            models.UniqueConstraint(fields=['company', 'code'], name='unique_ledgeraccount_code_per_company')
        ]

    def __str__(self):
        return self.name



class JournalEntry(BaseModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='journal_entries', null=True, blank=True)
    date = models.DateField(default=timezone.now)
    description = models.CharField(max_length=700, blank=True, null=True)

    # Reversal fields — once posted, entries are never deleted; reversals create a mirror entry
    is_reversed = models.BooleanField(default=False)
    reversal_of = models.ForeignKey(
        'self', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='reversals',
        help_text='Points to the original entry this entry reverses.',
    )
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_reason = models.CharField(max_length=500, blank=True)

    def __str__(self):
        return f"Entry on {self.date.strftime('%Y-%m-%d')}: {self.description[:50]}..."

    def _assert_period_open(self):
        """
        NFRS requires closed periods to be immutable. Block any journal entry
        dated inside a fiscal year that has already been closed (FiscalYear.close()
        sets is_closed=True only after posting its own closing entry, so the
        closing entry itself is unaffected by this check).
        """
        if not self.company_id or not self.date:
            return
        closed_fy = FiscalYear.objects.filter(
            company_id=self.company_id,
            is_closed=True,
            start_date__lte=self.date,
            end_date__gte=self.date,
        ).first()
        if closed_fy:
            raise ValidationError(
                f"Cannot post journal entry dated {self.date}: fiscal year "
                f"'{closed_fy.name}' covering this date is closed."
            )

    def save(self, *args, **kwargs):
        self._assert_period_open()
        super().save(*args, **kwargs)

    @property
    def debit_total(self):
        cache_key = f'journal_entry_{self.id}_debit_total'
        total = cache.get(cache_key)
        if total is None:
            from django.db.models import Sum
            total = self.lines.filter(entry_type='DEBIT').aggregate(t=Sum('amount'))['t'] or 0
            cache.set(cache_key, total, 60 * 5)
        return total

    @property
    def credit_total(self):
        cache_key = f'journal_entry_{self.id}_credit_total'
        total = cache.get(cache_key)
        if total is None:
            from django.db.models import Sum
            total = self.lines.filter(entry_type='CREDIT').aggregate(t=Sum('amount'))['t'] or 0
            cache.set(cache_key, total, 60 * 5)
        return total

    @property
    def is_balanced(self):
        return self.debit_total == self.credit_total

    @property
    def balance_difference(self):
        return self.debit_total - self.credit_total


def assert_balanced(entry):
    """
    Raise ValueError if the given JournalEntry's debit and credit totals
    don't match within BALANCE_TOLERANCE. ORM-level backstop used by callers
    that build entries outside post_journal_entry (e.g. bulk_create), and by
    non-Postgres backends where the DB-level trigger isn't present.
    """
    debit = entry.debit_total
    credit = entry.credit_total
    if abs(debit - credit) > BALANCE_TOLERANCE:
        raise ValueError(
            f"Unbalanced journal entry (id={entry.pk}): debit={debit} credit={credit}."
        )


def post_journal_entry(company, date, description, lines, created_by=None):
    """
    Single, safe entry point for posting a balanced double-entry transaction.

    `lines` is a list of dicts: {'account': LedgerAccount, 'entry_type': 'DEBIT'|'CREDIT', 'amount': Decimal, 'narration': str (optional)}.

    Guarantees, so callers don't have to re-implement double-entry safety themselves:
      - the whole operation (entry + all lines) is atomic — no half-posted entries on failure
      - lines are created via .create() (never bulk_create), so each line runs
        JournalEntryLine.save() -> _assert_entry_balanced(), not just the Postgres trigger
      - an explicit pre-flight balance check gives a clear error before touching the DB
      - JournalEntry.save() itself blocks posting into a closed fiscal year
    """
    debit = sum((l['amount'] for l in lines if l['entry_type'] == 'DEBIT'), Decimal('0'))
    credit = sum((l['amount'] for l in lines if l['entry_type'] == 'CREDIT'), Decimal('0'))
    if len(lines) < 2:
        raise ValidationError("A journal entry requires at least two lines (double-entry).")
    if abs(debit - credit) > BALANCE_TOLERANCE:
        raise ValidationError(
            f"Cannot post unbalanced journal entry: debit={debit} credit={credit} "
            f"(description={description!r})."
        )

    with transaction.atomic():
        entry = JournalEntry.objects.create(
            company=company, date=date, description=description, created_by=created_by,
        )
        for line in lines:
            JournalEntryLine.objects.create(
                journal_entry=entry,
                account=line['account'],
                entry_type=line['entry_type'],
                amount=line['amount'],
                narration=line.get('narration', ''),
            )
    return entry


class JournalEntryLine(BaseModel):
    journal_entry = models.ForeignKey(JournalEntry, related_name='lines', on_delete=models.CASCADE)
    account = models.ForeignKey(LedgerAccount, on_delete=models.CASCADE)
    entry_type = models.CharField(max_length=10, choices=JOURNAL_ENTRY_TYPES)
    narration = models.CharField(max_length=250, blank=True, null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.entry_type} {self.amount} to {self.account.name} for {self.journal_entry.description[:50]}..."

    def _invalidate_entry_cache(self):
        jeid = self.journal_entry_id
        cache.delete(f'journal_entry_{jeid}_debit_total')
        cache.delete(f'journal_entry_{jeid}_credit_total')

    def _assert_entry_balanced(self):
        """
        Python-level mirror of the Postgres trg_journal_entry_balance_check
        trigger (apps/bookkeeping/migrations/0009_...). The trigger is the
        primary guard on Postgres, but this backs it up on any backend
        (e.g. SQLite in tests) and also covers hard-deletes, which the
        trigger (INSERT/UPDATE only) does not.
        """
        from django.db.models import Sum
        lines = JournalEntryLine.objects.filter(journal_entry_id=self.journal_entry_id)
        if lines.count() < 2:
            return
        debit = lines.filter(entry_type='DEBIT').aggregate(t=Sum('amount'))['t'] or Decimal('0')
        credit = lines.filter(entry_type='CREDIT').aggregate(t=Sum('amount'))['t'] or Decimal('0')
        if abs(debit - credit) > BALANCE_TOLERANCE:
            raise ValidationError(
                f"Journal entry {self.journal_entry_id} is unbalanced: "
                f"debit={debit} credit={credit}. Double-entry requires debit == credit."
            )

    def save(self, *args, **kwargs):
        with transaction.atomic():
            super().save(*args, **kwargs)
            self._invalidate_entry_cache()
            self._assert_entry_balanced()

    def delete(self, *args, **kwargs):
        with transaction.atomic():
            jeid = self.journal_entry_id
            super().delete(*args, **kwargs)
            self._invalidate_entry_cache()
            remaining = JournalEntryLine.objects.filter(journal_entry_id=jeid)
            remaining_count = remaining.count()
            if remaining_count == 1:
                # A single leftover line can never balance (amount > 0 by
                # constraint), so this is always an invalid double-entry state.
                raise ValidationError(
                    f"Cannot delete this line: journal entry {jeid} would be left "
                    f"with a single unmatched line, which is never balanced."
                )
            if remaining_count >= 2:
                from django.db.models import Sum
                debit = remaining.filter(entry_type='DEBIT').aggregate(t=Sum('amount'))['t'] or Decimal('0')
                credit = remaining.filter(entry_type='CREDIT').aggregate(t=Sum('amount'))['t'] or Decimal('0')
                if abs(debit - credit) > BALANCE_TOLERANCE:
                    raise ValidationError(
                        f"Cannot delete this line: journal entry {jeid} would become "
                        f"unbalanced (debit={debit} credit={credit})."
                    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="amount_positive"
            )
        ]
        indexes = [
            models.Index(fields=['account', 'entry_type'], name='jel_account_type_idx'),
            models.Index(fields=['journal_entry', 'entry_type'], name='jel_entry_type_idx'),
        ]



def reverse_journal(original: 'JournalEntry', reason: str = '', user=None) -> 'JournalEntry':
    """
    Accounting-safe reversal: creates a mirror entry with flipped DEBIT/CREDIT
    and marks the original as reversed.  The original is NEVER deleted.

    Returns the new reversal JournalEntry.
    """
    from django.utils import timezone as tz

    if original.is_reversed:
        # Already reversed — return the existing reversal to avoid double-reversals
        existing = original.reversals.filter(is_deleted=False).first()
        if existing:
            return existing

    flip = {'DEBIT': 'CREDIT', 'CREDIT': 'DEBIT'}
    original_lines = list(original.lines.filter(is_deleted=False))
    if not original_lines:
        # Nothing to reverse — mark original as reversed so callers don't retry
        original.is_reversed = True
        original.reversed_at = tz.now()
        original.reversed_reason = reason or 'System reversal (no lines)'
        original.save(update_fields=['is_reversed', 'reversed_at', 'reversed_reason'])
        return original

    reversal = JournalEntry.objects.create(
        company=original.company,
        date=tz.now().date(),
        description=f"REVERSAL: {original.description}",
        reversal_of=original,
    )
    lines = [
        JournalEntryLine(
            journal_entry=reversal,
            account=line.account,
            entry_type=flip[line.entry_type],
            amount=line.amount,
            narration=f"Reversal of line {line.pk}",
        )
        for line in original_lines
    ]
    JournalEntryLine.objects.bulk_create(lines)

    # bulk_create bypasses JournalEntryLine.save(), so _assert_entry_balanced()
    # never ran for these lines — the Postgres trigger backs it up in prod,
    # but SQLite (tests) has no such trigger, so verify explicitly here too.
    debit = sum(l.amount for l in lines if l.entry_type == 'DEBIT')
    credit = sum(l.amount for l in lines if l.entry_type == 'CREDIT')
    if abs(debit - credit) > BALANCE_TOLERANCE:
        raise ValidationError(
            f"Reversal of journal entry {original.pk} is unbalanced: "
            f"debit={debit} credit={credit}."
        )

    original.is_reversed = True
    original.reversed_at = tz.now()
    original.reversed_reason = reason or 'System reversal'
    original.save(update_fields=['is_reversed', 'reversed_at', 'reversed_reason'])

    # Write to ActivityLog
    try:
        from apps.activity_log.models import ActivityLog
        ActivityLog.log(
            user=user,
            action=ActivityLog.ACTION_REVERSE,
            instance=original,
            object_repr=str(original),
            changes={
                'is_reversed': {'old': False, 'new': True},
                'reversal_entry_id': str(reversal.pk),
                'reason': reason,
            },
            extra={'reversal_entry_id': str(reversal.pk)},
        )
    except Exception:
        pass  # never let audit failure break accounting

    return reversal


class LedgerOpeningBalance(models.Model):
    account = models.ForeignKey(LedgerAccount, on_delete=models.CASCADE, related_name='opening_balances')
    fiscal_year = models.ForeignKey(FiscalYear, on_delete=models.CASCADE)
    opening_type = models.CharField(max_length=10, choices=JOURNAL_ENTRY_TYPES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        unique_together = ('account', 'fiscal_year')

    @classmethod
    def assert_fiscal_year_balanced(cls, fiscal_year):
        """
        Opening balances seed the trial balance for a fiscal year, so their
        DEBIT and CREDIT totals must net to zero just like any posted journal
        entry — an unbalanced seed silently breaks every report built on top
        of it (trial balance, balance sheet) with no journal entry to blame.
        """
        from django.db.models import Sum
        rows = cls.objects.filter(fiscal_year=fiscal_year)
        debit = rows.filter(opening_type='DEBIT').aggregate(t=Sum('amount'))['t'] or Decimal('0')
        credit = rows.filter(opening_type='CREDIT').aggregate(t=Sum('amount'))['t'] or Decimal('0')
        if abs(debit - credit) > BALANCE_TOLERANCE:
            raise ValidationError(
                f"Opening balances for fiscal year '{fiscal_year}' are unbalanced: "
                f"debit={debit} credit={credit}. Double-entry requires debit == credit."
            )


# ─── NFRS 13 — Property, Plant and Equipment ─────────────────────────────────

DEPRECIATION_METHOD_CHOICES = [
    ('SLM', 'Straight-Line Method (SLM)'),
    ('WDV', 'Written Down Value / Diminishing Balance (WDV)'),
]

ASSET_STATUS_CHOICES = [
    ('ACTIVE',    'Active'),
    ('DISPOSED',  'Disposed'),
    ('IMPAIRED',  'Impaired'),
]


class FixedAsset(BaseModel):
    """
    NFRS 13 (IAS 16) — Property, Plant and Equipment register.

    Each asset tracks its own cost, useful life, and accumulated depreciation.
    Depreciation journals are posted via FixedAssetService.post_depreciation().
    """
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name='fixed_assets'
    )
    name = models.CharField(max_length=255)
    asset_code = models.CharField(max_length=50, blank=True, null=True, unique=True)
    description = models.TextField(blank=True, null=True)
    category = models.CharField(max_length=100, blank=True, null=True,
        help_text='e.g. Furniture, Computers, Vehicles, Buildings')

    # Cost model (NFRS 13 para 30)
    cost = models.DecimalField(max_digits=14, decimal_places=2,
        help_text='Original acquisition cost including all costs to bring asset to working condition')
    residual_value = models.DecimalField(max_digits=14, decimal_places=2, default=0,
        help_text='Estimated scrap/salvage value at end of useful life')
    useful_life_years = models.PositiveSmallIntegerField(
        help_text='Estimated useful life in years')
    depreciation_method = models.CharField(
        max_length=3, choices=DEPRECIATION_METHOD_CHOICES, default='SLM')
    depreciation_rate = models.DecimalField(
        max_digits=5, decimal_places=2, blank=True, null=True,
        help_text='Annual rate % for WDV method. Leave blank for SLM (auto-computed).')

    acquisition_date = models.DateField(help_text='Date asset was put into service')
    disposal_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=ASSET_STATUS_CHOICES, default='ACTIVE')

    # Accumulated depreciation — updated each time a depreciation journal is posted
    accumulated_depreciation = models.DecimalField(
        max_digits=14, decimal_places=2, default=0)

    # Ledger accounts for this asset (auto-created from defaults if blank)
    asset_account = models.ForeignKey(
        LedgerAccount, on_delete=models.PROTECT,
        related_name='fixed_assets_asset', null=True, blank=True,
        help_text='Asset cost account (ASSET type)')
    accumulated_dep_account = models.ForeignKey(
        LedgerAccount, on_delete=models.PROTECT,
        related_name='fixed_assets_accum_dep', null=True, blank=True,
        help_text='Accumulated depreciation contra-asset account')
    depreciation_expense_account = models.ForeignKey(
        LedgerAccount, on_delete=models.PROTECT,
        related_name='fixed_assets_dep_expense', null=True, blank=True,
        help_text='Depreciation expense account (EXPENSE type)')

    class Meta:
        ordering = ['category', 'name']

    def __str__(self):
        return f"{self.name} ({self.asset_code or self.id})"

    @property
    def net_book_value(self):
        return self.cost - self.accumulated_depreciation

    @property
    def depreciable_amount(self):
        return self.cost - self.residual_value

    def annual_depreciation(self):
        from decimal import Decimal
        if self.depreciation_method == 'SLM':
            if self.useful_life_years > 0:
                return (self.depreciable_amount / self.useful_life_years).quantize(Decimal('0.01'))
            return Decimal('0.00')
        else:  # WDV
            rate = self.depreciation_rate or Decimal('0.00')
            return (self.net_book_value * rate / Decimal('100')).quantize(Decimal('0.01'))


class FixedAssetDepreciationLog(BaseModel):
    """One row per depreciation journal posting — audit trail for NFRS 13."""
    asset = models.ForeignKey(
        FixedAsset, on_delete=models.CASCADE, related_name='depreciation_logs')
    journal_entry = models.ForeignKey(
        JournalEntry, on_delete=models.SET_NULL, null=True, blank=True)
    period_start = models.DateField()
    period_end = models.DateField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        ordering = ['-period_end']

    def __str__(self):
        return f"Depreciation {self.amount} for {self.asset.name} ({self.period_end})"