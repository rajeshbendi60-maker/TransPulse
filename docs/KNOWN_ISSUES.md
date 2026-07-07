# Known Issues

- Full runtime route tests were blocked in this workspace because the available Python runtime lacks the Flask dependencies and the system Python launcher is not usable.
- `LIVE_GPS_DATA`, delay profiles, and passenger tracking sessions are process-local.
- The GTFS importer purges GTFS-backed tables before loading a feed. Back up production data before imports.
- `calendar_dates.txt` and `feed_info.txt` are logged but not persisted because matching models are not currently defined.
- SQLite is acceptable for local/demo use. Production should use PostgreSQL for concurrency.
