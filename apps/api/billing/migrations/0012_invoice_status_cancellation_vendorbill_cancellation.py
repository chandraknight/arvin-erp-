from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Situation:
      - Migration 0003 removed Invoice.status from Django's migration STATE,
        but the column was never actually dropped from the PostgreSQL database.
      - billing_vendorbill.status also already exists in the DB.

    Strategy:
      - Use SeparateDatabaseAndState to re-add Invoice.status to Django's
        migration state WITHOUT issuing any DDL (the column is already there).
      - Add Invoice.cancellation_reason and VendorBill.cancellation_reason
        normally (these are genuinely new columns).
    """

    dependencies = [
        ('billing', '0011_add_invoice_branch'),
    ]

    operations = [
        # Re-introduce Invoice.status into Django's migration state only.
        # The column already exists in the DB so database_forwards is a no-op.
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='invoice',
                    name='status',
                    field=models.CharField(
                        max_length=10,
                        choices=[
                            ('DRAFT',     'Draft'),
                            ('ISSUED',    'Issued'),
                            ('CANCELLED', 'Cancelled'),
                        ],
                        default='DRAFT',
                        help_text='DRAFT = editable; ISSUED = locked; CANCELLED = voided.',
                    ),
                ),
            ],
            database_operations=[],   # column already exists — do nothing
        ),

        # Add Invoice.cancellation_reason — genuinely new column
        migrations.AddField(
            model_name='invoice',
            name='cancellation_reason',
            field=models.TextField(
                blank=True,
                null=True,
                help_text='Required when cancelling an issued invoice.',
            ),
        ),

        # Add VendorBill.cancellation_reason — genuinely new column
        migrations.AddField(
            model_name='vendorbill',
            name='cancellation_reason',
            field=models.TextField(
                blank=True,
                null=True,
                help_text='Required when cancelling a vendor bill.',
            ),
        ),
    ]
