from decimal import Decimal
from apps.billing.models import VendorBill, Invoice
from apps.bookkeeping.models import JournalEntry, LedgerAccount
from apps.company.models import Company, Branch
from apps.utils.baseModel import *


class BankAccount(BaseModel):
    """
    A company bank account. Each one gets its own LedgerAccount (under the
    'Bank' parent) so payments made through it post to a distinct ledger
    instead of a single shared 'Bank' account.
    """
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='bank_accounts')
    bank_name = models.CharField(max_length=150)
    account_name = models.CharField(max_length=150, help_text="Account holder / title as per bank records.")
    account_number = models.CharField(max_length=50)
    branch_name = models.CharField(max_length=150, blank=True, default='')
    is_active = models.BooleanField(default=True)
    ledger_account = models.OneToOneField(
        LedgerAccount,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='bank_account',
        help_text="Automatically assigned ledger account for this bank account.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['company', 'account_number'], name='unique_bank_account_number_per_company'),
        ]
        ordering = ['bank_name']

    def __str__(self):
        return f"{self.bank_name} — {self.account_number}"

    def save(self, *args, **kwargs):
        if self.company is None:
            raise ValueError("Bank account must be associated with a company.")

        bank_parent, _ = LedgerAccount.objects.get_or_create(
            company=self.company,
            name='Bank',
            defaults={'account_type': 'ASSET', 'system_created': True},
        )

        if not self.ledger_account:
            account_name = f"Bank - {self.bank_name} - {self.account_number}"
            self.ledger_account = LedgerAccount.objects.create(
                company=self.company,
                name=account_name,
                account_type='ASSET',
                parent_account=bank_parent,
            )

        super().save(*args, **kwargs)


class VendorPayment(BaseModel):
    vendor_bill = models.ForeignKey(VendorBill, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateField(default=timezone.now)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    bank_account = models.ForeignKey(
        BankAccount, on_delete=models.SET_NULL, null=True, blank=True, related_name='vendor_payments',
        help_text="Bank account this payment was sent from (for BANK_TRANSFER/CHEQUE).",
    )
    transaction_id = models.CharField(max_length=100, blank=True, null=True)
    reference_number = models.CharField(max_length=100, blank=True, null=True,
                                        help_text='Auto-generated vendor payment number (VPY-...)')

    def __str__(self):
        ref = self.reference_number or str(self.id)[:8]
        return f"VPY {ref}: {self.amount} for Bill #{self.vendor_bill.bill_number}"


class Payment(BaseModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='company_payments', null=True, blank=True)
    branch = models.ForeignKey(
        Branch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payments',
        help_text='Branch this payment was recorded at (optional).',
    )
    journal_entry = models.OneToOneField(JournalEntry, on_delete=models.CASCADE, related_name='payment', null=True, blank=True)
    invoice = models.ForeignKey(Invoice, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')
    date = models.DateField(default=timezone.now)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    amount_applied = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPE_CHOICES, default='CUSTOMER')
    ledger_account = models.ForeignKey(LedgerAccount, on_delete=models.SET_NULL, null=True, blank=True,
                                     help_text="Target ledger account for non-customer payments")
    bank_account = models.ForeignKey(
        'payments.BankAccount', on_delete=models.SET_NULL, null=True, blank=True, related_name='payments',
        help_text="Bank account this payment was received into / paid from (for BANK_TRANSFER/CHEQUE).",
    )
    reference_number = models.CharField(max_length=100, blank=True, null=True, help_text="Payment/Bill number")
    description = models.TextField(blank=True, null=True)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    user_payment_destination = models.CharField(max_length=20, null=True, blank=True)
    sequence_number = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ['-date', '-created_at']
        constraints = [
            # Partial unique index: no two payments in the same company may share
            # a reference_number, but NULL reference_numbers are allowed to coexist.
            models.UniqueConstraint(
                fields=['company', 'reference_number'],
                condition=models.Q(reference_number__isnull=False),
                name='unique_payment_reference_per_company',
            ),
        ]

    def __str__(self):
        if self.reference_number:
            return f"Bill #{self.reference_number}: {self.amount} on {self.date.strftime('%Y-%m-%d')}"
        elif self.invoice and self.invoice.invoice_number:
            return f"Bill #{self.invoice.invoice_number}: {self.amount} on {self.date.strftime('%Y-%m-%d')}"
        else:
            return f"{self.get_payment_type_display()}: {self.amount} on {self.date.strftime('%Y-%m-%d')}"
    
    @property
    def payment_number(self):
        """Returns the payment number to be used as bill/invoice number"""
        if self.reference_number:
            return self.reference_number
        elif self.invoice and self.invoice.invoice_number:
            return self.invoice.invoice_number
        else:
            return f"PAY-{self.id}"
    
    @property
    def payment_source(self):
        """Returns the source account based on payment method"""
        if self.method == 'CASH':
            return 'Cash'
        elif self.method in ['BANK_TRANSFER', 'CHEQUE']:
            return 'Bank'
        return 'Other'
    
    @property
    def payment_destination(self):
        """Returns the destination account based on payment type"""
        if self.payment_type == 'CUSTOMER':
            return 'Accounts Receivable'
        elif self.payment_type == 'VENDOR':
            return 'Accounts Payable'
        elif self.payment_type == 'EXPENSE':
            return self.ledger_account.name if self.ledger_account else 'Expense'
        elif self.payment_type == 'SALARY':
            return 'Salary Expense'
        elif self.payment_type == 'OTHER' and self.ledger_account:
            return self.ledger_account.name
        return 'Other'

    @property
    def is_cancelled(self):
        return self.is_deleted

    def cancel(self, cancelled_by, reason=''):
        """
        Payments are immutable once recorded.  Cancellation soft-deletes the
        record and, if the payment was applied to an invoice, restores the
        invoice's outstanding balance.
        """
        if self.is_deleted:
            raise ValueError("Payment is already cancelled.")
        from django.db import transaction as db_transaction
        with db_transaction.atomic():
            if self.invoice and self.amount_applied:
                self.invoice.outstanding_balance += self.amount_applied
                self.invoice.save(update_fields=['outstanding_balance'])
            self.soft_delete(deleted_by=cancelled_by)


class Expense(BaseModel):
    """
    A single company expense with mandatory double-entry journal posting.
    DR: expense_account (EXPENSE)  |  CR: payment_account (ASSET – cash/bank)
    """
    EXPENSE_STATUS = [
        ('RECORDED', 'Recorded'),
        ('CANCELLED', 'Cancelled'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='expenses')
    date = models.DateField()
    title = models.CharField(max_length=255)
    expense_account = models.ForeignKey(
        LedgerAccount, on_delete=models.PROTECT,
        related_name='expense_debits',
        help_text='Expense / cost account that gets debited',
    )
    payment_account = models.ForeignKey(
        LedgerAccount, on_delete=models.PROTECT,
        related_name='expense_credits',
        help_text='Cash or bank account that gets credited',
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    reference_number = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=10, choices=EXPENSE_STATUS, default='RECORDED')
    # ForeignKey (not OneToOne) so a batch of expense lines can share one journal
    journal_entry = models.ForeignKey(
        JournalEntry, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='expenses',
    )

    class Meta:
        ordering = ['-date', '-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'reference_number'],
                condition=models.Q(reference_number__isnull=False) & ~models.Q(reference_number=''),
                name='unique_expense_reference_per_company',
            ),
        ]

    def __str__(self):
        return f"{self.title} – {self.amount} ({self.date})"
