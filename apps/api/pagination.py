"""
Simple pagination utility for API list views.

Reads ?page and ?page_size from request.GET.
Returns a tuple of (page_queryset, total_count, total_pages, current_page).
"""
import math


def paginate_queryset(queryset, request, default_page_size=20, max_page_size=100):
    """
    Paginate a queryset using ?page and ?page_size query parameters.

    Args:
        queryset: Django queryset to paginate.
        request: DRF request object.
        default_page_size: Items per page when ?page_size is not provided.
        max_page_size: Hard cap on page_size to prevent abuse.

    Returns:
        (page_data, total_count, total_pages, current_page)
        page_data is a sliced queryset (or list slice).
    """
    try:
        page = max(1, int(request.GET.get('page', 1)))
    except (ValueError, TypeError):
        page = 1

    try:
        page_size = int(request.GET.get('page_size', default_page_size))
    except (ValueError, TypeError):
        page_size = default_page_size

    page_size = max(1, min(page_size, max_page_size))

    total_count = queryset.count()
    total_pages = max(1, math.ceil(total_count / page_size))

    # Clamp page to valid range
    page = min(page, total_pages)

    offset = (page - 1) * page_size
    page_data = queryset[offset: offset + page_size]

    return page_data, total_count, total_pages, page
