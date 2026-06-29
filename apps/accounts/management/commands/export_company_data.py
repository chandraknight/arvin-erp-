"""
Export all data for a single company as a JSON fixture loadable on any DB backend.

Usage:
    python manage.py export_company_data DPSDABU --output dpsdabu_fixture.json
"""

import json
from django.core.management.base import BaseCommand, CommandError
from django.core import serializers
from django.apps import apps
from apps.accounts.models import Company


COMPANY_RELATED_MODELS = [
    # order matters: parents before children
    "accounts.User",
    "company.Branch",
    "company.FiscalYear",
    "bookkeeping.LedgerAccount",
    "products.CategoryType",
    "products.Category",
    "products.Package",
    "products.Product",
    "customers.Customer",
    "vendors.Vendor",
    "bookkeeping.FixedAsset",
    "bookkeeping.JournalEntry",
    "billing.Invoice",
    "billing.CreditNote",
    "billing.DebitNote",
    "billing.VendorBill",
    "billing.CBMSSubmission",
    "payments.Payment",
    "orders.SalesOrder",
    "orders.DeliveryNote",
    "purchasing.PurchaseOrder",
    "pos.POSSale",
    "projects.CostCentre",
    "projects.Project",
    "projects.Budget",
    "projects.Forecast",
    "hrpayroll.LeaveType",
    "hrpayroll.JobPosition",
    "hrpayroll.JobApplication",
    "hrpayroll.Employee",
    "hrpayroll.PayrollRun",
    "hrpayroll.PerformanceReview",
    "manufacturing.Machine",
    "manufacturing.BillOfMaterials",
    "manufacturing.WorkOrder",
    "ecom.SiteSettings",
    "ecom.HeroBanner",
    "ecom.Announcement",
    "ecom.Page",
    "ecom.EcomOrder",
    "restaurant.TableSection",
    "restaurant.RestaurantTable",
    "restaurant.PrinterStation",
    "restaurant.PrintJob",
    "restaurant.DiningOrder",
    "tours.TourDestination",
    "tours.TourPackage",
    "tours.TourEnquiry",
    "tours.TourBooking",
    "tours.IATASourceFile",
    "tours.AIRFile",
    "tours.AirTicket",
    "api.APIToken",
]


class Command(BaseCommand):
    help = "Export all data for a company as a JSON fixture"

    def add_arguments(self, parser):
        parser.add_argument("company_name", help="Exact company name (case-insensitive)")
        parser.add_argument("--output", default="company_export.json", help="Output file path")

    def handle(self, *args, **options):
        name = options["company_name"]
        try:
            company = Company.objects.get(name__iexact=name)
        except Company.DoesNotExist:
            raise CommandError(f"Company '{name}' not found")

        self.stdout.write(f"Exporting company: {company.name} (ID: {company.id})")

        all_objects = [company]

        for label in COMPANY_RELATED_MODELS:
            try:
                model = apps.get_model(label)
            except LookupError:
                self.stderr.write(f"  Skipping unknown model: {label}")
                continue

            # Find the company FK field name
            company_field = self._find_company_field(model)
            if not company_field:
                self.stderr.write(f"  No company field on {label}, skipping")
                continue

            qs = model.objects.filter(**{company_field: company})
            count = qs.count()
            if count:
                self.stdout.write(f"  {label}: {count} records")
                all_objects.extend(list(qs))

        output_path = options["output"]
        data = serializers.serialize(
            "json",
            all_objects,
            indent=2,
            use_natural_foreign_keys=False,
            use_natural_primary_keys=False,
        )

        with open(output_path, "w") as f:
            f.write(data)

        self.stdout.write(self.style.SUCCESS(
            f"\nExported {len(all_objects)} total objects to {output_path}"
        ))
        self.stdout.write(
            f"Load on staging with: python manage.py loaddata {output_path}"
        )

    def _find_company_field(self, model):
        for field in model._meta.get_fields():
            if (
                hasattr(field, "related_model")
                and field.related_model
                and field.related_model.__name__ == "Company"
                and hasattr(field, "attname")
            ):
                return field.name
        return None
