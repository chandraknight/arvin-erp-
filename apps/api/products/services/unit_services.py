from decimal import Decimal
from apps.products.models import Product, ProductStock, ProductVariant


def get_stock_in_purchase_units(product: Product) -> Decimal:
    try:
        stock_obj = ProductStock.objects.get(product=product)
    except ProductStock.DoesNotExist:
        return Decimal('0')
    factor = Decimal(str(product.conversion_factor)) if product.conversion_factor else Decimal('1')
    if factor == 0:
        return Decimal('0')
    return Decimal(str(stock_obj.stock)) / factor


def add_stock_from_purchase(product: Product, purchase_qty: Decimal, stock_type: str = 'POS') -> int:
    """
    Converts purchase_qty (purchase units) → sale units and adds to stock.
    Returns updated stock in sale units.
    """
    factor = Decimal(str(product.conversion_factor)) if product.conversion_factor else Decimal('1')
    sale_qty = int(purchase_qty * factor)
    stock_obj, _ = ProductStock.objects.get_or_create(product=product)
    if stock_type == 'ECOM':
        stock_obj.ecom_stock += sale_qty
    else:
        stock_obj.stock += sale_qty
    stock_obj.save(update_fields=['stock', 'ecom_stock', 'updated_at'])
    return stock_obj.stock if stock_type == 'POS' else stock_obj.ecom_stock


def get_variant_stock(variant: ProductVariant) -> dict:
    return {
        'pos': variant.stock,
        'ecom': variant.ecom_stock,
        'pos_in_purchase_units': _to_purchase_units(variant.product, variant.stock),
        'ecom_in_purchase_units': _to_purchase_units(variant.product, variant.ecom_stock),
    }


def add_variant_stock_from_purchase(variant: ProductVariant, purchase_qty: Decimal, stock_type: str = 'POS') -> int:
    factor = Decimal(str(variant.product.conversion_factor)) if variant.product.conversion_factor else Decimal('1')
    sale_qty = int(purchase_qty * factor)
    if stock_type == 'ECOM':
        variant.ecom_stock += sale_qty
    else:
        variant.stock += sale_qty
    variant.save(update_fields=['stock', 'ecom_stock', 'updated_at'])
    return variant.stock if stock_type == 'POS' else variant.ecom_stock


def _to_purchase_units(product: Product, sale_qty: int) -> Decimal:
    factor = Decimal(str(product.conversion_factor)) if product.conversion_factor else Decimal('1')
    if factor == 0:
        return Decimal('0')
    return Decimal(str(sale_qty)) / factor
