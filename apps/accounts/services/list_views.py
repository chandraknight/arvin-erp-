from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from ..models import *
from django.db.models import Q

from ...utils.decorator import auth_required


@auth_required('accounts.view_user')
def user_list_view(request):
    base_queryset = User.active_objects.select_related('company').order_by('email')

    if request.user.is_superuser:
        pass  # sees everyone
    elif request.user.is_company_admin:
        # Company admin sees only non-superuser users within their company
        base_queryset = base_queryset.filter(
            is_superuser=False,
            company=request.user.company,
        )
    else:
        base_queryset = base_queryset.none()

    try:
        paginate_by = int(request.GET.get('paginate_by', 10))
    except (ValueError, TypeError):
        paginate_by = 10

    paginator = Paginator(base_queryset, paginate_by)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'accounts/user_list.html', {
        'object_list': page_obj.object_list,
        'page_obj': page_obj,
        'paginate_by': paginate_by
    })

def rbac_list_view(request):
    def clean_filter_value(val):
        if val in [None, '', 'None']:
            return None
        return val

    selected_role = clean_filter_value(request.GET.get('role'))
    selected_model = clean_filter_value(request.GET.get('model'))
    selected_app_name = clean_filter_value(request.GET.get('app'))

    queryset = RolePermission.objects.select_related('group', 'content_type')

    if selected_role:
        queryset = queryset.filter(group_id=selected_role)

    if selected_model:
        queryset = queryset.filter(content_type_id=selected_model)

    if selected_app_name:
        queryset = queryset.filter(content_type__app_label=selected_app_name)

    queryset = queryset.order_by('group__name', 'content_type__model')

    try:
        paginate_by = int(request.GET.get('paginate_by', 10))
    except (ValueError, TypeError):
        paginate_by = 10

    paginator = Paginator(queryset, paginate_by)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    apps_with_permissions = ContentType.objects.filter(
        id__in=RolePermission.objects.values_list('content_type_id', flat=True)
    ).order_by('app_label').values_list('app_label', flat=True).distinct()

    # Get models based on selected app (if any)
    models_queryset = ContentType.objects.filter(
        id__in=RolePermission.objects.values_list('content_type_id', flat=True)
    )
    if selected_app_name:
        models_queryset = models_queryset.filter(app_label=selected_app_name)

    models = models_queryset.order_by('model').distinct()

    context = {
        'object_list': page_obj.object_list,
        'page_obj': page_obj,
        'selected_role': selected_role,
        'selected_model': selected_model,
        'selected_app_name': selected_app_name,
        'roles': Group.objects.all(),
        'models':models,
        'apps': apps_with_permissions,
        'paginate_by': paginate_by
    }
    return render(request, 'accounts/role_list.html', context)



