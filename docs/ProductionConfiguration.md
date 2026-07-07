# Production Configuration

## Required Environment Variables

- `SECRET_KEY`: required stable secret for sessions, CSRF, and password reset tokens. Do not use a generated value in production.
- `DATABASE_URL`: production database URL. `postgres://` is normalized to `postgresql://` by `config.py`.
- `GOOGLE_CLIENT_ID`: OAuth client ID used as the expected Google ID token audience.
- `MAIL_USERNAME`: SMTP username/sender for password reset email.
- `MAIL_PASSWORD` or `TRANSPULSE_GMAIL_APP_PASSWORD`: SMTP password/app password.
- `RATELIMIT_STORAGE_URI`: persistent Flask-Limiter storage. Redis is recommended, for example `redis://host:6379/0`.
- `FLASK_ENV=production`: enables secure-cookie behavior.

## Security Settings

- `SESSION_COOKIE_HTTPONLY=True` prevents JavaScript from reading the session cookie.
- `SESSION_COOKIE_SAMESITE=Lax` protects normal cross-site request contexts while preserving login navigation.
- `SESSION_COOKIE_SECURE=True` when `FLASK_ENV=production`; production must use HTTPS.
- CSRF is enabled globally with Flask-WTF.
- Google auth rejects missing, invalid, unsigned, wrong-audience, wrong-issuer, subjectless, or unverified-email ID tokens.

## Deployment Notes

- Terminate TLS at the platform load balancer or reverse proxy.
- Configure trusted proxy headers at the platform layer when deploying behind a proxy.
- Use migrations in `migrations/versions/` against the existing database; do not recreate production data.
