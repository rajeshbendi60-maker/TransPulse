import os
import csv
import zipfile
import io
import math
from datetime import datetime, timedelta
from app import create_app
from models import db, Route, Stop, Trip, Bus, Agency, Calendar, Shape

def haversine_km(lat1, lng1, lat2, lng2):
    radius = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (math.sin(d_lat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lng / 2) ** 2)
    return 2 * radius * math.asin(math.sqrt(a))

def execute_apsrtc_import():
    app = create_app()
    with app.app_context():
        print("[APSRTC ETL ENGINE] Ensuring schema safety bounds...")
        db.create_all()
        
        zip_path = os.path.join(os.getcwd(), 'mdb-3050-202605310135.zip')
        if not os.path.exists(zip_path):
            print(f"[FATAL] Source file missing: {zip_path}")
            return

        print("[APSRTC ETL ENGINE] Purging obsolete simulated geometries...")
        Trip.query.delete()
        Stop.query.delete()
        Route.query.delete()
        Shape.query.delete()
        Agency.query.delete()
        Calendar.query.delete()
        db.session.commit()

        try:
            with zipfile.ZipFile(zip_path, 'r') as archive:
                def extract_csv_rows(filename):
                    if filename in archive.namelist():
                        with archive.open(filename) as f:
                            wrapper = io.TextIOWrapper(f, encoding='utf-8-sig')
                            return list(csv.DictReader(wrapper))
                    return []

                print("[ETL] Parsing structural GTFS elements...")
                agencies = extract_csv_rows('agency.txt')
                calendars = extract_csv_rows('calendar.txt')
                routes = extract_csv_rows('routes.txt')
                stops = extract_csv_rows('stops.txt')
                trips = extract_csv_rows('trips.txt')
                stop_times = extract_csv_rows('stop_times.txt')
                shapes = extract_csv_rows('shapes.txt')

                if agencies:
                    db.session.bulk_insert_mappings(Agency, agencies)
                    db.session.commit()

                if calendars:
                    db.session.bulk_insert_mappings(Calendar, calendars)
                    db.session.commit()

                if shapes:
                    print(f"[ETL] Bulk processing {len(shapes)} shape nodes...")
                    chunk = []
                    for s in shapes:
                        chunk.append(Shape(
                            shape_id=s['shape_id'],
                            shape_pt_lat=float(s['shape_pt_lat']),
                            shape_pt_lon=float(s['shape_pt_lon']),
                            shape_pt_sequence=int(s['shape_pt_sequence'])
                        ))
                        if len(chunk) >= 20000:
                            db.session.bulk_save_objects(chunk)
                            db.session.commit()
                            chunk = []
                    if chunk:
                        db.session.bulk_save_objects(chunk)
                        db.session.commit()

                stops_lookup = {s['stop_id']: s for s in stops}
                
                route_trips_map = {}
                for t in trips:
                    route_trips_map.setdefault(t['route_id'], []).append(t)
                    
                trip_stop_times_map = {}
                for st in stop_times:
                    trip_stop_times_map.setdefault(st['trip_id'], []).append(st)

                print("[ETL] Transforming and saving true route channels...")
                for r in routes:
                    rcode = r.get('route_id')[:30]
                    rname = r.get('route_long_name', r.get('route_short_name', rcode))
                    
                    matched_trips = route_trips_map.get(rcode, [])
                    longest_trip = max(matched_trips, key=lambda x: len(trip_stop_times_map.get(x['trip_id'], [])), default=None)
                    
                    origin, dest = "AP Source Station", "AP Terminal Depot"
                    total_distance = 0.0
                    
                    if longest_trip:
                        st_list = sorted(trip_stop_times_map.get(longest_trip['trip_id'], []), key=lambda x: int(x['stop_sequence']))
                        if st_list:
                            origin = stops_lookup[st_list[0]['stop_id']]['stop_name'][:120]
                            dest = stops_lookup[st_list[-1]['stop_id']]['stop_name'][:120]
                            
                            for i in range(1, len(st_list)):
                                p_stop = stops_lookup.get(st_list[i-1]['stop_id'])
                                c_stop = stops_lookup.get(st_list[i]['stop_id'])
                                if p_stop and c_stop:
                                    total_distance += haversine_km(
                                        float(p_stop['stop_lat']), float(p_stop['stop_lon']),
                                        float(c_stop['stop_lat']), float(c_stop['stop_lon'])
                                    )

                    route_db_record = Route(
                        route_code=rcode,
                        name=rname[:120],
                        origin=origin,
                        destination=dest,
                        distance_km=round(total_distance, 2),
                        route_url=longest_trip.get('shape_id') if longest_trip else None
                    )
                    db.session.add(route_db_record)
                    db.session.flush()

                    if longest_trip:
                        st_list = sorted(trip_stop_times_map.get(longest_trip['trip_id'], []), key=lambda x: int(x['stop_sequence']))
                        stop_records = []
                        for idx, st in enumerate(st_list):
                            sinfo = stops_lookup.get(st['stop_id'])
                            if sinfo:
                                stop_records.append(Stop(
                                    route_id=route_db_record.id,
                                    stop_name=sinfo['stop_name'][:120],
                                    stop_order=idx+1,
                                    eta_minutes=idx * 12,
                                    stop_lat=float(sinfo['stop_lat']),
                                    stop_lon=float(sinfo['stop_lon'])
                                ))
                        if stop_records:
                            db.session.bulk_save_objects(stop_records)
                            db.session.flush()

                db.session.commit()
                
                print("[ETL] Remapping vehicles to real network paths...")
                fleet = Bus.query.all()
                active_routes = Route.query.all()
                if fleet and active_routes:
                    for idx, vehicle in enumerate(fleet):
                        assigned_rt = active_routes[idx % len(active_routes)]
                        db.session.add(Trip(
                            bus_id=vehicle.id,
                            route_id=assigned_rt.id,
                            shape_id=assigned_rt.route_url,
                            start_time=datetime.utcnow() - timedelta(minutes=10),
                            status="in_progress"
                        ))
                    db.session.commit()
                print("[SUCCESS] Real route deployment synchronization complete.")

        except Exception as err:
            print(f"[CRITICAL] Process dropped: {str(err)}")
            db.session.rollback()

if __name__ == "__main__":
    execute_apsrtc_import()
