# TransPulse API Documentation

TransPulse uses RESTful API endpoints for client-server communication. The following highlights the primary APIs used by the frontend applications.

Authentication APIs

Login

1. Method: `POST`
2. Endpoint: `/api/login`
3. Description: Authenticates a user and establishes a secure session cookie.
4. Payload: `{ "email": "...", "password": "..." }`
5. Response: `{ "success": true, "redirect": "/dashboard" }`

Logout

1. Method: `POST`
2. Endpoint: `/api/logout`
3. Description: Terminates the active session securely.
4. Response: `{ "success": true }`

---

Driver APIs

Start Trip

1. Method: `POST`
2. Endpoint: `/api/driver/start-trip`
3. Description: Transitions a driver's assigned bus into an active state. Creates a new Trip record.
4. Response: `{ "success": true, "trip_id": 123, "bus_status": "ACTIVE" }`

End Trip

1. Method: `POST`
2. Endpoint: `/api/driver/end-trip`
3. Description: Concludes an active trip. Automatically manages state transition into `RETURN_READY` or `OFFLINE`.
4. Response: `{ "success": true, "next_trip_status": "OFFLINE" }`

Update Occupancy

1. Method: `POST`
2. Endpoint: `/api/driver/update-occupancy`
3. Description: Submits live passenger density for the active bus.
4. Payload: `{ "level": "LOW|MEDIUM|HIGH" }`
5. Response: `{ "success": true }`

Broadcast GPS

1. Method: `POST`
2. Endpoint: `/api/driver/gps`
3. Description: Ingests live telemetry coordinates from the driver's device.
4. Payload: `{ "lat": 16.5, "lon": 80.6, "speed": 40, "bearing": 90 }`
5. Response: `{ "success": true }`

---

Passenger Tracking APIs

Live Fleet Feed

1. Method: `GET`
2. Endpoint: `/api/buses/live`
3. Description: Streams real-time telemetry, ETA, and progress of all currently active buses.
4. Response: `{ "buses": [ { "bus_id": 1, "lat": 16.5, "lon": 80.6, "status": "Running", ... } ] }`

Completed Trip Snapshot

1. Method: `GET`
2. Endpoint: `/api/tracking/completed/<bus_identifier>`
3. Description: Retrieves the static summary timeline and metrics for a trip that has concluded.
4. Response: `{ "success": true, "bus": { "service_status": "completed", "stops": [...] } }`

---

Admin APIs

Assign Bus

1. Method: `POST`
2. Endpoint: `/api/admin/assign-bus`
3. Description: Allocates a physical bus to a specific driver and GTFS route.
4. Payload: `{ "bus_id": 1, "route_id": 5, "driver_code": "DRV-001" }`
5. Response: `{ "success": true }`

Create SOS Alert

1. Method: `POST`
2. Endpoint: `/api/sos`
3. Description: Dispatches an emergency alert directly to the central command dashboard.
4. Payload: `{ "bus_id": 1, "emergency_type": "Medical Emergency" }`
5. Response: `{ "success": true }`

---

API Reference

All state-changing APIs are protected by Flask-WTF CSRF. The base template injects the token into forms and same-origin `fetch()` requests.

Authentication:

1. `POST /login`
2. `POST /logout`
3. `POST /google_login`
4. `POST /google_register`
5. `GET|POST /forgot-password`
6. `GET|POST /reset-password/<token>`

Fleet and tracking:

1. `GET /api/buses/live`
2. `GET /api/buses/offline`
3. `GET /api/routes/live`
4. `GET /api/map/center`
5. `GET /api/tracking/completed/<bus_identifier>`
6. `POST /api/tracking/session`

Driver:

1. `POST /api/driver/start-trip`
2. `POST /api/driver/end-trip`
3. `POST /api/driver/location`
4. `POST /api/driver/update-occupancy`
5. `POST /api/driver/report-delay`
6. `POST /api/buses/delay`
7. `GET /api/driver/analytics`

Operations:

1. `GET|POST /api/complaints`
2. `POST /api/complaints/<id>/reply`
3. `GET|POST /api/lost-and-found`
4. `POST /api/lost-and-found/<id>/reply`
5. `POST /api/lost-and-found/<id>/return`
6. `GET|POST /api/notifications`
7. `GET /api/notifications/unread`
8. `POST /api/notifications/<id>/read`

SOS:

1. `POST /api/sos/trigger`
2. `GET /api/sos/<id>/status`
3. `GET /api/admin/sos`
4. `POST /api/admin/sos/<id>/status`
5. `POST /api/sos/driver/acknowledge/<id>`
6. `POST /api/sos/resolve/<id>`

Admin analytics:

1. `GET /api/command-center/stats`
2. `GET /api/admin/data-integrity`
3. `GET /heatmap/data`

API errors return JSON with an HTTP status code for AJAX/API callers.
<!-- TP-v2.0-Release -->
