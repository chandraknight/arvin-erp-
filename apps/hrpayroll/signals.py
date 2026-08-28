from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

from apps.hrpayroll.models import Payslip

# No explicit "finalize payslip" view/action exists in hrpayroll/views.py —
# generate_payslips() always creates payslips with is_finalized=False and
# never flips it. Watch the False→True transition here instead of inventing
# a finalize endpoint the rest of the app doesn't call.
_PRE_SAVE_FINALIZED_CACHE = {}


@receiver(pre_save, sender=Payslip)
def _capture_previous_is_finalized(sender, instance, **kwargs):
    if not instance.pk:
        _PRE_SAVE_FINALIZED_CACHE[instance.pk] = False
        return
    previous = Payslip.objects.filter(pk=instance.pk).values_list('is_finalized', flat=True).first()
    _PRE_SAVE_FINALIZED_CACHE[instance.pk] = bool(previous)


@receiver(post_save, sender=Payslip)
def post_payslip_journal_on_finalize(sender, instance, created, **kwargs):
    was_finalized = _PRE_SAVE_FINALIZED_CACHE.pop(instance.pk, False)
    if instance.is_finalized and not was_finalized:
        from apps.hrpayroll.services.payroll_posting_service import post_payslip_journal
        post_payslip_journal(instance)
