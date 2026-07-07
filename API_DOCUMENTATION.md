# TransPulse API Documentation

TransPulse uses RESTful API endpoints for client-server communication. The following highlights the primary APIs used by the frontend applications.

## Authentication APIs

### Login
- **Method:** `POST`
- **Endpoint:** `/api/login`
- **Description:** Authenticates a user and establishes a secure session cookie.
- **Payload:** `{ "email": "...", "password": "..." }`
- **Response:** `{ "success": true, "redirect": "/dashboard" }`

### Logout
- **Method:** `POST`
- **Endpoint:** `/api/logout`
- **Description:** Terminates the active session securely.
- **Response:** `{ "success": true }`

---

## Driver APIs

### Start Trip
- **Method:** `POST`
- **Endpoint:** `/api/driver/start-trip`
- **Description:** Transitions a driver's assigned bus into an active state. Creates a new Trip record.
- **Response:** `{ "success": true, "trip_id": 123, "bus_status": "ACTIVE" }`

### End Trip
- **Method:** `POST`
- **Endpoint:** `/api/driver/end-trip`
- **Description:** Concludes an active trip. Automatically manages state transition into `RETURN_READY` or `OFFLINE`.
- **Response:** `{ "success": true, "next_trip_status": "OFFLINE" }`

### Update Occupancy
- **Method:** `POST`
- **Endpoint:** `/api/driver/update-occupancy`
- **Description:** Submits live passenger density for the active bus.
- **Payload:** `{ "level": "LOW|MEDIUM|HIGH" }`
- **Response:** `{ "success": true }`

### Broadcast GPS
- **Method:** `POST`
- **Endpoint:** `/api/driver/gps`
- **Description:** Ingests live telemetry coordinates from the driver's device.
- **Payload:** `{ "lat": 16.5, "lon": 80.6, "speed": 40, "bearing": 90 }`
- **Response:** `{ "success": true }`

---

## Passenger Tracking APIs

### Live Fleet Feed
- **Method:** `GET`
- **Endpoint:** `/api/buses/live`
- **Description:** Streams real-time telemetry, ETA, and progress of all currently active buses.
- **Response:** `{ "buses": [ { "bus_id": 1, "lat": 16.5, "lon": 80.6, "status": "Running", ... } ] }`

### Completed Trip Snapshot
- **Method:** `GET`
- **Endpoint:** `/api/tracking/completed/<bus_identifier>`
- **Description:** Retrieves the static summary timeline and metrics for a trip that has concluded.
- **Response:** `{ "success": true, "bus": { "service_status": "completed", "stops": [...] } }`

---

## Admin APIs

### Assign Bus
- **Method:** `POST`
- **Endpoint:** `/api/admin/assign-bus`
- **Description:** Allocates a physical bus to a specific driver and GTFS route.
- **Payload:** `{ "bus_id": 1, "route_id": 5, "driver_code": "DRV-001" }`
- **Response:** `{ "success": true }`

### Create SOS Alert
- **Method:** `POST`
- **Endpoint:** `/api/sos`
- **Description:** Dispatches an emergency alert directly to the central command dashboard.
- **Payload:** `{ "bus_id": 1, "emergency_type": "Medical Emergency" }`
- **Response:** `{ "success": true }`
