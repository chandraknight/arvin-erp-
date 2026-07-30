"""
Management command: dump_catalog_mysql
Outputs MySQL INSERT statements for CategoryType, Category, and Product.

Usage:
    python manage.py dump_catalog_mysql                         # all companies
    python manage.py dump_catalog_mysql --company <uuid>        # single company
    python manage.py dump_catalog_mysql --output catalog.sql    # write to file
"""

import sys
from django.core.management.base import BaseCommand
from apps.products.models import CategoryType, Category, Product


def _esc(val):
    """Escape a value for MySQL string literal."""
    if val is None:
        return 'NULL'
    return "'" + str(val).replace('\\', '\\\\').replace("'", "\\'") + "'"


def _dec(val):
    return 'NULL' if val is None else str(val)


def _bool(val):
    return '1' if val else '0'


class Command(BaseCommand):
    help = 'Dump CategoryType, Category, and Product as MySQL INSERT statements.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--company', dest='company', default=None,
            help='UUID of the company to dump (omit for all companies).',
        )
        parser.add_argument(
            '--output', dest='output', default=None,
            help='File path to write the SQL (default: stdout).',
        )

    def handle(self, *args, **options):
        company_id = options['company']
        output_path = options['output']

        lines = []
        lines.append('-- ERP Billing Engine — catalog dump')
        lines.append('-- Tables: products_categorytype, products_category, products_product')
        lines.append('SET NAMES utf8mb4;')
        lines.append('SET FOREIGN_KEY_CHECKS = 0;')
        lines.append('')

        # ── CategoryType ──────────────────────────────────────────────────────
        ct_qs = CategoryType.active_objects.all().order_by('created_at')
        if company_id:
            ct_qs = ct_qs.filter(company_id=company_id)

        lines.append('-- CategoryType')
        for ct in ct_qs:
            lines.append(
                f"INSERT INTO products_categorytype "
                f"(id, company_id, name, created_at, updated_at, is_deleted) VALUES ("
                f"{_esc(ct.id)}, {_esc(ct.company_id)}, {_esc(ct.name)}, "
                f"{_esc(ct.created_at)}, {_esc(ct.updated_at)}, {_bool(ct.is_deleted)}"
                f");"
            )
        lines.append('')

        # ── Category ──────────────────────────────────────────────────────────
        cat_qs = Category.active_objects.select_related('type').all().order_by('created_at')
        if company_id:
            cat_qs = cat_qs.filter(company_id=company_id)

        lines.append('-- Category')
        for cat in cat_qs:
            lines.append(
                f"INSERT INTO products_category "
                f"(id, company_id, name, parent_id, type_id, created_at, updated_at, is_deleted) VALUES ("
                f"{_esc(cat.id)}, {_esc(cat.company_id)}, {_esc(cat.name)}, "
                f"{_esc(cat.parent_id)}, {_esc(cat.type_id)}, "
                f"{_esc(cat.created_at)}, {_esc(cat.updated_at)}, {_bool(cat.is_deleted)}"
                f");"
            )
        lines.append('')

        # ── Product ───────────────────────────────────────────────────────────
        prod_qs = (
            Product.active_objects
            .select_related('category', 'purchase_unit', 'sale_unit', 'vendor')
            .all()
            .order_by('created_at')
        )
        if company_id:
            prod_qs = prod_qs.filter(company_id=company_id)

        lines.append('-- Product')
        for p in prod_qs:
            lines.append(
                f"INSERT INTO products_product "
                f"(id, company_id, name, category_id, barcode, sku, vendor_id, "
                f"price, compare_at_price, cost_price, cost_method, nrv, hscode, "
                f"is_service, show_on_ecom, short_description, ecom_description, color, "
                f"purchase_unit_id, sale_unit_id, conversion_factor, has_variants, "
                f"created_at, updated_at, is_deleted) VALUES ("
                f"{_esc(p.id)}, {_esc(p.company_id)}, {_esc(p.name)}, {_esc(p.category_id)}, "
                f"{_esc(p.barcode)}, {_esc(p.sku)}, {_esc(p.vendor_id)}, "
                f"{_dec(p.price)}, {_dec(p.compare_at_price)}, {_dec(p.cost_price)}, "
                f"{_esc(p.cost_method)}, {_dec(p.nrv)}, {_esc(p.hscode)}, "
                f"{_bool(p.is_service)}, {_bool(p.show_on_ecom)}, "
                f"{_esc(p.short_description)}, {_esc(p.ecom_description)}, {_esc(p.color)}, "
                f"{_esc(p.purchase_unit_id)}, {_esc(p.sale_unit_id)}, {_dec(p.conversion_factor)}, "
                f"{_bool(p.has_variants)}, "
                f"{_esc(p.created_at)}, {_esc(p.updated_at)}, {_bool(p.is_deleted)}"
                f");"
            )
        lines.append('')
        lines.append('SET FOREIGN_KEY_CHECKS = 1;')

        sql = '\n'.join(lines)

        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(sql)
            self.stdout.write(self.style.SUCCESS(f'Written to {output_path}'))
        else:
            sys.stdout.write(sql + '\n')
