from django.contrib.auth.models import Permission , Group
from django.contrib.auth.hashers import make_password
from .models import User, RolePermission
from django.db.utils import IntegrityError
from django.contrib.contenttypes.models import ContentType
from django.apps import apps
import os
from ..utils.constant import RoleEnum


def seed_groups():
    if Group.objects.all().count() == 0:
        print("Seeding role-based groups and permissions...")
        role_permission_map = {
            RoleEnum.Staff.value: ['view_'],
            RoleEnum.Manager.value: ['view_', 'change_'],
            RoleEnum.Admin.value: ['view_', 'add_', 'change_', 'delete_'],
        }
        for role_name in role_permission_map.keys():
            Group.objects.get_or_create(name=role_name)
        for role_name, perm_prefixes in role_permission_map.items():
            group = Group.objects.get(name=role_name)

            for app_config in apps.get_app_configs():
                if app_config.name.startswith('django.'):
                    continue

                for model in app_config.get_models():
                    content_type = ContentType.objects.get_for_model(model)
                    RolePermission.objects.get_or_create(
                        group=group,
                        content_type=content_type,
                        defaults={
                            'can_view': 'view_' in perm_prefixes,
                            'can_add': 'add_' in perm_prefixes,
                            'can_change': 'change_' in perm_prefixes,
                            'can_delete': 'delete_' in perm_prefixes,
                        }
                    )
                    print("✅ All groups and RolePermissions seeded successfully.")

    sync_rolepermission_permission()
    seed_admin()

def sync_rolepermission_permission():
    role_permission_map = {
        RoleEnum.Staff.value: ['view_'],
        RoleEnum.Manager.value: ['view_', 'change_'],
        RoleEnum.Admin.value: ['view_', 'add_', 'change_', 'delete_'],
    }

    for app_config in apps.get_app_configs():
        if app_config.name.startswith('django.'):
            continue

        for model in app_config.get_models():
            content_type = ContentType.objects.get_for_model(model)

            if not RolePermission.objects.filter(content_type=content_type).exists():
                print(f"Creating RolePermissions for new model: {content_type.model}")

                for role_name, perm_prefixes in role_permission_map.items():
                    group, _ = Group.objects.get_or_create(name=role_name)

                    RolePermission.objects.get_or_create(
                        group=group,
                        content_type=content_type,
                        can_view='view_' in perm_prefixes,
                        can_add='add_' in perm_prefixes,
                        can_change='change_' in perm_prefixes,
                        can_delete='delete_' in perm_prefixes,
                    )
                    print("✅ RolePermissions and Permission synced successfully.")

def seed_admin():
    if User.objects.all().count() == 0:
        username = os.getenv("DJANGO_SUPERUSER_USERNAME", "super007")
        email = os.getenv("DJANGO_SUPERUSER_EMAIL", "system@admin.com")
        password = os.getenv("DJANGO_SUPERUSER_PASSWORD", "admin@1234")
        try:
            admin_user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'email': email,
                    'password': make_password(password),
                    'is_staff': False,
                    'is_superuser': True,
                    'first_name': 'admin',
                    'last_name': 'admin',
                }
            )

            if created:
                print(f"✅ Admin user '{username}' created successfully!")
            else:
                print(f"ℹ️ Admin user '{username}' already exists")

            admin_group, _ = Group.objects.get_or_create(name=RoleEnum.Admin.name)
            admin_user.groups.add(admin_group)

            all_permission = Permission.objects.all()
            admin_group, _ = Group.objects.get_or_create(name=RoleEnum.Admin.name)

            existing_group_perms = admin_group.permissions.values_list('id', flat=True)
            missing_group_perms = all_permission.exclude(id__in=existing_group_perms)
            admin_group.permissions.add(*missing_group_perms)

            existing_user_perms = admin_user.user_permissions.values_list('id', flat=True)
            missing_user_perms = all_permission.exclude(id__in=existing_user_perms)
            admin_user.user_permissions.add(*missing_user_perms)

            print("✅ Admin user, group, and all permissions seeded successfully.")
        except IntegrityError as e:
            print(f"⚠️ Error creating admin user: {e}")