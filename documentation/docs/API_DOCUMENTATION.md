# Internal API Documentation

The following endpoints are used by the frontend SPA dashboards to maintain real-time state without reloading the page.

## 1. GET /api/buses/live
- Description: Retrieves the real-time coordinates, speed, and status of all active buses.
- Usage: Polled by the Passenger and Admin dashboards to update the map markers.

## 2. POST /api/driver/status
- Description: Receives live GPS telemetry from active drivers.
- Payload: JSON containing latitude, longitude, speed, and current stop index.
- Usage: Called via JavaScript setInterval on the Driver Dashboard.

## 3. GET /api/buses/route-info
- Description: Retrieves the list of stops and coordinates for a specific route.
- Usage: Used to draw the route path sequence on the map.

## 4. POST /api/sos/trigger
- Description: Emits an emergency distress signal.
- Payload: JSON containing the location and bus ID.
- Usage: Updates the SOS monitoring table on the Admin Dashboard.
