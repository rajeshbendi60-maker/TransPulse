import os
import csv
import zipfile
from collections import defaultdict
from datetime import datetime, UTC
from app import app
from sqlalchemy.exc import SQLAlchemyError
from models import db, Route, Stop, Trip, Shape, RoadGeometryCache
from models.stop import StopTime

ZIP_FILENAME = "mdb-3050-202605310135.zip"
GTFS_DIR = os.path.join(os.getcwd(), "gtfs_data")

def find_file(filename, search_path):
    for root, dirs, files in os.walk(search_path):
        if filename in files:
            return os.path.join(root, filename)
    return None

def time_to_minutes(t_str):
    try:
        h, m, s = map(int, t_str.split(':'))
        return h * 60 + m
    except:
        return 0

def process_extracted_gtfs():
    print(f"[GTFS ETL] Initializing Real Dataset Ingestion...")
    if os.path.exists(ZIP_FILENAME):
        with zipfile.ZipFile(ZIP_FILENAME, 'r') as zip_ref:
            zip_ref.extractall(GTFS_DIR)
    elif not os.path.exists(GTFS_DIR):
        print(f"[ERROR] Could not find {ZIP_FILENAME} or extracted folder.")
        return

    try:
        print("[GTFS ETL] Purging existing GTFS tables...")
        db.session.query(StopTime).delete()
        db.session.query(Trip).delete()
        db.session.query(Stop).delete()
        db.session.query(Shape).delete()
        # Render-only road geometry is tied to the imported stop sequence.
        # It is intentionally rebuilt lazily for the new GTFS feed.
        db.session.query(RoadGeometryCache).delete()
        db.session.query(Route).delete()
        db.session.commit()
        print("[GTFS ETL] Purge complete.")
    except SQLAlchemyError as e:
        db.session.rollback()
        print(f"[ERROR] Database purge failed: {e}")
        return

    try:
        print("[GTFS ETL] Importing routes.txt...")
        routes_file = find_file('routes.txt', GTFS_DIR)
        route_map = {}
        if routes_file:
            routes_to_insert = []
            with open(routes_file, 'r', encoding='utf-8-sig') as f:
                for row in csv.DictReader(f):
                    r_id = row['route_id']
                    s_name = row.get('route_short_name', '').strip()
                    l_name = row.get('route_long_name', '').strip()
                    name = f"{s_name} {l_name}".strip() or r_id
                    routes_to_insert.append(Route(
                        route_code=r_id, name=name, origin="Unknown", destination="Unknown",
                        distance_km=0.0, route_long_name=l_name, route_type=int(row.get('route_type', 3)),
                        route_color=row.get('route_color'), route_text_color=row.get('route_text_color')
                    ))
            db.session.bulk_save_objects(routes_to_insert)
            db.session.commit()
            for r in Route.query.all(): route_map[r.route_code] = r.id
            print(f"[GTFS ETL] Loaded {len(routes_to_insert)} routes.")

        print("[GTFS ETL] Importing stops.txt...")
        stops_file = find_file('stops.txt', GTFS_DIR)
        stop_map = {}
        if stops_file:
            stops_to_insert = []
            with open(stops_file, 'r', encoding='utf-8-sig') as f:
                for row in csv.DictReader(f):
                    stops_to_insert.append(Stop(
                        stop_code=row['stop_id'], stop_name=row.get('stop_name', 'Unknown Stop'),
                        stop_lat=float(row['stop_lat']) if row.get('stop_lat') else 0.0,
                        stop_lon=float(row['stop_lon']) if row.get('stop_lon') else 0.0,
                        route_id=None, stop_order=None, eta_minutes=0,
                        stop_desc=row.get('stop_desc'), zone_id=row.get('zone_id'),
                        location_type=int(row.get('location_type', 0)), parent_station=row.get('parent_station')
                    ))
            db.session.bulk_save_objects(stops_to_insert)
            db.session.commit()
            for s in Stop.query.all(): stop_map[s.stop_code] = s.id
            print(f"[GTFS ETL] Loaded {len(stops_to_insert)} stops.")

        print("[GTFS ETL] Importing shapes.txt...")
        shapes_file = find_file('shapes.txt', GTFS_DIR)
        if shapes_file:
            shapes_to_insert = []
            count = 0
            with open(shapes_file, 'r', encoding='utf-8-sig') as f:
                for row in csv.DictReader(f):
                    shapes_to_insert.append(Shape(
                        shape_id=row['shape_id'], shape_pt_lat=float(row['shape_pt_lat']),
                        shape_pt_lon=float(row['shape_pt_lon']), shape_pt_sequence=int(row['shape_pt_sequence'])
                    ))
                    if len(shapes_to_insert) >= 20000:
                        db.session.bulk_save_objects(shapes_to_insert)
                        shapes_to_insert = []
                        count += 20000
            if shapes_to_insert:
                db.session.bulk_save_objects(shapes_to_insert)
                count += len(shapes_to_insert)
            db.session.commit()
            print(f"[GTFS ETL] Loaded {count} shape points.")

        print("[GTFS ETL] Importing trips.txt...")
        trips_file = find_file('trips.txt', GTFS_DIR)
        trip_external_map = {}
        if trips_file:
            count = 0
            with open(trips_file, 'r', encoding='utf-8-sig') as f:
                for row in csv.DictReader(f):
                    r_id = route_map.get(row['route_id'])
                    if not r_id:
                        continue
                    trip = Trip(
                        route_id=r_id,
                        shape_id=row.get('shape_id'),
                        service_id=row.get('service_id'),
                        direction_id=int(row.get('direction_id', 0)) if row.get('direction_id') else None,
                        trip_headsign=row.get('trip_headsign'),
                        trip_short_name=row.get('trip_short_name'),
                        block_id=row.get('block_id'),
                        bus_id=None,
                        status="scheduled",
                        start_time=datetime.now(UTC)
                    )
                    db.session.add(trip)
                    db.session.flush()
                    trip_external_map[row['trip_id']] = trip.id
                    count += 1
                    if count % 10000 == 0:
                        db.session.commit()
            db.session.commit()
            print(f"[GTFS ETL] Loaded {count} trips.")

        print("[GTFS ETL] Importing stop_times.txt...")

        stop_times_file = find_file('stop_times.txt', GTFS_DIR)

        if stop_times_file:

            stop_times_to_insert = []
            count = 0

            with open(stop_times_file, 'r', encoding='utf-8-sig') as f:

                for row in csv.DictReader(f):

                    stop_code = row['stop_id']

                    db_trip_id = trip_external_map.get(row['trip_id'])

                    stop_obj = Stop.query.filter_by(
                        stop_code=stop_code
                    ).first()

                    if not db_trip_id or not stop_obj:
                        continue

                    stop_times_to_insert.append(
                        StopTime(
                            trip_id=db_trip_id,
                            stop_id=stop_obj.id,
                            arrival_time=row['arrival_time'],
                            departure_time=row['departure_time'],
                            stop_sequence=int(row['stop_sequence'])
                        )
                    )

                    if len(stop_times_to_insert) >= 5000:
                        db.session.bulk_save_objects(
                            stop_times_to_insert
                        )
                        db.session.commit()

                        count += len(stop_times_to_insert)

                        stop_times_to_insert = []

            if stop_times_to_insert:
                db.session.bulk_save_objects(
                    stop_times_to_insert
                )
                db.session.commit()

                count += len(stop_times_to_insert)

            print(
                f"[GTFS ETL] Loaded {count} stop times."
            )

        print("[GTFS ETL] Building route origins and destinations...")

        for route in Route.query.all():

            trip = Trip.query.filter_by(
                route_id=route.id
            ).first()

            if not trip:
                continue

            stops = (
                StopTime.query
                .filter_by(trip_id=trip.id)
                .order_by(StopTime.stop_sequence)
                .all()
            )

            if len(stops) < 2:
                continue

            first_stop = stops[0].stop
            last_stop = stops[-1].stop

            route.origin = first_stop.stop_name
            route.destination = last_stop.stop_name
            route.name = f"{route.origin} → {route.destination}"

        db.session.commit()

        print("[GTFS ETL] Route mapping complete.")
        print("✅ [SUCCESS] Production GTFS ingestion complete.")

    except SQLAlchemyError as e:
        db.session.rollback()
        print(f"[CRITICAL ERROR] Transaction failed. Rolled back. Details: {e}")

if __name__ == "__main__":
     with app.app_context():
         process_extracted_gtfs()
