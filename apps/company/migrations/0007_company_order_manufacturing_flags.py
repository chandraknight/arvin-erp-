"""Add enable_order_management and enable_manufacturing flags to Company."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('company', '0006_company_organisation_type_vat'),
    ]

    operations = [
        migrations.AddField(
            model_name='company',
            name='enable_order_management',
            field=models.BooleanField(
                default=False,
                help_text='Enable Sales Orders and Delivery Management module.',
            ),
        ),
        migrations.AddField(
            model_name='company',
            name='enable_manufacturing',
            field=models.BooleanField(
                default=False,
                help_text='Enable Manufacturing module (BOM, Work Orders, Production Runs).',
            ),
        ),
    ]
