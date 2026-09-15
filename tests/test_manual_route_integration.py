import os
import sys
import unittest
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import app, _apply_manual_route_schedule, _create_trip_for_bus, _route_points_for_assigned_trip
from models import db, Route, Trip, Stop, StopTime, Bus, Shape

class ManualRouteIntegrationTests(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['LOGIN_DISABLED'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['ROUTE_MATCH_THRESHOLD_KM'] = 2.0
        app.config['STOP_RADIUS_KM'] = 0.03
        self.app_context = app.app_context()
        self.app_context.push()
        db.create_all()
        self.client = app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _send_gps(self, bus_id, lat, lon):
        with app.test_request_context(json={"bus_id": bus_id, "lat": lat, "lon": lon}):
            return app.view_functions["api_driver_location"]()

    def get_runtime(self, bus_id):
        from app import DRIVER_RUNTIME_SESSIONS
        return DRIVER_RUNTIME_SESSIONS.get(bus_id)

    def test_7_8_9_manual_route_integration(self):
        # Create route 01003
        r = Route(route_code="01003", name="Palasa - Srikakulam", origin="Palasa", destination="Srikakulam", distance_km=80.0, departure_time="10:00", arrival_time="12:00")
        db.session.add(r)
        db.session.flush()

        # Simulate manual stop schedule generation (Test 7)
        # Passing mock stop names
        _apply_manual_route_schedule(r, "Tekkali")
        db.session.commit()

        # Verify generated Service, Trip, StopTimes, Shape
        baseline_trip = Trip.query.filter_by(route_id=r.id, gtfs_trip_id=f"TRIP_MANUAL_{r.id}_001").first()
        self.assertIsNotNone(baseline_trip)
        self.assertEqual(baseline_trip.service_id, f"MANUAL_SRV_{r.id}")
        
        stop_times = StopTime.query.filter_by(trip_id=baseline_trip.id).order_by(StopTime.stop_sequence).all()
        self.assertEqual(len(stop_times), 3)
        self.assertEqual(stop_times[0].stop.stop_name, "Palasa")
        
        shape_count = Shape.query.filter_by(shape_id=baseline_trip.shape_id).count()
        self.assertGreater(shape_count, 0)

        # Assign a bus
        b = Bus(bus_number="APSRTC-102", registration_number="AP-02-Y-5678", capacity=40, route_id=r.id, is_active=True)
        db.session.add(b)
        db.session.commit()

        # Start trip
        assigned_trip = _create_trip_for_bus(b, r.id)
        self.assertEqual(assigned_trip.route_id, r.id)
        self.assertEqual(assigned_trip.shape_id, baseline_trip.shape_id)
        
        # Test 8 - Manual route intermediate stop GPS update
        # Get coordinates from the generated stops
        stops = [st.stop for st in StopTime.query.filter_by(trip_id=assigned_trip.id).order_by(StopTime.stop_sequence).all()]
        palasa = stops[0]
        tekkali = stops[1]
        
        # We need to manually add coordinates to these stops for the test to work effectively
        # since _apply_manual_route_schedule creates new stops with no coordinates 
        # (they default to None unless geocoded, but let's mock it)
        palasa.stop_lat, palasa.stop_lon = 18.7663, 84.4136
        tekkali.stop_lat, tekkali.stop_lon = 18.6146, 84.2323
        db.session.commit()
        
        # Send GPS to intermediate stop
        self._send_gps(b.id, tekkali.stop_lat, tekkali.stop_lon)
        rt = self.get_runtime(b.id)
        self.assertEqual(rt["gps_state"], "ACTIVE")
        self.assertEqual(rt["current_stop"], "Tekkali")
        
        # Test 9 - Manual route wrong location
        self._send_gps(b.id, 10.0, 10.0)
        rt = self.get_runtime(b.id)
        self.assertEqual(rt["gps_state"], "WAITING_FOR_ROUTE_MATCH")
        self.assertEqual(rt["current_stop"], "Not available")

if __name__ == '__main__':
    unittest.main()
