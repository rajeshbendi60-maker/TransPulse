# GTFS Import

The CLI command `flask import-gtfs` calls `process_extracted_gtfs()` in `import_apsrtc_data.py`.

```mermaid
flowchart TD
    Zip["GTFS zip or gtfs_data folder"] --> Parse["Parse routes, stops, trips, stop_times, shapes"]
    Parse --> RouteDisplay["Build route display fields from routes.txt only"]
    RouteDisplay --> Purge["Purge GTFS-backed tables and route geometry cache"]
    Purge --> Bulk["Bulk insert agency, calendar, calendar_dates, feed_info, routes, stops, shapes, trips"]
    Bulk --> Link["Map gtfs_trip_id and stop_code"]
    Link --> StopTimes["Bulk insert stop_times"]
    StopTimes --> ShapeRepair["Generate missing shapes from ordered stop coordinates"]
    ShapeRepair --> Integrity["Run GTFS integrity checks"]
    Integrity --> Commit["Single transaction commit"]
```

Supported files:

- `agency.txt`
- `calendar.txt`
- `routes.txt`
- `trips.txt`
- `stops.txt`
- `stop_times.txt`
- `shapes.txt`
- `calendar_dates.txt`
- `feed_info.txt`

Performance notes:

- Inserts are batched with `bulk_insert_mappings`.
- `trips.gtfs_trip_id` avoids per-trip flush loops.
- Stop time lookups use in-memory source maps and database indexes.
- `StopTime` is the authoritative route-stop ordering source.
- `Route.origin` and `Route.destination` are display-only fields and never reject assignments.
- Generated shapes are invalidated and rebuilt when GTFS is re-imported because `road_geometry_cache` is purged.
- Import failures rollback the transaction and log exception details.
