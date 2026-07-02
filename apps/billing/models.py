from .services.all_services import *
from apps.utils.baseModel import *
from apps.company.models import Company, Branch
from apps.customers.models import Customer
from apps.products.models import Product, Package
from apps.bookkeeping.models import JournalEntry, LedgerAccount
from apps.purchasing.models import PurchaseOrder
from apps.vendors.models import Vendor
from decimal import Decimal


INVOICE_STATUS_CHOICES = [
    ('DRAFT',     'Draft'),
    ('ISSUED',    'Issued'),
    ('ESTIMATE',  'Estimate'),
    ('CANCELLED', 'Cancelled'),
]


class Invoice(BaseModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='invoices', null=True, blank=True)
    branch = models.ForeignKey(
        Branch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='invoices',
        help_text='Branch this invoice was raised from (optional).',
    )
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True)
    invoice_number = models.CharField(max_length=50, unique=True, blank=True, null=True)
    transaction_date = models.DateField(default=timezone.now, help_text='Date of the invoice transaction')
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text='Total before discount and tax')
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text='Total discount amount')
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'), help_text='Discount percentage')
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text='Tax amount')
    total = models.DecimalField(max_digits=10, decimal_places=2, help_text='Final total after discount and tax')
    outstanding_balance = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    due_date = models.DateField(null=True, blank=True)
    due_date_bs = models.CharField(max_length=50, null=True, blank=True)
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'), help_text='Tax percentage applied')
    sequence_number = models.PositiveIntegerField(null=True, blank=True)
    fiscal_year = models.ForeignKey(
        'company.FiscalYear',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='invoices',
        db_constraint=False,
    )
    status = models.CharField(
        max_length=10,
        choices=INVOICE_STATUS_CHOICES,
        default='DRAFT',
        help_text='DRAFT = editable; ISSUED = locked; CANCELLED = voided.',
    )
    reference_number = models.CharField(
        max_length=100, blank=True, null=True,
        help_text='Optional external reference (customer PO#, contract#, cheque#, etc.).',
    )
    cancellation_reason = models.TextField(
        blank=True, null=True,
        help_text='Required when cancelling an issued invoice.',
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'fiscal_year', 'sequence_number'],
                name='unique_invoice_seq_per_company_fy',
                condition=models.Q(sequence_number__isnull=False),
            )
        ]
        indexes = [
            models.Index(fields=['company', 'status', 'outstanding_balance'], name='invoice_company_status_idx'),
            models.Index(fields=['company', 'transaction_date'], name='invoice_company_date_idx'),
        ]

    def __str__(self):
        return f"Invoice #{self.invoice_number if self.invoice_number else self.id}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    @property
    def is_paid(self):
        return self.outstanding_balance == 0

    @property
    def is_issued(self):
        return self.status == 'ISSUED'

    @property
    def is_cancelled(self):
        return self.status == 'CANCELLED'

    @property
    def is_locked(self):
        """True when the invoice must not be edited or deleted."""
        return self.status in ('ISSUED', 'CANCELLED')

    @property
    def is_estimate(self):
        return self.status == 'ESTIMATE'

    def cancel(self, cancelled_by, reason=''):
        """
        Void an issued invoice.  Sets status=CANCELLED and records the reason.
        Does NOT reverse journal entries — that is handled by a CreditNote.
        """
        if self.status == 'CANCELLED':
            raise ValueError("Invoice is already cancelled.")
        self.status = 'CANCELLED'
        self.cancellation_reason = reason
        self.updated_by = cancelled_by
        self.save(update_fields=['status', 'cancellation_reason', 'updated_by', 'updated_at'])

INVOICE_ITEM_TYPE_CHOICES = [
    ('product', 'Item'),
    ('service', 'Service'),
    ('package', 'Package'),
    ('other', 'Other'),
]

class InvoiceItem(models.Model):
    invoice = models.ForeignKey(Invoice, related_name='items', on_delete=models.CASCADE)
    item_type = models.CharField(
        max_length=10, choices=INVOICE_ITEM_TYPE_CHOICES, default='product',
    )
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.SET_NULL)
    package = models.ForeignKey(Package, null=True, blank=True, on_delete=models.SET_NULL)
    description = models.CharField(max_length=255, blank=True, null=True)
    hscode = models.CharField(max_length=50, blank=True, null=True, verbose_name="HS Code")
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'), help_text='Item discount percentage')
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text='Item discount amount')

    @property
    def total_price(self):
        base = Decimal(self.quantity) * self.price
        if self.discount_amount > 0:
            return max(Decimal('0.00'), (base - self.discount_amount).quantize(Decimal('0.01')))
        elif self.discount_percent > 0:
            discount = (base * self.discount_percent / Decimal('100')).quantize(Decimal('0.01'))
            return max(Decimal('0.00'), (base - discount).quantize(Decimal('0.01')))
        return base.quantize(Decimal('0.01'))

    def _sync_invoice_totals(self, invoice):
        calculate_total(invoice)
        # Use queryset update so Django's post_save signal is NOT fired.
        # Firing post_save here triggers post_invoice_journal multiple times
        # within the same atomic block, causing FK violations in journalentryline.
        Invoice.objects.filter(pk=invoice.pk).update(
            subtotal=invoice.subtotal,
            discount_amount=invoice.discount_amount,
            tax_amount=invoice.tax_amount,
            total=invoice.total,
            outstanding_balance=Decimal('0.00') if invoice.status == 'ESTIMATE' else invoice.total,
        )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self._sync_invoice_totals(self.invoice)

    def delete(self, *args, **kwargs):
        invoice = self.invoice
        super().delete(*args, **kwargs)
        self._sync_invoice_totals(invoice)

    def __str__(self):
        item_name = self.product.name if self.product else (self.package.name if self.package else self.description or "Unknown Item")
        return f"{self.quantity}x {item_name} @ ${self.price:.2f} on Invoice #{self.invoice.id}"

class CreditNote(BaseModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='credit_notes_company', null=True, blank=True)
    invoice = models.ForeignKey(Invoice, on_delete=models.SET_NULL, null=True, blank=True, related_name='credit_notes')
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True)
    credit_note_number = models.CharField(max_length=50, unique=True, blank=True, null=True)
    status = models.CharField(max_length=10, choices=DEBIT_CREDIT_NOTE_STATUS_CHOICES, default='DRAFT')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    tax_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('0.00'),
        help_text='VAT/tax portion of this note. Pro-rated from the linked invoice when available.',
    )
    reason = models.TextField(blank=True, null=True)
    journal_entry = models.OneToOneField(JournalEntry, on_delete=models.SET_NULL, null=True, blank=True, related_name='credit_note')

    def __str__(self):
        return f"{self.credit_note_number if self.credit_note_number else self.id}"

class DebitNote(BaseModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='debit_notes_company', null=True, blank=True)
    invoice = models.ForeignKey(Invoice, on_delete=models.SET_NULL, null=True, blank=True, related_name='debit_notes')
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True)
    debit_note_number = models.CharField(max_length=50, unique=True, blank=True, null=True)
    status = models.CharField(max_length=10, choices=DEBIT_CREDIT_NOTE_STATUS_CHOICES, default='DRAFT')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    tax_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('0.00'),
        help_text='VAT/tax portion of this note. Pro-rated from the linked invoice when available.',
    )
    reason = models.TextField(blank=True, null=True)
    journal_entry = models.OneToOneField(JournalEntry, on_delete=models.SET_NULL, null=True, blank=True, related_name='debit_note')

    def __str__(self):
        return f"{self.debit_note_number if self.debit_note_number else self.id}"

class VendorBill(models.Model):
    # Integer PK intentionally kept — UUID migration requires FK backfill on VendorBillItem + VendorPayment
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_vendorbill',
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='updated_vendorbill',
    )
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='deleted_vendorbill',
    )

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name='vendor_bills',
        null=True, blank=True,
        help_text='Company this bill belongs to.',
    )
    branch = models.ForeignKey(
        Branch, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='vendor_bills',
        help_text='Branch this bill was recorded at (optional).',
    )
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='vendor_bills')
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.SET_NULL, null=True, blank=True, related_name='vendor_bills')
    bill_number = models.CharField(max_length=100, unique=True)
    bill_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    tax_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0.00'),
        help_text='VAT/tax rate applied to this bill (e.g. 13.00).',
    )
    tax_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('0.00'),
        help_text='VAT/tax amount charged on this bill.',
    )
    status = models.CharField(max_length=10, choices=VENDOR_BILL_STATUS_CHOICES, default='UNPAID')
    cancellation_reason = models.TextField(
        blank=True, null=True,
        help_text='Required when cancelling a vendor bill.',
    )

    objects = models.Manager()
    active_objects = SoftDeletedManager()

    def __str__(self):
        return f"{self.bill_number} from {self.vendor.name}"

    @property
    def is_locked(self):
        return self.status in ('PAID', 'CANCELLED')

    def soft_delete(self, deleted_by=None):
        self.is_deleted = True
        self.deleted_by = deleted_by
        self.save(update_fields=['is_deleted', 'deleted_by', 'updated_at'])

    def cancel(self, cancelled_by, reason=''):
        if self.status == 'CANCELLED':
            raise ValueError("Vendor bill is already cancelled.")
        self.status = 'CANCELLED'
        self.cancellation_reason = reason
        self.updated_by = cancelled_by
        self.save(update_fields=['status', 'cancellation_reason', 'updated_by', 'updated_at'])

class VendorBillItem(BaseModel):
    vendor_bill = models.ForeignKey(VendorBill, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.SET_NULL)
    description = models.CharField(max_length=255, blank=True, null=True)
    hscode = models.CharField(max_length=50, blank=True, null=True, verbose_name="HS Code")
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    debit_account = models.ForeignKey(LedgerAccount, on_delete=models.PROTECT)

    @property
    def total_price(self):
        return (self.quantity * self.price).quantize(Decimal('0.01'))

    def __str__(self):
        item_name = self.product.name if self.product else self.description
        return f"{self.quantity} x {item_name} @ ${self.price:.2f}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        update_vendor_bill_total(self.vendor_bill)


CBMS_SUBMISSION_TYPE = [
    ('BILL',        'Bill'),
    ('BILL_RETURN', 'Bill Return (Credit Note)'),
]

CBMS_RESPONSE_CODES = {
    '100': 'API credentials do not match',
    '101': 'Bill already exists / does not exist',
    '102': 'Exception while saving — check model fields',
    '103': 'Unknown exception — check API URL and fields',
    '104': 'Model invalid',
    '200': 'Success',
}


class CBMSSubmission(BaseModel):
    """Audit log for every IRD CBMS API call. Never deleted — permanent record."""

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name='cbms_submissions'
    )
    invoice = models.ForeignKey(
        Invoice, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cbms_submissions'
    )
    credit_note = models.ForeignKey(
        CreditNote, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cbms_submissions'
    )
    submission_type = models.CharField(
        max_length=15, choices=CBMS_SUBMISSION_TYPE, default='BILL'
    )
    payload = models.JSONField(help_text='Payload sent to CBMS (password redacted).')
    response_code = models.CharField(max_length=10, blank=True, null=True)
    response_body = models.TextField(blank=True, null=True)
    success = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(auto_now_add=True)
    error_detail = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-submitted_at']

    def __str__(self):
        ref = self.invoice.invoice_number if self.invoice else (
            self.credit_note.credit_note_number if self.credit_note else '?'
        )
        return f"CBMS {self.submission_type} {ref} [{self.response_code}]"
