from django.contrib.auth.models import update_last_login
from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_migrate
from django.dispatch import receiver
from django.utils import timezone

from .seeds import seed_groups


user_logged_in.disconnect(update_last_login)
user_logged_in.disconnect(dispatch_uid='update_last_login')


@receiver(user_logged_in, dispatch_uid='accounts.update_last_login_safely')
def update_last_login_safely(sender, user, **kwargs):
    if not user or not user.pk:
        return
    sender.objects.filter(pk=user.pk).update(last_login=timezone.now())


@receiver(post_migrate)
def handle_post_migrate(sender, **kwargs):
    seed_groups()
