# Backend Audit

## Verified

- Route registration and duplicate function scan.
- Authentication, dashboard, driver, passenger, admin, tracking, SOS, notifications, complaints, Lost & Found, occupancy, heatmap, analytics, and command-center flows.
- SQLAlchemy commit/rollback handling in high-risk write endpoints.
- API response status behavior for common validation/auth errors.

## Fixes Applied

- Moved limiter initialization before route registration.
- Added login/register/reset/forgot/Google auth throttles.
- Added email and password validation for local auth flows.
- Hardened admin bus capacity validation and route duplicate handling.
- Fixed subscription endpoint control flow and database commit.
- Fixed offline bus route geometry helper misuse.
- Added stale in-memory state cleanup.
- Optimized subscription cache query with a join.
- Eager-loaded complaint and Lost & Found list relationships to reduce repeated lookups.

## Notes

- `LIVE_GPS_DATA`, `BUS_DELAY_DATA`, `BUS_SIMULATION_STATE`, and passenger tracking sessions remain in-process memory. This is acceptable for a single-process demo, but production multi-worker deployments should move this state to Redis or a database-backed store.
