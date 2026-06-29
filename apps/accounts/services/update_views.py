import logging

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from django.views.generic import UpdateView
from ..forms import *
from ..models import *
from django.urls import reverse_lazy
from django.http import JsonResponse
import json

from ...utils.decorator import auth_required
from ...utils.mixins import AuthMixin

audit = logging.getLogger('audit')


class UserUpdateView(AuthMixin, UpdateView):
    model = User
    form_class = UserChangeForm
    template_name = 'accounts/user_update.html'
    context_object_name = 'user_to_update'
    success_url = reverse_lazy('accounts:user_dashboard')
    permission_required = ['accounts.change_user']
    pk_url_kwarg = 'id'

    def get_queryset(self):
        if self.request.user.is_superuser:
            return User.objects.all()
        # Company admins can only edit users within their own company
        return User.objects.filter(company=self.request.user.company)

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        # Extra ownership check — raises 403 instead of 404 for existing users
        if not self.request.user.is_superuser:
            if obj.company != self.request.user.company:
                audit.warning(
                    'USER_UPDATE_DENIED actor=%s target=%s reason=cross_company',
                    self.request.user.email, obj.email,
                )
                raise PermissionDenied('You can only edit users within your own company.')
        return obj

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def form_valid(self, form):
        audit.info(
            'USER_UPDATED actor=%s target=%s company=%s',
            self.request.user.email,
            form.instance.email,
            getattr(form.instance.company, 'name', None),
        )
        messages.success(self.request, f"User {form.instance.email} updated successfully!")
        return super().form_valid(form)


@auth_required('accounts.change_rolepermission')
def update_rbac(request, id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=400)

    try:
        data = json.loads(request.body)
        field = data.get('field')
        value = data.get('value')

        value = str(value).lower() in ['true', '1', 'yes']

        rp = RolePermission.objects.get(id=id)

        if field not in ['can_view', 'can_add', 'can_change', 'can_delete']:
            return JsonResponse({'error': 'Invalid field'}, status=400)

        setattr(rp, field, value)
        rp.updated_at = timezone.now()
        rp.updated_by = request.user
        rp.save()

        ct = rp.content_type
        model = ct.model

        codename_map = {
            'can_view': f'view_{model}',
            'can_add': f'add_{model}',
            'can_change': f'change_{model}',
            'can_delete': f'delete_{model}',
        }
        codename = codename_map[field]

        try:
            perm = Permission.objects.get(codename=codename, content_type=ct)
        except Permission.DoesNotExist:
            return JsonResponse({
                'error': f"Permission '{codename}' not found.",
                'details': f"ContentType: {ct.app_label}.{ct.model}"
            }, status=404)

        group = rp.group
        if value:
            group.permissions.add(perm)
        else:
            group.permissions.remove(perm)
            users = User.active_objects.filter(groups=group).all()
            for user in users:
                if perm in user.user_permissions.all():
                    user.user_permissions.remove(perm)

        return JsonResponse({
            'status': 'success',
            'details': {
                'group': group.name,
                'permission': codename,
                'action': 'added' if value else 'removed'
            }
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except RolePermission.DoesNotExist:
        return JsonResponse({'error': 'RolePermission not found'}, status=404)
    except Exception as e:
        import traceback
        import logging
        logger = logging.getLogger(__name__)
        logger.error("RBAC Update Error: %s\n%s", e, traceback.format_exc())
        return JsonResponse({'error': 'Internal server error'}, status=500)