# Performance

Implemented improvements:

- GTFS trip linking uses `gtfs_trip_id` and bulk insert mappings.
- Stop times, trips, and occupancy have composite indexes for frequent lookups.
- Existing SQLite databases receive index backfills at startup.
- Tracking frontend avoids overlapping map updates with `mapUpdateInFlight`.
- The app uses SQLAlchemy `pool_pre_ping`.

High-value cache areas:

- GTFS route and stop schedule payloads.
- Shape path lists by `shape_id`.
- Route geometry cache in `road_geometry_cache`.
- Fleet snapshot response for admin dashboards.
- Heatmap city density payload.

Production note: in-memory caches are per-process. Use Redis or database-backed cache for multi-worker consistency.
