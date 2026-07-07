import csv
import hashlib
import logging
import os
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from app import app
from models import Agency, Calendar, CalendarDate, FeedInfo, Route, Shape, Stop, Trip, db
from models.road_geometry_cache import RoadGeometryCache
from models.stop import StopTime


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

ZIP_FILENAME = "mdb-3050-202605310135.zip"
GTFS_DIR = Path(os.getcwd()) / "gtfs_data"
BATCH_SIZE = 20000


def find_file(filename, search_path):
    for root, _dirs, files in os.walk(search_path):
        if filename in files:
            return Path(root) / filename
    return None


def _int_value(value, default=0):
    try:
        return int(value) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _float_value(value, default=0.0):
    try:
        return float(value) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _route_code_for_gtfs_id(route_id: str, seen_codes: set) -> str:
    base = re.sub(r"[^A-Za-z0-9_-]+", "-", (route_id or "").strip())[:30] if route_id else ""
    if not base:
        base = "GTFS-ROUTE"
    route_code = base[:30]
    if route_code not in seen_codes:
        return route_code
    digest = hashlib.sha1(route_id.encode("utf-8")).hexdigest()[:8]
    candidate = f"{base[:21]}-{digest}"[:30]
    suffix = 1
    while candidate in seen_codes:
        suffix += 1
        candidate = f"{base[:18]}-{digest}-{suffix}"[:30]
    return candidate


def _route_display_fields(row):
    route_id = row.get("route_id") or ""
    short_name = (row.get("route_short_name") or "").strip()
    long_name = (row.get("route_long_name") or "").strip()
    display_name = f"{short_name} {long_name}".strip() or route_id or "GTFS Route"

    # Route.origin/destination are display hints only.  They come from routes.txt,
    # never from sampled trip endpoints.
    origin = long_name or short_name or route_id or "GTFS Route"
    destination = long_name or short_name or route_id or "GTFS Route"
    separator_pattern = r"\s+(?:to|TO)\s+|\s*(?:-|>|/|\\|\u2013|\u2014|\u2192)\s*"
    separator_match = re.split(separator_pattern, long_name, maxsplit=1)
    if len(separator_match) == 2 and all(part.strip() for part in separator_match):
        origin = separator_match[0].strip()
        destination = separator_match[1].strip()

    return display_name[:120], origin[:120], destination[:120]


def _read_rows(filename):
    path = find_file(filename, GTFS_DIR)
    if not path:
        logger.warning("[GTFS ETL] %s not found; skipping", filename)
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _bulk_insert(model, rows):
    if not rows:
        return 0
    for start in range(0, len(rows), BATCH_SIZE):
        db.session.bulk_insert_mappings(model, rows[start:start + BATCH_SIZE])
    return len(rows)


def _safe_extract_zip(zip_ref, target_dir: Path) -> None:
    target_root = target_dir.resolve()
    for member in zip_ref.infolist():
        destination = (target_root / member.filename).resolve()
        if target_root != destination and target_root not in destination.parents:
            raise ValueError(f"Unsafe path in GTFS archive: {member.filename}")
    zip_ref.extractall(target_root)


def _chunked(values, size):
    for start in range(0, len(values), size):
        yield values[start:start + size]


def _generate_missing_trip_shapes_from_stop_times() -> int:
    shape_counts = {
        shape_id: count
        for shape_id, count in (
            db.session.query(Shape.shape_id, func.count(Shape.id))
            .group_by(Shape.shape_id)
            .all()
        )
    }
    missing_trip_ids = []
    trip_shape_ids = {}
    for trip in Trip.query.filter(Trip.bus_id.is_(None)).order_by(Trip.id.asc()).all():
        shape_id = (trip.shape_id or "").strip()
        if shape_id and shape_counts.get(shape_id, 0) >= 2:
            continue
        if not shape_id:
            shape_id = f"tp-gtfs-{trip.id}"
            trip.shape_id = shape_id
        missing_trip_ids.append(trip.id)
        trip_shape_ids[trip.id] = shape_id
    if not missing_trip_ids:
        return 0

    db.session.flush()
    generated_shape_ids = set()
    shape_mappings = []
    for trip_id_chunk in _chunked(missing_trip_ids, 500):
        rows = (
            db.session.query(
                StopTime.trip_id,
                StopTime.stop_sequence,
                Stop.stop_lat,
                Stop.stop_lon,
            )
            .join(Stop, Stop.id == StopTime.stop_id)
            .filter(StopTime.trip_id.in_(trip_id_chunk))
            .order_by(StopTime.trip_id.asc(), StopTime.stop_sequence.asc())
            .all()
        )
        points_by_trip = {}
        for trip_id, _sequence, lat, lon in rows:
            if lat is None or lon is None:
                continue
            points_by_trip.setdefault(trip_id, []).append((float(lat), float(lon)))

        for trip_id in trip_id_chunk:
            shape_id = trip_shape_ids.get(trip_id)
            if not shape_id or shape_id in generated_shape_ids:
                continue
            points = points_by_trip.get(trip_id, [])
            if len(points) < 2:
                continue
            if shape_counts.get(shape_id, 0):
                Shape.query.filter_by(shape_id=shape_id).delete(synchronize_session=False)
            for sequence, (lat, lon) in enumerate(points, start=1):
                shape_mappings.append({
                    "shape_id": shape_id,
                    "shape_pt_lat": lat,
                    "shape_pt_lon": lon,
                    "shape_pt_sequence": sequence,
                })
            shape_counts[shape_id] = len(points)
            generated_shape_ids.add(shape_id)
            if len(shape_mappings) >= BATCH_SIZE:
                db.session.bulk_insert_mappings(Shape, shape_mappings)
                shape_mappings = []

    if shape_mappings:
        db.session.bulk_insert_mappings(Shape, shape_mappings)
    db.session.flush()
    if generated_shape_ids:
        logger.warning(
            "[GTFS ETL] Generated %s missing shapes from ordered stop_times",
            len(generated_shape_ids),
        )
    return len(generated_shape_ids)


def _grouped_duplicate_count(model, *columns) -> int:
    rows = (
        db.session.query(*columns)
        .group_by(*columns)
        .having(func.count(model.id) > 1)
        .all()
    )
    return len(rows)


def _validate_gtfs_integrity() -> dict:
    hard_issues = {}
    hard_issues["orphan_trips"] = (
        Trip.query
        .outerjoin(Route, Trip.route_id == Route.id)
        .filter(Route.id.is_(None))
        .count()
    )
    hard_issues["orphan_stop_times_trip"] = (
        StopTime.query
        .outerjoin(Trip, StopTime.trip_id == Trip.id)
        .filter(Trip.id.is_(None))
        .count()
    )
    hard_issues["orphan_stop_times_stop"] = (
        StopTime.query
        .outerjoin(Stop, StopTime.stop_id == Stop.id)
        .filter(Stop.id.is_(None))
        .count()
    )
    hard_issues["template_trips_without_stop_times"] = (
        Trip.query
        .filter(Trip.bus_id.is_(None))
        .outerjoin(StopTime, StopTime.trip_id == Trip.id)
        .filter(StopTime.id.is_(None))
        .count()
    )
    hard_issues["template_trips_without_shape"] = (
        Trip.query
        .filter(Trip.bus_id.is_(None))
        .outerjoin(Shape, Trip.shape_id == Shape.shape_id)
        .filter(Trip.shape_id.isnot(None), Shape.id.is_(None))
        .count()
    )
    hard_issues["duplicate_route_codes"] = _grouped_duplicate_count(Route, Route.route_code)
    hard_issues["duplicate_gtfs_trip_ids"] = len(
        db.session.query(Trip.gtfs_trip_id)
        .filter(Trip.gtfs_trip_id.isnot(None))
        .group_by(Trip.gtfs_trip_id)
        .having(func.count(Trip.id) > 1)
        .all()
    )
    hard_issues["duplicate_stop_codes"] = len(
        db.session.query(Stop.stop_code)
        .filter(Stop.stop_code.isnot(None))
        .group_by(Stop.stop_code)
        .having(func.count(Stop.id) > 1)
        .all()
    )
    hard_issues["duplicate_shape_sequences"] = _grouped_duplicate_count(
        Shape,
        Shape.shape_id,
        Shape.shape_pt_sequence,
    )
    hard_issues["duplicate_stop_time_sequences"] = _grouped_duplicate_count(
        StopTime,
        StopTime.trip_id,
        StopTime.stop_sequence,
    )

    unused_shape_ids = len(
        db.session.query(Shape.shape_id)
        .outerjoin(Trip, Shape.shape_id == Trip.shape_id)
        .filter(Trip.id.is_(None))
        .group_by(Shape.shape_id)
        .all()
    )
    summary = {
        "agency": Agency.query.count(),
        "routes": Route.query.count(),
        "stops": Stop.query.count(),
        "trips": Trip.query.filter(Trip.bus_id.is_(None)).count(),
        "stop_times": StopTime.query.count(),
        "shapes": db.session.query(Shape.shape_id).group_by(Shape.shape_id).count(),
        "calendar": Calendar.query.count(),
        "calendar_dates": CalendarDate.query.count(),
        "feed_info": FeedInfo.query.count(),
        "unused_shape_ids": unused_shape_ids,
        "hard_issues": {key: value for key, value in hard_issues.items() if value},
    }
    if summary["hard_issues"]:
        for key, value in summary["hard_issues"].items():
            logger.error("[GTFS ETL] Integrity issue: %s=%s", key, value)
    else:
        logger.info("[GTFS ETL] Integrity checks passed: %s", summary)
    if unused_shape_ids:
        logger.warning(
            "[GTFS ETL] %s shape IDs are present but not referenced by trips; retained as feed metadata",
            unused_shape_ids,
        )
    return summary


def _update_route_origin_destination_from_trips() -> None:
    logger.info("[GTFS ETL] Updating route origin/destination from trips and stops")
    routes = Route.query.all()
    updated_count = 0
    for route in routes:
        is_manual = (
            route.route_long_name is None
            and route.route_color is None
            and route.route_text_color is None
            and route.route_url is None
        )
        if is_manual:
            logger.info("[GTFS ETL] Skipping manual route: route_code=%s", route.route_code)
            continue
            
        trip = Trip.query.filter_by(route_id=route.id).first()
        if not trip:
            logger.warning("[GTFS ETL] No trip found for route_code=%s", route.route_code)
            continue
        
        stop_times = (
            StopTime.query.filter_by(trip_id=trip.id)
            .order_by(StopTime.stop_sequence.asc())
            .all()
        )
        if len(stop_times) < 2:
            logger.warning("[GTFS ETL] Insufficient stop times for trip_id=%s on route_code=%s", trip.id, route.route_code)
            continue
            
        first_stop_time = stop_times[0]
        last_stop_time = stop_times[-1]
        
        first_stop = db.session.get(Stop, first_stop_time.stop_id)
        last_stop = db.session.get(Stop, last_stop_time.stop_id)
        
        if first_stop and last_stop:
            origin_name = (first_stop.stop_name or "").strip()
            dest_name = (last_stop.stop_name or "").strip()
            
            route.origin = origin_name
            route.destination = dest_name
            route.name = f"{origin_name} ➜ {dest_name}"
            updated_count += 1
    logger.info("[GTFS ETL] Successfully updated origin/destination for %d routes", updated_count)


def process_extracted_gtfs():
    logger.info("[GTFS ETL] Initializing APSRTC dataset ingestion")
    zip_path = Path(os.getcwd()) / ZIP_FILENAME
    if zip_path.exists():
        GTFS_DIR.mkdir(exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            _safe_extract_zip(zip_ref, GTFS_DIR)
    elif not GTFS_DIR.exists():
        logger.error("[GTFS ETL] Could not find %s or extracted gtfs_data folder", ZIP_FILENAME)
        return

    try:
        routes_rows = _read_rows("routes.txt")
        trips_rows = _read_rows("trips.txt")
        stops_rows = _read_rows("stops.txt")
        stop_times_rows = _read_rows("stop_times.txt")
        shapes_rows = _read_rows("shapes.txt")
        agency_rows = _read_rows("agency.txt")
        calendar_rows = _read_rows("calendar.txt")
        calendar_dates_rows = _read_rows("calendar_dates.txt")
        feed_info_rows = _read_rows("feed_info.txt")
        logger.info(
            "[GTFS ETL] Optional files detected: calendar_dates=%s feed_info=%s",
            len(calendar_dates_rows),
            len(feed_info_rows),
        )

        logger.info("[GTFS ETL] Purging existing GTFS-backed tables")
        db.session.query(StopTime).delete(synchronize_session=False)
        db.session.query(Trip).delete(synchronize_session=False)
        db.session.query(Stop).delete(synchronize_session=False)
        db.session.query(Shape).delete(synchronize_session=False)
        db.session.query(RoadGeometryCache).delete(synchronize_session=False)
        db.session.query(FeedInfo).delete(synchronize_session=False)
        db.session.query(CalendarDate).delete(synchronize_session=False)
        db.session.query(Calendar).delete(synchronize_session=False)
        db.session.query(Agency).delete(synchronize_session=False)
        db.session.query(Route).filter(
            db.or_(
                Route.route_long_name.isnot(None),
                Route.route_color.isnot(None),
                Route.route_text_color.isnot(None),
                Route.route_url.isnot(None)
            )
        ).delete(synchronize_session=False)

        logger.info("[GTFS ETL] Importing agency, calendar, routes, stops, shapes")
        agency_mappings = []
        seen_agencies = set()
        for row in agency_rows:
            agency_key = row.get("agency_id") or row.get("agency_name")
            if not agency_key or agency_key in seen_agencies:
                continue
            seen_agencies.add(agency_key)
            agency_mappings.append({
                "agency_id": row.get("agency_id"),
                "agency_name": row.get("agency_name") or "GTFS Agency",
                "agency_url": row.get("agency_url") or "https://example.invalid/",
                "agency_timezone": row.get("agency_timezone") or "UTC",
                "agency_lang": row.get("agency_lang"),
                "agency_phone": row.get("agency_phone"),
            })
        _bulk_insert(Agency, agency_mappings)

        calendar_mappings = []
        seen_services = set()
        for row in calendar_rows:
            service_id = row.get("service_id") or ""
            if not service_id or service_id in seen_services:
                continue
            seen_services.add(service_id)
            calendar_mappings.append({
                "service_id": service_id,
                "monday": _int_value(row.get("monday")),
                "tuesday": _int_value(row.get("tuesday")),
                "wednesday": _int_value(row.get("wednesday")),
                "thursday": _int_value(row.get("thursday")),
                "friday": _int_value(row.get("friday")),
                "saturday": _int_value(row.get("saturday")),
                "sunday": _int_value(row.get("sunday")),
                "start_date": row.get("start_date") or "",
                "end_date": row.get("end_date") or "",
            })
        _bulk_insert(Calendar, calendar_mappings)

        calendar_date_mappings = []
        seen_calendar_dates = set()
        for row in calendar_dates_rows:
            service_id = row.get("service_id") or ""
            date = row.get("date") or ""
            key = (service_id, date)
            if not service_id or not date or key in seen_calendar_dates:
                continue
            seen_calendar_dates.add(key)
            calendar_date_mappings.append({
                "service_id": service_id,
                "date": date,
                "exception_type": _int_value(row.get("exception_type")),
            })
        _bulk_insert(CalendarDate, calendar_date_mappings)

        _bulk_insert(FeedInfo, [{
            "feed_publisher_name": row.get("feed_publisher_name") or "GTFS Publisher",
            "feed_publisher_url": row.get("feed_publisher_url") or "https://example.invalid/",
            "feed_lang": row.get("feed_lang") or "en",
            "default_lang": row.get("default_lang"),
            "feed_start_date": row.get("feed_start_date"),
            "feed_end_date": row.get("feed_end_date"),
            "feed_version": row.get("feed_version"),
            "feed_contact_email": row.get("feed_contact_email"),
            "feed_contact_url": row.get("feed_contact_url"),
        } for row in feed_info_rows])

        route_external_to_code = {}
        route_mappings = []
        seen_route_codes = set()
        seen_route_ids = set()
        for row in routes_rows:
            route_id = row.get("route_id") or ""
            if not route_id or route_id in seen_route_ids:
                logger.warning("[GTFS ETL] Skipping duplicate/blank route_id=%s", route_id)
                continue
            seen_route_ids.add(route_id)
            route_code = _route_code_for_gtfs_id(route_id, seen_route_codes)
            seen_route_codes.add(route_code)
            route_external_to_code[route_id] = route_code
            short_name = (row.get("route_short_name") or "").strip()
            long_name = (row.get("route_long_name") or "").strip()
            display_name, origin, destination = _route_display_fields(row)
            route_mappings.append({
                "route_code": route_code,
                "name": display_name[:120],
                "origin": origin,
                "destination": destination,
                "distance_km": 0.0,
                "route_long_name": long_name[:255] if long_name else None,
                "route_type": _int_value(row.get("route_type"), 3),
                "route_url": row.get("route_url"),
                "route_color": row.get("route_color"),
                "route_text_color": row.get("route_text_color"),
                "is_operational": True,
            })
        _bulk_insert(Route, route_mappings)
        db.session.flush()

        route_map = dict(db.session.query(Route.route_code, Route.id).all())

        stop_mappings = []
        seen_stops = set()
        for row in stops_rows:
            stop_id = row.get("stop_id")
            if not stop_id or stop_id in seen_stops:
                continue
            seen_stops.add(stop_id)
            stop_mappings.append({
                "stop_code": stop_id,
                "stop_name": (row.get("stop_name") or "Unknown Stop")[:120],
                "stop_lat": _float_value(row.get("stop_lat")),
                "stop_lon": _float_value(row.get("stop_lon")),
                "route_id": None,
                "stop_order": None,
                "eta_minutes": 0,
                "stop_desc": row.get("stop_desc"),
                "zone_id": row.get("zone_id"),
                "location_type": _int_value(row.get("location_type")),
                "parent_station": row.get("parent_station"),
            })
        _bulk_insert(Stop, stop_mappings)
        db.session.flush()
        stop_map = dict(db.session.query(Stop.stop_code, Stop.id).all())

        shape_mappings = []
        seen_shapes = set()
        for row in shapes_rows:
            shape_id = row.get("shape_id")
            sequence = _int_value(row.get("shape_pt_sequence"))
            key = (shape_id, sequence)
            if not shape_id or key in seen_shapes:
                continue
            seen_shapes.add(key)
            shape_mappings.append({
                "shape_id": shape_id,
                "shape_pt_lat": _float_value(row.get("shape_pt_lat")),
                "shape_pt_lon": _float_value(row.get("shape_pt_lon")),
                "shape_pt_sequence": sequence,
            })
        _bulk_insert(Shape, shape_mappings)

        trip_mappings = []
        seen_trips = set()
        for row in trips_rows:
            gtfs_trip_id = row.get("trip_id")
            if not gtfs_trip_id or gtfs_trip_id in seen_trips:
                continue
            seen_trips.add(gtfs_trip_id)
            route_code = route_external_to_code.get(row.get("route_id"))
            route_id = route_map.get(route_code)
            if not route_id:
                continue
            trip_mappings.append({
                "route_id": route_id,
                "gtfs_trip_id": gtfs_trip_id,
                "shape_id": row.get("shape_id"),
                "service_id": row.get("service_id"),
                "direction_id": _int_value(row.get("direction_id")) if row.get("direction_id") else None,
                "trip_headsign": row.get("trip_headsign"),
                "trip_short_name": row.get("trip_short_name"),
                "block_id": row.get("block_id"),
                "bus_id": None,
                "status": "scheduled",
                "start_time": datetime.now(UTC),
            })
        _bulk_insert(Trip, trip_mappings)
        db.session.flush()
        trip_map = dict(db.session.query(Trip.gtfs_trip_id, Trip.id).filter(Trip.gtfs_trip_id.isnot(None)).all())

        stop_time_mappings = []
        seen_stop_times = set()
        for row in stop_times_rows:
            trip_id = trip_map.get(row.get("trip_id"))
            stop_id = stop_map.get(row.get("stop_id"))
            if not trip_id or not stop_id:
                continue
            sequence = _int_value(row.get("stop_sequence"))
            key = (trip_id, sequence)
            if key in seen_stop_times:
                continue
            seen_stop_times.add(key)
            stop_time_mappings.append({
                "trip_id": trip_id,
                "stop_id": stop_id,
                "arrival_time": row.get("arrival_time") or "00:00:00",
                "departure_time": row.get("departure_time") or row.get("arrival_time") or "00:00:00",
                "stop_sequence": sequence,
            })
            if len(stop_time_mappings) >= BATCH_SIZE:
                db.session.bulk_insert_mappings(StopTime, stop_time_mappings)
                stop_time_mappings = []
        if stop_time_mappings:
            db.session.bulk_insert_mappings(StopTime, stop_time_mappings)

        generated_shape_count = _generate_missing_trip_shapes_from_stop_times()
        integrity_summary = _validate_gtfs_integrity()
        if integrity_summary["hard_issues"]:
            raise ValueError(f"GTFS integrity validation failed: {integrity_summary['hard_issues']}")

        _update_route_origin_destination_from_trips()
        db.session.commit()
        logger.info(
            "[GTFS ETL] Complete: routes=%s stops=%s trips=%s stop_times=%s shapes=%s generated_shapes=%s",
            len(route_mappings),
            len(stop_mappings),
            len(trip_mappings),
            StopTime.query.count(),
            db.session.query(Shape.shape_id).group_by(Shape.shape_id).count(),
            generated_shape_count,
        )

    except SQLAlchemyError as exc:
        db.session.rollback()
        logger.exception("[GTFS ETL] Database transaction failed and was rolled back: %s", exc)
    except Exception as exc:
        db.session.rollback()
        logger.exception("[GTFS ETL] Import failed and was rolled back: %s", exc)


if __name__ == "__main__":
    with app.app_context():
        process_extracted_gtfs()
