"""
Migration 0005 — Add branch FK to Payment.
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0004_repair_vendorpayment_table'),
        ('company', '0006_company_organisation_type_vat'),
    ]

    operations = [
        migrations.AddField(
            model_name='payment',
            name='branch',
            field=models.ForeignKey(
                'company.Branch',
                on_delete=django.db.models.deletion.SET_NULL,
                null=True, blank=True,
                related_name='payments',
                help_text='Branch this payment was recorded at (optional).',
            ),
        ),
    ]
