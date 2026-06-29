"""
apps/restaurant/models.py
=========================
Restaurant module — Table Management, KOT/BOT, Dining Orders, Printer Stations.

Enabled per-company via Company.enable_restaurant = True.

Models
------
TableSection     — Floor / area grouping (e.g. Ground Floor, Rooftop, Bar).
RestaurantTable  — A physical table with status and capacity.
PrinterStation   — Network printer config for KOT, BOT, or Bill printing.
DiningOrder      — An open order tied to a table (replaces SalesOrder for dine-in).
DiningOrderItem  — Line item with item_type (FOOD/BEVERAGE) and print-tracking flags.
PrintJob         — Audit trail of every KOT/BOT/Bill print request.
"""

from decimal import Decimal
from django.db import models
from django.utils import timezone
from apps.utils.baseModel import BaseModel


# ── Choices ───────────────────────────────────────────────────────────────────

TABLE_STATUS_CHOICES = [
    ('AVAILABLE', 'Available'),
    ('OCCUPIED',  'Occupied'),
    ('RESERVED',  'Reserved'),
    ('CLEANING',  'Cleaning'),
]

ORDER_STATUS_CHOICES = [
    ('OPEN',      'Open'),
    ('KOT_SENT',  'KOT Sent'),
    ('BOT_SENT',  'BOT Sent'),
    ('BILLED',    'Billed'),
    ('PAID',      'Paid'),
    ('CANCELLED', 'Cancelled'),
]

ITEM_TYPE_CHOICES = [
    ('FOOD',      'Food'),
    ('BEVERAGE',  'Beverage'),
]

ITEM_STATUS_CHOICES = [
    ('PENDING',    'Pending'),
    ('PREPARING',  'Preparing'),
    ('READY',      'Ready'),
    ('SERVED',     'Served'),
    ('CANCELLED',  'Cancelled'),
]

PRINTER_TYPE_CHOICES = [
    ('KOT',  'Kitchen Order Ticket (KOT)'),
    ('BOT',  'Bar Order Ticket (BOT)'),
    ('BILL', 'Bill / Receipt Printer'),
]

PRINT_JOB_STATUS_CHOICES = [
    ('QUEUED',  'Queued'),
    ('SENT',    'Sent'),
    ('FAILED',  'Failed'),
]


# ── Models ────────────────────────────────────────────────────────────────────

class TableSection(BaseModel):
    """
    A named area or floor within the restaurant.
    e.g. Ground Floor, Rooftop, Bar, Private Dining.
    """
    company = models.ForeignKey(
        'company.Company', on_delete=models.CASCADE, related_name='table_sections'
    )
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=255, blank=True, null=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'name']
        unique_together = ('company', 'name')

    def __str__(self):
        return self.name


class RestaurantTable(BaseModel):
    """
    A physical table in the restaurant.
    Status drives the floor-plan colour coding.
    """
    company = models.ForeignKey(
        'company.Company', on_delete=models.CASCADE, related_name='restaurant_tables'
    )
    section = models.ForeignKey(
        TableSection, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='tables'
    )
    table_number = models.CharField(max_length=20)
    display_name = models.CharField(
        max_length=50, blank=True, null=True,
        help_text='Optional friendly name, e.g. "Window Table".'
    )
    capacity = models.PositiveSmallIntegerField(default=4)
    status = models.CharField(
        max_length=10, choices=TABLE_STATUS_CHOICES, default='AVAILABLE'
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['section__sort_order', 'table_number']
        unique_together = ('company', 'table_number')

    def __str__(self):
        label = self.display_name or f"Table {self.table_number}"
        return f"{label} ({self.get_status_display()})"

    @property
    def label(self):
        return self.display_name or f"Table {self.table_number}"

    @property
    def active_order(self):
        """Return the current open/KOT/BOT order for this table, or None."""
        return self.dining_orders.filter(
            status__in=['OPEN', 'KOT_SENT', 'BOT_SENT', 'BILLED']
        ).first()


class PrinterStation(BaseModel):
    """
    A network-connected printer used for KOT, BOT, or Bill printing.
    The ERP sends a print job record; the actual printing is handled by
    a local print agent that polls for QUEUED jobs.
    """
    company = models.ForeignKey(
        'company.Company', on_delete=models.CASCADE, related_name='printer_stations'
    )
    name = models.CharField(max_length=100, help_text='e.g. "Kitchen Printer", "Bar Printer"')
    printer_type = models.CharField(max_length=5, choices=PRINTER_TYPE_CHOICES)
    ip_address = models.CharField(
        max_length=100, blank=True, null=True,
        help_text='IP address or hostname of the network printer.'
    )
    port = models.PositiveIntegerField(
        default=9100,
        help_text='TCP port (default 9100 for most thermal printers).'
    )
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(
        default=False,
        help_text='Mark as default printer for this type.'
    )
    notes = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        ordering = ['printer_type', 'name']

    def __str__(self):
        return f"{self.name} ({self.get_printer_type_display()})"


class DiningOrder(BaseModel):
    """
    An open restaurant order tied to a table.
    Lifecycle: OPEN → KOT_SENT / BOT_SENT → BILLED → PAID
    On BILLED, an Invoice is created via convert_to_invoice().
    """
    company = models.ForeignKey(
        'company.Company', on_delete=models.CASCADE, related_name='dining_orders'
    )
    branch = models.ForeignKey(
        'company.Branch', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='dining_orders'
    )
    table = models.ForeignKey(
        RestaurantTable, on_delete=models.PROTECT, related_name='dining_orders'
    )
    order_number = models.CharField(max_length=50, unique=True, blank=True, null=True)
    status = models.CharField(
        max_length=10, choices=ORDER_STATUS_CHOICES, default='OPEN'
    )
    covers = models.PositiveSmallIntegerField(
        default=1, help_text='Number of guests (pax).'
    )
    waiter_name = models.CharField(max_length=100, blank=True, null=True)
    customer = models.ForeignKey(
        'customers.Customer', on_delete=models.SET_NULL, null=True, blank=True,
        help_text='Optional — for loyalty / credit customers.'
    )
    opened_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)

    # Financials (computed from items)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    discount_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))

    # Link to invoice once billed
    invoice = models.OneToOneField(
        'billing.Invoice', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='dining_order'
    )
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-opened_at']

    def __str__(self):
        return f"Order {self.order_number or self.id} — {self.table}"

    def recalculate_totals(self):
        """Recompute subtotal / tax / total from active items."""
        items = self.items.exclude(status='CANCELLED')
        subtotal = sum(i.line_subtotal for i in items)
        discount = sum(i.discount_amount for i in items)
        tax = sum(i.tax_amount for i in items)
        self.subtotal = subtotal
        self.discount_amount = discount
        self.tax_amount = tax
        self.total = subtotal - discount + tax
        self.save(update_fields=['subtotal', 'discount_amount', 'tax_amount', 'total'])

    @property
    def food_items(self):
        return self.items.filter(item_type='FOOD').exclude(status='CANCELLED')

    @property
    def beverage_items(self):
        return self.items.filter(item_type='BEVERAGE').exclude(status='CANCELLED')

    @property
    def unprinted_food_items(self):
        return self.items.filter(item_type='FOOD', kot_printed=False).exclude(status='CANCELLED')

    @property
    def unprinted_beverage_items(self):
        return self.items.filter(item_type='BEVERAGE', bot_printed=False).exclude(status='CANCELLED')


class DiningOrderItem(BaseModel):
    """
    A line item on a dining order.
    item_type drives which printer it goes to (KOT=kitchen, BOT=bar).
    kot_printed / bot_printed track whether the ticket has been sent.
    """
    order = models.ForeignKey(
        DiningOrder, on_delete=models.CASCADE, related_name='items'
    )
    product = models.ForeignKey(
        'products.Product', on_delete=models.PROTECT, related_name='dining_order_items'
    )
    item_type = models.CharField(
        max_length=9, choices=ITEM_TYPE_CHOICES, default='FOOD'
    )
    quantity = models.DecimalField(max_digits=8, decimal_places=3, default=Decimal('1.000'))
    unit_price = models.DecimalField(max_digits=14, decimal_places=2)
    discount_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0.00')
    )
    tax_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0.00')
    )
    status = models.CharField(
        max_length=10, choices=ITEM_STATUS_CHOICES, default='PENDING'
    )
    kot_printed = models.BooleanField(
        default=False,
        help_text='True once this item has been sent to the kitchen printer.'
    )
    bot_printed = models.BooleanField(
        default=False,
        help_text='True once this item has been sent to the bar printer.'
    )
    notes = models.CharField(
        max_length=255, blank=True, null=True,
        help_text='Special instructions, e.g. "no onions".'
    )

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.quantity} × {self.product.name}"

    @property
    def line_subtotal(self):
        return (self.quantity * self.unit_price).quantize(Decimal('0.01'))

    @property
    def discount_amount(self):
        return (self.line_subtotal * self.discount_percent / 100).quantize(Decimal('0.01'))

    @property
    def taxable_amount(self):
        return self.line_subtotal - self.discount_amount

    @property
    def tax_amount(self):
        return (self.taxable_amount * self.tax_percent / 100).quantize(Decimal('0.01'))

    @property
    def line_total(self):
        return self.taxable_amount + self.tax_amount


class PrintJob(BaseModel):
    """
    Audit trail for every KOT / BOT / Bill print request.
    A local print agent polls for QUEUED jobs and marks them SENT or FAILED.
    """
    company = models.ForeignKey(
        'company.Company', on_delete=models.CASCADE, related_name='print_jobs'
    )
    printer = models.ForeignKey(
        PrinterStation, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='print_jobs'
    )
    dining_order = models.ForeignKey(
        DiningOrder, on_delete=models.CASCADE, related_name='print_jobs'
    )
    job_type = models.CharField(max_length=5, choices=PRINTER_TYPE_CHOICES)
    status = models.CharField(
        max_length=8, choices=PRINT_JOB_STATUS_CHOICES, default='QUEUED'
    )
    payload = models.JSONField(
        default=dict,
        help_text='Serialised print data (items, table, order number, etc.).'
    )
    sent_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.job_type} job for {self.dining_order} — {self.status}"


# ── Menu Management ───────────────────────────────────────────────────────────

class Menu(BaseModel):
    company = models.ForeignKey('company.Company', on_delete=models.CASCADE, related_name='menus')
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    is_published = models.BooleanField(default=False)
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['company', 'name'], name='unique_menu_name_per_company'),
        ]

    def __str__(self):
        return self.name


class MenuCategory(BaseModel):
    CATEGORY_TYPE_CHOICES = [
        ('FOOD',      'Food'),
        ('BEVERAGE',  'Beverage'),
        ('BOTH',      'Food & Beverage'),
    ]
    menu = models.ForeignKey(Menu, on_delete=models.CASCADE, related_name='categories')
    name = models.CharField(max_length=100)
    item_type = models.CharField(max_length=9, choices=CATEGORY_TYPE_CHOICES, default='FOOD')
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['sort_order', 'name']
        constraints = [
            models.UniqueConstraint(fields=['menu', 'name'], name='unique_category_name_per_menu'),
        ]

    def __str__(self):
        return f"{self.menu.name} / {self.name}"


class MenuItem(BaseModel):
    category = models.ForeignKey(MenuCategory, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('products.Product', on_delete=models.PROTECT, related_name='menu_items')
    price_override = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text='Leave blank to use the product\'s default price.',
    )
    is_available = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    notes = models.CharField(max_length=255, blank=True, help_text='Display description on menu (e.g. "Contains nuts")')

    class Meta:
        ordering = ['sort_order', 'product__name']
        constraints = [
            models.UniqueConstraint(fields=['category', 'product'], name='unique_product_per_category'),
        ]

    @property
    def effective_price(self):
        return self.price_override if self.price_override is not None else self.product.price

    @property
    def item_type(self):
        return self.category.item_type

    def __str__(self):
        return f"{self.product.name} — {self.category.name}"


# ── Resort Room Management ────────────────────────────────────────────────────

ROOM_STATUS_CHOICES = [
    ('AVAILABLE',    'Available'),
    ('OCCUPIED',     'Occupied'),
    ('RESERVED',     'Reserved'),
    ('MAINTENANCE',  'Maintenance'),
    ('CHECKOUT',     'Pending Checkout'),
]

BOOKING_STATUS_CHOICES = [
    ('CONFIRMED',    'Confirmed'),
    ('CHECKED_IN',   'Checked In'),
    ('CHECKED_OUT',  'Checked Out'),
    ('CANCELLED',    'Cancelled'),
]


class RoomType(BaseModel):
    company = models.ForeignKey(
        'company.Company', on_delete=models.CASCADE, related_name='room_types'
    )
    name = models.CharField(max_length=100)
    capacity = models.PositiveSmallIntegerField(default=2, help_text='Max guests.')
    rate_per_night = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['name']
        unique_together = ('company', 'name')

    def __str__(self):
        return f"{self.name} — Rs {self.rate_per_night}/night"


class Room(BaseModel):
    company = models.ForeignKey(
        'company.Company', on_delete=models.CASCADE, related_name='rooms'
    )
    room_type = models.ForeignKey(
        RoomType, on_delete=models.PROTECT, related_name='rooms'
    )
    room_number = models.CharField(max_length=20)
    floor = models.CharField(max_length=20, blank=True)
    status = models.CharField(
        max_length=12, choices=ROOM_STATUS_CHOICES, default='AVAILABLE'
    )
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['floor', 'room_number']
        unique_together = ('company', 'room_number')

    def __str__(self):
        return f"Room {self.room_number} ({self.room_type.name}) — {self.get_status_display()}"

    @property
    def active_booking(self):
        return self.bookings.filter(
            status__in=['CONFIRMED', 'CHECKED_IN']
        ).first()


class RoomBooking(BaseModel):
    company = models.ForeignKey(
        'company.Company', on_delete=models.CASCADE, related_name='room_bookings'
    )
    room = models.ForeignKey(
        Room, on_delete=models.PROTECT, related_name='bookings'
    )
    guest_name = models.CharField(max_length=200)
    guest_phone = models.CharField(max_length=20)
    guest_email = models.EmailField(blank=True)
    check_in = models.DateField()
    check_out = models.DateField()
    adult_count = models.PositiveSmallIntegerField(default=1)
    child_count = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(
        max_length=12, choices=BOOKING_STATUS_CHOICES, default='CONFIRMED'
    )
    rate_per_night = models.DecimalField(
        max_digits=10, decimal_places=2,
        help_text='Locked at booking time from RoomType rate.'
    )
    notes = models.TextField(blank=True)

    # Invoice created at checkout
    invoice = models.OneToOneField(
        'billing.Invoice', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='room_booking'
    )

    # Actual check-in / check-out timestamps
    checked_in_at = models.DateTimeField(null=True, blank=True)
    checked_out_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-check_in']

    def __str__(self):
        return f"{self.guest_name} — Room {self.room.room_number} ({self.check_in} → {self.check_out})"

    @property
    def nights(self):
        return max((self.check_out - self.check_in).days, 1)

    @property
    def room_charge_total(self):
        return (self.nights * self.rate_per_night).quantize(Decimal('0.01'))

    @property
    def extra_charge_total(self):
        return sum(c.amount for c in self.charges.all())

    @property
    def grand_total(self):
        return (self.room_charge_total + self.extra_charge_total).quantize(Decimal('0.01'))


class RoomCharge(BaseModel):
    booking = models.ForeignKey(
        RoomBooking, on_delete=models.CASCADE, related_name='charges'
    )
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    charged_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['charged_at']

    def __str__(self):
        return f"{self.description} — Rs {self.amount}"
