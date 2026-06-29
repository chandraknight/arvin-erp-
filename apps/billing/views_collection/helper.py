from ..forms import *

class NoteCreateUpdateMixin:
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def form_valid(self, form):
        is_new = not form.instance.pk
        if is_new:
            if isinstance(form, CreditNoteForm):
                form.instance.credit_note_number = generate_credit_note_number()
            elif isinstance(form, DebitNoteForm):
                form.instance.debit_note_number = generate_debit_note_number()

        response = super().form_valid(form)

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

