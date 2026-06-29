import csv
import io
from decimal import Decimal, InvalidOperation

from django.db import transaction


CSV_COLUMNS = [
    'id', 'name', 'category', 'barcode', 'sku', 'hscode', 'price',
    'compare_at_price', 'cost_price', 'is_service', 'vendor', 'stock',
    'minimum_stock', 'ecom_stock', 'ecom_minimum_stock', 'description',
]
REQUIRED_COLUMNS = {'name', 'category', 'price'}
SAMPLE_ROWS = [
    CSV_COLUMNS,
    ['', 'Momo (Veg)', 'Starters', '', 'SKU-MOMO-V', '', '150.00', '', '60.00', 'FALSE', '', '100', '10', '0', '0', 'Steamed vegetable dumplings'],
    ['', 'Chicken Burger', 'Main Course', '', 'SKU-BURG-CH', '', '280.00', '350.00', '120.00', 'FALSE', '', '50', '5', '0', '0', 'Grilled chicken burger'],
    ['', 'Fresh Lime Soda', 'Beverages', '', 'SKU-SODA-LM', '', '80.00', '', '20.00', 'FALSE', '', '200', '20', '0', '0', 'Fresh lime with soda water'],
]


def generate_sample_csv() -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    for row in SAMPLE_ROWS:
        writer.writerow(row)
    return buf.getvalue().encode('utf-8')


def export_products_csv(company) -> bytes:
    """
    Export all of a company's products in the same column format accepted
    by parse_and_import_products, so the file can be edited and re-uploaded.
    """
    from apps.products.models import Product

    products = (
        Product.objects.filter(company=company)
        .select_related('category', 'vendor', 'productstock')
        .order_by('name')
    )

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_COLUMNS)
    for product in products:
        stock = getattr(product, 'productstock', None)
        writer.writerow([
            product.id,
            product.name,
            product.category.name if product.category else '',
            product.barcode or '',
            product.sku or '',
            product.hscode or '',
            product.price,
            product.compare_at_price if product.compare_at_price is not None else '',
            product.cost_price,
            'TRUE' if product.is_service else 'FALSE',
            product.vendor.name if product.vendor else '',
            stock.stock if stock else 0,
            stock.minimum_stock if stock else 0,
            stock.ecom_stock if stock else 0,
            stock.ecom_minimum_stock if stock else 0,
            product.short_description or '',
        ])
    return buf.getvalue().encode('utf-8')


def parse_and_import_products(file_obj, company, user) -> dict:
    """
    Parse uploaded CSV and bulk-create/update Product + ProductStock records.
    Returns {'created': int, 'updated': int, 'errors': [(row_num, message)]}
    """
    from apps.products.models import Product, ProductStock, Category
    from apps.vendors.models import Vendor

    try:
        text = file_obj.read().decode('utf-8-sig')
    except UnicodeDecodeError:
        file_obj.seek(0)
        text = file_obj.read().decode('latin-1')

    reader = csv.DictReader(io.StringIO(text))

    if reader.fieldnames is None:
        return {'created': 0, 'updated': 0, 'errors': [(0, 'File is empty or has no header row.')]}

    headers = {h.strip().lower() for h in reader.fieldnames}
    missing = REQUIRED_COLUMNS - headers
    if missing:
        return {'created': 0, 'updated': 0, 'errors': [(0, f'Missing required columns: {", ".join(missing)}')]}

    created = 0
    updated = 0
    errors = []

    def to_decimal(raw, default='0'):
        try:
            return Decimal(raw or default)
        except InvalidOperation:
            return Decimal(default)

    def to_non_negative_int(raw):
        try:
            value = int(Decimal(raw or '0'))
            return value if value >= 0 else 0
        except (InvalidOperation, ValueError):
            return 0

    for row_num, raw_row in enumerate(reader, start=2):
        row = {k.strip().lower(): (v or '').strip() for k, v in raw_row.items() if k}

        name = row.get('name', '').strip()
        if not name:
            errors.append((row_num, 'name is required'))
            continue

        category_name = row.get('category', '').strip()
        if not category_name:
            errors.append((row_num, 'category is required'))
            continue

        price_raw = row.get('price', '')
        try:
            price = Decimal(price_raw)
            if price < 0:
                raise ValueError()
        except (InvalidOperation, ValueError):
            errors.append((row_num, f'Invalid price: "{price_raw}"'))
            continue

        compare_raw = row.get('compare_at_price', '').strip()
        if compare_raw == '':
            compare_at_price = None
        else:
            try:
                compare_at_price = Decimal(compare_raw)
                if compare_at_price < 0:
                    raise ValueError()
            except (InvalidOperation, ValueError):
                errors.append((row_num, f'Invalid compare_at_price: "{compare_raw}"'))
                continue

        cost_price = to_decimal(row.get('cost_price'))
        is_service = row.get('is_service', '').strip().upper() in ('TRUE', '1', 'YES')
        description = row.get('description', '')
        barcode = row.get('barcode') or None
        sku = row.get('sku') or None
        hscode = row.get('hscode') or None

        vendor_name = row.get('vendor', '').strip()
        vendor = None
        if vendor_name:
            vendor = Vendor.objects.filter(company=company, name__iexact=vendor_name).first()
            if vendor is None:
                errors.append((row_num, f'Vendor "{vendor_name}" not found — skipped vendor assignment'))

        product_id = row.get('id', '').strip()

        try:
            with transaction.atomic():
                category, _ = Category.objects.get_or_create(
                    company=company,
                    name=category_name,
                    defaults={'created_by': user},
                )

                defaults = {
                    'category': category,
                    'barcode': barcode,
                    'sku': sku,
                    'hscode': hscode,
                    'price': price,
                    'compare_at_price': compare_at_price,
                    'cost_price': cost_price,
                    'short_description': description[:500] if description else '',
                    'is_service': is_service,
                    'vendor': vendor,
                    'updated_by': user,
                }

                if product_id:
                    # Explicit id wins — precise update, immune to duplicate names.
                    try:
                        product = Product.objects.get(id=product_id, company=company)
                    except (Product.DoesNotExist, ValueError):
                        errors.append((row_num, f'No product with id {product_id} in this company'))
                        continue
                    defaults['name'] = name
                    for field, value in defaults.items():
                        setattr(product, field, value)
                    product.save()
                    was_created = False
                else:
                    try:
                        product, was_created = Product.objects.update_or_create(
                            company=company, name=name, defaults=defaults,
                        )
                    except Product.MultipleObjectsReturned:
                        errors.append((row_num, f'Multiple products named "{name}" — add the id column to update the right one'))
                        continue

                if was_created:
                    product.created_by = user
                    product.save(update_fields=['created_by'])

                stock_obj, _ = ProductStock.objects.get_or_create(product=product)
                stock_obj.stock = to_non_negative_int(row.get('stock'))
                stock_obj.minimum_stock = to_non_negative_int(row.get('minimum_stock'))
                stock_obj.ecom_stock = to_non_negative_int(row.get('ecom_stock'))
                stock_obj.ecom_minimum_stock = to_non_negative_int(row.get('ecom_minimum_stock'))
                stock_obj.save(update_fields=['stock', 'minimum_stock', 'ecom_stock', 'ecom_minimum_stock'])

                if was_created:
                    created += 1
                else:
                    updated += 1

        except Exception as exc:
            errors.append((row_num, str(exc)))

    return {'created': created, 'updated': updated, 'errors': errors}
