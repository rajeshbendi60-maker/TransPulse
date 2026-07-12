# Passenger Guide

The Passenger Dashboard is an anonymous, public-facing portal designed to provide commuters with pixel-perfect tracking and ETAs.

## Track Bus
Passengers can track any active bus by navigating to `/tracking/<bus_number>`. If they do not know the number, the system automatically provisions an intuitive search functionality to discover buses.

## Real-Time Map
The map engine receives telemetry from the driver. 
- Markers glide smoothly using sub-second mathematical interpolation.
- The actual GTFS road network geometry is securely painted directly onto the map context.

## ETA & Progress
Using advanced geospatial calculations, TransPulse projects the remaining distance across the active route shape and combines it with real-time velocity to predict an accurate Estimated Time of Arrival (ETA).

## Route Timeline
A vertical timeline visually represents the sequence of stops.
- Completed stops are grayed out.
- The Active stop illuminates.
- Remaining stops display dynamically adjusted expected times.

## Occupancy
Passengers can see real-time crowding levels (Low, Medium, High) submitted directly by the drivers.

## Completed Trips
If a commuter attempts to track a bus that has just finished its route, TransPulse gracefully handles the transition. Instead of dropping the user into an error state, the system retrieves a static snapshot of the concluded trip, displaying a timeline of actual arrival times.

## Offline Buses
Buses that have not yet been started by a driver gracefully show an "Offline" state, ensuring passengers are not misled by stale coordinates.
