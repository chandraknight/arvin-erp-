"""
Management command: reassign_category_types

Reassigns all existing categories from the catch-all "General" CategoryType
to proper, descriptive CategoryTypes.

Run once per company that needs the fix:
    python manage.py reassign_category_types
    python manage.py reassign_category_types --company "DPSDABU"
    python manage.py reassign_category_types --dry-run
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from apps.products.models import CategoryType, Category
from apps.company.models import Company


# ---------------------------------------------------------------------------
# Configuration: define the new types and which existing category names
# belong to each.  Names are matched case-insensitively.
# ---------------------------------------------------------------------------
CATEGORY_TYPE_MAP = {
    "Physical Goods": [
        "imported",
        "household essentials",
        "kitchen & toilet items",
    ],
    "Lifestyle & Fashion": [
        "jewellery",
        "gold-plated",
        "silver",
        "lifestyle",
    ],
    "Electronics": [
        "electronics & electricals",
    ],
    "Decor & Collectibles": [
        "antique & decor",
    ],
}


class Command(BaseCommand):
    help = "Reassign categories from 'General' to proper CategoryTypes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--company",
            type=str,
            default=None,
            help="Company name to process (default: all companies).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview changes without saving.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        company_name = options["company"]

        companies = (
            Company.objects.filter(name=company_name)
            if company_name
            else Company.objects.all()
        )

        if not companies.exists():
            self.stderr.write(self.style.ERROR(f"No company found: {company_name}"))
            return

        for company in companies:
            self.stdout.write(f"\nProcessing: {company.name}")
            with transaction.atomic():
                self._process_company(company, dry_run)
                if dry_run:
                    transaction.set_rollback(True)

        if dry_run:
            self.stdout.write(self.style.WARNING("\n[DRY RUN] No changes saved."))
        else:
            self.stdout.write(self.style.SUCCESS("\nDone."))

    def _process_company(self, company, dry_run):
        # Build lookup: lower(category name) → Category instance
        cat_lookup = {
            c.name.lower(): c
            for c in Category.objects.filter(company=company)
        }

        for type_name, cat_names in CATEGORY_TYPE_MAP.items():
            # Get or create the target CategoryType
            ct, created = CategoryType.objects.get_or_create(
                company=company,
                name=type_name,
            )
            action = "Created" if created else "Found"
            self.stdout.write(f"  {action} CategoryType: {type_name}")

            for cat_name_lower in cat_names:
                cat = cat_lookup.get(cat_name_lower)
                if not cat:
                    self.stdout.write(
                        self.style.WARNING(f"    Category not found: '{cat_name_lower}' — skipping")
                    )
                    continue

                old_type = cat.type.name if cat.type else "None"
                if cat.type == ct:
                    self.stdout.write(f"    '{cat.name}' already → {type_name}")
                    continue

                self.stdout.write(
                    self.style.SUCCESS(
                        f"    '{cat.name}': {old_type} → {type_name}"
                        + (" [DRY RUN]" if dry_run else "")
                    )
                )
                if not dry_run:
                    cat.type = ct
                    cat.save(update_fields=["type", "updated_at"])

        # Report any categories still on "General"
        general_ct = CategoryType.objects.filter(company=company, name="General").first()
        if general_ct:
            remaining = Category.objects.filter(company=company, type=general_ct)
            if remaining.exists():
                self.stdout.write(
                    self.style.WARNING(
                        f"\n  Still on 'General': {[c.name for c in remaining]}"
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        "\n  'General' CategoryType is now empty — you may delete it."
                    )
                )
