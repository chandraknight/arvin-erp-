from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0020_sequence_number_nullable'),
    ]

    operations = [
        migrations.AddField(
            model_name='invoice',
            name='reference_number',
            field=models.CharField(
                blank=True,
                max_length=100,
                null=True,
                help_text='Optional external reference (customer PO#, contract#, cheque#, etc.).',
            ),
        ),
    ]
