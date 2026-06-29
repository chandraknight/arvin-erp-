import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('company', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='APIToken',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('key', models.CharField(
                    editable=False,
                    help_text='64-char hex token generated with secrets.token_hex(32).',
                    max_length=64,
                    unique=True,
                )),
                ('name', models.CharField(
                    help_text='Human-readable label, e.g. "Mobile App", "POS Terminal".',
                    max_length=100,
                )),
                ('scopes', models.JSONField(
                    default=list,
                    help_text='List of scope strings, e.g. ["invoices:read", "customers:read"].',
                )),
                ('expires_at', models.DateTimeField(
                    blank=True,
                    help_text='Expiry datetime. Null = never expires.',
                    null=True,
                )),
                ('last_used_at', models.DateTimeField(
                    blank=True,
                    help_text='Updated on every successful authentication (via update(), not save()).',
                    null=True,
                )),
                ('is_active', models.BooleanField(
                    default=True,
                    help_text='Set to False to revoke the token without deleting it.',
                )),
                ('company', models.ForeignKey(
                    blank=True,
                    help_text='Null for superuser tokens that are not scoped to a single company.',
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='api_tokens',
                    to='company.company',
                )),
                ('created_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='created_apitoken',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('deleted_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='deleted_apitoken',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('updated_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='updated_apitoken',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='api_tokens',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'API Token',
                'verbose_name_plural': 'API Tokens',
                'ordering': ['-created_at'],
            },
        ),
    ]
