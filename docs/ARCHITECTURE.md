TransPulse System Architecture

This document describes the high-level system overview, module interactions, request flows, and telemetry processing systems for TransPulse.

1. System Overview

TransPulse is a live transit tracking system built to synchronize GTFS schedule data with real-time driver GPS coordinates. The application acts as a bridge between transit operations (drivers) and the public (passengers/admins). The system has three main client interfaces: the Driver Dashboard Mobile, the Passenger Dashboard Web, and the Admin Command Center Web. These communicate with a backend Flask application which handles REST APIs, the live telemetry and GPS processing engine, the route management system, and authentication. Everything is backed by a SQLite or PostgreSQL database.

2. Module Interaction

1. Driver Module: Collects live telemetry from driver devices (lat, lon, speed, bearing) via HTTP POST requests and broadcasts status updates.
2. Passenger Module: Provides a client-oriented route search, interactive stop timeline, and map tracking screens using mapping libraries.
3. Admin Module: Aggregates overall system statistics, live fleet card grids, active operational delays, and interactive search portals.
4. Live GPS Engine: Computes nearest stop coordinates, tracks monotonic trip progress, checks stop radii, and calculates smoothed blended ETAs.
5. GTFS / Import Engine: Reads stop sequences, shapes, and journey configurations from standard GTFS imports to populate routes and stops.

3. Data and Request Flows

Driver GPS Telemetry Flow:
The driver's device broadcasts its location to the telemetry endpoint. The GPS engine validates the session, computes the nearest stop using Haversine distance, enforces monotonic progress (ensuring the current stop is greater than or equal to the previous stop), and performs boundary checks. It then saves the telemetry snapshot to a memory cache and acknowledges the driver with the current delay status.

GTFS Route Import Flow:
The import command parses standard GTFS text files. It saves the stops, routes, and shapes to the database. It then interpolates stop sequence path coordinates to construct the stop times and route geometries.

Blended ETA Calculation Flow:
The system calculates a blended velocity by combining live GPS speed, historical route averages, and scheduled speeds. This blended speed and the remaining route distance give the travel time. The base ETA is formed by weighing the travel time against the scheduled remaining duration, and finally, the live delay is added to produce the final smoothed ETA.

Tracking Page Resilient Routing Flow:
When the live tracking page loads, it tries to render the route using GTFS shapes if available. If not, it falls back to backend road coordinates, then to a client-side routing fallback, and as a final fallback, it draws straight stop-to-stop lines with a warning.

Project Architecture

TransPulse is a single-file Flask application for public transport operations. The project intentionally keeps route registration, dashboards, APIs, GPS simulation, notifications, SOS, complaints, lost and found, and GTFS helpers in the main application file. The browser communicates with the backend via Bootstrap, maps, and charts. The backend relies on Flask, SQLAlchemy, database connections, and a GTFS importer.

Key modules:
1. Application routing, APIs, dashboards, GPS engine, and notifications.
2. Models: Database tables and relationships.
3. GTFS ingestion script.
4. Templates: Dashboards and pages.
5. Static files: Tracking logic, heatmap, polling, SOS handling, and visual styling.

Architecture rule: The application routes and logic remain centralized to preserve the current architectural constraints.
<!-- TP-v2.0-Release -->
