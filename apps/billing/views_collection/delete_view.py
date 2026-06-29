"""
Cancel views for Invoice and VendorBill.

Design rules enforced here:
  - Issued invoices and vendor bills CANNOT be deleted — only cancelled.
  - DRAFT documents may be soft-deleted (they were never sent to a customer/vendor).
  - Cancellation requires a reason (POST field: `reason`).
  - All actions are logged to the audit logger.
"""
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from apps.billing.models import Invoice, VendorBill
from apps.utils.decorator import auth_required

logger = logging.getLogger('audit')


# ── helpers ──────────────────────────────────────────────────────────────────

def _company_owns_invoice(request, invoice):
    if request.user.is_superuser:
        return True
    return invoice.company == request.user_company


def _company_owns_bill(request, bill):
    if request.user.is_superuser:
        return True
    return (
        bill.vendor.company == request.user_company
        or (bill.purchase_order and bill.purchase_order.company == request.user_company)
    )


# ── Invoice cancel / delete ───────────────────────────────────────────────────

@auth_required('billing.change_invoice')
def invoice_cancel(request, pk):
    """
    Cancel an issued invoice.
    GET  → confirmation page showing the invoice and a reason field.
    POST → sets status=CANCELLED, records reason, redirects to dashboard.

    A DRAFT invoice (never issued) can be soft-deleted instead via
    invoice_delete below.
    """
    invoice = get_object_or_404(Invoice, pk=pk)

    if not _company_owns_invoice(request, invoice):
        raise PermissionDenied("You do not have access to this invoice.")

    if invoice.status == 'CANCELLED':
        messages.warning(request, f"Invoice {invoice.invoice_number} is already cancelled.")
        return redirect('accounts:user_dashboard')

    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        if not reason:
            messages.error(request, "A cancellation reason is required.")
            return render(request, 'billing/invoices/invoice_cancel_confirm.html', {'invoice': invoice})

        try:
            invoice.cancel(cancelled_by=request.user, reason=reason)
            logger.info(
                'INVOICE_CANCELLED invoice=%s actor=%s company=%s reason=%s',
                invoice.invoice_number, request.user.email, request.user_company, reason,
            )
            messages.success(
                request,
                f"Invoice {invoice.invoice_number} has been cancelled. "
                "Issue a new invoice to correct any errors.",
            )
        except ValueError as exc:
            messages.error(request, str(exc))

        return redirect('accounts:user_dashboard')

    return render(request, 'billing/invoices/invoice_cancel_confirm.html', {'invoice': invoice})


@auth_required('billing.delete_invoice')
def invoice_delete(request, pk):
    """
    Soft-delete a DRAFT invoice (one that was never issued).
    Issued or cancelled invoices cannot be deleted — cancel them instead.
    """
    invoice = get_object_or_404(Invoice, pk=pk)

    if not _company_owns_invoice(request, invoice):
        raise PermissionDenied("You do not have access to this invoice.")

    if invoice.is_locked:
        logger.warning(
            'INVOICE_DELETE_BLOCKED invoice=%s status=%s actor=%s',
            invoice.invoice_number, invoice.status, request.user.email,
        )
        messages.error(
            request,
            f"Invoice {invoice.invoice_number} is {invoice.status.lower()} and cannot be deleted. "
            "Use Cancel instead.",
        )
        return redirect('accounts:user_dashboard')

    if request.method == 'POST':
        ref = invoice.invoice_number or str(invoice.pk)
        invoice.soft_delete(deleted_by=request.user)
        logger.info(
            'INVOICE_DELETED invoice=%s actor=%s company=%s',
            ref, request.user.email, request.user_company,
        )
        messages.success(request, f"Draft invoice {ref} has been deleted.")
        return redirect('accounts:user_dashboard')

    return render(request, 'billing/invoices/invoice_delete_confirm.html', {'invoice': invoice})


# ── VendorBill cancel / delete ────────────────────────────────────────────────

@auth_required('billing.change_vendorbill')
def vendor_bill_cancel(request, pk):
    """
    Cancel a vendor bill (UNPAID or PAID).
    GET  → confirmation page with reason field.
    POST → sets status=CANCELLED, records reason.
    """
    bill = get_object_or_404(VendorBill, pk=pk)

    if not _company_owns_bill(request, bill):
        raise PermissionDenied("You do not have access to this vendor bill.")

    if bill.status == 'CANCELLED':
        messages.warning(request, f"Vendor bill {bill.bill_number} is already cancelled.")
        return redirect('accounts:user_dashboard')

    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        if not reason:
            messages.error(request, "A cancellation reason is required.")
            return render(request, 'billing/vendor_bills/vendor_bill_cancel_confirm.html', {'bill': bill})

        try:
            bill.cancel(cancelled_by=request.user, reason=reason)
            logger.info(
                'VENDOR_BILL_CANCELLED bill=%s actor=%s company=%s reason=%s',
                bill.bill_number, request.user.email, request.user_company, reason,
            )
            messages.success(
                request,
                f"Vendor bill {bill.bill_number} has been cancelled. "
                "Issue a new bill to correct any errors.",
            )
        except ValueError as exc:
            messages.error(request, str(exc))

        return redirect('accounts:user_dashboard')

    return render(request, 'billing/vendor_bills/vendor_bill_cancel_confirm.html', {'bill': bill})
