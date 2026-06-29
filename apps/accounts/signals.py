from django.db.models.signals import post_migrate
from django.dispatch import receiver
from .seeds import seed_groups

@receiver(post_migrate)
def handle_post_migrate(sender, **kwargs):
    seed_groups()
