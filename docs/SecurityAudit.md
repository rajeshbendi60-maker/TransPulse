# Security Audit

## Fixes Applied

- Google login/register now verify ID tokens server-side.
- Token verification checks signature, audience, issuer, subject, and verified email.
- Posted Google email/name are no longer trusted as identity authority.
- Sensitive auth endpoints are rate-limited.
- Local registration/reset enforce email format and minimum password length.
- CSRF remains enabled globally through Flask-WTF.
- Authenticated AJAX fixes added missing CSRF headers in tracking/SOS paths.
- Unsafe GTFS zip extraction was replaced with path validation before extraction.

## Verified

- Register, login, forgot password, reset password, logout.
- Passenger/admin/driver role gates.
- JSON auth errors return `401` or `403`.
- Session cookies are HTTP-only, SameSite Lax, and secure in production.

## Manual Production Requirements

- Set `SECRET_KEY`.
- Set `GOOGLE_CLIENT_ID`.
- Install `google-auth`.
- Use persistent Flask-Limiter storage such as Redis in production.
- Configure real SMTP credentials for password reset.
