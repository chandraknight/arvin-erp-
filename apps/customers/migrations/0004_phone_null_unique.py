from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('customers', '0003_customer_pan_number'),
    ]

    operations = [
        # Convert empty-string phones to NULL before adding the unique constraint.
        # Standard SQL — works on PostgreSQL, MySQL/MariaDB, and SQLite.
        migrations.RunSQL(
            sql="UPDATE customers_customer SET phone = NULL WHERE phone = '';",
            reverse_sql=migrations.RunSQL.noop,
        ),
        # AlterField lets Django generate the correct DDL per database engine:
        #   PostgreSQL → ALTER COLUMN phone DROP NOT NULL + CREATE UNIQUE INDEX
        #   MySQL/MariaDB → MODIFY COLUMN phone VARCHAR(15) NULL + ADD UNIQUE INDEX
        # On local PostgreSQL the unique index already existed (added outside migrations);
        # we use SeparateDatabaseAndState so PostgreSQL only runs the nullable DDL,
        # while MySQL (which has no prior unique index) runs the full AlterField.
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.AlterField(
                    model_name='customer',
                    name='phone',
                    field=models.CharField(blank=True, max_length=15, null=True, unique=True),
                ),
            ],
            state_operations=[
                migrations.AlterField(
                    model_name='customer',
                    name='phone',
                    field=models.CharField(blank=True, max_length=15, null=True, unique=True),
                ),
            ],
        ),
    ]
