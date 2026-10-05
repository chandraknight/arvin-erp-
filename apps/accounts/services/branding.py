from apps.ecom.tenant import resolve_store_company


def get_login_logo_url(request):
    """Client-uploaded logo for the login page: ecom store logo, then company logo.
    Returns None when nothing is uploaded so the template keeps the default ERP logo."""
    company = resolve_store_company(request)
    if not company:
        return None
    site_settings = getattr(company, 'ecom_settings', None)
    for logo in (getattr(site_settings, 'logo', None), company.logo):
        if logo:
            return logo.url
    return None
