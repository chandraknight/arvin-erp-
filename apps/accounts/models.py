from django.contrib.auth.models import AbstractUser, Group, Permission
from django.db import models
from apps.utils.baseModel import BaseModel
from apps.company.models import Company
from apps.accounts.manager import CustomUserManager
from django.contrib.contenttypes.models import ContentType

class User(AbstractUser, BaseModel):
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=150, unique=True, blank=True)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True, related_name='users')
    branch = models.ForeignKey(
        'company.Branch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users',
        help_text='Branch this user belongs to. Leave blank to allow access to all branches within the company.',
    )
    is_company_admin = models.BooleanField(
        default=False,
        help_text='Designates this user as the administrator for their company. '
                  'Company admins can create and manage users within their company.'
    )
    groups = models.ManyToManyField(Group, blank=True, related_name='users')
    user_permissions = models.ManyToManyField(Permission, blank=True, related_name='users')
    objects = CustomUserManager()
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def __str__(self):
        return self.email

    @property
    def can_manage_users(self):
        return self.is_superuser or self.is_company_admin

    @property
    def role_name(self):
        if self.is_superuser:
            return 'Super Admin'
        if self.is_company_admin:
            return 'Company Admin'
        return self.groups.first().name if self.groups.exists() else None

    @property
    def company_name(self):
        return self.company.name if self.company else None


class RolePermission(BaseModel):
    group = models.ForeignKey(Group, on_delete=models.CASCADE)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)

    can_view = models.BooleanField(default=False)
    can_add = models.BooleanField(default=False)
    can_change = models.BooleanField(default=False)
    can_delete = models.BooleanField(default=False)

    class Meta:
        unique_together = ('group', 'content_type')