# Backend Audit

Verified

1. Route registration and duplicate function scan.
2. Authentication, dashboard, driver, passenger, admin, tracking, SOS, notifications, complaints, Lost & Found, occupancy, heatmap, analytics, and command-center flows.
3. SQLAlchemy commit/rollback handling in high-risk write endpoints.
4. API response status behavior for common validation/auth errors.

Fixes Applied

1. Moved limiter initialization before route registration.
2. Added login/register/reset/forgot/Google auth throttles.
3. Added email and password validation for local auth flows.
4. Hardened admin bus capacity validation and route duplicate handling.
5. Fixed subscription endpoint control flow and database commit.
6. Fixed offline bus route geometry helper misuse.
7. Added stale in-memory state cleanup.
8. Optimized subscription cache query with a join.
9. Eager-loaded complaint and Lost & Found list relationships to reduce repeated lookups.

Notes

`LIVE_GPS_DATA`, `BUS_DELAY_DATA`, `BUS_SIMULATION_STATE`, and passenger tracking sessions remain in-process memory. This is acceptable for a single-process demo, but production multi-worker deployments should move this state to Redis or a database-backed store.
