# Known Issues

1. Full runtime route tests were blocked in this workspace because the available Python runtime lacks the Flask dependencies and the system Python launcher is not usable.
2. `LIVE_GPS_DATA`, delay profiles, and passenger tracking sessions are process-local.
3. The GTFS importer purges GTFS-backed tables before loading a feed. Back up production data before imports.
4. `calendar_dates.txt` and `feed_info.txt` are logged but not persisted because matching models are not currently defined.
5. SQLite is acceptable for local/demo use. Production should use PostgreSQL for concurrency.

Remaining Manual Work

1. Codex cannot complete dependency installation/runtime verification in this execution environment.
2. The user confirmed the local application starts successfully with `python app.py`, GTFS initializes, and database integrity checks pass.
3. Production needs real `SECRET_KEY`, `GOOGLE_CLIENT_ID`, SMTP credentials, and persistent rate-limit storage.
4. In-memory GPS/tracking/delay state should be externalized for multi-worker production.
5. No Alembic migration files were generated for the new indexes/constraint.
6. Full browser QA was not run in this environment.

Residual Risk

1. Some dashboard views still perform repeated helper queries at fleet scale.
2. OSRM road geometry generation is synchronous when cache misses occur.
3. Existing mojibake text in templates remains cosmetic debt.
<!-- TP-v2.0-Release -->
