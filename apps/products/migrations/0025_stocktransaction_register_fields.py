from django.db import migrations, models


def backfill_qty_change(apps, schema_editor):
    """Best-effort signed change for rows logged before qty_change existed.

    ADJUST rows stored the new absolute level, not a delta, so their true effect
    is unrecoverable — they are left at 0 rather than guessed.
    """
    StockTransaction = apps.get_model('products', 'StockTransaction')
    for txn in StockTransaction.objects.filter(qty_change__isnull=True).iterator():
        change = 0
        if txn.transaction_type == 'DISPOSAL':
            change = -txn.quantity
        elif txn.stock_type == 'POS':
            if txn.transaction_type == 'ADD':
                change = txn.quantity
            elif txn.transaction_type == 'REMOVE':
                change = -txn.quantity
        elif txn.transaction_type == 'REMOVE' and (txn.reason or '').startswith('Ecom order'):
            change = -txn.quantity
        StockTransaction.objects.filter(pk=txn.pk).update(qty_change=change)


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0024_remove_product_compare_at_price_remove_product_nrv_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='stocktransaction',
            name='qty_change',
            field=models.IntegerField(blank=True, null=True, help_text='Signed net change in total on-hand (POS + E-commerce). 0 for internal POS/E-commerce transfers.'),
        ),
        migrations.AddField(
            model_name='stocktransaction',
            name='unit_cost',
            field=models.DecimalField(blank=True, decimal_places=4, max_digits=12, null=True, help_text='Cost per unit at the time of the movement (actual FIFO/WA cost consumed or received).'),
        ),
        migrations.AddField(
            model_name='stocktransaction',
            name='reference',
            field=models.CharField(blank=True, default='', max_length=100, help_text='Source document number.'),
        ),
        migrations.RunPython(backfill_qty_change, migrations.RunPython.noop),
    ]
