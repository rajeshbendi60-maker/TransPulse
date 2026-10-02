# Database Schema

The platform utilizes a relational database (SQLite for local, PostgreSQL for production) managed by SQLAlchemy.

## Core Tables

1. Users
- Stores all system accounts.
- Distinguishes permissions via the `role` column (admin, driver, passenger).

2. Buses
- Represents physical vehicles.
- Tracks active assignments (assigned driver, active route).
- Stores the most recent GPS ping (latitude, longitude, speed, delay).

3. Routes & Stops
- Defines the path a bus takes.
- Stops are ordered geographically and time-based for ETA calculation.

4. Trips
- Represents a specific instance of a bus driving a route.
- Tracks the `current_stop_index` to determine how far along the route the bus has traveled.

5. Support Tables
- Complaints: Passenger-submitted feedback linked to specific routes.
- LostItems: Items reported lost by passengers or found by drivers.
- SOSAlerts: Emergency events requiring admin intervention.
