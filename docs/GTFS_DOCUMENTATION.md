GTFS Integration Guide

TransPulse is deeply integrated with the General Transit Feed Specification (GTFS). Instead of hardcoding routes or mapping data manually, TransPulse automatically maps abstract schedule data into living, tracking geometry.

GTFS Files Used

agency.txt
Identifies the operating transit agency. Currently hardcoded in the parser to validate basic dataset integrity.

routes.txt
Defines the distinct lines. TransPulse imports these into the Route model, extracting the IDs and names.

trips.txt
Links a route to a specific sequence of stops. Used to ascertain the direction of travel. TransPulse groups shape parameters dynamically based on these static trips.

stops.txt
Contains the precise physical coordinates of bus stops. TransPulse uses this to anchor the map UI and mathematically detect when a bus has successfully arrived at a designated station.

stop_times.txt
Dictates the sequence of stops and the expected arrival and departure times. TransPulse ingests these into the StopTime model to construct the Driver Dashboard sequence and the Passenger tracking timeline.

shapes.txt
Provides the high-fidelity polyline geometry outlining the physical road path of the route. TransPulse serializes this into a JSON array, serving it securely to mapping libraries to draw the tracking line on the maps.

calendar.txt and calendar_dates.txt
Provides service availability. Handled implicitly via the standard GTFS constraints logic.

Import Process

The import command performs a non-destructive teardown and rebuild of the static topology:
1. Clears existing static models.
2. Ingests stops, routes, and shapes.
3. Assembles trips and stop_times.
4. Leaves live state data untouched to prevent catastrophic live-system failure during a schedule update.

GTFS Import Logic

The parser extracts GTFS data from the source folder. It builds route display fields, purges the existing GTFS-backed tables and geometry cache, and bulk inserts the new files. It maps the trip IDs and stop codes, inserts the stop times, generates missing shapes from ordered stop coordinates, runs integrity checks, and commits everything in a single transaction.

Supported files:
1. agency.txt
2. calendar.txt
3. routes.txt
4. trips.txt
5. stops.txt
6. stop_times.txt
7. shapes.txt
8. calendar_dates.txt
9. feed_info.txt

Performance notes:
1. Inserts are batched to increase database write speeds.
2. Stop time lookups use in-memory source maps and database indexes.
3. The stop times are the authoritative route-stop ordering source.
4. Route origins and destinations are display-only fields and never reject assignments.
5. Generated shapes are invalidated and rebuilt when GTFS is re-imported.
6. Import failures rollback the entire transaction safely.
<!-- TP-v2.0-Release -->
