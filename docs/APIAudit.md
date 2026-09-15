# API Audit

Verified And Fixed

1. Auth-required APIs return `401`; role violations return `403`.
2. Missing records return `404`.
3. Validation failures return `400`.
4. Creation endpoints return `201` where already implemented for complaints, Lost & Found, and SOS.
5. Server errors are logged and JSON APIs return a sanitized `500`.

Specific Fixes

1. `/api/alerts/subscribe` no longer requires `bus_id` for stop subscriptions and commits changes.
2. `/api/buses/offline` no longer crashes on route geometry or stop coordinate attributes.
3. `/api/driver/location` validates coordinate ranges.
4. Lost & Found date parsing now returns `400` for invalid date format.
5. JSON reads use `silent=True` in repaired endpoints to avoid unsupported-media failures.

Recommended Manual Tests

1. Login/register/logout flows.
2. Google login/register with valid and invalid ID tokens.
3. Driver start/end/location/occupancy/delay.
4. Passenger route search/tracking/SOS.
5. Admin SOS acknowledge/resolve and complaint/Lost & Found replies.
<!-- TP-v2.0-Release -->
