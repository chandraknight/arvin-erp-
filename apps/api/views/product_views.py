"""
Product views.

ProductListView    GET  /api/v1/products/
ProductDetailView  GET  /api/v1/products/<uuid:pk>/

All views use request.auth.company for tenant isolation.
"""
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView

from apps.api.authentication import APITokenAuthentication
from apps.api.pagination import paginate_queryset
from apps.api.permissions import HasAPIScope
from apps.api.response import api_error, api_list, api_success
from apps.api.scopes import SCOPE_PRODUCTS_READ
from apps.api.serializers import ProductSerializer, ProductStockSerializer
from apps.products.models import Product, ProductStock


class ProductListView(APIView):
    """
    GET /api/v1/products/

    Returns a paginated list of products for the token's company.
    Query params:
        ?search=<name, barcode, or SKU>
        ?category=<uuid>
        ?is_service=true|false
        ?page=<int>
        ?page_size=<int>  (max 100)
    """
    authentication_classes = [APITokenAuthentication]
    permission_classes = [HasAPIScope]
    required_scope = SCOPE_PRODUCTS_READ

    def get(self, request):
        company = request.auth.company
        if company is None:
            return api_error('Superuser tokens must specify a company.', code='NO_COMPANY', status=400)

        qs = Product.active_objects.filter(company=company).select_related('category').order_by('name')

        search = request.GET.get('search', '').strip()
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(barcode__icontains=search) | Q(sku__icontains=search))

        category = request.GET.get('category', '').strip()
        if category:
            qs = qs.filter(category__id=category)

        is_service_param = request.GET.get('is_service', '').strip().lower()
        if is_service_param in ('true', '1'):
            qs = qs.filter(is_service=True)
        elif is_service_param in ('false', '0'):
            qs = qs.filter(is_service=False)

        page_data, total, total_pages, page = paginate_queryset(qs, request)
        page_size = int(request.GET.get('page_size', 20))

        data = ProductSerializer(page_data, many=True).data
        return api_list(
            data=data,
            pagination={
                'total': total,
                'page': page,
                'page_size': min(page_size, 100),
                'total_pages': total_pages,
            },
        )


class ProductDetailView(APIView):
    """
    GET /api/v1/products/<uuid:pk>/

    Returns a single product. Includes stock info for non-service products.
    Ownership is verified against the token's company.
    """
    authentication_classes = [APITokenAuthentication]
    permission_classes = [HasAPIScope]
    required_scope = SCOPE_PRODUCTS_READ

    def get(self, request, pk):
        company = request.auth.company
        if company is None:
            return api_error('Superuser tokens must specify a company.', code='NO_COMPANY', status=400)

        product = get_object_or_404(Product.active_objects, pk=pk, company=company)
        data = ProductSerializer(product).data

        # Include stock info for physical products
        if not product.is_service:
            try:
                stock = ProductStock.objects.get(product=product)
                data['stock'] = ProductStockSerializer(stock).data
            except ProductStock.DoesNotExist:
                data['stock'] = None

        return api_success(data=data)
