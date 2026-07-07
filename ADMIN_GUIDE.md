# Admin Guide

The Admin Dashboard is the central orchestration hub of TransPulse.

## Create Routes
Before buses can operate, routes must be established. Admins can manage these via the **Route Management** panel, ensuring accurate source and destination names.

## Import GTFS
TransPulse supports dynamic ingestion of GTFS static files.
1. Place the standard GTFS text files into the `gtfs_data/` directory.
2. Run the `flask import-gtfs` command.
3. The system parses shapes, stops, and sequences directly into the database.

## Assign Drivers
Admins allocate uniquely tracked Driver Codes (e.g., `DRV-001`) to the unified Driver portal. This abstracts identity management while retaining strict operational tracking.

## Assign Buses
Using the **Fleet Management** dashboard:
1. Select an offline Bus.
2. Assign it to a pre-defined GTFS Route.
3. Input the scheduled driver's code.
4. The Bus automatically queues into the driver's local dashboard.

## Monitor Fleet
The **Command Center** provides a sweeping, unified map of all active telemetry. Admins can view real-time movement, live occupancy, and ETA deviations across the entire city layout.

## View Analytics
Fleet counters automatically increment and decrement based on real-time state machines:
- **Running:** Buses currently traversing a route.
- **Return Ready:** Buses idle at the destination waiting to begin the reverse route.
- **Completed:** Total concluded trips.
- **Offline:** Unassigned or deactivated buses.

## Manage Emergency Systems
- **Complaints:** Review and resolve passenger grievances.
- **SOS:** Immediately acknowledge and dispatch assistance for emergency alerts.
- **Lost & Found:** Track, assign, and resolve items forgotten on the fleet.
