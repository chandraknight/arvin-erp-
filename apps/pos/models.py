"""
apps/pos/models.py
==================
Point of Sale — POSSale records a completed counter sale.

Design decisions
----------------
- Cart state is held in the user's session (no DB table) — fast, no migration
  needed for cart rows, and naturally isolated per browser tab.
- POSSale is created atomically at checkout alongside the Invoice + Payment.
- POSSale links back to the Invoice so all bookkeeping flows through the
  existing billing signals unchanged.
- No separate POS product or category model — reuses apps.products.
"""

from decimal import Decimal
from django.db import models
from apps.utils.baseModel import BaseModel
from apps.utils.constant import PAYMENT_METHOD_CHOICES


class Referrer(BaseModel):
    """
    A person credited with referring a POS sale (loyalty / commission tracking).
    Not necessarily a Customer — kept as its own lightweight directory so
    referrers can be typed/selected at checkout without a full customer record.
    """

    company = models.ForeignKey(
        'company.Company',
        on_delete=models.CASCADE,
        related_name='referrers',
    )
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, blank=True, default='')

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.phone})" if self.phone else self.name


class POSSale(BaseModel):
    """
    Audit record for a completed POS transaction.

    Created atomically with the Invoice and Payment at checkout.
    The Invoice carries all financial detail; POSSale adds POS-specific
    metadata (terminal, cashier, payment method used at the counter).
    """

    company = models.ForeignKey(
        'company.Company',
        on_delete=models.CASCADE,
        related_name='pos_sales',
    )
    branch = models.ForeignKey(
        'company.Branch',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='pos_sales',
    )
    invoice = models.OneToOneField(
        'billing.Invoice',
        on_delete=models.PROTECT,
        related_name='pos_sale',
    )
    customer = models.ForeignKey(
        'customers.Customer',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='pos_sales',
        help_text='Optional — walk-in sales have no customer.',
    )
    referred_by = models.ForeignKey(
        Referrer,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='referred_sales',
        help_text='Person credited with referring this sale (loyalty tracking). Not shown on the receipt.',
    )

    # Payment collected at the counter
    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        help_text='Method used at checkout (CASH, BANK_TRANSFER, etc.).',
    )
    amount_tendered = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00'),
        help_text='Amount handed over by the customer (cash sales).',
    )
    change_given = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00'),
        help_text='Change returned to the customer.',
    )

    # Totals (denormalised from Invoice for quick reporting)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    delivery_charge = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    # Optional note (e.g. "split bill", "loyalty discount applied")
    notes = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'POS Sale'
        verbose_name_plural = 'POS Sales'

    def __str__(self):
        return f"POS {self.invoice.invoice_number} — {self.total}"
