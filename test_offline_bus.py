import os
import sys

sys.path.insert(0, r'e:\Transpulse')
os.environ['FLASK_APP'] = 'app.py'

from app import app, db
from app import Bus, Route, Trip, User, _create_trip_for_bus, _live_fleet_snapshot

with app.app_context():
    bus = Bus.query.first()
    route = Route.query.first()
    if not bus:
        bus = Bus(bus_number="APSRTC-101", registration_number="AP11-X-1111", capacity=40, is_active=True)
        db.session.add(bus)
        db.session.commit()
    
    bus.assigned_driver_code = "DTP-001"
    print(f"Assigning Route {route.id} to Bus {bus.id}")
    bus.route_id = route.id
    
    # Cancel active trips
    Trip.query.filter_by(bus_id=bus.id).update({'status': 'completed'})
    db.session.commit()
    
    _create_trip_for_bus(bus, route.id)
    
    buses = _live_fleet_snapshot()
    
    found = False
    for b in buses:
        if b['bus_id'] == bus.id:
            found = True
            print(f"Bus {b['bus_number']} found in live fleet!")
            print(f"Service Status: {b.get('service_status')}")
            print(f"Bus Status: {b.get('bus_status')}")
            print(f"Trip Status: {b.get('trip_status')}")
            print(f"GPS Status: {b.get('gps_status')}")
            
    if not found:
        print("Bus not found in live fleet.")
