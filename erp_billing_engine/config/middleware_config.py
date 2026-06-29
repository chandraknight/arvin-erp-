MIDDLEWARE = [
    # ── Core Django ────────────────────────────────────────────────────────────
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',

    # ── Security: rate limiting & brute-force protection ──────────────────────
    # Must run BEFORE session expiry so locked-out requests are rejected early.
    'apps.utils.middleware.rate_limit.RateLimitMiddleware',
    'apps.utils.middleware.login_attempt_guard.LoginAttemptGuardMiddleware',

    # ── Security: session lifecycle ───────────────────────────────────────────
    'apps.utils.middleware.session_expiry.SessionExpiryMiddleware',

    # ── Security: multi-tenant isolation ─────────────────────────────────────
    'apps.utils.middleware.company_isolation.CompanyIsolationMiddleware',

    # ── Security: response hardening ─────────────────────────────────────────
    # Runs last so it can set headers on every response including error pages.
    'apps.utils.middleware.security_headers.SecurityHeadersMiddleware',

    # ── Observability: audit trail ────────────────────────────────────────────
    'apps.utils.middleware.audit_log.AuditLogMiddleware',

    # ── Activity log (thread-local user/IP for signals) ───────────────────────
    'apps.activity_log.middleware.ActivityLogMiddleware',
]