from django.contrib.auth.decorators import login_required
from django.http import JsonResponse

from apps.bookkeeping.models import LedgerAccount


@login_required
def account_search(request):
    q = request.GET.get('q', '')
    company = request.user.company

    accounts = LedgerAccount.objects.filter(
        company=company,
        name__icontains=q
    ).values('id', 'name')[:20]

    return JsonResponse(list(accounts), safe=False)