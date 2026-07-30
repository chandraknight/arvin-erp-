from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0018_package_ecom_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='packageitem',
            name='item_type',
            field=models.CharField(
                choices=[
                    ('core', 'Core (always included, mandatory)'),
                    ('optional', 'Optional (pre-selected, customer can remove)'),
                    ('addon', 'Add-on (not selected, customer can add)'),
                ],
                default='core',
                help_text='Core = always in bundle. Optional = pre-selected, customer can deselect. Add-on = customer can add.',
                max_length=10,
            ),
        ),
    ]
