from django.http import JsonResponse

from apps.products.models import Product, Package
from apps.utils.decorator import auth_required


@auth_required('products.view_product')
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