from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm as BaseUserChangeForm
from django.contrib.auth.models import Group

from .models import *


def _roles_for_company(company):
    """Return Groups whose names correspond to enabled modules on the company."""
    # These role names are always available regardless of module flags
    allowed = ['Staff', 'Manager']
    return Group.objects.filter(name__in=allowed)

class LoginForm(forms.Form):
    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Enter your email'})
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Enter your password'})
    )

class UserChangeForm(BaseUserChangeForm):
    company = forms.ModelChoiceField(queryset=None, required=False, label="Company", empty_label="--------")
    groups = forms.ModelMultipleChoiceField(
        queryset=None,
        required=False,
        label="Roles",
        widget=forms.CheckboxSelectMultiple
    )
    is_company_admin = forms.BooleanField(required=False, label="Company Admin")

    class Meta(BaseUserChangeForm.Meta):
        model = User
        fields = ('email', 'username', 'company', 'groups', 'is_active', 'is_staff', 'is_superuser', 'is_company_admin', 'user_permissions')

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if self.request:
            if self.request.user.is_superuser:
                # Superadmin: full access — all companies, all roles, can designate company admins
                self.fields['company'].queryset = Company.objects.all()
                self.fields['groups'].queryset = Group.objects.all()
            elif self.request.user.is_company_admin and self.request.user.company:
                # Company admin: locked to own company, scoped roles, cannot escalate
                company = self.request.user.company
                self.fields['company'].queryset = Company.objects.filter(id=company.id)
                self.fields['company'].initial = company
                self.fields['company'].widget.attrs['readonly'] = True
                self.fields['groups'].queryset = _roles_for_company(company)
                for field_name in ('is_staff', 'is_superuser', 'is_company_admin', 'user_permissions'):
                    if field_name in self.fields:
                        del self.fields[field_name]
            else:
                self.fields['company'].queryset = Company.objects.none()
                self.fields['groups'].queryset = Group.objects.none()


class CustomUserCreationForm(UserCreationForm):
    first_name = forms.CharField(label='First Name', max_length=100, required=False)
    last_name = forms.CharField(label='Last Name', max_length=100, required=False)
    email = forms.EmailField(required=True, label="Email")
    company = forms.ModelChoiceField(queryset=None, required=False, label="Company", empty_label="Select Company")
    role = forms.ModelChoiceField(queryset=None, required=False, label="Role", empty_label="Select Role")

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'company', 'role', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if self.request and self.request.user.is_superuser:
            # Superadmin: all companies, all roles
            self.fields['role'].queryset = Group.objects.all()
            self.fields['company'].queryset = Company.active_objects.all()
        elif self.request and self.request.user.is_company_admin and self.request.user.company:
            # Company admin: locked to own company, roles scoped to enabled modules
            company = self.request.user.company
            self.fields['company'].queryset = Company.active_objects.filter(id=company.id)
            self.fields['company'].initial = company
            self.fields['company'].widget.attrs['readonly'] = True
            self.fields['role'].queryset = _roles_for_company(company)
        else:
            self.fields['role'].queryset = Group.objects.none()
            self.fields['company'].queryset = Company.active_objects.none()



    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data.get('first_name')
        user.last_name = self.cleaned_data.get('last_name')
        user.email = self.cleaned_data.get('email')
        user.company = self.cleaned_data.get('company')
        user.username = self.cleaned_data.get('email')  # use email as username
        user.is_staff = False
        user.is_superuser = False

        if commit:
            user.save()
            self.save_m2m()

            role = self.cleaned_data.get('role')
            if role:
                user.groups.add(role)

        return user
