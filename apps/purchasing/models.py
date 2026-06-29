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
    date = models.DateField(default=timezone.now)
    status = models.CharField(max_length=10, choices=PURCHASE_STATUS_CHOICES, default='DRAFT')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

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




