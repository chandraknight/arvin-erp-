import logging

from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.views.generic import CreateView
from ..forms import *
from ..models import *
from django.urls import reverse_lazy
from ...utils.mixins import AuthMixin
from django.contrib import messages
from django.conf import settings

audit = logging.getLogger('audit')


def _send_invitation_email(request, user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    invitation_url = request.build_absolute_uri(
        reverse_lazy('accounts:accept_invitation', kwargs={'uidb64': uid, 'token': token})
    )
    context = {
        'user': user,
        'invitation_url': invitation_url,
        'company_name': getattr(user.company, 'name', 'ERP System'),
        'inviter': request.user,
    }
    subject = render_to_string('accounts/emails/invitation_subject.txt', context).strip()
    body_txt = render_to_string('accounts/emails/invitation_email.txt', context)
    body_html = render_to_string('accounts/emails/invitation_email.html', context)
    try:
        send_mail(
            subject=subject,
            message=body_txt,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=body_html,
            fail_silently=True,
        )
    except Exception as exc:
        audit.warning('INVITATION_EMAIL_FAIL user=%s error=%s', user.email, exc)


class UserCreateView(AuthMixin, CreateView):
    model = User
    form_class = CustomUserCreationForm
    template_name = 'accounts/user_create.html'
    success_url = reverse_lazy('accounts:user_list')
    permission_required = ['accounts.add_user']

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def form_valid(self, form):
        if not self.request.user.is_superuser and self.request.user.is_company_admin:
            form.instance.company = self.request.user.company
            form.instance.is_company_admin = False
            form.instance.is_superuser = False

        response = super().form_valid(form)

        audit.info(
            'USER_CREATED actor=%s new_user=%s company=%s role=%s',
            self.request.user.email,
            self.object.email,
            getattr(self.object.company, 'name', None),
            self.object.groups.first().name if self.object.groups.exists() else None,
        )

        # Send invitation email so the new user can set their own password
        _send_invitation_email(self.request, self.object)

        messages.success(
            self.request,
            f"User {self.object.email} created. An invitation email has been sent. "
            f"Now choose what they can access."
        )
        return response

    def get_success_url(self):
        if self.object.is_superuser or self.object.is_company_admin:
            return str(self.success_url)
        return reverse_lazy('accounts:user_access', kwargs={'id': self.object.id})
