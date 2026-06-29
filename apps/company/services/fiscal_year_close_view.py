from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import redirect, get_object_or_404, render
from django.views.decorators.http import require_http_methods
from ..models import FiscalYear


@login_required
@require_http_methods(["GET", "POST"])
def close_fiscal_year(request, pk):
    """
    GET  → show pre-close validation page with all checks
    POST → execute close if validation passes and user typed CLOSE
    """
    company = getattr(request.user, 'company', None)
    if not company:
        messages.error(request, "No company associated with your account.")
        return redirect('company:fiscalyear_list')

    fy = get_object_or_404(FiscalYear, pk=pk, company=company)

    if fy.is_closed:
        messages.warning(request, f"Fiscal year {fy.name} is already closed.")
        return redirect('company:fiscalyear_list')

    # Run validation
    validation = fy.get_close_validation()

    if request.method == 'POST':
        # Hard-block if there are errors
        if validation['errors']:
            messages.error(
                request,
                "Cannot close fiscal year — please resolve all blocking issues first."
            )
            return render(request, 'company/fiscalyear_close.html', {
                'fy': fy,
                'validation': validation,
            })

        # Require typed confirmation
        if request.POST.get('confirm') != 'CLOSE':
            messages.error(request, "Please type CLOSE exactly to confirm.")
            return render(request, 'company/fiscalyear_close.html', {
                'fy': fy,
                'validation': validation,
            })

        try:
            fy.close(closed_by_user=request.user)
            messages.success(
                request,
                f"✓ Fiscal year {fy.name} closed successfully. "
                "A year-end closing journal entry has been created. "
                "This period is now read-only."
            )
        except Exception as e:
            messages.error(request, f"Error closing fiscal year: {str(e)}")

        return redirect('company:fiscalyear_list')

    # GET — show the pre-close check page
    return render(request, 'company/fiscalyear_close.html', {
        'fy': fy,
        'validation': validation,
    })
