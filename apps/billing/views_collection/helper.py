from ..forms import *
from ..services.note_service import generate_credit_note_number, generate_debit_note_number

class NoteCreateUpdateMixin:
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def form_valid(self, form):
        is_new = not form.instance.pk
        if is_new:
            company = getattr(self.request.user, 'company', None)
            if isinstance(form, CreditNoteForm):
                number, seq, fy = generate_credit_note_number(company.id if company else None)
                form.instance.credit_note_number = number
                form.instance.sequence_number = seq
                form.instance.fiscal_year = fy
            elif isinstance(form, DebitNoteForm):
                number, seq, fy = generate_debit_note_number(company.id if company else None)
                form.instance.debit_note_number = number
                form.instance.sequence_number = seq
                form.instance.fiscal_year = fy

        response = super().form_valid(form)

        # No draft stage — notes apply (and journalise) immediately on creation
        if is_new:
            from apps.billing.services.note_service import apply_credit_note, apply_debit_note
            if isinstance(form, CreditNoteForm):
                apply_credit_note(form.instance)
            elif isinstance(form, DebitNoteForm):
                apply_debit_note(form.instance)

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

