# API Audit

## Verified And Fixed

- Auth-required APIs return `401`; role violations return `403`.
- Missing records return `404`.
- Validation failures return `400`.
- Creation endpoints return `201` where already implemented for complaints, Lost & Found, and SOS.
- Server errors are logged and JSON APIs return a sanitized `500`.

## Specific Fixes

- `/api/alerts/subscribe` no longer requires `bus_id` for stop subscriptions and commits changes.
- `/api/buses/offline` no longer crashes on route geometry or stop coordinate attributes.
- `/api/driver/location` validates coordinate ranges.
- Lost & Found date parsing now returns `400` for invalid date format.
- JSON reads use `silent=True` in repaired endpoints to avoid unsupported-media failures.

## Recommended Manual Tests

- Login/register/logout flows.
- Google login/register with valid and invalid ID tokens.
- Driver start/end/location/occupancy/delay.
- Passenger route search/tracking/SOS.
- Admin SOS acknowledge/resolve and complaint/Lost & Found replies.
