from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender='orders.SalesOrder')
def sync_ecom_order_status(sender, instance, **kwargs):
    """Keep EcomOrder.status in sync whenever SalesOrder.status changes."""
    if not hasattr(instance, 'ecom_order') or not instance.ecom_order:
        return

    so_to_ecom = {
        'DRAFT':       'PENDING',
        'CONFIRMED':   'CONFIRMED',
        'PROCESSING':  'PROCESSING',
        'DISPATCHED':  'DISPATCHED',
        'DELIVERED':   'DELIVERED',
        'CANCELLED':   'CANCELLED',
    }
    new_status = so_to_ecom.get(instance.status)
    if not new_status:
        return

    ecom = instance.ecom_order
    if ecom.status != new_status:
        ecom.status = new_status
        ecom.save(update_fields=['status'])
