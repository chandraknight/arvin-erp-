"""
apps/orders/models.py
=====================
Order and Delivery Management module.

Enabled per-company via Company.enable_order_management = True.

Models
------
SalesOrder       — A confirmed customer order before invoicing.
                   Lifecycle: DRAFT → CONFIRMED → PROCESSING → DISPATCHED → DELIVERED → CANCELLED
SalesOrderItem   — Line items on a sales order.
DeliveryNote     — A delivery document linked to a SalesOrder.
                   Tracks what was actually dispatched and when.
DeliveryNoteItem — Line items on a delivery note (can be partial delivery).
DeliveryTracking — Real-time tracking events for a delivery (GPS/status updates).
"""

from decimal import Decimal
from apps.utils.baseModel import BaseModel
from django.db import models
from django.utils import timezone


ORDER_STATUS_CHOICES = [
    ('DRAFT',       'Draft'),
    ('CONFIRMED',   'Confirmed'),
    ('PROCESSING',  'Processing'),
    ('DISPATCHED',  'Dispatched'),
    ('DELIVERED',   'Delivered'),
    ('CANCELLED',   'Cancelled'),
    ('RETURNED',    'Returned'),
]

DELIVERY_STATUS_CHOICES = [
    ('PENDING',     'Pending'),
    ('PACKED',      'Packed'),
    ('DISPATCHED',  'Dispatched'),
    ('IN_TRANSIT',  'In Transit'),
    ('OUT_FOR_DELIVERY', 'Out for Delivery'),
    ('DELIVERED',   'Delivered'),
    ('FAILED',      'Delivery Failed'),
    ('RETURNED',    'Returned'),
    ('CANCELLED',   'Cancelled'),
]

PRIORITY_CHOICES = [
    ('LOW',    'Low'),
    ('NORMAL', 'Normal'),
    ('HIGH',   'High'),
    ('URGENT', 'Urgent'),
]


class SalesOrder(BaseModel):
    """
    A confirmed customer order. Precedes invoicing.
    Can be converted to an Invoice once fulfilled.
    """
    company = models.ForeignKey(
        'company.Company', on_delete=models.CASCADE, related_name='sales_orders'
    )
    branch = models.ForeignKey(
        'company.Branch', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sales_orders'
    )
    customer = models.ForeignKey(
        'customers.Customer', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sales_orders'
    )
    order_number = models.CharField(max_length=50, unique=True, blank=True, null=True)
    order_date = models.DateField(default=timezone.now)
    expected_delivery_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=15, choices=ORDER_STATUS_CHOICES, default='DRAFT')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='NORMAL')

    # Financials (computed from items)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    discount_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    delivery_charge = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))

    # Delivery address (can differ from customer address)
    delivery_address = models.TextField(blank=True, null=True)
    delivery_contact = models.CharField(max_length=255, blank=True, null=True)
    delivery_phone = models.CharField(max_length=20, blank=True, null=True)

    # Links
    invoice = models.OneToOneField(
        'billing.Invoice', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sales_order',
        help_text='Invoice generated from this order.'
    )
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-order_date', '-created_at']

    def __str__(self):
        return f"SO-{self.order_number or self.id}"

    @property
    def is_fully_delivered(self):
        return self.status == 'DELIVERED'

    @property
    def total_ordered_qty(self):
        return sum(i.quantity for i in self.items.all())

    @property
    def total_delivered_qty(self):
        return sum(
            i.quantity_delivered
            for dn in self.delivery_notes.filter(status='DELIVERED')
            for i in dn.items.all()
        )


class SalesOrderItem(BaseModel):
    """Line item on a sales order."""
    order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(
        'products.Product', on_delete=models.SET_NULL, null=True, blank=True
    )
    description = models.CharField(max_length=500, blank=True, null=True)
    quantity = models.DecimalField(max_digits=10, decimal_places=3, default=Decimal('1.000'))
    unit_price = models.DecimalField(max_digits=14, decimal_places=2)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        name = self.product.name if self.product else self.description
        return f"{self.quantity} × {name}"

    @property
    def line_total(self):
        base = self.quantity * self.unit_price
        discount = base * self.discount_percent / 100
        taxable = base - discount
        tax = taxable * self.tax_percent / 100
        return taxable + tax

    @property
    def quantity_delivered(self):
        return sum(
            i.quantity_delivered
            for dn in self.order.delivery_notes.filter(status='DELIVERED')
            for i in dn.items.filter(order_item=self)
        )

    @property
    def quantity_pending(self):
        return self.quantity - Decimal(str(self.quantity_delivered))


class DeliveryNote(BaseModel):
    """
    A delivery document — records what was dispatched and tracks delivery status.
    Supports partial deliveries (one order → multiple delivery notes).
    """
    company = models.ForeignKey(
        'company.Company', on_delete=models.CASCADE, related_name='delivery_notes'
    )
    sales_order = models.ForeignKey(
        SalesOrder, on_delete=models.CASCADE, related_name='delivery_notes'
    )
    delivery_number = models.CharField(max_length=50, unique=True, blank=True, null=True)
    dispatch_date = models.DateField(default=timezone.now)
    expected_delivery_date = models.DateField(null=True, blank=True)
    actual_delivery_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=DELIVERY_STATUS_CHOICES, default='PENDING')

    # Carrier / logistics
    carrier_name = models.CharField(max_length=255, blank=True, null=True)
    tracking_number = models.CharField(max_length=100, blank=True, null=True)
    vehicle_number = models.CharField(max_length=50, blank=True, null=True)
    driver_name = models.CharField(max_length=255, blank=True, null=True)
    driver_phone = models.CharField(max_length=20, blank=True, null=True)

    # Delivery address (copied from order, can be overridden)
    delivery_address = models.TextField(blank=True, null=True)
    delivery_contact = models.CharField(max_length=255, blank=True, null=True)
    delivery_phone = models.CharField(max_length=20, blank=True, null=True)

    # Proof of delivery
    received_by = models.CharField(max_length=255, blank=True, null=True)
    delivery_signature = models.ImageField(
        upload_to='delivery_signatures/', blank=True, null=True
    )
    delivery_photo = models.ImageField(
        upload_to='delivery_photos/', blank=True, null=True
    )
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-dispatch_date', '-created_at']

    def __str__(self):
        return f"DN-{self.delivery_number or self.id}"


class DeliveryNoteItem(BaseModel):
    """Line item on a delivery note — tracks actual quantity delivered."""
    delivery_note = models.ForeignKey(
        DeliveryNote, on_delete=models.CASCADE, related_name='items'
    )
    order_item = models.ForeignKey(
        SalesOrderItem, on_delete=models.CASCADE, related_name='delivery_items'
    )
    quantity_delivered = models.DecimalField(max_digits=10, decimal_places=3)
    notes = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"{self.quantity_delivered} of {self.order_item}"


class DeliveryTracking(BaseModel):
    """
    Real-time tracking events for a delivery.
    Each row is a status update / checkpoint.
    """
    delivery_note = models.ForeignKey(
        DeliveryNote, on_delete=models.CASCADE, related_name='tracking_events'
    )
    event_time = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=20, choices=DELIVERY_STATUS_CHOICES)
    location = models.CharField(max_length=500, blank=True, null=True,
                                help_text='Location description or GPS coordinates.')
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    notes = models.CharField(max_length=500, blank=True, null=True)
    updated_by_name = models.CharField(max_length=255, blank=True, null=True,
                                       help_text='Name of person who logged this event.')

    class Meta:
        ordering = ['-event_time']

    def __str__(self):
        return f"{self.delivery_note} — {self.status} at {self.event_time}"
