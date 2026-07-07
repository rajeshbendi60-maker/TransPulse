# GTFS Audit

## Verified

- `import_apsrtc_data.py` transaction scope, rollback behavior, batching, stop-times, shapes, route metadata, logging, and duplicate import behavior.
- Route display fields now come from `routes.txt` only. They are not derived from sampled trip endpoints and are not used for GTFS assignment validation.
- Trip assignment now resolves from `Route -> GTFS Trip candidates -> direction -> StopTimes -> Shape -> nearest scheduled departure`.
- `StopTime` is the authoritative source for stop order, arrivals, departures, current stop, and next stop.
- Missing trip shapes are generated from ordered stop coordinates when the feed does not provide usable shape points.

## Fixes Applied

- Added safe zip extraction to block path traversal from malformed archives.
- Added duplicate/blank GTFS ID handling before route, stop, trip, shape, and stop-time insertion.
- Imported `calendar_dates.txt` and `feed_info.txt`.
- Added post-import integrity checks for orphan trips, orphan stop_times, duplicate GTFS IDs, duplicate shape sequences, duplicate stop-time sequences, and missing trip shapes.
- Removed endpoint-based GTFS validation. `Route.origin` and `Route.destination` are display-only fields.
- Kept one final commit for the import transaction and rollback on failure.
- Replaced `models/import_apsrtc_data.py` with a compatibility wrapper around the audited importer.

## Runtime Verification

Verified against `instance/transpulse.db` on 2026-07-06:

- Tables present: `routes`, `trips`, `stops`, `stop_times`, `shapes`, `calendar`, `calendar_dates`, `feed_info`.
- Current GTFS counts: 3,075 routes, 3,077 trips, 1,898 stops, 57,865 stop_times, 57,839 shape points.
- Assignment simulation checked every route. Result: 3,075 of 3,075 routes resolved to a GTFS trip.
- Resolved trips all have `gtfs_trip_id`, `service_id`, `direction_id`, `shape_id`, at least two stop_times, and at least two shape points.
- Integrity checks after repair: zero orphan trips, zero orphan stop_times, zero orphan shapes, zero duplicate route codes, zero duplicate GTFS trip IDs, zero duplicate stop codes, zero duplicate shape sequences, zero duplicate stop-time sequences, zero invalid shape references, zero non-continuous stop-time sequences, and zero missing stop coordinates.
- Data repair applied: removed 99 orphan stop_times left by prior deleted trip IDs, and backfilled 3,075 template trip `gtfs_trip_id` values from `gtfs_data/trips.txt`.
- Clean import verification into a temporary SQLite database produced zero duplicate routes, trips, stops, stop_times, or shapes, and zero invalid route, stop-time, stop, or shape references.

## Remaining Watch Items

- Import currently loads CSV rows into memory. This is acceptable for the included dataset size, but very large feeds should stream or chunk transform rows.
- Existing buses/trips are purged with GTFS-backed tables. Confirm operational data retention expectations before production imports.
- Apply migration `20260706_0002_gtfs_metadata_and_shape_integrity.py` before production import on existing databases.
- The extracted local feed currently does not include `agency.txt`, `calendar.txt`, `calendar_dates.txt`, or `feed_info.txt`; the importer supports them, and the database tables exist, but those source files imported zero rows in this feed copy.
