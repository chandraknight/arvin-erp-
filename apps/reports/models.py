from django.db import models
from apps.utils.baseModel import BaseModel


class Report(models.Model):
    name = models.CharField(max_length=255)
    report_type = models.CharField(max_length=50, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        app_label = 'reports'


class AccountingPolicyNote(BaseModel):
    """
    Free-text 'Significant Accounting Policies' disclosure for the Notes to the
    Financial Statements — one editable block per company (basis of preparation,
    revenue recognition, inventory valuation method, depreciation method, etc.).
    NFRS requires this narrative disclosure; it isn't derivable from transaction
    data, so it's a plain text field the company maintains directly.
    """
    company = models.OneToOneField(
        'company.Company', on_delete=models.CASCADE, related_name='accounting_policy_note'
    )
    content = models.TextField(
        blank=True, default='',
        help_text='Significant accounting policies — basis of preparation, revenue recognition, '
                   'inventory valuation, depreciation method, etc.',
    )

    class Meta:
        app_label = 'reports'

    def __str__(self):
        return f'Accounting Policies — {self.company}'


class RelatedPartyTransaction(BaseModel):
    """NFRS-required disclosure register for transactions with related parties (directors, key management, associated entities)."""
    company = models.ForeignKey(
        'company.Company', on_delete=models.CASCADE, related_name='related_party_transactions'
    )
    fiscal_year = models.ForeignKey(
        'company.FiscalYear', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='related_party_transactions',
    )
    party_name = models.CharField(max_length=255)
    relationship = models.CharField(
        max_length=100,
        help_text='e.g. Director, Key Management Personnel, Associated Company, Shareholder',
    )
    transaction_date = models.DateField()
    nature_of_transaction = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    outstanding_balance = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text='Amount still owed to/by the related party at period end, if any.',
    )
    remarks = models.TextField(blank=True, default='')

    class Meta:
        app_label = 'reports'
        ordering = ['-transaction_date']

    def __str__(self):
        return f'{self.party_name} — {self.nature_of_transaction} ({self.amount})'


class ContingentLiability(BaseModel):
    """NFRS-required disclosure register for contingent liabilities and commitments not recognised on the Balance Sheet."""

    STATUS_CHOICES = [
        ('OPEN', 'Open / Unresolved'),
        ('RESOLVED', 'Resolved'),
        ('CRYSTALLISED', 'Crystallised (now a liability)'),
    ]

    company = models.ForeignKey(
        'company.Company', on_delete=models.CASCADE, related_name='contingent_liabilities'
    )
    fiscal_year = models.ForeignKey(
        'company.FiscalYear', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='contingent_liabilities',
    )
    description = models.CharField(max_length=255)
    nature = models.CharField(
        max_length=100,
        help_text='e.g. Pending Litigation, Guarantee Given, Letter of Credit, Tax Dispute, Bond/Surety',
    )
    estimated_amount = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text='Best estimate of the potential obligation, if quantifiable.',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='OPEN')
    as_of_date = models.DateField()
    remarks = models.TextField(blank=True, default='')

    class Meta:
        app_label = 'reports'
        ordering = ['-as_of_date']

    def __str__(self):
        return f'{self.description} ({self.get_status_display()})'


class UserReportAccess(BaseModel):
    """Company admin grants specific reports to users within the same company."""
    company = models.ForeignKey(
        'company.Company', on_delete=models.CASCADE, related_name='report_access'
    )
    user = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE, related_name='report_access'
    )
    report_name = models.CharField(max_length=100, help_text='Report slug from REPORT_REGISTRY')
    granted_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, related_name='granted_report_access'
    )

    class Meta:
        app_label = 'reports'
        unique_together = ('company', 'user', 'report_name')

    def __str__(self):
        return f'{self.user} → {self.report_name}'
