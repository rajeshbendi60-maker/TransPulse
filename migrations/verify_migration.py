import os
import sys
from pathlib import Path
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import app
from models import db, Route, Stop, Trip, StopTime

def verify_migration():
    with app.app_context():
        print("--- Before Migration Status ---")
        
        legacy_stops = 0
        try:
            # Manually query using raw SQL to count legacy stops, since model dropped route_id
            legacy_stops = db.session.execute(text("SELECT COUNT(*) FROM stops WHERE route_id IS NOT NULL")).scalar()
            print(f"Legacy manual route stops (with route_id): {legacy_stops}")
        except Exception as e:
            if "no such column: route_id" in str(e).lower():
                print("route_id already dropped.")
            else:
                print(f"Error checking legacy stops: {e}")

        trips_count = Trip.query.count()
        stop_times_count = StopTime.query.count()
        
        print(f"Total Trips: {trips_count}")
        print(f"Total StopTimes: {stop_times_count}")
        
        print("\n--- Running Migration ---")
        from migrate_manual_stops import migrate
        migrate()
        
        print("\n--- After Migration Status ---")
        new_trips_count = Trip.query.count()
        new_stop_times_count = StopTime.query.count()
        
        print(f"Total Trips: {new_trips_count} (+{new_trips_count - trips_count})")
        print(f"Total StopTimes: {new_stop_times_count} (+{new_stop_times_count - stop_times_count})")
        
        if new_stop_times_count >= stop_times_count + legacy_stops:
            print("SUCCESS: All legacy stops were successfully converted to StopTimes.")
        else:
            print("WARNING: The number of new StopTimes is less than the number of legacy stops. Please verify.")

if __name__ == "__main__":
    verify_migration()
# TP-v2.0-Release
