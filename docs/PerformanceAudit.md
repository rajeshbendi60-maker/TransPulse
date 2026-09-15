# Performance Audit

Fixes Applied

1. Added stale live-state cleanup for in-memory GPS/delay/simulation/session caches.
2. Replaced subscription cache N+1 lookups with a joined query.
3. Eager-loaded complaint and Lost & Found list relationships.
4. Added indexes for notification polling, SOS list filtering, road geometry cache lookup, and subscription uniqueness.
5. Preserved GTFS batching with `bulk_insert_mappings`.

Remaining Optimization Candidates

1. `_live_fleet_snapshot()` still performs multiple helper queries per active bus. For large fleets, preloading active trips, routes, stop times, shapes, and occupancy records would reduce query count further.
2. OSRM geometry generation is synchronous on request. Cached failures reduce repeated calls, but background generation would be better in production.
3. In-memory live state is not shared across workers.
<!-- TP-v2.0-Release -->
