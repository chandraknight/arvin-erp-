from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from apps.products.models import Product, Package, Category


@login_required()
def get_product_price(request, product_id):
    try:
        qs = Product.active_objects
        if not request.user.is_superuser and hasattr(request.user, 'company'):
            qs = qs.filter(company=request.user.company)
        product = qs.get(pk=product_id)

        price = product.price

        # If selling price is not set, fall back to the most recent purchase price
        # for this product (most recent PurchaseOrderItem by created_at).
        if not price or price == 0:
            from apps.purchasing.models import PurchaseOrderItem
            last_purchase = (
                PurchaseOrderItem.objects
                .filter(product=product, is_deleted=False)
                .order_by('-created_at')
                .values_list('price', flat=True)
                .first()
            )
            if last_purchase:
                price = last_purchase

        # Stock info so the frontend can show available qty
        stock = 0
        try:
            stock = product.productstock.stock
        except Exception:
            pass

        return JsonResponse({
            'price': str(price),
            'hscode': product.hscode or '',
            'stock': stock,
            'cost_price': str(product.cost_price),
        })
    except Product.DoesNotExist:
        return JsonResponse({'error': 'Product not found'}, status=404)


@login_required()
def get_package_detail(request, package_id):
    try:
        qs = Package.objects
        if not request.user.is_superuser and hasattr(request.user, 'company'):
            qs = qs.filter(company=request.user.company)
        package = qs.get(pk=package_id)

        product_names = package.items.values_list('product__name', flat=True)
        product_names = [name for name in product_names if name]

        return JsonResponse({
            'price': str(package.price),
            'products': ', '.join(product_names)
        })
    except Package.DoesNotExist:
        return JsonResponse({'error': 'Package not found'}, status=404)

@login_required()
def get_user_categories(request):
    category_type_id = request.GET.get('category_type_id')
    user = request.user

    categories = Category.active_objects.all()

    if not user.is_superuser:
        categories = categories.filter(company=user.company)

    if category_type_id:
        categories = categories.filter(type_id=category_type_id)

    data = {
        "categories": [{"id": c.id, "name": c.name} for c in categories]
    }
    return JsonResponse(data)

@login_required()
def get_user_products(request):
    category_type_id = request.GET.get('category_type_id')
    user = request.user

    products = Product.active_objects.none()
    if user.is_superuser:
        products = Product.active_objects.all()
    elif user.company:
        products = Product.active_objects.filter(company=user.company)

    if category_type_id:
        products = products.filter(category__type_id=category_type_id)

    data = {
        "products": [{"id": p.id, "name": p.name} for p in products]
    }
    return JsonResponse(data)


@login_required()
def get_user_product_packages(request):
    category_type_id = request.GET.get('category_type_id')
    user = request.user

    products = Product.active_objects.none()
    packages = Package.objects.none()

    if user.is_superuser:
        products = Product.active_objects.all()
        packages = Package.objects.all()
    elif user.company:
        products = Product.active_objects.filter(company=user.company)
        packages = Package.objects.filter(company=user.company)

    if category_type_id:
        products = products.filter(category__type_id=category_type_id)
        packages = packages.filter(items__product__category__type_id=category_type_id).distinct()

    data = {
        "products": [{"id": p.id, "name": p.name} for p in products],
        "packages": [{"id": pkg.id, "name": pkg.name} for pkg in packages],
    }
    return JsonResponse(data)