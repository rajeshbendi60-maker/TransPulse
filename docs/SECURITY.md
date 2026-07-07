# Security

Implemented controls:

- Flask-Login protects dashboards and private APIs.
- Role decorators enforce admin, driver, and passenger permissions.
- Flask-WTF CSRF protects forms and same-origin AJAX.
- API unauthorized/forbidden responses return JSON status codes.
- Session cookies are HTTP-only, SameSite Lax, and secure in production.
- Login clears the old session before creating the authenticated session.
- Password reset tokens are signed and include a password-hash fingerprint.
- Security headers are added after each request.
- Mail and default bootstrap passwords are environment-driven.

Required production environment:

- `SECRET_KEY`
- `DATABASE_URL`
- `TRANSPULSE_DEFAULT_ADMIN_PASSWORD`
- `TRANSPULSE_DEFAULT_PASSENGER_PASSWORD`
- `TRANSPULSE_DEFAULT_DRIVER_PASSWORD`
- `MAIL_USERNAME`
- `MAIL_PASSWORD`
- `RATELIMIT_STORAGE_URI` for non-memory rate limit storage

Remaining security work:

- Use a shared server-side store for GPS/session-like live state in multi-worker deployments.
- Add centralized audit logging for admin status changes.
