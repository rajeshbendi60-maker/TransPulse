# GPS Engine

Live driver GPS is held in `LIVE_GPS_DATA` and exposed through the live bus APIs. Simulated movement uses GTFS stops/shapes and trip state when real driver coordinates are not fresh.

```mermaid
flowchart TD
    Driver["Driver location POST"] --> Validate["Coordinate, speed, jump validation"]
    Validate --> Memory["LIVE_GPS_DATA"]
    Memory --> Snapshot["Live fleet snapshot"]
    Snapshot --> Passenger["Passenger tracking"]
    Snapshot --> Admin["Admin live fleet"]
    Snapshot --> DriverDash["Driver telemetry"]
```

Key behaviors:

- Stale GPS packets are ignored by `_fresh_gps_packet`.
- Driver trip start/end clears stale live GPS state.
- Passenger tracking heartbeats are recorded by `/api/tracking/session`.
- Delay reports update ETA, schedule labels, and notifications.
- Completed trips can still be rendered briefly through `/api/tracking/completed/<bus_identifier>`.

Operational limits:

- In-memory GPS state is process-local. Multi-worker production deployments need Redis or another shared store.
