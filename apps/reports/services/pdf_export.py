"""Shared PDF rendering for report export views."""
from django.http import HttpResponse
from django.template.loader import render_to_string
from weasyprint import HTML


def render_pdf_response(template_name, context, filename):
    html_string = render_to_string(template_name, context)
    pdf_bytes = HTML(string=html_string).write_pdf()

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
