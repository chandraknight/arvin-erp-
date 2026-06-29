import io
import os
from PIL import Image as PilImage
from django.core.files.base import ContentFile
from apps.utils.baseModel import *
from apps.company.models import Company
from apps.accounts.models import User
from apps.vendors.models import Vendor

class UnitOfMeasure(BaseModel):
    UOM_TYPE_CHOICES = [
        ('WEIGHT',  'Weight (kg, gram, etc.)'),
        ('COUNT',   'Count (pcs, dozen, etc.)'),
        ('LENGTH',  'Length (meter, cm, etc.)'),
        ('VOLUME',  'Volume (liter, ml, etc.)'),
    ]
    name = models.CharField(max_length=50, unique=True)
    symbol = models.CharField(max_length=10)
    uom_type = models.CharField(max_length=10, choices=UOM_TYPE_CHOICES, default='COUNT')

    def __str__(self):
        return f"{self.name} ({self.symbol})"


class CategoryType(BaseModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='category_type')
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

class Category(BaseModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='product_categories')
    name = models.CharField(max_length=100)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE)
    type = models.ForeignKey(CategoryType, on_delete=models.PROTECT, blank=True, null=True)
    ecom_image = models.ImageField(upload_to='categories/', blank=True, null=True)

    def __str__(self):
        return self.name

    @property
    def type_name(self):
        return self.type.name if self.type else ''

class Product(BaseModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='products')
    name = models.CharField(max_length=100)
    category = models.ForeignKey(Category, on_delete=models.PROTECT)
    barcode = models.CharField(max_length=50, unique=True, blank=True, null=True)
    sku = models.CharField(max_length=50, unique=True, blank=True, null=True, verbose_name="SKU")
    vendor = models.ForeignKey(
        Vendor, on_delete=models.SET_NULL, null=True, blank=True, related_name='products',
        help_text="Preferred vendor to purchase this item from.",
    )
    price = models.DecimalField(max_digits=10, decimal_places=2)
    compare_at_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Original price shown struck-through on the store. Leave blank if no discount.",
    )
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    # NFRS 2 (IAS 2): cost formula for inventory valuation
    COST_METHOD_CHOICES = [
        ('FIFO', 'First-In First-Out (FIFO)'),
        ('WA',   'Weighted Average Cost'),
    ]
    cost_method = models.CharField(
        max_length=4, choices=COST_METHOD_CHOICES, default='WA',
        help_text='NFRS 2: inventory cost formula used for COGS and stock valuation.',
    )
    # NFRS 2: net realisable value — used for lower-of-cost-or-NRV test
    nrv = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text='NFRS 2: Net Realisable Value. If NRV < cost_price, inventory must be written down.',
    )
    hscode = models.CharField(max_length=50, blank=True, null=True, verbose_name="HS Code")
    is_service = models.BooleanField(default=False, help_text="Check if this product is a service or non-stock item.")
    show_on_ecom = models.BooleanField(default=False)
    short_description = models.CharField(max_length=500, blank=True, null=True, help_text="Brief product summary for e-commerce listings (max 500 chars)")
    ecom_description = models.TextField(blank=True, null=True, help_text="Full product description shown on the e-commerce store")
    color = models.CharField(max_length=50, blank=True, default='', help_text="Product color for storefront filter (e.g. Red, Blue)")

    purchase_unit = models.ForeignKey(
        'products.UnitOfMeasure', on_delete=models.PROTECT,
        null=True, blank=True, related_name='purchased_products',
        help_text="Unit in which this product is received (e.g. KG, Dozen)."
    )
    sale_unit = models.ForeignKey(
        'products.UnitOfMeasure', on_delete=models.PROTECT,
        null=True, blank=True, related_name='sold_products',
        help_text="Unit in which this product is sold (e.g. Gram, Piece)."
    )
    conversion_factor = models.DecimalField(
        max_digits=12, decimal_places=4, default=1,
        help_text="How many sale units equal 1 purchase unit (e.g. 1000 for KG→Gram, 12 for Dozen→Piece)."
    )
    has_variants = models.BooleanField(
        default=False,
        help_text="Enable size/color variants (clothes, shoes). Stock tracked per variant when enabled."
    )

    def __str__(self):
        return f"{self.name} ({self.barcode})"

    @property
    def category_name(self):
        return self.category.name

    @property
    def type_name(self):
        return self.category.type_name if self.category else ''

    @property
    def has_discount(self):
        return bool(self.compare_at_price and self.compare_at_price > self.price)

    @property
    def discount_percent(self):
        if not self.has_discount:
            return 0
        return round((self.compare_at_price - self.price) / self.compare_at_price * 100)

    @property
    def primary_image_url(self):
        # Use prefetch cache when available — avoid filtered queryset that bypasses it
        all_images = self.images.all()
        primary = next((i for i in all_images if i.is_primary), None) or next(iter(all_images), None)
        return primary.image.url if primary else None

class ProductStock(BaseModel):
    product = models.OneToOneField(Product, on_delete=models.CASCADE)
    stock = models.PositiveIntegerField(default=0, help_text="Stock available for POS/In-store sales.")
    minimum_stock = models.PositiveIntegerField(default=0)
    ecom_stock = models.PositiveIntegerField(default=0, help_text="Stock reserved specifically for E-commerce.")
    ecom_minimum_stock = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.product.name} - POS: {self.stock}, Ecom: {self.ecom_stock}"

class ProductVariant(BaseModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')
    size = models.CharField(max_length=20, blank=True, default='', help_text="e.g. S, M, L, XL or 6, 7, 8, 9, 10")
    color = models.CharField(max_length=50, blank=True, default='', help_text="e.g. Red, Blue, Black")
    sku = models.CharField(max_length=50, unique=True, blank=True, null=True)
    barcode = models.CharField(max_length=50, unique=True, blank=True, null=True)
    price_adjustment = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Added to or subtracted from product base price for this variant."
    )
    stock = models.PositiveIntegerField(default=0, help_text="POS/in-store stock in sale units.")
    ecom_stock = models.PositiveIntegerField(default=0, help_text="E-commerce stock in sale units.")
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('product', 'size', 'color')

    def __str__(self):
        parts = [self.product.name]
        if self.size:
            parts.append(self.size)
        if self.color:
            parts.append(self.color)
        return ' / '.join(parts)

    @property
    def sale_price(self):
        return self.product.price + self.price_adjustment


# Moved from pos.models
class StockTransaction(BaseModel):
    TRANSACTION_TYPES = (
        ('ADD', 'Add Stock'),
        ('REMOVE', 'Remove Stock'),
        ('ADJUST', 'Adjust Stock'),
    )
    STOCK_TYPES = (
        ('POS', 'POS Stock'),
        ('ECOM', 'E-commerce Stock'),
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    stock_type = models.CharField(max_length=10, choices=STOCK_TYPES, default='POS')
    quantity = models.IntegerField()
    reason = models.TextField(blank=True)

    def __str__(self):
        return f"{self.transaction_type} {self.quantity} x {self.product.name}"


class Package(BaseModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='package', null=True, blank=True)
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    compare_at_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    show_on_ecom = models.BooleanField(default=False)
    ecom_image = models.ImageField(upload_to='packages/', blank=True, null=True)
    ecom_description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name

    @property
    def has_discount(self):
        return bool(self.compare_at_price and self.compare_at_price > self.price)

    @property
    def discount_percent(self):
        if not self.has_discount:
            return 0
        return round((self.compare_at_price - self.price) / self.compare_at_price * 100)

class PackageItem(BaseModel):
    package = models.ForeignKey(Package, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(null=True, blank=True, default=1)

    def __str__(self):
        name = self.product.name if self.product else "Unknown Product"
        return f"{self.quantity}x {name} in {self.package.name}"

class ProductImage(BaseModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='products/')
    is_primary = models.BooleanField(default=False)
    image_hash = models.CharField(max_length=64, blank=True, default='')

    def __str__(self):
        return f"Image for {self.product.name}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.image:
            try:
                img_path = self.image.path
                # Skip if already WebP
                if img_path.lower().endswith('.webp'):
                    return
                with PilImage.open(img_path) as img:
                    # Preserve EXIF orientation
                    try:
                        from PIL import ImageOps
                        img = ImageOps.exif_transpose(img)
                    except Exception:
                        pass
                    if img.mode in ('RGBA', 'LA'):
                        background = PilImage.new('RGB', img.size, (255, 255, 255))
                        background.paste(img, mask=img.split()[-1])
                        img = background
                    elif img.mode != 'RGB':
                        img = img.convert('RGB')
                    webp_name = os.path.splitext(os.path.basename(img_path))[0] + '.webp'
                    buf = io.BytesIO()
                    img.save(buf, format='WEBP', quality=82, method=6)
                    buf.seek(0)
                    # Replace the file in storage, update field name
                    old_name = self.image.name
                    new_name = os.path.join(os.path.dirname(old_name), webp_name)
                    self.image.storage.save(new_name, ContentFile(buf.read()))
                    self.image.storage.delete(img_path)
                    # Update DB field without recursion
                    ProductImage.objects.filter(pk=self.pk).update(image=new_name)
            except Exception:
                pass  # Never break upload if optimization fails
