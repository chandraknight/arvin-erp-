from django.shortcuts import redirect


def home_redirect_view(request):
    user = request.user
    if user.is_authenticated:
        if user.is_staff or user.is_superuser or user.is_company_admin:
            return redirect('accounts:user_dashboard')
        return redirect('ecom:account')
    return redirect('ecom:home')
