from django.conf import settings


def get_client_ip(request) -> str:
    """
    Return the real client IP address.

    Only trusts X-Forwarded-For when REMOTE_ADDR matches a configured
    trusted proxy (TRUSTED_PROXY_IPS setting). Falls back to REMOTE_ADDR
    so that attackers cannot spoof their IP by injecting the header directly.
    """
    remote_addr = request.META.get('REMOTE_ADDR', '0.0.0.0')
    trusted_proxies = getattr(settings, 'TRUSTED_PROXY_IPS', [])

    if remote_addr in trusted_proxies:
        xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
        if xff:
            return xff.split(',')[0].strip()

    return remote_addr
