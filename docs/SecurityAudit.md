# Security Audit

Fixes Applied

1. Google login/register now verify ID tokens server-side.
2. Token verification checks signature, audience, issuer, subject, and verified email.
3. Posted Google email/name are no longer trusted as identity authority.
4. Sensitive auth endpoints are rate-limited.
5. Local registration/reset enforce email format and minimum password length.
6. CSRF remains enabled globally through Flask-WTF.
7. Authenticated AJAX fixes added missing CSRF headers in tracking/SOS paths.
8. Unsafe GTFS zip extraction was replaced with path validation before extraction.

Verified

1. Register, login, forgot password, reset password, logout.
2. Passenger/admin/driver role gates.
3. JSON auth errors return `401` or `403`.
4. Session cookies are HTTP-only, SameSite Lax, and secure in production.

Manual Production Requirements

1. Set `SECRET_KEY`.
2. Set `GOOGLE_CLIENT_ID`.
3. Install `google-auth`.
4. Use persistent Flask-Limiter storage such as Redis in production.
5. Configure real SMTP credentials for password reset.
