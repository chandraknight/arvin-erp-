from django.db import migrations


def fix_mysql_session_data_column(apps, schema_editor):
    if schema_editor.connection.vendor != 'mysql':
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            'ALTER TABLE django_session MODIFY session_data LONGTEXT NOT NULL'
        )


class Migration(migrations.Migration):

    dependencies = [
        ('sessions', '0001_initial'),
        ('accounts', '0006_alter_user_managers'),
    ]

    operations = [
        migrations.RunPython(fix_mysql_session_data_column, migrations.RunPython.noop),
    ]
