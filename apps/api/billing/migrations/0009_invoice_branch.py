"""
Migration 0009 — Add branch FK to Invoice and VendorBill.
Nullable so existing records are unaffected.
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0008_invoice_transaction_date'),
        ('company', '0006_company_organisation_type_vat'),
    ]

    operations = [
        migrations.AddField(
            model_name='invoice',
            name='branch',
            field=models.ForeignKey(
                'company.Branch',
                on_delete=django.db.models.deletion.SET_NULL,
                null=True, blank=True,
                related_name='invoices',
                help_text='Branch this invoice was raised from (optional).',
            ),
        ),
        migrations.AddField(
            model_name='vendorbill',
            name='branch',
            field=models.ForeignKey(
                'company.Branch',
                on_delete=django.db.models.deletion.SET_NULL,
                null=True, blank=True,
                related_name='vendor_bills',
                help_text='Branch this vendor bill belongs to (optional).',
            ),
        ),
    ]
