# Changelog - TransPulse

All notable changes to the TransPulse project are documented in this file.

---

## [2.0.0] - 2026-07-08

### Added
- **Centralized GPS & Live Tracking Control:**
  - Added backend-driven `tracking_available` flag as the single source of truth across all modules.
  - Disabled Track actions across passenger lists, search results, admin fleets, and tracking history lists when a bus is offline.
  - Built automatic live recovery on tracking screens when drivers start the trip.
- **Dynamic Stop progression & Monotonic progression constraint:**
  - Implemented closest-stop GPS lookup based on coordinate distances.
  - Enforced a strict monotonic stop index condition (`max(prev_stop_idx, nearest_stop_idx)`) to prevent timeline jumps from GPS signal drift.
  - Configured adaptive stop detection boundaries (default 30 meters).
- **Blended ETA Calculation Engine:**
  - Implemented blended speed estimation: `(0.5 * Live Speed) + (0.3 * Historical Average) + (0.2 * Scheduled Speed)`.
  - Added live delay propagation and schedule blending.
- **Return Journey Support:**
  - Added driver action to start return journeys, reversing stops sequences, timelines, metrics, and geometry layouts automatically.
- **Resilient Map Route snappings fallback:**
  - Designed hierarchical Leaflet routing: GTFS Shapes ➜ Backend road cache ➜ Client-side OSRM queries ➜ Straight-line fallback with console warnings.
  - Placed the live bus marker directly on GPS coordinate fixes to remove visual sliding animations.

---

## [1.0.0] - 2026-06-01

### Added
- Initial project release.
- Static scheduling and route listings.
- User authentication and role authorizations.
- Basic driver and passenger screens.
- Basic complaints lodging and lost & found reporting forms.
