from social_core.exceptions import AuthForbidden


def block_staff_social_login(backend, user, *args, **kwargs):
    """Prevent staff/admin accounts from logging in via social auth on the storefront."""
    if user and (user.is_staff or user.is_superuser):
        raise AuthForbidden(backend)
