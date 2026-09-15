import os
import sys
import unittest
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import app, _route_points_for_assigned_trip
from models import db, Route, Trip, Stop, StopTime, Bus

class GPSTrackingTests(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['ROUTE_MATCH_THRESHOLD_KM'] = 2.0
        app.config['STOP_RADIUS_KM'] = 0.03
        self.app_context = app.app_context()
        self.app_context.push()
        db.create_all()
        self.client = app.test_client()
        self._setup_mock_data()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _setup_mock_data(self):
        # Route 1: Nellore to Tirupati (GTFS)
        r1 = Route(route_code="01004", name="Nellore - Tirupati", origin="Nellore", destination="Tirupati", distance_km=100.0)
        db.session.add(r1)
        
        # Route 2: Palasa to Srikakulam (Manual)
        r2 = Route(route_code="01003", name="Palasa - Srikakulam", origin="Palasa", destination="Srikakulam", distance_km=80.0)
        db.session.add(r2)
        
        db.session.flush()

        # Stops for Route 1
        s1 = Stop(stop_name="Nellore Bus Stand", stop_lat=14.4426, stop_lon=79.9865)
        s2 = Stop(stop_name="Gudur", stop_lat=14.1463, stop_lon=79.8504)
        s3 = Stop(stop_name="Naidupeta", stop_lat=13.9378, stop_lon=79.7490)
        s4 = Stop(stop_name="Tirupati Bus Stand", stop_lat=13.6288, stop_lon=79.4192)
        db.session.add_all([s1, s2, s3, s4])

        # Stops for Route 2
        s5 = Stop(stop_name="Palasa", stop_lat=18.7663, stop_lon=84.4136)
        s6 = Stop(stop_name="Tekkali", stop_lat=18.6146, stop_lon=84.2323)
        s7 = Stop(stop_name="Srikakulam", stop_lat=18.2949, stop_lon=83.8938)
        db.session.add_all([s5, s6, s7])
        
        # Unrelated stop in Vizianagaram
        s8 = Stop(stop_name="Vizianagaram", stop_lat=18.1067, stop_lon=83.3956)
        db.session.add(s8)
        db.session.flush()

        # Trip for Route 1
        t1 = Trip(route_id=r1.id, service_id="SRV_1", status="assigned", gtfs_trip_id="TRIP_1")
        db.session.add(t1)
        db.session.flush()

        # StopTimes for Route 1
        st1 = StopTime(trip_id=t1.id, stop_id=s1.id, arrival_time="10:00:00", departure_time="10:00:00", stop_sequence=1)
        st2 = StopTime(trip_id=t1.id, stop_id=s2.id, arrival_time="11:00:00", departure_time="11:00:00", stop_sequence=2)
        st3 = StopTime(trip_id=t1.id, stop_id=s3.id, arrival_time="11:30:00", departure_time="11:30:00", stop_sequence=3)
        st4 = StopTime(trip_id=t1.id, stop_id=s4.id, arrival_time="13:00:00", departure_time="13:00:00", stop_sequence=4)
        db.session.add_all([st1, st2, st3, st4])

        # Bus Assignment
        b1 = Bus(bus_number="APSRTC-101", registration_number="AP-01-X-1234", capacity=40, route_id=r1.id, is_active=True)
        db.session.add(b1)
        db.session.commit()

        # Initialize tracking state
        from app import LIVE_GPS_DATA, DRIVER_RUNTIME_SESSIONS
        LIVE_GPS_DATA.clear()
        DRIVER_RUNTIME_SESSIONS.clear()
        
        self.r1 = r1
        self.r2 = r2
        self.t1 = t1
        self.b1 = b1
        self.s_nellore = s1
        self.s_gudur = s2
        self.s_naidupeta = s3
        self.s_tirupati = s4
        self.s_vzm = s8

    def _send_gps(self, bus_id, lat, lon):
        from app import api_driver_location
        # Using the internal function api_driver_location directly for testing logic without HTTP wrapper
        # The app uses request.json, we will mock request context
        with app.test_request_context(json={"bus_id": bus_id, "lat": lat, "lon": lon}):
            return api_driver_location()

    def get_runtime(self, bus_id):
        from app import DRIVER_RUNTIME_SESSIONS
        return DRIVER_RUNTIME_SESSIONS.get(bus_id)

    def test_1_wrong_global_location(self):
        # Driver assigned to Nellore->Tirupati, but GPS is in Vizianagaram
        response, code = self._send_gps(self.b1.id, self.s_vzm.stop_lat, self.s_vzm.stop_lon)
        self.assertEqual(code, 200)
        rt = self.get_runtime(self.b1.id)
        self.assertEqual(rt["gps_state"], "WAITING_FOR_ROUTE_MATCH")
        self.assertEqual(rt["current_stop"], "Not available")
        
    def test_2_valid_source_stop(self):
        # GPS at Nellore
        response, code = self._send_gps(self.b1.id, self.s_nellore.stop_lat, self.s_nellore.stop_lon)
        rt = self.get_runtime(self.b1.id)
        self.assertEqual(rt["gps_state"], "ACTIVE")
        self.assertEqual(rt["current_stop"], "Nellore Bus Stand")
        self.assertEqual(rt["next_stop"], "Gudur")

    def test_3_valid_intermediate_stop(self):
        # Driver starts directly at Gudur
        self._send_gps(self.b1.id, self.s_gudur.stop_lat, self.s_gudur.stop_lon)
        rt = self.get_runtime(self.b1.id)
        self.assertEqual(rt["gps_state"], "ACTIVE")
        self.assertEqual(rt["current_stop"], "Gudur")
        self.assertEqual(rt["next_stop"], "Naidupeta")

    def test_4_valid_destination(self):
        # Driver at Tirupati
        self._send_gps(self.b1.id, self.s_tirupati.stop_lat, self.s_tirupati.stop_lon)
        rt = self.get_runtime(self.b1.id)
        self.assertEqual(rt["gps_state"], "ACTIVE")
        self.assertEqual(rt["current_stop"], "Tirupati Bus Stand")
        self.assertEqual(rt["next_stop"], "--") # End of line

    def test_5_unrelated_route_stop(self):
        # Driver close to Palasa (Route 2)
        self._send_gps(self.b1.id, 18.7663, 84.4136)
        rt = self.get_runtime(self.b1.id)
        self.assertEqual(rt["gps_state"], "WAITING_FOR_ROUTE_MATCH")
        self.assertEqual(rt["current_stop"], "Not available")
        # Ensure it doesn't switch route
        from app import Trip
        active_trip = Trip.query.filter_by(bus_id=self.b1.id, status="assigned").first()
        self.assertEqual(active_trip.route_id, self.r1.id)

    def test_6_gps_jitter(self):
        # Move to Stop 3
        self._send_gps(self.b1.id, self.s_naidupeta.stop_lat, self.s_naidupeta.stop_lon)
        rt = self.get_runtime(self.b1.id)
        self.assertEqual(rt["current_stop"], "Naidupeta")
        
        # Jitter back towards Stop 2
        self._send_gps(self.b1.id, self.s_gudur.stop_lat + 0.01, self.s_gudur.stop_lon + 0.01)
        rt2 = self.get_runtime(self.b1.id)
        # Progress remains at Stop 3 due to monotonic progression
        self.assertEqual(rt2["current_stop"], "Naidupeta")

    def test_10_waiting_state_stale_data(self):
        # First valid stop
        self._send_gps(self.b1.id, self.s_gudur.stop_lat, self.s_gudur.stop_lon)
        rt = self.get_runtime(self.b1.id)
        self.assertEqual(rt["current_stop"], "Gudur")
        
        # Move outside route
        self._send_gps(self.b1.id, 10.0, 10.0) # Far away
        rt2 = self.get_runtime(self.b1.id)
        self.assertEqual(rt2["gps_state"], "WAITING_FOR_ROUTE_MATCH")
        self.assertEqual(rt2["current_stop"], "Not available")
        self.assertEqual(rt2["next_stop"], "Not available")

if __name__ == '__main__':
    unittest.main()
