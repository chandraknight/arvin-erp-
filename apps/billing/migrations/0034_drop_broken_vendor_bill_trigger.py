from django.db import migrations


class Migration(migrations.Migration):
    """
    bookkeeping.0009 installed trg_vendor_bill_total, whose function declares the bill id
    as UUID — but VendorBill has an integer primary key, so every VendorBillItem insert
    on PostgreSQL fails ("invalid input syntax for type uuid"). It also overwrote
    total_amount with the pre-tax subtotal. Totals (incl. VAT) are maintained in Python by
    billing.services.vendor_bill_service.update_vendor_bill_total, so the trigger is dropped.
    """

    dependencies = [
        ('billing', '0033_inventory_perpetual'),
        ('bookkeeping', '0031_inventory_perpetual'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                DROP TRIGGER IF EXISTS trg_vendor_bill_total ON billing_vendorbillitem;
                DROP FUNCTION IF EXISTS trg_fn_vendor_bill_recalc_total();
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
