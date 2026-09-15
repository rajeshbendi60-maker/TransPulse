System Flow

The TransPulse platform follows a clear operational sequence connecting drivers, passengers, and administrators through a central backend.

When a driver starts a trip, the backend creates an active trip record in the database. As the journey progresses, the driver's device posts GPS coordinates, which the system validates and stores in live memory. 

Passengers use the tracking interface to view buses, pulling live fleet snapshots from the backend. If a passenger or driver triggers an SOS, the system stores the alert in the database and pushes a notification payload to the administrators. The administrators can then resolve the SOS, updating the status in the database.

Dashboard interaction flow:

1. Admin: Views the fleet, analytics, SOS alerts, complaints, and management pages.
2. Driver: Manages their assigned bus trip lifecycle, GPS broadcast, occupancy, delays, reports, and alerts.
3. Passenger: Searches routes, tracks buses, receives notifications, and submits SOS, complaints, and lost-and-found reports.
<!-- TP-v2.0-Release -->
