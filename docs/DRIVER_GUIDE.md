# Driver Guide

The Driver Dashboard acts as a specialized, low-distraction interface for operating the bus.

## Login
Drivers access the system using the unified Driver portal via a shared login (e.g., `driver@transpulse.com`), but physically claim their assigned trips via their uniquely provided Driver Code (e.g., `DRV-001`).

## Assigned Bus
Upon logging in, the system checks the backend to find any bus assigned to the driver by the Administrator. If unassigned, the interface remains gracefully offline.

## Start Trip
When a driver is ready to begin a route:
1. Click **Start Trip**.
2. The browser automatically provisions the hardware GPS receiver via `navigator.geolocation.watchPosition`.
3. The server immediately registers the bus into the public tracking stream.

## Live GPS Broadcasting
Drivers do not need to interact with the map. As long as the dashboard is open (even in the background on mobile browsers), it securely broadcasts latitude, longitude, heading, and speed directly to the backend every few seconds.

## Update Occupancy
Drivers can update the live density of the bus with a single tap:
- **Low (25%)**
- **Medium (55%)**
- **High (85%)**
This directly reflects on the Passenger Dashboard to help commuters plan appropriately.

## Emergency (SOS)
If an incident occurs, the driver can utilize the integrated SOS function to silently alert the Admin Dashboard with the bus's exact coordinates.

## End Trip
Clicking **End Trip** completes the forward route.
- The GPS receiver automatically powers down.
- The bus is temporarily hidden from the live public feed.
- The UI transforms into the `RETURN_READY` state.

## Start Return Trip
Clicking **Start Return Trip**:
- Reconstructs the GTFS geometry dynamically in reverse.
- Flips the origin and destination stops.
- Reignites the GPS broadcaster.

## End Return Trip
Concluding the return journey cleanly de-registers the bus from the active fleet, shutting down all telemetry streams, and marks the shift as offline.
