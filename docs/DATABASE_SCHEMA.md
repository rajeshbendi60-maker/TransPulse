TransPulse Database Schema

This document details the database models, their fields, and relationships within the TransPulse system.

1. User and Authorization Roles

User Table
Stores login credentials and roles for Driver, Admin, Passenger, and Auditor accounts.
Fields include id, username, password_hash, role (enforced as admin, driver, passenger, auditor), driver_code, and created_at.

2. Transit Network and GTFS Infrastructure

Bus Table
Represents a physical vehicle in the fleet.
Fields include id, bus_number, registration_number, route_id, assigned_driver_id, and is_active.
It relates to the Route and User tables.

Route Table
Corresponds to a GTFS route mapping.
Fields include id, route_code, name, origin, destination, distance_km, departure_time, arrival_time, and is_operational.
It relates to Stop, Trip, and Bus tables.

Trip Table
Represents a scheduled or active dispatch of a Route.
Fields include id, route_id, bus_id, service_id, trip_id, trip_headsign, direction_id, shape_id, start_time, end_time, and status.
It relates to Route and Bus tables.

Stop Table
Stores geographical checkpoints.
Fields include id, stop_id, stop_code, stop_name, stop_desc, stop_lat, stop_lon, and zone_id.
It relates to the StopTime table.

StopTime Table
Maps the ordered sequence of Stops for a Trip.
Fields include id, trip_id, stop_id, arrival_time, departure_time, and stop_sequence.
It relates to Trip and Stop tables.

Shape Table
Stores coordinates forming the line path of a route.
Fields include id, shape_id, shape_pt_lat, shape_pt_lon, shape_pt_sequence, and shape_dist_traveled.

3. Operations and Support

Complaint Table
Passenger complaints.
Fields include id, user_id, route_id, bus_id, category, description, status, and created_at.

Notification Table
System broadcasts or alert notifications.
Fields include id, title, message, is_read, and created_at.

LostAndFound Table
Reports for items lost during trips.
Fields include id, user_id, route_id, item_name, description, status, and created_at.

SOSAlert Table
Emergency signals triggered by passengers or drivers.
Fields include id, bus_id, route_id, lat, lon, status, and created_at.

4. Entity Relationship Mapping

The database links users to buses, complaints, and lost/found reports. A route contains multiple buses, trips, complaints, lost/found items, and SOS alerts. A bus serves trips and can trigger SOS alerts. A trip contains an ordered sequence of stop times, and each stop time corresponds to a specific stop checkpoint.
