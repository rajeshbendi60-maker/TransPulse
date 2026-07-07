# Production Checklist

- Install all dependencies from `requirements.txt`.
- Set `SECRET_KEY`.
- Set `GOOGLE_CLIENT_ID`.
- Set SMTP credentials for password reset.
- Configure `RATELIMIT_STORAGE_URI` to Redis or another persistent backend.
- Run database migrations or confirm startup schema patching is acceptable.
- Apply `migrations/versions/20260706_0001_production_indexes_and_schema_guards.py` against the existing database.
- Run the full test suite.
- Run browser QA for passenger, driver, and admin workflows.
- Verify Google OAuth consent screen and authorized origins.
- Verify HTTPS, secure cookies, proxy headers, and CSRF behavior.
- Move live GPS/delay/session state to Redis for multi-worker deployments.
- Schedule GTFS imports with backup/rollback procedure.
- Monitor logs for `[APP_ERROR]`, `[GOOGLE_AUTH]`, `[GTFS ETL]`, and `[ROAD_GEOMETRY]`.
