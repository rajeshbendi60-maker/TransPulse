import os
import sys
from pathlib import Path
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import app
from models import db, Route, Stop, Trip, StopTime

def migrate():
    with app.app_context():
        # First, ensure we don't have pending data
        db.session.commit()
        
        print("Migrating existing manual stops to default Trips...")
        # Get all routes
        routes = Route.query.all()
        for route in routes:
            # We need to use raw SQL for Stop.route_id because we removed it from the model
            try:
                # Check if route_id column exists before querying
                result = db.session.execute(text("SELECT id, stop_name, stop_order, scheduled_arrival_time, scheduled_departure_time FROM stops WHERE route_id = :route_id ORDER BY stop_order ASC"), {"route_id": route.id}).fetchall()
                if not result:
                    continue
                
                print(f"Found {len(result)} stops for route {route.route_code}")
                
                # Check if default trip exists
                trip_query = Trip.query.filter_by(route_id=route.id, gtfs_trip_id=None).first()
                if not trip_query:
                    # Create default trip
                    trip_query = Trip(
                        route_id=route.id,
                        service_id=f"MANUAL_SRV_{route.id}",
                        status="scheduled",
                        direction_id=0,
                        gtfs_trip_id=f"TRIP_MANUAL_{route.id}_001"
                    )
                    db.session.add(trip_query)
                    db.session.flush()
                
                # Migrate stops to stop times
                for stop_id, stop_name, stop_order, arr_time, dep_time in result:
                    # Does stop_time already exist?
                    st_exists = StopTime.query.filter_by(trip_id=trip_query.id, stop_id=stop_id).first()
                    if not st_exists:
                        st = StopTime(
                            trip_id=trip_query.id,
                            stop_id=stop_id,
                            arrival_time=arr_time or "00:00:00",
                            departure_time=dep_time or "00:00:00",
                            stop_sequence=stop_order or 1
                        )
                        db.session.add(st)
                
                db.session.commit()
            except Exception as e:
                # Column might already be gone
                if "no such column" in str(e).lower() or "column" in str(e).lower() and "route_id" in str(e).lower():
                    print("route_id column already removed from stops table.")
                    break
                print(f"Error migrating route {route.id}: {e}")
                db.session.rollback()

        print("Dropping route_id and stop_order columns from stops...")
        try:
            # Drop the foreign key constraint first if it exists
            # SQLite workaround: ALter table drop column is supported in 3.35+
            db.session.execute(text("ALTER TABLE stops DROP COLUMN route_id;"))
            db.session.execute(text("ALTER TABLE stops DROP COLUMN stop_order;"))
            db.session.commit()
            print("Successfully dropped columns.")
        except Exception as e:
            print(f"Error dropping columns (might need manual recreation for old SQLite or Alembic): {e}")

if __name__ == "__main__":
    migrate()
# TP-v2.0-Release
