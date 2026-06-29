"""
Plain-language module access for company staff.
Maps human-readable modules + levels onto Django per-user permissions,
so the existing sidebar and AuthMixin checks enforce them.
"""
from django.contrib.auth.models import Permission

MODULES = [
    ('billing', 'Sales & Billing', None, ['billing']),
    ('orders', 'Order Management', 'enable_order_management', ['orders']),
    ('purchasing', 'Purchasing', 'enable_purchasing', ['purchasing']),
    ('contacts', 'Customers & Vendors', None, ['customers', 'vendors']),
    ('inventory', 'Inventory', 'enable_inventory', ['products']),
    ('pos', 'Point of Sale', 'enable_pos', ['pos']),
    ('payments', 'Payments & Expenses', None, ['payments']),
    ('bookkeeping', 'Bookkeeping', None, ['bookkeeping']),
    ('hr', 'HR & Payroll', 'enable_hr_payroll', ['hrpayroll']),
    ('reports', 'Reports', None, ['reports']),
    ('tours', 'Tours & Ticketing', 'enable_tours', ['tours']),
    ('restaurant', 'Restaurant', 'enable_restaurant', ['restaurant']),
    ('manufacturing', 'Manufacturing', 'enable_manufacturing', ['manufacturing']),
    ('projects', 'Projects', 'enable_project_tracking', ['projects']),
]

LEVELS = [
    ('none', 'No access'),
    ('view', 'View only'),
    ('create', 'View & create'),
    ('full', 'Full control'),
]

LEVEL_ACTIONS = {
    'none': [],
    'view': ['view'],
    'create': ['view', 'add'],
    'full': ['view', 'add', 'change', 'delete'],
}


def modules_for_company(company):
    """Modules available to a company's staff — disabled module flags are hidden."""
    result = []
    for key, label, flag, app_labels in MODULES:
        if flag is None or (company and getattr(company, flag, False)):
            result.append({'key': key, 'label': label, 'app_labels': app_labels})
    return result


def get_module_levels(user):
    perms = set(
        user.user_permissions.select_related('content_type')
        .values_list('content_type__app_label', 'codename')
    )
    levels = {}
    for key, label, flag, app_labels in MODULES:
        actions = set()
        for app_label, codename in perms:
            if app_label in app_labels:
                actions.add(codename.split('_')[0])
        if 'delete' in actions or 'change' in actions:
            levels[key] = 'full'
        elif 'add' in actions:
            levels[key] = 'create'
        elif 'view' in actions:
            levels[key] = 'view'
        else:
            levels[key] = 'none'
    return levels


def set_module_levels(user, levels):
    """levels: {'orders': 'create', ...}. Replaces managed perms, keeps anything else."""
    managed_apps = {app for _, _, _, app_labels in MODULES for app in app_labels}
    keep = [
        p for p in user.user_permissions.select_related('content_type')
        if p.content_type.app_label not in managed_apps
    ]
    grant = []
    for key, label, flag, app_labels in MODULES:
        actions = LEVEL_ACTIONS.get(levels.get(key, 'none'), [])
        if not actions:
            continue
        prefixes = tuple(f'{a}_' for a in actions)
        grant += [
            p for p in Permission.objects.filter(content_type__app_label__in=app_labels)
            .select_related('content_type')
            if p.codename.startswith(prefixes)
        ]
    user.user_permissions.set(keep + grant)
