from django.contrib.auth.decorators import login_required, permission_required
from django.http import JsonResponse
import traceback

from ..utils.global_models import *
from .services.all_services import *

# Set up logging
logger = logging.getLogger(__name__)

from .models import Product, Category, ProductStock, StockTransaction, Package, PackageItem, UnitOfMeasure, ProductVariant
from .forms import ItemForm, StockTransactionForm, CategoryForm, PackageForm, PackageItemForm

# Create your views here.

@login_required
def inventory_management(request):

    if not (request.user.has_perm('products.view_product') or
            request.user.is_superuser or
            (request.user.groups and request.user.groups.first().name == 'Admin')):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("You don't have permission to view inventory.")

    try:
        packages_per_page = int(request.GET.get('packages_per_page', 5))
    except (ValueError, TypeError):
        packages_per_page = 5

    try:
        products_per_page = int(request.GET.get('products_per_page', 5))  # New products pagination
    except (ValueError, TypeError):
        products_per_page = 5

    q = request.GET.get('q', '').strip()
    category_filter = request.GET.get('category_filter', '').strip()

    if request.user.company:
        products_queryset = Product.active_objects.filter(
            company=request.user.company
        ).prefetch_related('images', 'productstock').order_by('name')
        products_count = products_queryset.count()
        low_stock_products = Product.active_objects.filter(
            company=request.user.company,
            is_service=False
        ).filter(
            Q(productstock__stock__lte=F('productstock__minimum_stock')) |
            Q(productstock__ecom_stock__lte=F('productstock__ecom_minimum_stock'))
        ).prefetch_related('productstock')
        low_stock_products_count = low_stock_products.count()
        transactions = StockTransaction.objects.filter(
            product__company=request.user.company
        ).order_by('-created_at')[:10]

        categories_queryset = Category.objects.filter(company=request.user.company).select_related('type').order_by('type__name', 'name')
        categories_count = categories_queryset.count()
        # Group categories by type for the template
        _cat_types = CategoryType.active_objects.filter(company=request.user.company).order_by('name')
        _cat_map = {}
        for c in categories_queryset:
            key = c.type_id
            if key not in _cat_map:
                _cat_map[key] = {'type': c.type, 'categories': []}
            _cat_map[key]['categories'].append(c)
        # categories with no type go under a virtual "Uncategorised" bucket
        _uncategorised = [c for c in categories_queryset if c.type_id is None]
        category_groups = list(_cat_map.values())
        if _uncategorised:
            category_groups.append({'type': None, 'categories': _uncategorised})
        packages_queryset = Package.objects.filter(
            items__product__company=request.user.company
        ).distinct().prefetch_related('items__product').order_by('name')
        packages_count = packages_queryset.count()
    else:
        products_queryset = Product.active_objects.all().order_by('name')
        products_count = products_queryset.count()
        low_stock_products = Product.active_objects.filter(is_service=False).filter(
            Q(productstock__stock__lte=F('productstock__minimum_stock')) |
            Q(productstock__ecom_stock__lte=F('productstock__ecom_minimum_stock'))
        ).prefetch_related('productstock')
        low_stock_products_count = low_stock_products.count()
        transactions = StockTransaction.active_objects.all().order_by('-created_at')[:10]

        categories_queryset = Category.active_objects.all().select_related('type').order_by('type__name', 'name')
        categories_count = categories_queryset.count()
        _cat_map = {}
        for c in categories_queryset:
            key = c.type_id
            if key not in _cat_map:
                _cat_map[key] = {'type': c.type, 'categories': []}
            _cat_map[key]['categories'].append(c)
        _uncategorised = [c for c in categories_queryset if c.type_id is None]
        category_groups = list(_cat_map.values())
        if _uncategorised:
            category_groups.append({'type': None, 'categories': _uncategorised})
        packages_queryset = Package.active_objects.all().prefetch_related('items__product').order_by('name')
        packages_count = packages_queryset.count()

    if q:
        products_queryset = products_queryset.filter(
            Q(name__icontains=q) | Q(barcode__icontains=q) | Q(sku__icontains=q)
        )
    if category_filter:
        products_queryset = products_queryset.filter(category__id=category_filter)

    products_count = products_queryset.count()

    products_paginator = Paginator(products_queryset, products_per_page)
    products_page = request.GET.get('products_page', 1)
    try:
        products_page = int(products_page)
        products = products_paginator.page(products_page)
    except (PageNotAnInteger, ValueError):
        products = products_paginator.page(1)
    except EmptyPage:
        products = products_paginator.page(products_paginator.num_pages)


    packages_paginator = Paginator(packages_queryset, packages_per_page)
    packages_page = request.GET.get('packages_page', 1)
    try:
        packages_page = int(packages_page)
        packages = packages_paginator.page(packages_page)
    except (PageNotAnInteger, ValueError):
        packages = packages_paginator.page(1)
    except EmptyPage:
        packages = packages_paginator.page(packages_paginator.num_pages)

    return render(request, 'products/inventory_management.html', {
        'products_count': products_count,
        'low_stock_products_count': low_stock_products_count,
        'categories_count': categories_count,
        'packages_count': packages_count,
        'products': products,
        'low_stock_products': low_stock_products,
        'transactions': transactions,
        'category_groups': category_groups,
        'packages': packages,
        'rupee': RUPEE,
        'products_paginator': products_paginator,
        'packages_paginator': packages_paginator,
        'products_per_page': products_per_page,
        'packages_per_page': packages_per_page,
        'q': q,
        'category_filter': category_filter,
        'all_categories': categories_queryset,
    })


@login_required
def all_products(request):
    if not (request.user.has_perm('products.view_product') or
            request.user.is_superuser or
            (request.user.groups and request.user.groups.first().name == 'Admin')):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("You don't have permission to view inventory.")

    try:
        products_per_page = int(request.GET.get('products_per_page', 20))
    except (ValueError, TypeError):
        products_per_page = 20

    q = request.GET.get('q', '').strip()
    category_filter = request.GET.get('category_filter', '').strip()

    if request.user.company:
        products_queryset = Product.active_objects.filter(
            company=request.user.company
        ).prefetch_related('images', 'productstock').order_by('name')
        categories_queryset = Category.objects.filter(company=request.user.company).order_by('name')
    else:
        products_queryset = Product.active_objects.all().order_by('name')
        categories_queryset = Category.active_objects.all().order_by('name')

    if q:
        products_queryset = products_queryset.filter(
            Q(name__icontains=q) | Q(barcode__icontains=q) | Q(sku__icontains=q)
        )
    if category_filter:
        products_queryset = products_queryset.filter(category__id=category_filter)

    products_paginator = Paginator(products_queryset, products_per_page)
    products_page = request.GET.get('products_page', 1)
    try:
        products_page = int(products_page)
        products = products_paginator.page(products_page)
    except (PageNotAnInteger, ValueError):
        products = products_paginator.page(1)
    except EmptyPage:
        products = products_paginator.page(products_paginator.num_pages)

    return render(request, 'products/all_products.html', {
        'products': products,
        'rupee': RUPEE,
        'products_per_page': products_per_page,
        'q': q,
        'category_filter': category_filter,
        'all_categories': categories_queryset,
    })


@login_required
@permission_required('products.delete_package', raise_exception=True)
def delete_package(request, package_id):
    package = get_object_or_404(Package, id=package_id)
    if request.method == 'POST':
        try:
            package_name = package.name
            package.delete()
            messages.success(request, f"Package '{package_name}' has been deleted.")
        except Exception as e:
            messages.error(request, f"An error occurred while deleting the package: {str(e)}")
            logger.error(f"Error deleting package {package_id}: {str(e)}")
    return redirect('products:inventory_management')




@login_required
@permission_required('products.view_product', raise_exception=True)
def search_items_by_barcode(request):
    logger.info(f"search_items_by_barcode received request. Method: {request.method}")
    if request.method == 'GET':
        query = request.GET.get('term', '')
        logger.info(f"Search query received: '{query}'")
        if query:
            try:
                products = Product.objects.filter(
                    Q(barcode__startswith=query) | Q(sku__startswith=query) | Q(name__icontains=query) | Q(is_service=True)
                )[:10]
                results = []
                for product in products:
                    results.append({
                        'id': product.id,
                        'label': f'{product.name} ({product.barcode}) - Rs. {product.price}',
                        'value': product.barcode,
                        'price': str(product.price),
                        'name': product.name,
                    })
                logger.info(f"Returning {len(results)} products for query '{query}'")
                return JsonResponse({'products': results}, safe=False)
            except Exception as e:
                logger.error(f"Error during product search for query '{query}': {e}")
                return JsonResponse({'error': f'Server error during search: {e}'}, status=500)
        # Return an empty list of products if query is empty
        logger.info("No query provided or empty query, returning empty products list.")
        return JsonResponse({'products': []}, safe=False)
    # Return a 400 error for non-GET requests
    logger.warning(f"Invalid request method: {request.method} for search_items_by_barcode.")
    return JsonResponse({'error': 'Invalid request method.'}, status=400)

@login_required
def advanced_inventory_analytics(request):
    """
    Comprehensive inventory analytics with advanced predictive insights
    
    Logging Levels:
    - INFO: General processing information
    - WARNING: Non-critical issues
    - ERROR: Product-specific processing errors
    - CRITICAL: Entire view failure
    """
    # Log the start of the analytics generation
    logger.info(f"Starting advanced inventory analytics for user {request.user.username}")
    
    try:
        # Performance tracking
        start_time = timezone.now()

        # Filter by company — superusers see all, regular users are scoped to their tenant
        if request.user.is_superuser:
            products = Product.objects.all()
            stock_transactions = StockTransaction.objects.all()
        elif request.user.company:
            products = Product.objects.filter(company=request.user.company)
            stock_transactions = StockTransaction.objects.filter(
                product__company=request.user.company
            )
        else:
            # Non-superuser with no company — block access (CompanyIsolationMiddleware
            # should have caught this, but defend in depth)
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied(
                "Your account is not associated with a company. "
                "Please contact your administrator."
            )

        # Advanced Stock Turnover Analysis
        stock_turnover_data = []
        inventory_health_metrics = {
            'total_products': len(products),
            'high_risk_products': 0,
            'medium_risk_products': 0,
            'low_risk_products': 0,
        }

        # Track processing statistics
        processed_products = 0
        error_products = 0

        for product in products:
            try:
                # Get stock transactions for this product in the last 180 days
                recent_transactions = stock_transactions.filter(
                    product=product, 
                    created_at__gte=timezone.now() - timedelta(days=180)
                )

                # Calculate advanced stock metrics
                total_removed = recent_transactions.filter(
                    transaction_type='REMOVE'
                ).aggregate(total=Sum('quantity'))['total'] or 0
                
                total_added = recent_transactions.filter(
                    transaction_type='ADD'
                ).aggregate(total=Sum('quantity'))['total'] or 0
                
                days = 180
                avg_daily_usage = total_removed / days if days > 0 else 0
                avg_daily_replenishment = total_added / days if days > 0 else 0

                # Current stock
                current_stock = product.productstock.stock if hasattr(product, 'productstock') else 0
                minimum_stock = product.productstock.minimum_stock if hasattr(product, 'productstock') else 0

                # Advanced stock health calculations
                if avg_daily_usage > 0:
                    days_of_stock = current_stock / avg_daily_usage
                    stock_coverage_ratio = days_of_stock / 30
                else:
                    # If usage is 0, we only have 0 days of stock if we are already out
                    days_of_stock = float('inf') if current_stock > 0 else 0
                    stock_coverage_ratio = float('inf') if current_stock > 0 else 0

                # Predictive trend analysis using linear regression
                try:
                    daily_transactions = recent_transactions.annotate(
                        day=TruncDay('created_at')
                    ).values('day').annotate(
                        daily_usage=Sum(
                            Case(
                                When(transaction_type='REMOVE', then=F('quantity')),
                                default=0
                            )
                        )
                    ).order_by('day')

                    x = list(range(len(daily_transactions)))
                    y = [t['daily_usage'] for t in daily_transactions]
                    
                    if len(y) > 1:
                        import numpy as np
                        slope, intercept = np.polyfit(x, y, 1)
                        if slope > 0.1:
                            trend = 'Increasing'
                        elif slope < -0.1:
                            trend = 'Decreasing'
                        else:
                            trend = 'Stable'
                    else:
                        slope = 0
                        trend = 'New/Stable' if avg_daily_usage == 0 else 'Stable'

                except Exception as trend_error:
                    logger.warning(f"Trend analysis failed for product {product.id}: {trend_error}")
                    slope, trend = 0, 'Insufficient Data'

                # Stockout risk assessment (The "Exact Calculation")
                # 1. Critical: Already out of stock
                if current_stock <= 0:
                    stockout_risk = 'High'
                # 2. Urgent: Less than 15 days of stock based on current sales
                elif days_of_stock <= 15:
                    stockout_risk = 'High'
                # 3. Warning: Below minimum safety stock set by admin
                elif current_stock <= minimum_stock:
                    stockout_risk = 'Medium'
                # 4. Caution: Between 15 and 30 days of stock
                elif days_of_stock <= 30:
                    stockout_risk = 'Medium'
                # 5. Safe: Plenty of stock or no sales pressure
                else:
                    stockout_risk = 'Low'

                # Update health metrics for the dashboard
                if stockout_risk == 'High':
                    inventory_health_metrics['high_risk_products'] += 1
                elif stockout_risk == 'Medium':
                    inventory_health_metrics['medium_risk_products'] += 1
                else:
                    inventory_health_metrics['low_risk_products'] += 1

                # Prepare data for frontend
                stock_turnover_data.append({
                    'product': product,
                    'avg_daily_usage': round(avg_daily_usage, 2),
                    'avg_daily_replenishment': round(avg_daily_replenishment, 2),
                    'current_stock': current_stock,
                    'minimum_stock': minimum_stock,
                    'days_of_stock': round(days_of_stock, 2),
                    'stock_coverage_ratio': round(stock_coverage_ratio, 2),
                    'stockout_risk': stockout_risk,
                    'usage_trend': trend,
                    'usage_trend_slope': round(slope, 4)
                })

                processed_products += 1

            except Exception as product_error:
                error_products += 1
                logger.error(
                    f"Error processing product {product.id}: {product_error}. "
                    f"Traceback: {traceback.format_exc()}"
                )
                continue

        # Sort by stockout risk and usage trend
        stock_turnover_data.sort(key=lambda x: 
            (
                {'High': 0, 'Medium': 1, 'Low': 2}[x['stockout_risk']],
                -abs(x['usage_trend_slope'])
            )
        )

        # Inventory Forecasting with more advanced techniques
        forecast_data = []
        for product in products:
            try:
                transactions = stock_transactions.filter(
                    product=product, 
                    created_at__gte=timezone.now() - timedelta(days=180)
                ).order_by('created_at')

                if transactions.exists():
                    # Exponential weighted moving average forecast
                    quantities = [t.quantity for t in transactions if t.transaction_type == 'REMOVE']
                    
                    if quantities:
                        # Simple exponential smoothing
                        alpha = 0.3  # Smoothing factor
                        forecast = sum(
                            [quantities[i] * (alpha * (1-alpha)**i) for i in range(len(quantities))]
                        )
                        
                        forecast_data.append({
                            'product': product,
                            'forecast_30_days': round(forecast, 2),
                            'historical_avg': round(sum(quantities) / len(quantities), 2),
                            'historical_std': round(
                                (sum((q - sum(quantities) / len(quantities)) ** 2 for q in quantities) / len(quantities)) ** 0.5, 2
                            )
                        })

            except Exception as forecast_error:
                logger.error(
                    f"Forecasting error for product {product.id}: {forecast_error}. "
                    f"Traceback: {traceback.format_exc()}"
                )
                continue

        # Performance logging
        end_time = timezone.now()
        processing_duration = (end_time - start_time).total_seconds()

        # Log processing statistics
        logger.info(
            f"Inventory Analytics Processing Summary: "
            f"Total Products: {len(products)}, "
            f"Processed: {processed_products}, "
            f"Errors: {error_products}, "
            f"Duration: {processing_duration:.2f} seconds"
        )

        context = {
            'stock_turnover_data': stock_turnover_data,
            'forecast_data': forecast_data,
            'inventory_health_metrics': inventory_health_metrics,
            'processing_stats': {
                'total_products': len(products),
                'processed_products': processed_products,
                'error_products': error_products,
                'processing_duration': round(processing_duration, 2)
            }
        }

        return render(request, 'products/advanced_inventory_analytics.html', context)

    except Exception as e:
        # Critical error handling
        logger.critical(
            f"Critical error in advanced inventory analytics: {e}. "
            f"Traceback: {traceback.format_exc()}"
        )
        messages.error(request, "An error occurred while generating inventory analytics. Please try again later.")
        return redirect('products:inventory_management')  # Fallback redirect


# ── Bulk Product Upload ───────────────────────────────────────────────────────

@login_required
def bulk_product_upload(request):
    from .services.bulk_upload_service import parse_and_import_products
    company = request.user_company if hasattr(request, 'user_company') else getattr(request.user, 'company', None)

    results = None
    if request.method == 'POST':
        uploaded = request.FILES.get('csv_file')
        if not uploaded:
            messages.error(request, 'Please select a CSV file to upload.')
        elif not uploaded.name.lower().endswith('.csv'):
            messages.error(request, 'Only CSV files are accepted.')
        elif not company:
            messages.error(request, 'No company associated with your account.')
        else:
            results = parse_and_import_products(uploaded, company, request.user)
            if results['errors'] and not results['created'] and not results['updated']:
                messages.error(request, 'Upload failed — see errors below.')
            else:
                messages.success(
                    request,
                    f"{results['created']} product(s) created, {results['updated']} updated"
                    + (f", {len(results['errors'])} row(s) skipped." if results['errors'] else '.'),
                )

    return render(request, 'products/bulk_upload.html', {'results': results})


@login_required
def bulk_product_sample_csv(request):
    from .services.bulk_upload_service import generate_sample_csv
    from django.http import HttpResponse
    content = generate_sample_csv()
    resp = HttpResponse(content, content_type='text/csv')
    resp['Content-Disposition'] = 'attachment; filename="products_bulk_upload_sample.csv"'
    return resp


@login_required
def bulk_product_export(request):
    from .services.bulk_upload_service import export_products_csv
    from django.http import HttpResponse
    company = request.user_company if hasattr(request, 'user_company') else getattr(request.user, 'company', None)
    if not company:
        messages.error(request, 'No company associated with your account.')
        return redirect('products:inventory_management')
    content = export_products_csv(company)
    resp = HttpResponse(content, content_type='text/csv')
    resp['Content-Disposition'] = 'attachment; filename="inventory_export.csv"'
    return resp


@login_required
def print_labels(request):
    raw = request.GET.get('ids', '')
    qty_map = {}
    for token in raw.split(','):
        token = token.strip()
        if not token:
            continue
        if ':' in token:
            pid, _, q = token.partition(':')
            qty_map[pid.strip()] = max(1, int(q) if q.strip().isdigit() else 1)
        else:
            qty_map[token] = 1

    company = request.user.company if hasattr(request.user, 'company') else None
    qs = Product.objects.filter(id__in=qty_map.keys())
    if company:
        qs = qs.filter(company=company)

    label_items = []
    for product in qs.only('id', 'name', 'price', 'barcode'):
        qty = qty_map.get(str(product.id), 1)
        for _ in range(qty):
            label_items.append({
                'name': product.name,
                'price': product.price,
                'barcode': product.barcode or '',
            })

    return render(request, 'products/print_labels.html', {'labels': label_items})


# ── Unit of Measure ───────────────────────────────────────────────────────────

@login_required
def print_labels_selector(request):
    company = getattr(request.user, 'company', None)
    qs = Product.active_objects.filter(is_service=False)
    if company:
        qs = qs.filter(company=company)
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(name__icontains=q) | Q(barcode__icontains=q) | Q(sku__icontains=q)
        )
    qs = qs.order_by('name').only('id', 'name', 'barcode', 'sku', 'price')
    paginator = Paginator(qs, 50)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'products/print_labels_selector.html', {
        'products': page_obj,
        'page_obj': page_obj,
        'q': q,
    })


@login_required
def uom_list(request):
    company = getattr(request.user, 'company', None)
    units = UnitOfMeasure.objects.all().order_by('uom_type', 'name').prefetch_related(
        'purchased_products', 'sold_products'
    )
    return render(request, 'products/uom_list.html', {'units': units})


@login_required
def uom_create(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        symbol = request.POST.get('symbol', '').strip()
        uom_type = request.POST.get('uom_type', 'COUNT')
        if not name or not symbol:
            messages.error(request, 'Name and symbol are required.')
            return redirect('products:uom_list')
        if UnitOfMeasure.objects.filter(name__iexact=name).exists():
            messages.error(request, f'Unit "{name}" already exists.')
            return redirect('products:uom_list')
        UnitOfMeasure.objects.create(name=name, symbol=symbol, uom_type=uom_type)
        messages.success(request, f'Unit "{name}" created.')
        return redirect('products:uom_list')
    return redirect('products:uom_list')


@login_required
def uom_delete(request, pk):
    unit = get_object_or_404(UnitOfMeasure, pk=pk)
    if request.method == 'POST':
        try:
            unit.delete()
            messages.success(request, f'Unit "{unit.name}" deleted.')
        except Exception:
            messages.error(request, 'Cannot delete — unit is in use by products.')
    return redirect('products:uom_list')


# ── Product Variants ──────────────────────────────────────────────────────────

@login_required
def variant_list(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    variants = product.variants.filter(is_deleted=False).order_by('size', 'color')
    return render(request, 'products/variant_list.html', {'product': product, 'variants': variants})


@login_required
def variant_create(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    if request.method == 'POST':
        size = request.POST.get('size', '').strip()
        color = request.POST.get('color', '').strip()
        sku = request.POST.get('sku', '').strip() or None
        barcode = request.POST.get('barcode', '').strip() or None
        try:
            price_adj = float(request.POST.get('price_adjustment', 0) or 0)
        except ValueError:
            price_adj = 0
        if not size and not color:
            messages.error(request, 'At least size or color is required.')
            return redirect('products:variant_list', product_id=product_id)
        if ProductVariant.objects.filter(product=product, size__iexact=size, color__iexact=color).exists():
            messages.error(request, f'Variant {size}/{color} already exists.')
            return redirect('products:variant_list', product_id=product_id)
        ProductVariant.objects.create(
            product=product, size=size, color=color,
            sku=sku, barcode=barcode, price_adjustment=price_adj
        )
        if not product.has_variants:
            product.has_variants = True
            product.save(update_fields=['has_variants', 'updated_at'])
        messages.success(request, 'Variant created.')
        return redirect('products:variant_list', product_id=product_id)
    return redirect('products:variant_list', product_id=product_id)


@login_required
def variant_update_stock(request, variant_id):
    variant = get_object_or_404(ProductVariant, pk=variant_id)
    if request.method == 'POST':
        try:
            pos_stock = int(request.POST.get('stock', variant.stock))
            ecom_stock = int(request.POST.get('ecom_stock', variant.ecom_stock))
        except ValueError:
            messages.error(request, 'Invalid stock value.')
            return redirect('products:variant_list', product_id=variant.product_id)
        variant.stock = pos_stock
        variant.ecom_stock = ecom_stock
        variant.save(update_fields=['stock', 'ecom_stock', 'updated_at'])
        messages.success(request, f'Stock updated for {variant}.')
    return redirect('products:variant_list', product_id=variant.product_id)


@login_required
def variant_delete(request, variant_id):
    variant = get_object_or_404(ProductVariant, pk=variant_id)
    product_id = variant.product_id
    if request.method == 'POST':
        variant.soft_delete(deleted_by=request.user)
        messages.success(request, 'Variant deleted.')
    return redirect('products:variant_list', product_id=product_id)
