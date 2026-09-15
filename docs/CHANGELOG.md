# Changelog - TransPulse

All notable changes to the TransPulse project are documented in this file.

---

[2.0.0] - 2026-07-08

Added

1. Centralized GPS & Live Tracking Control:
   1. Added backend-driven `tracking_available` flag as the single source of truth across all modules.
   2. Disabled Track actions across passenger lists, search results, admin fleets, and tracking history lists when a bus is offline.
   3. Built automatic live recovery on tracking screens when drivers start the trip.
2. Dynamic Stop progression & Monotonic progression constraint:
   1. Implemented closest-stop GPS lookup based on coordinate distances.
   2. Enforced a strict monotonic stop index condition (`max(prev_stop_idx, nearest_stop_idx)`) to prevent timeline jumps from GPS signal drift.
   3. Configured adaptive stop detection boundaries (default 30 meters).
3. Blended ETA Calculation Engine:
   1. Implemented blended speed estimation: `(0.5 * Live Speed) + (0.3 * Historical Average) + (0.2 * Scheduled Speed)`.
   2. Added live delay propagation and schedule blending.
4. Return Journey Support:
   1. Added driver action to start return journeys, reversing stops sequences, timelines, metrics, and geometry layouts automatically.
5. Resilient Map Route snappings fallback:
   1. Designed hierarchical Leaflet routing: GTFS Shapes --> Backend road cache --> Client-side OSRM queries --> Straight-line fallback with console warnings.
   2. Placed the live bus marker directly on GPS coordinate fixes to remove visual sliding animations.

---

[1.0.0] - 2026-06-01

Added

1. Initial project release.
2. Static scheduling and route listings.
3. User authentication and role authorizations.
4. Basic driver and passenger screens.
5. Basic complaints lodging and lost & found reporting forms.
