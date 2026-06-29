"""
Load a company fixture while suppressing post_save signals that auto-create
branches and ledger accounts (which would duplicate data already in the fixture).

Usage:
    python manage.py load_company_data dpsdabu_fixture.json
"""

from django.core.management.base import BaseCommand
from django.core import serializers
from django.db import transaction
from django.db.models.signals import post_save
from apps.company.signals import create_main_branch, create_default_ledger_accounts


class Command(BaseCommand):
    help = "Load a company fixture with post_save signals suppressed"

    def add_arguments(self, parser):
        parser.add_argument("fixture", help="Path to the JSON fixture file")

    def handle(self, *args, **options):
        fixture_path = options["fixture"]

        # Disconnect signals that auto-create data already in the fixture
        post_save.disconnect(create_main_branch, sender=None)
        post_save.disconnect(create_default_ledger_accounts, sender=None)

        try:
            with open(fixture_path) as f:
                objects = list(serializers.deserialize("json", f))

            self.stdout.write(f"Loading {len(objects)} objects from {fixture_path}...")

            with transaction.atomic():
                for obj in objects:
                    obj.save()

            self.stdout.write(self.style.SUCCESS(f"Successfully loaded {len(objects)} objects."))

        finally:
            # Always reconnect signals
            from apps.company.signals import create_main_branch, create_default_ledger_accounts
            from apps.company.models import Company
            post_save.connect(create_main_branch, sender=Company)
            post_save.connect(create_default_ledger_accounts, sender=Company)
