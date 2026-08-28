import logging
from django.db import transaction
from django.utils import timezone

from apps.purchasing.models import PurchaseOrder

audit = logging.getLogger('audit')


def evaluate_approval_requirement(purchase_order: PurchaseOrder) -> PurchaseOrder:
    """
    Sets approval_status based on the company's po_approval_threshold.
    Opt-in: a company with no threshold configured never requires approval.
    Call after total_amount changes (create, or item recompute).
    """
    company = purchase_order.company
    threshold = getattr(company, 'po_approval_threshold', None) if company else None

    if threshold is not None and purchase_order.total_amount >= threshold:
        purchase_order.approval_status = 'PENDING'
        if purchase_order.status != 'RECEIVED' and purchase_order.status != 'CANCELLED':
            purchase_order.status = 'DRAFT'
    else:
        purchase_order.approval_status = 'NOT_REQUIRED'

    purchase_order.save(update_fields=['approval_status', 'status'])
    return purchase_order


def approve_purchase_order(purchase_order: PurchaseOrder, user, request) -> PurchaseOrder:
    """Authorize a PO pending approval and allow it to progress to SENT."""
    if not (user.is_superuser or getattr(user, 'is_company_admin', False)):
        raise ValueError("Only a company admin can approve a purchase order.")
    if purchase_order.approval_status != 'PENDING':
        raise ValueError(f"Purchase Order is {purchase_order.approval_status} — nothing to approve.")

    with transaction.atomic():
        purchase_order.approval_status = 'APPROVED'
        purchase_order.approved_by = user
        purchase_order.approved_at = timezone.now()
        purchase_order.status = 'SENT'
        purchase_order.save(update_fields=['approval_status', 'approved_by', 'approved_at', 'status'])

        audit.info(
            'PO_APPROVED po=%s amount=%s actor=%s',
            purchase_order.purchase_order_number, purchase_order.total_amount, user.email,
        )
    return purchase_order


def reject_purchase_order(purchase_order: PurchaseOrder, reason: str, user, request) -> PurchaseOrder:
    """Reject a PO pending approval. PO stays out of SENT status."""
    if not (user.is_superuser or getattr(user, 'is_company_admin', False)):
        raise ValueError("Only a company admin can reject a purchase order.")
    if purchase_order.approval_status != 'PENDING':
        raise ValueError(f"Purchase Order is {purchase_order.approval_status} — nothing to reject.")
    if not reason or not reason.strip():
        raise ValueError("A reason is required to reject a purchase order.")

    with transaction.atomic():
        purchase_order.approval_status = 'REJECTED'
        purchase_order.rejection_reason = reason.strip()
        purchase_order.save(update_fields=['approval_status', 'rejection_reason'])

        audit.info(
            'PO_REJECTED po=%s reason=%s actor=%s',
            purchase_order.purchase_order_number, reason.strip(), user.email,
        )
    return purchase_order
