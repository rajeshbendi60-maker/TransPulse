# Multi-Worker Readiness

The current application keeps several live operational states in process memory. This works for a single-process deployment and local demos, but multiple Gunicorn workers or multiple instances will not share these values.

## In-Memory State To Externalize

- `LIVE_GPS_DATA`: live driver GPS packets.
- `BUS_DELAY_DATA`: generated/manual delay profiles and notification cooldowns.
- `BUS_SIMULATION_STATE`: fallback/simulated movement state.
- `PASSENGER_TRACKING_SESSIONS`: passenger tracking heartbeat state.
- `_MAP_DEFAULT_CENTER`: cached map center.

## Required Production Direction

- Move live GPS, delay profiles, cooldowns, and passenger tracking sessions to Redis or database tables before scaling beyond one worker.
- Use Redis TTLs for GPS freshness and tracking-session expiry.
- Keep road geometry in the database-backed `road_geometry_cache` table.
- Keep Flask-Limiter on Redis through `RATELIMIT_STORAGE_URI`.

No architecture redesign was implemented in this audit; this document identifies the required production scaling work.
