"""
All DRF serializers for the API app.

Grouped by domain:
  - Auth / Token
  - Company
  - Customer
  - Product / Stock
  - Invoice / InvoiceItem
  - Payment
  - Dashboard
"""
from rest_framework import serializers

from apps.api.models import APIToken


# ---------------------------------------------------------------------------
# Auth / Token serializers
# ---------------------------------------------------------------------------

class TokenObtainSerializer(serializers.Serializer):
    """Validates credentials and requested scopes for token creation."""
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    token_name = serializers.CharField(default='API Token', max_length=100)
    scopes = serializers.ListField(
        child=serializers.CharField(),
        default=list,
    )


class APITokenSerializer(serializers.ModelSerializer):
    """
    Read-only representation of an APIToken.
    The raw key is NOT included — it is only shown once at creation time.
    """
    company_name = serializers.SerializerMethodField()

    class Meta:
        model = APIToken
        fields = [
            'id',
            'name',
            'scopes',
            'expires_at',
            'last_used_at',
            'is_active',
            'created_at',
            'company_name',
        ]
        read_only_fields = fields

    def get_company_name(self, obj):
        return obj.company.name if obj.company else None


class TokenCreateResponseSerializer(serializers.Serializer):
    """
    Response shape returned once when a token is created.
    The raw key is included here and NEVER returned again.
    """
    token = serializers.CharField()       # raw key — show once only
    token_id = serializers.UUIDField()
    name = serializers.CharField()
    scopes = serializers.ListField(child=serializers.CharField())
    expires_at = serializers.DateTimeField(allow_null=True)


# ---------------------------------------------------------------------------
# Company serializer
# ---------------------------------------------------------------------------

class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        from apps.company.models import Company
        model = Company
        fields = [
            'id',
            'name',
            'address',
            'phone',
            'email',
            'organisation_type',
            'vat_registered',
            'vat_number',
            'tax_rate',
            'enable_inventory',
            'enable_purchasing',
            'enable_hr_payroll',
            'enable_order_management',
            'enable_project_tracking',
            'enable_manufacturing',
            'enable_restaurant',
        ]


# ---------------------------------------------------------------------------
# Customer serializers
# ---------------------------------------------------------------------------

class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        from apps.customers.models import Customer
        model = Customer
        fields = ['id', 'name', 'email', 'phone', 'address']


class CustomerCreateSerializer(serializers.ModelSerializer):
    class Meta:
        from apps.customers.models import Customer
        model = Customer
        fields = ['name', 'email', 'phone', 'address']

    def validate_email(self, value):
        from apps.customers.models import Customer
        if value and Customer.active_objects.filter(email=value).exists():
            raise serializers.ValidationError('A customer with this email already exists.')
        return value


# ---------------------------------------------------------------------------
# Product / Stock serializers
# ---------------------------------------------------------------------------

class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)

    class Meta:
        from apps.products.models import Product
        model = Product
        fields = [
            'id',
            'name',
            'barcode',
            'sku',
            'vendor',
            'price',
            'cost_price',
            'is_service',
            'category',
            'category_name',
        ]


class ProductStockSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        from apps.products.models import ProductStock
        model = ProductStock
        fields = ['product', 'product_name', 'stock', 'minimum_stock']


# ---------------------------------------------------------------------------
# Invoice serializers
# ---------------------------------------------------------------------------

class InvoiceItemSerializer(serializers.ModelSerializer):
    product_name = serializers.SerializerMethodField()

    class Meta:
        from apps.billing.models import InvoiceItem
        model = InvoiceItem
        fields = [
            'id',
            'product',
            'product_name',
            'package',
            'description',
            'quantity',
            'price',
            'discount_percent',
            'discount_amount',
            'total_price',
        ]

    def get_product_name(self, obj):
        if obj.product:
            return obj.product.name
        if obj.package:
            return obj.package.name
        return obj.description or ''


class InvoiceSerializer(serializers.ModelSerializer):
    items = InvoiceItemSerializer(many=True, read_only=True)
    customer_name = serializers.CharField(
        source='customer.name', read_only=True, allow_null=True,
    )
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        from apps.billing.models import Invoice
        model = Invoice
        fields = [
            'id',
            'invoice_number',
            'transaction_date',
            'customer',
            'customer_name',
            'subtotal',
            'discount_amount',
            'tax_amount',
            'total',
            'outstanding_balance',
            'status',
            'status_display',
            'due_date',
            'items',
            'created_at',
        ]


class InvoiceCreateSerializer(serializers.Serializer):
    """
    Validates the payload for creating an invoice via the API.
    Items is a list of dicts: {product_id, quantity, price, discount_percent}.
    """
    customer_id = serializers.UUIDField(required=False, allow_null=True)
    transaction_date = serializers.DateField()
    tax_percent = serializers.DecimalField(max_digits=5, decimal_places=2, default=0)
    discount_percent = serializers.DecimalField(max_digits=5, decimal_places=2, default=0)
    due_date = serializers.DateField(required=False, allow_null=True)
    items = serializers.ListField(
        child=serializers.DictField(),
        min_length=1,
    )

    def validate_items(self, items):
        errors = []
        for i, item in enumerate(items):
            if 'product_id' not in item:
                errors.append(f'Item {i}: product_id is required.')
            if 'quantity' not in item:
                errors.append(f'Item {i}: quantity is required.')
            if 'price' not in item:
                errors.append(f'Item {i}: price is required.')
        if errors:
            raise serializers.ValidationError(errors)
        return items


# ---------------------------------------------------------------------------
# Payment serializer
# ---------------------------------------------------------------------------

class PaymentSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(
        source='invoice.invoice_number', read_only=True, allow_null=True,
    )
    method_display = serializers.CharField(source='get_method_display', read_only=True)

    class Meta:
        from apps.payments.models import Payment
        model = Payment
        fields = [
            'id',
            'date',
            'amount',
            'method',
            'method_display',
            'payment_type',
            'invoice',
            'invoice_number',
            'reference_number',
            'description',
            'created_at',
        ]


# ---------------------------------------------------------------------------
# Dashboard serializer
# ---------------------------------------------------------------------------

class DashboardSerializer(serializers.Serializer):
    total_invoices = serializers.IntegerField()
    total_customers = serializers.IntegerField()
    total_outstanding = serializers.DecimalField(max_digits=12, decimal_places=2)
    today_sales = serializers.DecimalField(max_digits=12, decimal_places=2)
    recent_invoices = InvoiceSerializer(many=True)
