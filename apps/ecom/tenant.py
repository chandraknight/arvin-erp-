from urllib.parse import urlsplit

from apps.company.models import Company


def resolve_store_company(request):
    if request.user.is_authenticated and not request.user.is_superuser:
        return getattr(request.user, 'company', None)

    host = (urlsplit(f'//{request.get_host()}').hostname or '').lower().rstrip('.')
    if host:
        company = Company.active_objects.filter(store_domain__iexact=host).first()
        if company:
            return company

    companies = Company.active_objects.all()
    if companies.count() == 1:
        return companies.first()
    return None
