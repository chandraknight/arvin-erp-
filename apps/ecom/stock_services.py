"""
Bulk ecom stock allocation. Ecom stock is a pool transferred from POS
stock — same balancing rules as products' single-product stock page,
applied to many products in one save, with StockTransaction audit rows.
"""
from decimal import Decimal, InvalidOperation

from django.db import transaction

from apps.products.models import Product, ProductStock, StockTransaction


@transaction.atomic
def bulk_set_ecom_stock(company, user, quantities):
    """quantities: {product_id: new_ecom_qty}. Returns (updated, skipped)
    where skipped is a list of (product_name, reason)."""
    updated, skipped = 0, []
    products = (
        Product.objects.filter(id__in=quantities.keys(), company=company)
        .select_related('productstock')
    )
    for product in products:
        new_qty = quantities[str(product.id)]
        stock, _ = ProductStock.objects.select_for_update().get_or_create(product=product)
        diff = new_qty - stock.ecom_stock
        if diff == 0:
            continue
        if diff > 0 and stock.stock < diff:
            skipped.append((product.name, f'only {stock.stock} in POS stock, needs {diff}'))
            continue
        stock.stock -= diff
        stock.ecom_stock = new_qty
        stock.save(update_fields=['stock', 'ecom_stock', 'updated_at'])
        StockTransaction.objects.create(
            product=product,
            user=user,
            transaction_type='ADJUST',
            stock_type='ECOM',
            quantity=new_qty,
            reason='Bulk ecom inventory update',
        )
        updated += 1
    return updated, skipped


@transaction.atomic
def bulk_set_ecom_prices(company, prices):
    """prices: {product_id: {'price': str|None, 'compare_at_price': str|None}}.
    A blank compare-at clears the discount. Returns (updated, skipped)."""
    updated, skipped = 0, []
    products = Product.objects.filter(id__in=prices.keys(), company=company).select_for_update()
    for product in products:
        entry = prices[str(product.id)]
        changed = False

        raw_price = entry.get('price')
        if raw_price not in (None, ''):
            try:
                new_price = Decimal(raw_price)
            except (InvalidOperation, TypeError):
                skipped.append((product.name, f'invalid price “{raw_price}”'))
                continue
            if new_price < 0:
                skipped.append((product.name, 'price cannot be negative'))
                continue
            if new_price != product.price:
                product.price = new_price
                changed = True

        if 'compare_at_price' in entry:
            raw_cmp = entry.get('compare_at_price')
            if raw_cmp in (None, ''):
                new_cmp = None
            else:
                try:
                    new_cmp = Decimal(raw_cmp)
                except (InvalidOperation, TypeError):
                    skipped.append((product.name, f'invalid compare-at “{raw_cmp}”'))
                    continue
                if new_cmp < 0:
                    skipped.append((product.name, 'compare-at cannot be negative'))
                    continue
            if new_cmp != product.compare_at_price:
                product.compare_at_price = new_cmp
                changed = True

        if changed:
            product.save(update_fields=['price', 'compare_at_price', 'updated_at'])
            updated += 1
    return updated, skipped
