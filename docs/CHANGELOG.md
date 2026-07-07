# Changelog

## 2026-07-05 Production Audit Pass

- Added JSON-aware 401, 403, 404, and 500 handling.
- Added security headers and safer session behavior.
- Added missing complaint model fields used by routes.
- Added compatibility migrations for complaint fields and lookup indexes.
- Added missing `/api/tracking/session` heartbeat endpoint.
- Added missing SOS acknowledge and resolve endpoints used by the frontend.
- Removed non-APSRTC heatmap hub labels.
- Reworked GTFS import into a batched transactional loader.
- Added `trips.gtfs_trip_id` for efficient GTFS stop-time linking.
- Added requested documentation files.
