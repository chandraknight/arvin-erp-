from decimal import Decimal
from django.db import models
from django.utils import timezone
from apps.utils.baseModel import BaseModel


# ── CMS ──────────────────────────────────────────────────────────────────────

class SiteSettings(BaseModel):
    """One row per company — controls storefront branding and contact info."""
    company = models.OneToOneField(
        'company.Company', on_delete=models.CASCADE, related_name='ecom_settings'
    )
    store_name = models.CharField(max_length=200, blank=True)
    tagline = models.CharField(max_length=300, blank=True)
    logo = models.ImageField(upload_to='ecom/logo/', blank=True, null=True)
    favicon = models.ImageField(upload_to='ecom/favicon/', blank=True, null=True)
    contact_phone = models.CharField(max_length=30, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_address = models.TextField(blank=True)
    facebook_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)
    tiktok_url = models.URLField(blank=True)
    twitter_url = models.URLField(blank=True)
    footer_text = models.CharField(max_length=300, blank=True)
    free_shipping_threshold = models.PositiveIntegerField(default=5000)
    delivery_charge = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('0.00'),
        help_text="Fixed delivery fee added at checkout. Set 0 to disable."
    )
    show_topbar = models.BooleanField(default=True, help_text="Show the top announcement/info bar on storefront")
    show_special_offer = models.BooleanField(default=True, help_text="Show the Special Offer badge in header")

    class Meta:
        verbose_name = 'Site Settings'
        verbose_name_plural = 'Site Settings'

    def __str__(self):
        return f"Ecom Settings — {self.company.name}"


BANNER_TYPE_CHOICES = [
    ('HERO',  'Hero Slider'),
    ('PROMO', 'Promo Box (right side)'),
]


class HeroBanner(BaseModel):
    """Rotating hero banners and promo boxes on the storefront homepage."""
    company = models.ForeignKey(
        'company.Company', on_delete=models.CASCADE, related_name='ecom_banners'
    )
    banner_type = models.CharField(max_length=10, choices=BANNER_TYPE_CHOICES, default='HERO')
    title = models.CharField(max_length=200, blank=True)
    subtitle = models.CharField(max_length=300, blank=True)
    image = models.ImageField(upload_to='ecom/banners/')
    link_url = models.CharField(max_length=500, blank=True, help_text="Optional link when banner is tapped.")
    link_label = models.CharField(max_length=100, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['sort_order', 'created_at']

    def __str__(self):
        return self.title or f"Banner {self.id}"


PAGE_SLUG_CHOICES = [
    ('about',           'About Us'),
    ('contact',         'Contact Us'),
    ('terms',           'Terms & Conditions'),
    ('privacy',         'Privacy Policy'),
    ('shipping',        'Shipping Policy'),
    ('refund',          'Refund & Return Policy'),
    ('payment',         'Payment Policy'),
    ('custom',          'Custom Page'),
]


class Page(BaseModel):
    """Static CMS pages (About, Policies, etc.) editable from ERP."""
    company = models.ForeignKey(
        'company.Company', on_delete=models.CASCADE, related_name='ecom_pages'
    )
    slug_type = models.CharField(max_length=20, choices=PAGE_SLUG_CHOICES, default='custom')
    slug = models.SlugField(max_length=100)
    title = models.CharField(max_length=200)
    content = models.TextField()
    is_published = models.BooleanField(default=True)
    show_in_footer = models.BooleanField(default=True)
    show_in_nav = models.BooleanField(default=False)

    class Meta:
        unique_together = ('company', 'slug')
        ordering = ['slug_type', 'title']

    def __str__(self):
        return self.title


class Announcement(BaseModel):
    """Site-wide announcement bar or news item shown on storefront."""
    ANNOUNCEMENT_TYPES = [
        ('BANNER', 'Top Banner Bar'),
        ('NEWS',   'News / What\'s New'),
    ]
    company = models.ForeignKey(
        'company.Company', on_delete=models.CASCADE, related_name='ecom_announcements'
    )
    announcement_type = models.CharField(max_length=10, choices=ANNOUNCEMENT_TYPES, default='BANNER')
    text = models.CharField(max_length=500)
    link_url = models.CharField(max_length=500, blank=True)
    link_label = models.CharField(max_length=100, blank=True)
    bg_color = models.CharField(max_length=20, default='indigo', help_text="Tailwind color name: indigo, red, green, yellow")
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', '-created_at']

    def __str__(self):
        return self.text[:60]

    def is_visible(self):
        if not self.is_active:
            return False
        if self.expires_at and self.expires_at < timezone.now():
            return False
        return True


# ── Coupons ──────────────────────────────────────────────────────────────────

DISCOUNT_TYPE_CHOICES = [
    ('PERCENT', 'Percentage (%)'),
    ('FIXED',   'Fixed Amount (Rs.)'),
]


class DiscountCoupon(BaseModel):
    company = models.ForeignKey(
        'company.Company', on_delete=models.CASCADE, related_name='discount_coupons'
    )
    code = models.CharField(max_length=50)
    discount_type = models.CharField(max_length=10, choices=DISCOUNT_TYPE_CHOICES, default='PERCENT')
    value = models.DecimalField(max_digits=10, decimal_places=2)
    min_order_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    max_uses = models.PositiveIntegerField(null=True, blank=True, help_text='Leave blank for unlimited')
    uses_count = models.PositiveIntegerField(default=0)
    valid_from = models.DateField(null=True, blank=True)
    valid_until = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('company', 'code')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.code} ({self.get_discount_type_display()} — {self.value})"

    def is_valid(self, order_subtotal):
        from django.utils import timezone
        today = timezone.now().date()
        if not self.is_active:
            return False, 'Coupon is inactive.'
        if self.valid_from and today < self.valid_from:
            return False, 'Coupon is not yet valid.'
        if self.valid_until and today > self.valid_until:
            return False, 'Coupon has expired.'
        if self.max_uses is not None and self.uses_count >= self.max_uses:
            return False, 'Coupon usage limit reached.'
        if Decimal(str(order_subtotal)) < self.min_order_amount:
            return False, f'Minimum order amount is Rs.{self.min_order_amount}.'
        return True, None

    def compute_discount(self, subtotal):
        subtotal = Decimal(str(subtotal))
        if self.discount_type == 'PERCENT':
            return min((subtotal * self.value / 100).quantize(Decimal('0.01')), subtotal)
        return min(self.value, subtotal)


# ── Orders ────────────────────────────────────────────────────────────────────

ECOM_ORDER_STATUS = [
    ('PENDING',    'Pending'),
    ('CONFIRMED',  'Confirmed'),
    ('PROCESSING', 'Processing'),
    ('DISPATCHED', 'Dispatched'),
    ('DELIVERED',  'Delivered'),
    ('CANCELLED',  'Cancelled'),
]

PAYMENT_METHOD_CHOICES = [
    ('COD', 'Cash on Delivery'),
]

COD_STATUS_CHOICES = [
    ('PENDING',    'Pending Collection'),
    ('COLLECTED',  'Cash Collected'),
    ('FAILED',     'Collection Failed'),
]


class EcomOrder(BaseModel):
    """
    An order placed through the e-commerce storefront.
    Automatically creates a SalesOrder in apps/orders on save.
    """
    company = models.ForeignKey(
        'company.Company', on_delete=models.CASCADE, related_name='ecom_orders'
    )
    sales_order = models.OneToOneField(
        'orders.SalesOrder', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='ecom_order'
    )

    # Customer info (guest or linked customer)
    customer = models.ForeignKey(
        'customers.Customer', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='ecom_orders'
    )
    customer_name = models.CharField(max_length=200)
    customer_phone = models.CharField(max_length=20)
    customer_email = models.EmailField(blank=True, null=True)
    delivery_address = models.TextField()
    notes = models.TextField(blank=True, null=True)

    # Order details
    order_number = models.CharField(max_length=50, unique=True, blank=True, null=True)
    status = models.CharField(max_length=15, choices=ECOM_ORDER_STATUS, default='PENDING')
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHOD_CHOICES, default='COD')
    cod_status = models.CharField(max_length=15, choices=COD_STATUS_CHOICES, default='PENDING')

    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    discount_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    delivery_charge = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    coupon = models.ForeignKey(
        'ecom.DiscountCoupon', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='orders'
    )
    total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"ECOM-{self.order_number or self.id} — {self.customer_name}"

    def save(self, *args, **kwargs):
        if not self.order_number:
            # Scope to company so each company's sequence is independent
            last = (
                EcomOrder.objects
                .filter(company=self.company, order_number__isnull=False)
                .exclude(order_number='')
                .order_by('-created_at')
                .first()
            )
            try:
                num = int(last.order_number.split('-')[-1]) + 1 if last else 1
            except (ValueError, IndexError):
                num = 1
            self.order_number = f"EC-{num:05d}"
        super().save(*args, **kwargs)


# ── Blog ─────────────────────────────────────────────────────────────────────

class BlogPost(BaseModel):
    company = models.ForeignKey(
        'company.Company', on_delete=models.CASCADE, related_name='ecom_blog_posts'
    )
    title = models.CharField(max_length=300)
    slug = models.SlugField(max_length=300, unique=True)
    excerpt = models.TextField(blank=True, help_text="Short summary shown in blog list.")
    content = models.TextField()
    cover_image = models.ImageField(upload_to='ecom/blog/', blank=True, null=True)
    author_name = models.CharField(max_length=100, blank=True)
    is_published = models.BooleanField(default=True)
    published_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-published_at']

    def __str__(self):
        return self.title


# ── Contact ───────────────────────────────────────────────────────────────────

class ContactMessage(BaseModel):
    company = models.ForeignKey(
        'company.Company', on_delete=models.CASCADE, related_name='ecom_contact_messages'
    )
    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    subject = models.CharField(max_length=300, blank=True)
    message = models.TextField()
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} — {self.subject or 'No subject'}"


def _media_upload_path(instance, filename):
    return f'ecom/uploads/{instance.company_id}/{instance.folder or "general"}/{filename}'


class MediaFile(BaseModel):
    company = models.ForeignKey(
        'company.Company', on_delete=models.CASCADE, related_name='media_files'
    )
    file = models.ImageField(upload_to=_media_upload_path)
    label = models.CharField(max_length=255, blank=True)
    folder = models.CharField(max_length=100, blank=True, default='general')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.label or self.file.name


class MediaFolder(BaseModel):
    company = models.ForeignKey(
        'company.Company', on_delete=models.CASCADE, related_name='media_folders'
    )
    name = models.CharField(max_length=100)

    class Meta:
        unique_together = ('company', 'name')
        ordering = ['name']

    def __str__(self):
        return self.name


class EcomOrderItem(BaseModel):
    order = models.ForeignKey(EcomOrder, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('products.Product', on_delete=models.PROTECT)
    variant = models.ForeignKey(
        'products.ProductVariant', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='ecom_order_items',
        help_text="Populated when ordering a size/color variant."
    )
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=14, decimal_places=2)

    def __str__(self):
        return f"{self.quantity}x {self.product.name}"

    def save(self, *args, **kwargs):
        self.total_price = self.unit_price * self.quantity
        super().save(*args, **kwargs)
