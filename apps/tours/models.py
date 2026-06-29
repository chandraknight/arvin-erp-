from decimal import Decimal
from django.db import models
from apps.utils.baseModel import BaseModel
from apps.company.models import Company
from apps.customers.models import Customer
from django.conf import settings


class TourDestination(BaseModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='tour_destinations')
    name = models.CharField(max_length=200)
    country = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name}, {self.country}"


class TourPackage(BaseModel):
    PACKAGE_TYPE_CHOICES = [
        ('DOMESTIC', 'Domestic'),
        ('INTERNATIONAL', 'International'),
        ('PILGRIMAGE', 'Pilgrimage'),
        ('ADVENTURE', 'Adventure'),
        ('HONEYMOON', 'Honeymoon'),
        ('CORPORATE', 'Corporate'),
        ('CUSTOM', 'Custom'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='tour_packages')
    destination = models.ForeignKey(TourDestination, on_delete=models.PROTECT, related_name='packages')
    name = models.CharField(max_length=200)
    package_type = models.CharField(max_length=20, choices=PACKAGE_TYPE_CHOICES, default='DOMESTIC')
    duration_days = models.PositiveIntegerField(default=1)
    duration_nights = models.PositiveIntegerField(default=0)
    price_per_adult = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    price_per_child = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    max_capacity = models.PositiveIntegerField(default=20)
    inclusions = models.TextField(blank=True, help_text='What is included (one per line)')
    exclusions = models.TextField(blank=True, help_text='What is excluded (one per line)')
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.duration_days}D/{self.duration_nights}N)"


class TourEnquiry(BaseModel):
    ENQUIRY_STATUS_CHOICES = [
        ('NEW', 'New'),
        ('CONTACTED', 'Contacted'),
        ('QUOTED', 'Quoted'),
        ('CONVERTED', 'Converted to Booking'),
        ('LOST', 'Lost'),
    ]

    SOURCE_CHOICES = [
        ('WALK_IN', 'Walk-in'),
        ('PHONE', 'Phone'),
        ('EMAIL', 'Email'),
        ('WEBSITE', 'Website'),
        ('REFERRAL', 'Referral'),
        ('SOCIAL', 'Social Media'),
        ('OTHER', 'Other'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='tour_enquiries')
    enquiry_number = models.CharField(max_length=30, blank=True)

    # Customer — can be existing or walk-in
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name='tour_enquiries')
    contact_name = models.CharField(max_length=200)
    contact_phone = models.CharField(max_length=30, blank=True)
    contact_email = models.EmailField(blank=True)

    # Package interest
    package = models.ForeignKey(TourPackage, on_delete=models.SET_NULL, null=True, blank=True, related_name='enquiries')
    destination = models.ForeignKey(TourDestination, on_delete=models.SET_NULL, null=True, blank=True, related_name='enquiries')
    travel_date = models.DateField(null=True, blank=True)
    return_date = models.DateField(null=True, blank=True)
    num_adults = models.PositiveIntegerField(default=1)
    num_children = models.PositiveIntegerField(default=0)

    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='WALK_IN')
    status = models.CharField(max_length=20, choices=ENQUIRY_STATUS_CHOICES, default='NEW')
    special_requests = models.TextField(blank=True)
    internal_notes = models.TextField(blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='assigned_enquiries'
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.enquiry_number} — {self.contact_name}"

    def save(self, *args, **kwargs):
        if not self.enquiry_number:
            from django.db import transaction
            from django.utils import timezone
            with transaction.atomic():
                last = (
                    TourEnquiry.objects.select_for_update()
                    .filter(company=self.company)
                    .order_by('-created_at')
                    .first()
                )
                if last and last.enquiry_number:
                    try:
                        count = int(last.enquiry_number.split('-')[-1]) + 1
                    except (ValueError, IndexError):
                        count = TourEnquiry.objects.filter(company=self.company).count() + 1
                else:
                    count = 1
                self.enquiry_number = f"ENQ-{timezone.now().year}-{count:04d}"
        super().save(*args, **kwargs)

    @property
    def total_pax(self):
        return self.num_adults + self.num_children


class TourBooking(BaseModel):
    BOOKING_STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('CONFIRMED', 'Confirmed'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='tour_bookings')
    booking_number = models.CharField(max_length=30, blank=True)
    enquiry = models.OneToOneField(TourEnquiry, on_delete=models.SET_NULL, null=True, blank=True, related_name='booking')

    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name='tour_bookings')
    contact_name = models.CharField(max_length=200)
    contact_phone = models.CharField(max_length=30, blank=True)
    contact_email = models.EmailField(blank=True)

    travel_date = models.DateField()
    return_date = models.DateField(null=True, blank=True)
    num_adults = models.PositiveIntegerField(default=1)
    num_children = models.PositiveIntegerField(default=0)

    status = models.CharField(max_length=20, choices=BOOKING_STATUS_CHOICES, default='DRAFT')
    special_requests = models.TextField(blank=True)
    internal_notes = models.TextField(blank=True)

    # Financials
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('13.00'))
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    # Link to billing invoice once issued
    invoice = models.OneToOneField(
        'billing.Invoice', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='tour_booking'
    )

    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='assigned_bookings'
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.booking_number} — {self.contact_name}"

    def save(self, *args, **kwargs):
        if not self.booking_number:
            from django.db import transaction
            from django.utils import timezone
            with transaction.atomic():
                last = (
                    TourBooking.objects.select_for_update()
                    .filter(company=self.company)
                    .order_by('-created_at')
                    .first()
                )
                if last and last.booking_number:
                    try:
                        count = int(last.booking_number.split('-')[-1]) + 1
                    except (ValueError, IndexError):
                        count = TourBooking.objects.filter(company=self.company).count() + 1
                else:
                    count = 1
                self.booking_number = f"BKG-{timezone.now().year}-{count:04d}"
        super().save(*args, **kwargs)

    def recalculate_totals(self):
        items = self.items.filter(is_deleted=False)
        subtotal = sum((item.line_total for item in items), Decimal('0.00'))
        taxable = subtotal - (self.discount_amount or Decimal('0.00'))
        tax_amount = (taxable * self.tax_percent / Decimal('100')).quantize(Decimal('0.01'))
        total = (taxable + tax_amount).quantize(Decimal('0.01'))
        self.subtotal = subtotal.quantize(Decimal('0.01'))
        self.tax_amount = tax_amount
        self.total = total
        self.save(update_fields=['subtotal', 'tax_amount', 'total'])

    @property
    def total_pax(self):
        return self.num_adults + self.num_children

    @property
    def has_invoice(self):
        return self.invoice_id is not None


class TourBookingItem(BaseModel):
    ITEM_TYPE_CHOICES = [
        ('PACKAGE', 'Tour Package'),
        ('TICKET', 'Ticket / Entry'),
        ('HOTEL', 'Hotel / Accommodation'),
        ('TRANSPORT', 'Transport'),
        ('VISA', 'Visa / Insurance'),
        ('GUIDE', 'Guide / Service'),
        ('MISC', 'Miscellaneous'),
    ]

    booking = models.ForeignKey(TourBooking, on_delete=models.CASCADE, related_name='items')
    item_type = models.CharField(max_length=20, choices=ITEM_TYPE_CHOICES, default='PACKAGE')
    package = models.ForeignKey(TourPackage, on_delete=models.SET_NULL, null=True, blank=True)
    description = models.CharField(max_length=500)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.description} × {self.quantity}"

    @property
    def line_total(self):
        gross = self.unit_price * self.quantity
        return gross - (gross * self.discount_percent / 100)


# ── IATA Reference Data ───────────────────────────────────────────────────────

class IATAAirline(BaseModel):
    """IATA airline reference — 2-letter designator codes."""
    iata_code = models.CharField(max_length=3, unique=True, help_text='2-letter IATA designator (e.g. QR, EK, AI)')
    icao_code = models.CharField(max_length=4, blank=True, help_text='4-letter ICAO code')
    name = models.CharField(max_length=200)
    country = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['iata_code']

    def __str__(self):
        return f"{self.iata_code} — {self.name}"


class IATAAirport(BaseModel):
    """IATA airport reference — 3-letter location codes."""
    iata_code = models.CharField(max_length=3, unique=True, help_text='3-letter IATA airport code (e.g. KTM, DEL, DXB)')
    icao_code = models.CharField(max_length=4, blank=True)
    name = models.CharField(max_length=200)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    country_code = models.CharField(max_length=2, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['iata_code']

    def __str__(self):
        return f"{self.iata_code} — {self.name}, {self.country}"


# ── Air Tickets ───────────────────────────────────────────────────────────────

class AirTicket(BaseModel):
    """Individual air ticket record linked to a booking."""
    TICKET_STATUS_CHOICES = [
        ('ISSUED', 'Issued'),
        ('REISSUED', 'Reissued'),
        ('REFUNDED', 'Refunded'),
        ('VOIDED', 'Voided'),
        ('EXCHANGED', 'Exchanged'),
    ]

    TRIP_TYPE_CHOICES = [
        ('OW', 'One Way'),
        ('RT', 'Round Trip'),
        ('MC', 'Multi City'),
    ]

    CABIN_CHOICES = [
        ('Y', 'Economy'),
        ('W', 'Premium Economy'),
        ('C', 'Business'),
        ('F', 'First'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='air_tickets')
    booking = models.ForeignKey(TourBooking, on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets')

    # Ticket identity
    ticket_number = models.CharField(max_length=20, help_text='13-digit ticket number (e.g. 157-2345678901)')
    pnr = models.CharField(max_length=10, blank=True, help_text='GDS/Airline PNR reference')
    conjunction_tickets = models.CharField(max_length=100, blank=True, help_text='Comma-separated conjunction ticket numbers')

    # Passenger
    passenger_name = models.CharField(max_length=200, help_text='As printed on ticket (SURNAME/FIRSTNAME)')
    passenger_type = models.CharField(max_length=3, default='ADT', help_text='ADT / CHD / INF')

    # Route
    airline = models.ForeignKey(IATAAirline, on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets')
    validating_carrier = models.CharField(max_length=3, blank=True, help_text='2-letter IATA code of validating airline')
    origin = models.ForeignKey(IATAAirport, on_delete=models.SET_NULL, null=True, blank=True, related_name='departing_tickets')
    destination = models.ForeignKey(IATAAirport, on_delete=models.SET_NULL, null=True, blank=True, related_name='arriving_tickets')
    routing = models.CharField(max_length=200, blank=True, help_text='Full routing e.g. KTM-DEL-DXB-DEL-KTM')
    trip_type = models.CharField(max_length=2, choices=TRIP_TYPE_CHOICES, default='RT')
    cabin = models.CharField(max_length=1, choices=CABIN_CHOICES, default='Y')
    fare_basis = models.CharField(max_length=20, blank=True)

    # Dates
    issue_date = models.DateField()
    departure_date = models.DateField(null=True, blank=True)
    return_date = models.DateField(null=True, blank=True)

    # Financials (all in NPR unless noted)
    fare_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), help_text='Base fare')
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), help_text='All taxes combined')
    fuel_surcharge = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    gross_fare = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), help_text='fare + tax + fuel surcharge')

    # Commission / nett
    commission_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    commission_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    net_fare = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), help_text='gross_fare - commission')

    # BSP
    bsp_reference = models.CharField(max_length=50, blank=True, help_text='IATA BSP transaction reference')

    status = models.CharField(max_length=15, choices=TICKET_STATUS_CHOICES, default='ISSUED')
    remarks = models.TextField(blank=True)

    class Meta:
        ordering = ['-issue_date', 'ticket_number']

    def __str__(self):
        return f"{self.ticket_number} — {self.passenger_name}"

    def save(self, *args, **kwargs):
        # Auto-compute gross and net if not set
        if not self.gross_fare:
            self.gross_fare = self.fare_amount + self.tax_amount + self.fuel_surcharge
        if not self.commission_amount and self.commission_percent and self.fare_amount:
            self.commission_amount = (self.fare_amount * self.commission_percent / 100).quantize(Decimal('0.01'))
        if not self.net_fare:
            self.net_fare = self.gross_fare - self.commission_amount
        super().save(*args, **kwargs)


# ── IATA BSP Source File & Reconciliation ────────────────────────────────────

class IATASourceFile(BaseModel):
    """Uploaded IATA BSP billing file (CSV/Excel) for reconciliation."""
    FILE_STATUS_CHOICES = [
        ('UPLOADED', 'Uploaded'),
        ('PROCESSING', 'Processing'),
        ('PROCESSED', 'Processed'),
        ('ERROR', 'Error'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='iata_source_files')
    file = models.FileField(upload_to='iata_files/%Y/%m/')
    original_filename = models.CharField(max_length=255)
    period_from = models.DateField(null=True, blank=True, help_text='BSP billing period start')
    period_to = models.DateField(null=True, blank=True, help_text='BSP billing period end')
    description = models.CharField(max_length=300, blank=True)
    status = models.CharField(max_length=15, choices=FILE_STATUS_CHOICES, default='UPLOADED')
    rows_total = models.PositiveIntegerField(default=0)
    rows_matched = models.PositiveIntegerField(default=0)
    rows_unmatched = models.PositiveIntegerField(default=0)
    rows_new = models.PositiveIntegerField(default=0)
    error_log = models.TextField(blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.original_filename} ({self.get_status_display()})"


# ── AIR File (Agency Invoice Report) & Payment Reconciliation ─────────────────

class AIRFile(BaseModel):
    """
    IATA BSP Agency Invoice Report — the billing summary that tells the agency
    exactly what is owed to BSP for a billing period.
    Upload the AIR file, record payments against it, and mark it reconciled.
    """
    PAYMENT_STATUS_CHOICES = [
        ('PENDING',        'Pending Payment'),
        ('PARTIALLY_PAID', 'Partially Paid'),
        ('PAID',           'Paid'),
        ('DISPUTED',       'Disputed'),
    ]

    company          = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='air_files')
    file             = models.FileField(upload_to='air_files/%Y/%m/', blank=True, null=True)
    original_filename = models.CharField(max_length=255, blank=True)

    # Billing period
    period_from       = models.DateField(help_text='BSP billing period start')
    period_to         = models.DateField(help_text='BSP billing period end')
    billing_reference = models.CharField(max_length=100, blank=True, help_text='BSP billing reference / remittance ID')

    # Summary amounts (extracted from AIR file or entered manually)
    total_sales      = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), help_text='Total ticket sales gross amount')
    total_refunds    = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), help_text='Refunds / voids in this period')
    total_commission = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), help_text='Commission earned on sales')
    total_taxes      = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    net_amount_due   = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), help_text='Net payable to BSP (sales - refunds - commission)')

    # Payment tracking
    payment_status    = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='PENDING')
    amount_paid       = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    payment_due_date  = models.DateField(null=True, blank=True, help_text='BSP payment due date')

    description  = models.CharField(max_length=300, blank=True)
    notes        = models.TextField(blank=True)
    uploaded_by  = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    # Optional link to the detailed BSP billing file (ticket-level)
    bsp_source_file = models.ForeignKey(
        IATASourceFile, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='air_files', help_text='Link to the matching BSP billing file for ticket-level drill-down'
    )

    class Meta:
        ordering = ['-period_to']

    def __str__(self):
        return f"AIR {self.billing_reference or self.period_from} → {self.period_to}"

    @property
    def balance_due(self):
        return self.net_amount_due - self.amount_paid

    def recalculate_paid(self):
        """Sum all accepted payment records and update amount_paid + status."""
        paid = self.payments.filter(is_deleted=False).aggregate(
            s=models.Sum('amount')
        )['s'] or Decimal('0.00')
        self.amount_paid = paid
        if paid <= 0:
            self.payment_status = 'PENDING'
        elif paid < self.net_amount_due:
            self.payment_status = 'PARTIALLY_PAID'
        else:
            self.payment_status = 'PAID'
        self.save(update_fields=['amount_paid', 'payment_status'])


class BSPPaymentRecord(BaseModel):
    """Individual payment made to BSP against an AIR file billing period."""
    PAYMENT_METHOD_CHOICES = [
        ('BANK_TRANSFER', 'Bank Transfer'),
        ('CHEQUE',        'Cheque'),
        ('ONLINE',        'Online Payment'),
        ('OTHER',         'Other'),
    ]

    air_file         = models.ForeignKey(AIRFile, on_delete=models.CASCADE, related_name='payments')
    payment_date     = models.DateField()
    amount           = models.DecimalField(max_digits=14, decimal_places=2)
    payment_method   = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='BANK_TRANSFER')
    bank_reference   = models.CharField(max_length=200, blank=True, help_text='Bank transaction / cheque reference')
    notes            = models.TextField(blank=True)
    recorded_by      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['payment_date']

    def __str__(self):
        return f"Payment {self.amount} on {self.payment_date} for {self.air_file}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.air_file.recalculate_paid()

    def delete(self, *args, **kwargs):
        air = self.air_file
        super().delete(*args, **kwargs)
        air.recalculate_paid()


class IATAReconciliationItem(BaseModel):
    """Single row from a processed IATA source file, matched/unmatched against AirTicket records."""
    MATCH_STATUS_CHOICES = [
        ('MATCHED', 'Matched'),
        ('UNMATCHED', 'Not in system'),
        ('MISMATCH', 'Amount mismatch'),
        ('NEW_IMPORTED', 'Imported as new ticket'),
    ]

    source_file = models.ForeignKey(IATASourceFile, on_delete=models.CASCADE, related_name='items')
    air_ticket = models.ForeignKey(AirTicket, on_delete=models.SET_NULL, null=True, blank=True, related_name='reconciliation_items')

    # Raw data from source file
    raw_ticket_number = models.CharField(max_length=20)
    raw_passenger_name = models.CharField(max_length=200, blank=True)
    raw_issue_date = models.DateField(null=True, blank=True)
    raw_airline_code = models.CharField(max_length=3, blank=True)
    raw_routing = models.CharField(max_length=200, blank=True)
    raw_fare = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    raw_tax = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    raw_gross = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    raw_commission = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    raw_net = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    match_status = models.CharField(max_length=15, choices=MATCH_STATUS_CHOICES, default='UNMATCHED')
    mismatch_note = models.TextField(blank=True)

    class Meta:
        ordering = ['raw_ticket_number']

    def __str__(self):
        return f"{self.raw_ticket_number} — {self.match_status}"
