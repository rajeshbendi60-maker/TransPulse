# Performance

Implemented improvements:

1. GTFS trip linking uses `gtfs_trip_id` and bulk insert mappings.
2. Stop times, trips, and occupancy have composite indexes for frequent lookups.
3. Existing SQLite databases receive index backfills at startup.
4. Tracking frontend avoids overlapping map updates with `mapUpdateInFlight`.
5. The app uses SQLAlchemy `pool_pre_ping`.

High-value cache areas:

1. GTFS route and stop schedule payloads.
2. Shape path lists by `shape_id`.
3. Route geometry cache in `road_geometry_cache`.
4. Fleet snapshot response for admin dashboards.
5. Heatmap city density payload.

Production note: in-memory caches are per-process. Use Redis or database-backed cache for multi-worker consistency.
