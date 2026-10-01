"""
Stock Register (stock ledger) — NFRS 2 (IAS 2).

Per product, for a period: Opening + Receipts - Issues = Closing, in quantity
and value. Built from the signed StockTransaction.qty_change ledger, working
backwards from the current on-hand balance so that the closing figures always
agree with the live stock / valuation report.

Value of a movement = qty_change x unit_cost (actual cost at the time), falling
back to the product's current cost_price for rows logged without a cost.
Internal POS <-> E-commerce transfers (qty_change == 0) are not movements and
are excluded.
"""
from datetime import timedelta
from decimal import Decimal

from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.db.models.functions import Coalesce

ZERO = Decimal('0')
_VALUE = ExpressionWrapper(
    F('qty_change') * Coalesce(F('unit_cost'), F('product__cost_price'), output_field=DecimalField(max_digits=14, decimal_places=4)),
    output_field=DecimalField(max_digits=20, decimal_places=4),
)


def _on_hand_value(product, qty):
    if product.cost_method == 'FIFO':
        from .fifo_service import fifo_stock_value
        return fifo_stock_value(product)
    return Decimal(qty) * (product.cost_price or ZERO)


def _after(txns, product_ids, after_date):
    """{product_id: (qty, value)} of movements dated after `after_date`."""
    rows = (
        txns.filter(product_id__in=product_ids, created_at__date__gt=after_date)
        .values('product_id')
        .annotate(q=Sum('qty_change'), v=Sum(_VALUE))
    )
    return {r['product_id']: (r['q'] or 0, r['v'] or ZERO) for r in rows}


def build_stock_register(company, date_from, date_to, category_id=None, product_id=None):
    """
    Returns (rows, totals, lines).

    rows:   one dict per product with activity or a balance — opening/in/out/closing qty & value.
    lines:  chronological movements with running balance; only when product_id is given.
    """
    from ..models import Product, StockTransaction

    products = Product.objects.filter(
        company=company, is_service=False, is_deleted=False,
    ).select_related('productstock', 'category').order_by('category__name', 'name')
    if category_id:
        products = products.filter(category_id=category_id)
    if product_id:
        products = products.filter(pk=product_id)
    products = list(products)
    ids = [p.pk for p in products]

    txns = StockTransaction.objects.filter(is_deleted=False, qty_change__isnull=False).exclude(qty_change=0)
    after_to = _after(txns, ids, date_to)

    period = {}
    for t in txns.filter(
        product_id__in=ids, created_at__date__gte=date_from, created_at__date__lte=date_to,
    ).select_related('product', 'user').order_by('created_at'):
        period.setdefault(t.product_id, []).append(t)

    rows, lines = [], []
    totals = {k: ZERO for k in ('opening_value', 'in_value', 'out_value', 'closing_value')}
    totals.update(opening_qty=0, in_qty=0, out_qty=0, closing_qty=0)

    for p in products:
        stock = getattr(p, 'productstock', None)
        now_qty = (stock.stock + stock.ecom_stock) if stock else 0
        now_value = _on_hand_value(p, now_qty)

        a_q, a_v = after_to.get(p.pk, (0, ZERO))
        closing_qty, closing_value = now_qty - a_q, now_value - a_v
        moves = period.get(p.pk, [])

        in_qty = out_qty = 0
        in_value = out_value = ZERO
        for t in moves:
            cost = t.unit_cost if t.unit_cost is not None else (p.cost_price or ZERO)
            value = Decimal(t.qty_change) * cost
            if t.qty_change > 0:
                in_qty += t.qty_change
                in_value += value
            else:
                out_qty += -t.qty_change
                out_value += -value
        opening_qty = closing_qty - in_qty + out_qty
        opening_value = closing_value - in_value + out_value

        if not (moves or opening_qty or closing_qty):
            continue

        rows.append({
            'product': p, 'category': p.category.name if p.category else '',
            'opening_qty': opening_qty, 'opening_value': opening_value,
            'in_qty': in_qty, 'in_value': in_value,
            'out_qty': out_qty, 'out_value': out_value,
            'closing_qty': closing_qty, 'closing_value': closing_value,
        })
        for k in ('opening', 'in', 'out', 'closing'):
            totals[f'{k}_qty'] += rows[-1][f'{k}_qty']
            totals[f'{k}_value'] += rows[-1][f'{k}_value']

        if product_id:
            bal_qty, bal_value = opening_qty, opening_value
            for t in moves:
                cost = t.unit_cost if t.unit_cost is not None else (p.cost_price or ZERO)
                value = Decimal(t.qty_change) * cost
                bal_qty += t.qty_change
                bal_value += value
                lines.append({
                    'txn': t, 'date': t.created_at, 'reference': t.reference or t.reason,
                    'unit_cost': cost,
                    'in_qty': t.qty_change if t.qty_change > 0 else None,
                    'in_value': value if t.qty_change > 0 else None,
                    'out_qty': -t.qty_change if t.qty_change < 0 else None,
                    'out_value': -value if t.qty_change < 0 else None,
                    'bal_qty': bal_qty, 'bal_value': bal_value,
                })
    return rows, totals, lines
