from apps.company.models import Company, FiscalYear
from apps.utils.baseModel import *
from django.core.cache import cache

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

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self._invalidate_entry_cache()

    def delete(self, *args, **kwargs):
        self._invalidate_entry_cache()
        super().delete(*args, **kwargs)

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