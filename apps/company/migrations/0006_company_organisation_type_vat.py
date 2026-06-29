"""
Migration 0006 — Company organisation type, VAT configuration, and feature flags.

Adds to Company:
  organisation_type  — TRADING | SERVICE | PROJECT | NGO | MANUFACTURING | OTHER
  vat_registered     — bool (default False)
  vat_number         — PAN/VAT registration number
  vat_inclusive      — prices include VAT (default False = exclusive)
  enable_branch_accounting — bool, enables branch-wise P&L
  enable_project_tracking  — bool, enables project/cost-centre module
  enable_forecasting       — bool, enables budget & forecast module
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('company', '0005_fiscalyear_closed_at_fiscalyear_closed_by_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='company',
            name='organisation_type',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('TRADING',       'Trading / Retail'),
                    ('SERVICE',       'Service'),
                    ('PROJECT',       'Project-Based'),
                    ('NGO',           'NGO / Non-Profit'),
                    ('MANUFACTURING', 'Manufacturing'),
                    ('OTHER',         'Other'),
                ],
                default='TRADING',
                help_text='Nature of the organisation — drives which modules are available.',
            ),
        ),
        migrations.AddField(
            model_name='company',
            name='vat_registered',
            field=models.BooleanField(
                default=False,
                help_text='Is this company registered for VAT/PAN?',
            ),
        ),
        migrations.AddField(
            model_name='company',
            name='vat_number',
            field=models.CharField(
                max_length=50, blank=True, null=True,
                help_text='PAN / VAT registration number.',
            ),
        ),
        migrations.AddField(
            model_name='company',
            name='vat_inclusive',
            field=models.BooleanField(
                default=False,
                help_text='If True, listed prices already include VAT (tax-inclusive pricing).',
            ),
        ),
        migrations.AddField(
            model_name='company',
            name='enable_branch_accounting',
            field=models.BooleanField(
                default=False,
                help_text='Enable branch-wise reporting and transaction tagging.',
            ),
        ),
        migrations.AddField(
            model_name='company',
            name='enable_project_tracking',
            field=models.BooleanField(
                default=False,
                help_text='Enable project / cost-centre module (auto-enabled for PROJECT type).',
            ),
        ),
        migrations.AddField(
            model_name='company',
            name='enable_forecasting',
            field=models.BooleanField(
                default=False,
                help_text='Enable budget and revenue/expense forecasting module.',
            ),
        ),
    ]
