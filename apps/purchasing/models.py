from apps.company.models import Company, Branch
from apps.products.models import Product
from apps.vendors.models import Vendor
from apps.bookkeeping.models import LedgerAccount
from apps.utils.baseModel import *
from apps.utils.constant import *


class PurchaseOrder(BaseModel):
    company = models.ForeignKey(Company, on_delete=models.SET_NULL, related_name='purchase_orders_company', null=True)
    branch = models.ForeignKey(
        Branch, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='purchase_orders',
        help_text='Branch this PO was raised from (optional).',
    )
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='purchase_orders')
    purchase_order_number = models.CharField(max_length=50, unique=True, blank=True, null=True)
    sequence_number = models.PositiveIntegerField(null=True, blank=True)
    fiscal_year = models.ForeignKey(
        'company.FiscalYear',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='purchase_orders',
        db_constraint=False,
    )
    date = models.DateField(default=timezone.now)
    status = models.CharField(max_length=10, choices=PURCHASE_STATUS_CHOICES, default='SENT')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'fiscal_year', 'sequence_number'],
                name='unique_po_seq_per_company_fy',
                condition=models.Q(sequence_number__isnull=False),
            )
        ]

    def __str__(self):
        return f"{self.purchase_order_number if self.purchase_order_number else self.id} from {self.vendor.name}"


class PurchaseOrderItem(BaseModel):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items')
    item_type = models.CharField(
        max_length=10,
        choices=PO_ITEM_TYPE_CHOICES,
        default='STOCK',
        help_text="Stock item updates inventory on receive; Service and Non-Stock do not."
    )
    # Stock items reference a product; service/non-stock use description instead
    product = models.ForeignKey(Product, on_delete=models.CASCADE, null=True, blank=True)
    description = models.CharField(
        max_length=255, blank=True, null=True,
        help_text="Required for Service and Non-Stock items."
    )
    expense_account = models.ForeignKey(
        LedgerAccount,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='po_items',
        help_text="Expense/asset account to debit for Service and Non-Stock lines."
    )
    hscode = models.CharField(max_length=50, blank=True, null=True, verbose_name="HS Code")
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)

    purchase_unit = models.ForeignKey(
        'products.UnitOfMeasure', on_delete=models.PROTECT,
        null=True, blank=True, related_name='po_item_purchase_unit',
        help_text="Unit this line was purchased in. Defaults to the product's purchase_unit if not set.",
    )
    conversion_unit = models.ForeignKey(
        'products.UnitOfMeasure', on_delete=models.PROTECT,
        null=True, blank=True, related_name='po_item_conversion_unit',
        help_text="Unit this line converts into for stock keeping. Defaults to the product's default_unit if not set.",
    )
    conversion_factor_override = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True,
        help_text="Overrides the product's conversion_factor for this line only, if set.",
    )

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.item_type == 'STOCK' and not self.product:
            raise ValidationError("A product is required for Stock items.")
        if self.item_type in ('SERVICE', 'NON_STOCK') and not self.description:
            raise ValidationError("A description is required for Service and Non-Stock items.")

    @property
    def line_name(self):
        if self.product:
            return self.product.name
        return self.description or '—'

    def __str__(self):
        po_ref = self.purchase_order.purchase_order_number or str(self.purchase_order.id)
        return f"{self.quantity} x {self.line_name} on {po_ref}"




