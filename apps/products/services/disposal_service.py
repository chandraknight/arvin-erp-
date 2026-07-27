"""
Stock disposal — write off damaged/unusable inventory.

dispose_stock(product, quantity, stock_type, reason, user)
  → decrements ProductStock, logs a StockTransaction, and posts an NFRS
    journal entry (DR Inventory Write-off Expense / CR Inventory Asset).
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction


def _get_or_create_account(company, name, account_type, code=None):
    from apps.bookkeeping.models import LedgerAccount
    acc, _ = LedgerAccount.objects.get_or_create(
        company=company,
        name=name,
        defaults={
            'account_type': account_type,
            'code': code,
            'system_created': True,
            'is_current': account_type not in ('ASSET',),
        },
    )
    return acc


@transaction.atomic
def dispose_stock(product, quantity, stock_type, reason, user):
    from ..models import ProductStock, StockTransaction, StockDisposal
    from apps.bookkeeping.models import post_journal_entry
    from django.utils import timezone

    if quantity <= 0:
        raise ValidationError("Disposal quantity must be greater than zero.")
    if not reason or not reason.strip():
        raise ValidationError("A reason is required to dispose of stock.")

    stock_instance, _ = ProductStock.objects.get_or_create(product=product)

    if stock_type == 'POS':
        if stock_instance.stock < quantity:
            raise ValidationError(
                f"Insufficient POS stock ({stock_instance.stock}) to dispose of {quantity}."
            )
        stock_instance.stock -= quantity
    elif stock_type == 'ECOM':
        if stock_instance.ecom_stock < quantity:
            raise ValidationError(
                f"Insufficient E-commerce stock ({stock_instance.ecom_stock}) to dispose of {quantity}."
            )
        stock_instance.ecom_stock -= quantity
    else:
        raise ValidationError(f"Unknown stock type: {stock_type}")

    stock_instance.save()

    StockTransaction.objects.create(
        product=product,
        user=user,
        transaction_type='DISPOSE',
        stock_type=stock_type,
        quantity=quantity,
        reason=reason,
    )

    company = product.company
    unit_cost = product.cost_price or Decimal('0')
    total_value = (Decimal(quantity) * unit_cost).quantize(Decimal('0.01'))

    journal_entry = None
    if total_value > Decimal('0'):
        writeoff_expense_acc = _get_or_create_account(
            company, 'Inventory Write-off', 'EXPENSE', code='5900'
        )
        inventory_asset_acc = _get_or_create_account(
            company, 'Inventory', 'ASSET', code='1300'
        )
        journal_entry = post_journal_entry(
            company=company,
            date=timezone.now().date(),
            description=f"Stock disposal — {quantity} x {product.name} ({reason[:100]})",
            lines=[
                {'account': writeoff_expense_acc, 'entry_type': 'DEBIT', 'amount': total_value,
                 'narration': f'Write-off of {product.name}'},
                {'account': inventory_asset_acc, 'entry_type': 'CREDIT', 'amount': total_value,
                 'narration': f'Inventory reduction — {product.name}'},
            ],
            created_by=user,
            source_type='STOCK_DISPOSAL',
        )

    disposal = StockDisposal.objects.create(
        product=product,
        stock_type=stock_type,
        quantity=quantity,
        reason=reason,
        unit_cost=unit_cost,
        total_value=total_value,
        disposed_by=user,
        journal_entry=journal_entry,
    )
    return disposal
