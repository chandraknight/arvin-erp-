# Generated manually

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('bookkeeping', '0008_remove_ledgeraccount_opening_type'),
        ('payments', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='payment',
            name='payment_type',
            field=models.CharField(choices=[('CUSTOMER', 'Customer Payment'), ('VENDOR', 'Vendor Payment'), ('EXPENSE', 'Expense Payment'), ('SALARY', 'Salary Payment'), ('OTHER', 'Other Payment')], default='CUSTOMER', max_length=20),
        ),
        migrations.AddField(
            model_name='payment',
            name='ledger_account',
            field=models.ForeignKey(blank=True, help_text='Target ledger account for non-customer payments', null=True, on_delete=django.db.models.deletion.SET_NULL, to='bookkeeping.ledgeraccount'),
        ),
        migrations.AddField(
            model_name='payment',
            name='reference_number',
            field=models.CharField(blank=True, help_text='Reference number for payment', max_length=100, null=True),
        ),
    ]
