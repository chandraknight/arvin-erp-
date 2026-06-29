# Generated migration for transaction_date field

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0007_invoiceitem_discount_percent_invoiceitem_discount_amount'),
    ]

    operations = [
        migrations.AddField(
            model_name='invoice',
            name='transaction_date',
            field=models.DateField(default=django.utils.timezone.now, help_text='Date of the invoice transaction'),
        ),
    ]
