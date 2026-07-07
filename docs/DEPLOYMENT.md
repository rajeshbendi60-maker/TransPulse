# Deployment

## Required Environment

- `SECRET_KEY`
- `DATABASE_URL`
- `GOOGLE_CLIENT_ID`
- `MAIL_USERNAME`
- `MAIL_PASSWORD`
- `RATELIMIT_STORAGE_URI`
- `FLASK_ENV=production`

## Steps

1. Install dependencies from `requirements.txt`.
2. Apply migrations or run the startup schema patch once against a backed-up database.
3. Import GTFS data with `flask import-gtfs` or `python import_apsrtc_data.py`.
4. Start with Gunicorn or the platform web command.
5. Verify login, Google auth, password reset, driver GPS, passenger tracking, SOS, and admin dashboards.

## Notes

- Use HTTPS in production.
- Use persistent rate-limit storage.
- Use one shared live-state backend if running more than one worker.
- See `ProductionConfiguration.md` and `MultiWorkerReadiness.md` for the final production configuration and scaling requirements.
