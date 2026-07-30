"""
NFRS 2 (IAS 2) inventory valuation — lower of cost or net realisable value.

Single source of truth for stock_valuation_report and anything that needs
the current carrying value of inventory (e.g. posting a closing stock
journal entry).
"""
from decimal import Decimal


def compute_stock_valuation(company, category_id=None):
    """
    Returns (rows, totals) for all stocked (non-service) products of `company`.

    Each row: product, category, cost_method, qty, unit_cost, value_at_cost,
    nrv, value_at_nrv, carrying_value, write_down.

    Valuation is against LIVE current stock (ProductStock.stock + ecom_stock),
    not historical as-of-date — accurate only for "right now", not a past
    period-end once further transactions have occurred.
    """
    from ..models import Product

    products = Product.objects.filter(
        company=company, is_service=False
    ).select_related('productstock', 'category').order_by('category__name', 'name')

    if category_id:
        products = products.filter(category_id=category_id)

    rows = []
    total_cost_value = Decimal('0')
    total_nrv_value = Decimal('0')
    total_carrying_value = Decimal('0')

    for product in products:
        stock = getattr(product, 'productstock', None)
        qty = Decimal(stock.stock + stock.ecom_stock) if stock else Decimal('0')
        if qty == 0:
            continue

        cost_price = product.cost_price or Decimal('0')
        value_at_cost = qty * cost_price

        nrv = product.nrv if product.nrv is not None else cost_price
        value_at_nrv = qty * nrv

        carrying_value = min(value_at_cost, value_at_nrv)
        write_down = value_at_cost - carrying_value if value_at_nrv < value_at_cost else Decimal('0')

        rows.append({
            'product': product,
            'category': product.category.name if product.category else '',
            'cost_method': product.get_cost_method_display(),
            'qty': qty,
            'unit_cost': cost_price,
            'value_at_cost': value_at_cost,
            'nrv': nrv,
            'value_at_nrv': value_at_nrv,
            'carrying_value': carrying_value,
            'write_down': write_down,
        })
        total_cost_value += value_at_cost
        total_nrv_value += value_at_nrv
        total_carrying_value += carrying_value

    totals = {
        'total_cost_value': total_cost_value,
        'total_nrv_value': total_nrv_value,
        'total_carrying_value': total_carrying_value,
        'total_write_down': total_cost_value - total_carrying_value,
    }
    return rows, totals
