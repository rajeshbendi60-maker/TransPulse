# Known Issues

- Full runtime route tests were blocked in this workspace because the available Python runtime lacks the Flask dependencies and the system Python launcher is not usable.
- `LIVE_GPS_DATA`, delay profiles, and passenger tracking sessions are process-local.
- The GTFS importer purges GTFS-backed tables before loading a feed. Back up production data before imports.
- `calendar_dates.txt` and `feed_info.txt` are logged but not persisted because matching models are not currently defined.
- SQLite is acceptable for local/demo use. Production should use PostgreSQL for concurrency.


<!-- Merged from KnownIssues.md -->

# Known Issues

## Remaining Manual Work

- Codex cannot complete dependency installation/runtime verification in this execution environment.
- The user confirmed the local application starts successfully with `python app.py`, GTFS initializes, and database integrity checks pass.
- Production needs real `SECRET_KEY`, `GOOGLE_CLIENT_ID`, SMTP credentials, and persistent rate-limit storage.
- In-memory GPS/tracking/delay state should be externalized for multi-worker production.
- No Alembic migration files were generated for the new indexes/constraint.
- Full browser QA was not run in this environment.

## Residual Risk

- Some dashboard views still perform repeated helper queries at fleet scale.
- OSRM road geometry generation is synchronous when cache misses occur.
- Existing mojibake text in templates remains cosmetic debt.
