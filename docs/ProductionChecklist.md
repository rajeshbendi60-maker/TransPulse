# Production Checklist

1. Install all dependencies from `requirements.txt`.
2. Set `SECRET_KEY`.
3. Set `GOOGLE_CLIENT_ID`.
4. Set SMTP credentials for password reset.
5. Configure `RATELIMIT_STORAGE_URI` to Redis or another persistent backend.
6. Run database migrations or confirm startup schema patching is acceptable.
7. Apply `migrations/versions/20260706_0001_production_indexes_and_schema_guards.py` against the existing database.
8. Run the full test suite.
9. Run browser QA for passenger, driver, and admin workflows.
10. Verify Google OAuth consent screen and authorized origins.
11. Verify HTTPS, secure cookies, proxy headers, and CSRF behavior.
12. Move live GPS/delay/session state to Redis for multi-worker deployments.
13. Schedule GTFS imports with backup/rollback procedure.
14. Monitor logs for `[APP_ERROR]`, `[GOOGLE_AUTH]`, `[GTFS ETL]`, and `[ROAD_GEOMETRY]`.
