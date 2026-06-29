"""
Consistent JSON response envelope helpers.

All API responses use one of three shapes:

Single object:
    {"success": true, "data": {...}, "message": "optional"}

List with pagination:
    {"success": true, "data": [...], "pagination": {...}}

Error:
    {"success": false, "error": "human readable", "code": "ERROR_CODE"}
"""
from rest_framework.response import Response


def api_success(data=None, message=None, status=200):
    """Return a successful single-object response."""
    payload = {'success': True}
    if data is not None:
        payload['data'] = data
    if message:
        payload['message'] = message
    return Response(payload, status=status)


def api_error(error, code=None, status=400):
    """Return an error response."""
    payload = {'success': False, 'error': error}
    if code:
        payload['code'] = code
    return Response(payload, status=status)


def api_list(data, pagination, message=None):
    """Return a paginated list response."""
    payload = {
        'success': True,
        'data': data,
        'pagination': pagination,
    }
    if message:
        payload['message'] = message
    return Response(payload, status=200)
