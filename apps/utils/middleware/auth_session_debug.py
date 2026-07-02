import json
import logging


logger = logging.getLogger('audit')


class AuthSessionDebugMiddleware:
    """
    Temporary production diagnostic for the staging login loop.
    Logs only auth/session metadata, never cookies or session contents.
    """

    WATCHED_PATHS = frozenset({
        '/accounts/dashboard/',
    })

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path_info in self.WATCHED_PATHS:
            user = getattr(request, 'user', None)
            session = getattr(request, 'session', None)
            if session is not None and (not user or not user.is_authenticated):
                auth_user_id = session.get('_auth_user_id')
                auth_backend = session.get('_auth_user_backend')
                auth_hash_present = bool(session.get('_auth_user_hash'))
                logger.warning(
                    json.dumps(
                        {
                            "event": "auth_session_anonymous_dashboard",
                            "path": request.path_info,
                            "session_key": getattr(session, "session_key", None),
                            "session_auth_user_id": auth_user_id,
                            "session_auth_backend": auth_backend,
                            "session_auth_hash_present": auth_hash_present,
                        },
                        default=str,
                    )
                )

        return self.get_response(request)
