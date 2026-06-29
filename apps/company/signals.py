from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Company, Branch, FiscalYear
from .services.company_services import setup_default_ledger_accounts


@receiver(post_save, sender=Company)
def create_main_branch(sender, instance, created, **kwargs):
    if created and not instance.branches.exists():
        Branch.objects.create(
            company=instance,
            name=f"{instance.name} - (Main Branch)",
            address=instance.address,
            phone=instance.phone,
            email=instance.email,
            is_main_branch=True
        )

@receiver(post_save, sender=Company)
def create_default_ledger_accounts(sender, instance, created, **kwargs):
    if created:
        setup_default_ledger_accounts(instance)


@receiver(post_save, sender=FiscalYear)
def set_single_active_fiscal_year(sender, instance, created, **kwargs):
    if instance.is_active:
        FiscalYear.objects.filter(
            company=instance.company,
            is_active=True
        ).exclude(pk=instance.pk).update(is_active=False)