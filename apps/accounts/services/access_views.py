import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from ..models import User
from . import staff_access

audit = logging.getLogger('audit')


@login_required
def user_module_access(request, id):
    if not (request.user.is_superuser or request.user.is_company_admin):
        raise PermissionDenied
    target = get_object_or_404(User.active_objects, id=id)
    if not request.user.is_superuser and target.company != request.user.company:
        audit.warning('USER_ACCESS_DENIED actor=%s target=%s reason=cross_company',
                      request.user.email, target.email)
        raise PermissionDenied
    if target.is_superuser or target.is_company_admin:
        messages.info(request, f"{target.email} is an admin and already has full access.")
        return redirect('accounts:user_list')

    company = target.company or request.user.company
    modules = staff_access.modules_for_company(company)
    valid_levels = dict(staff_access.LEVELS)

    if request.method == 'POST':
        levels = {}
        for module in modules:
            level = request.POST.get(f"level_{module['key']}", 'none')
            levels[module['key']] = level if level in valid_levels else 'none'
        staff_access.set_module_levels(target, levels)
        audit.info('USER_ACCESS_UPDATED actor=%s target=%s levels=%s',
                   request.user.email, target.email,
                   {k: v for k, v in levels.items() if v != 'none'})
        messages.success(request, f"Access updated for {target.email}.")
        return redirect('accounts:user_list')

    current = staff_access.get_module_levels(target)
    for module in modules:
        module['current'] = current.get(module['key'], 'none')
    return render(request, 'accounts/user_access.html', {
        'target': target,
        'modules': modules,
        'levels': staff_access.LEVELS,
    })
