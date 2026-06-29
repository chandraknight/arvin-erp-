import json
from django.shortcuts import render
from django.http import JsonResponse
from django.db import connection


def health_check(request):
    """
    Liveness + readiness probe for Docker, Kubernetes, and load balancers.
    Returns 200 when the app and DB are healthy, 503 otherwise.
    """
    db_ok = False
    try:
        connection.ensure_connection()
        db_ok = True
    except Exception:
        pass

    status = 200 if db_ok else 503
    return JsonResponse({'status': 'ok' if db_ok else 'degraded', 'db': db_ok}, status=status)


def search_results(request):
    query = request.GET.get('q')
    # Implement your search logic here. For now, it will just display the query.
    context = {
        'query': query,
        'results': [], # Placeholder for actual search results
    }
    return render(request, 'search/search_results.html', context) 