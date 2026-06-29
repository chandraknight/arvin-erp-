# Generated migration to add default value for total_amount field

from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0017_invoice_invoice_company_status_idx_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='vendorbill',
            name='total_amount',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=10),
        ),
    ]