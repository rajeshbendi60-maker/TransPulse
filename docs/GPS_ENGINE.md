GPS Engine

Live driver GPS is held in memory and exposed through the live bus APIs. Simulated movement uses GTFS stops, shapes, and trip state when real driver coordinates are not fresh.

Key behaviors:

1. Stale GPS packets are ignored during validation.
2. Driver trip start and end events clear the stale live GPS state.
3. Passenger tracking heartbeats are recorded by the tracking session endpoint.
4. Delay reports update ETA, schedule labels, and notifications.
5. Completed trips can still be rendered briefly through the completed tracking endpoints.
6. The driver's location is posted, validated for coordinates, speed, and jumps, stored in memory, and merged into a live fleet snapshot which feeds the passenger tracking map, the admin fleet view, and the driver telemetry.

Operational limits:

1. In-memory GPS state is process-local. Multi-worker production deployments need a shared store.
