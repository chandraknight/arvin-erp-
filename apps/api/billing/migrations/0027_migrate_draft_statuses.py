from django.db import migrations


def forwards(apps, schema_editor):
    # Billing: drafts become issued (estimates keep their own status)
    Invoice = apps.get_model('billing', 'Invoice')
    Invoice.objects.filter(status='DRAFT').update(status='ISSUED')
    for model_name in ('CreditNote', 'DebitNote'):
        model = apps.get_model('billing', model_name)
        model.objects.filter(status='DRAFT').update(status='ISSUED')

    PurchaseOrder = apps.get_model('purchasing', 'PurchaseOrder')
    PurchaseOrder.objects.filter(status='DRAFT').update(status='SENT')

    SalesOrder = apps.get_model('orders', 'SalesOrder')
    SalesOrder.objects.filter(status='DRAFT').update(status='CONFIRMED')

    WorkOrder = apps.get_model('manufacturing', 'WorkOrder')
    WorkOrder.objects.filter(status='DRAFT').update(status='PLANNED')

    PerformanceReview = apps.get_model('hrpayroll', 'PerformanceReview')
    PerformanceReview.objects.filter(status='DRAFT').update(status='SUBMITTED')

    TourBooking = apps.get_model('tours', 'TourBooking')
    TourBooking.objects.filter(status='DRAFT').update(status='CONFIRMED')


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0026_debitnote_vendor_debitnote_vendor_bill_and_more'),
        ('purchasing', '0006_alter_purchaseorder_status'),
        ('orders', '0005_alter_salesorder_status'),
        ('manufacturing', '0003_alter_workorder_status'),
        ('hrpayroll', '0004_alter_performancereview_status'),
        ('tours', '0004_alter_tourbooking_status'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
