"""
API scope constants.

Scopes are stored as a list of strings on each APIToken.
Views declare which scope they require via HasAPIScope.required_scope.
"""

SCOPE_INVOICES_READ   = 'invoices:read'
SCOPE_INVOICES_WRITE  = 'invoices:write'
SCOPE_CUSTOMERS_READ  = 'customers:read'
SCOPE_CUSTOMERS_WRITE = 'customers:write'
SCOPE_PRODUCTS_READ   = 'products:read'
SCOPE_PAYMENTS_READ   = 'payments:read'
SCOPE_DASHBOARD_READ  = 'dashboard:read'

ALL_SCOPES = [
    SCOPE_INVOICES_READ,
    SCOPE_INVOICES_WRITE,
    SCOPE_CUSTOMERS_READ,
    SCOPE_CUSTOMERS_WRITE,
    SCOPE_PRODUCTS_READ,
    SCOPE_PAYMENTS_READ,
    SCOPE_DASHBOARD_READ,
]
