# Production Configuration

Required Environment Variables

1. `SECRET_KEY`: required stable secret for sessions, CSRF, and password reset tokens. Do not use a generated value in production.
2. `DATABASE_URL`: production database URL. `postgres://` is normalized to `postgresql://` by `config.py`.
3. `GOOGLE_CLIENT_ID`: OAuth client ID used as the expected Google ID token audience.
4. `MAIL_USERNAME`: SMTP username/sender for password reset email.
5. `MAIL_PASSWORD` or `TRANSPULSE_GMAIL_APP_PASSWORD`: SMTP password/app password.
6. `RATELIMIT_STORAGE_URI`: persistent Flask-Limiter storage. Redis is recommended, for example `redis://host:6379/0`.
7. `FLASK_ENV=production`: enables secure-cookie behavior.

Security Settings

1. `SESSION_COOKIE_HTTPONLY=True` prevents JavaScript from reading the session cookie.
2. `SESSION_COOKIE_SAMESITE=Lax` protects normal cross-site request contexts while preserving login navigation.
3. `SESSION_COOKIE_SECURE=True` when `FLASK_ENV=production`; production must use HTTPS.
4. CSRF is enabled globally with Flask-WTF.
5. Google auth rejects missing, invalid, unsigned, wrong-audience, wrong-issuer, subjectless, or unverified-email ID tokens.

Deployment Notes

1. Terminate TLS at the platform load balancer or reverse proxy.
2. Configure trusted proxy headers at the platform layer when deploying behind a proxy.
3. Use migrations in `migrations/versions/` against the existing database; do not recreate production data.
<!-- TP-v2.0-Release -->
