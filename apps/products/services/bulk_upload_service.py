import csv
import io
from decimal import Decimal, InvalidOperation

from django.db import transaction


CSV_COLUMNS = [
    'id', 'name', 'category', 'barcode', 'sku', 'hscode', 'price',
    'cost_price', 'is_service',
    'purchase_unit', 'default_unit', 'conversion_factor', 'stock',
    'minimum_stock', 'ecom_stock', 'ecom_minimum_stock', 'description',
]
REQUIRED_COLUMNS = {'name', 'category', 'price'}
SAMPLE_ROWS = [
    CSV_COLUMNS,
    ['', 'Momo (Veg)', 'Starters', '', 'SKU-MOMO-V', '', '150.00', '60.00', 'FALSE', '', '', '', '100', '10', '0', '0', 'Steamed vegetable dumplings'],
    ['', 'Chicken Burger', 'Main Course', '', 'SKU-BURG-CH', '', '280.00', '120.00', 'FALSE', '', '', '', '50', '5', '0', '0', 'Grilled chicken burger'],
    ['', 'Rice (retail)', 'Groceries', '', 'SKU-RICE-1', '', '2.00', '1.50', 'FALSE', 'kg', 'g', '1000', '200', '20', '0', '0', 'Sold by the gram, bought by the kg'],
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
        .select_related('category', 'productstock', 'purchase_unit', 'default_unit')
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
            product.cost_price,
            'TRUE' if product.is_service else 'FALSE',
            product.purchase_unit.name if product.purchase_unit else '',
            product.default_unit.name if product.default_unit else '',
            product.conversion_factor,
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
    from apps.products.models import Product, ProductStock, Category, UnitOfMeasure

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

        cost_price = to_decimal(row.get('cost_price'))
        is_service = row.get('is_service', '').strip().upper() in ('TRUE', '1', 'YES')
        description = row.get('description', '')
        barcode = row.get('barcode') or None
        sku = row.get('sku') or None
        hscode = row.get('hscode') or None

        purchase_unit_name = row.get('purchase_unit', '').strip()
        purchase_unit = None
        if purchase_unit_name:
            purchase_unit = UnitOfMeasure.objects.filter(name__iexact=purchase_unit_name).first()
            if purchase_unit is None:
                errors.append((row_num, f'Purchase unit "{purchase_unit_name}" not found — skipped'))

        default_unit_name = row.get('default_unit', '').strip()
        default_unit = None
        if default_unit_name:
            default_unit = UnitOfMeasure.objects.filter(name__iexact=default_unit_name).first()
            if default_unit is None:
                errors.append((row_num, f'Default unit "{default_unit_name}" not found — skipped'))

        conversion_raw = row.get('conversion_factor', '').strip()
        if conversion_raw == '':
            conversion_factor = Decimal('1')
        else:
            try:
                conversion_factor = Decimal(conversion_raw)
                if conversion_factor <= 0:
                    raise ValueError()
            except (InvalidOperation, ValueError):
                errors.append((row_num, f'Invalid conversion_factor: "{conversion_raw}" — using 1'))
                conversion_factor = Decimal('1')

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
                    'cost_price': cost_price,
                    'short_description': description[:500] if description else '',
                    'is_service': is_service,
                    'purchase_unit': purchase_unit,
                    'default_unit': default_unit,
                    'conversion_factor': conversion_factor,
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
