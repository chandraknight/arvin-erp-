from decimal import Decimal

from django.db import transaction

from apps.utils.constant import StatusChoicesEnum

from ..forms import *
from ..services.note_service import apply_credit_note, apply_debit_note


class NoteCreateUpdateMixin:
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def form_valid(self, form):
        is_new = not form.instance.pk
        old_invoice, old_amount = None, Decimal('0.00')
        if is_new:
            if isinstance(form, CreditNoteForm):
                form.instance.credit_note_number = generate_credit_note_number()
            elif isinstance(form, DebitNoteForm):
                form.instance.debit_note_number = generate_debit_note_number()
        else:
            # Re-applying an already-applied note must first revert its
            # previous effect on the invoice balance.
            old = type(form.instance).objects.get(pk=form.instance.pk)
            if old.status == StatusChoicesEnum.Applied.value:
                old_invoice, old_amount = old.invoice, old.amount

        with transaction.atomic():
            response = super().form_valid(form)
            # Apply the note immediately: adjusts the invoice balance and,
            # via the APPLIED-status post_save signal, posts the NFRS journal
            # entry (sales return / purchase return).
            if isinstance(form, CreditNoteForm):
                apply_credit_note(form.instance, old_invoice, old_amount)
            elif isinstance(form, DebitNoteForm):
                apply_debit_note(form.instance, old_invoice, old_amount)

        # Submit new credit notes to IRD CBMS if e-billing is enabled
        if is_new and isinstance(form, CreditNoteForm):
            company = getattr(self.request.user, 'company', None)
            if company and company.enable_ebilling:
                from apps.billing.services.cbms_service import post_credit_note
                from django.contrib import messages
                cbms_log = post_credit_note(form.instance)
                if cbms_log and not cbms_log.success:
                    messages.warning(
                        self.request,
                        f"Credit note saved but CBMS submission failed (code {cbms_log.response_code})."
                    )

        return response

