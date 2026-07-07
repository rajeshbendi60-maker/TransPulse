# Performance Audit

## Fixes Applied

- Added stale live-state cleanup for in-memory GPS/delay/simulation/session caches.
- Replaced subscription cache N+1 lookups with a joined query.
- Eager-loaded complaint and Lost & Found list relationships.
- Added indexes for notification polling, SOS list filtering, road geometry cache lookup, and subscription uniqueness.
- Preserved GTFS batching with `bulk_insert_mappings`.

## Remaining Optimization Candidates

- `_live_fleet_snapshot()` still performs multiple helper queries per active bus. For large fleets, preloading active trips, routes, stop times, shapes, and occupancy records would reduce query count further.
- OSRM geometry generation is synchronous on request. Cached failures reduce repeated calls, but background generation would be better in production.
- In-memory live state is not shared across workers.
