import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError


_ROOT = Path(__file__).resolve().parents[1]
_TEMP_DB = tempfile.TemporaryDirectory()

os.environ["DATABASE_URL"] = f"sqlite:///{(Path(_TEMP_DB.name) / 'transpulse-test.db').as_posix()}"
os.environ["RATELIMIT_STORAGE_URI"] = "memory://"
sys.path.insert(0, str(_ROOT))

import app as transpulse_app
from models import Bus, Route, Shape, Stop, Trip, User, db
from models.stop import StopTime


class StartTripLiveVisibilityTest(unittest.TestCase):
    def setUp(self):
        self.app = transpulse_app.app
        self.app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            RATELIMIT_ENABLED=False,
        )

        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            transpulse_app.initialize_database()
            self.fixture = self._build_gtfs_assigned_bus()
            transpulse_app.LIVE_GPS_DATA.clear()
            transpulse_app.LIVE_GPS_BREADCRUMBS.clear()
            transpulse_app.DRIVER_RUNTIME_SESSIONS.clear()
            transpulse_app.BUS_DELAY_DATA.clear()
            transpulse_app._invalidate_fleet_snapshot_cache()

        self.client = self.app.test_client()

    def _build_gtfs_assigned_bus(self):
        route = Route(
            route_code="FLOW-1",
            name="Start Trip Flow",
            origin="Origin Terminal",
            destination="Destination Terminal",
            distance_km=8.5,
            departure_time="09:00:00",
            arrival_time="09:25:00",
            is_operational=True,
        )
        db.session.add(route)
        db.session.flush()

        stops = [
            Stop(
                route_id=route.id,
                stop_name="Origin Terminal",
                stop_order=1,
                eta_minutes=0,
                scheduled_arrival_time="09:00:00",
                scheduled_departure_time="09:00:00",
                stop_code="FLOW-A",
                stop_lat=17.3850,
                stop_lon=78.4867,
            ),
            Stop(
                route_id=route.id,
                stop_name="Midtown",
                stop_order=2,
                eta_minutes=12,
                scheduled_arrival_time="09:12:00",
                scheduled_departure_time="09:12:00",
                stop_code="FLOW-B",
                stop_lat=17.3950,
                stop_lon=78.4967,
            ),
            Stop(
                route_id=route.id,
                stop_name="Destination Terminal",
                stop_order=3,
                eta_minutes=25,
                scheduled_arrival_time="09:25:00",
                scheduled_departure_time="09:25:00",
                stop_code="FLOW-C",
                stop_lat=17.4050,
                stop_lon=78.5067,
            ),
        ]
        db.session.add_all(stops)

        shape_id = "shape-flow-1"
        db.session.add_all([
            Shape(shape_id=shape_id, shape_pt_lat=17.3850, shape_pt_lon=78.4867, shape_pt_sequence=1),
            Shape(shape_id=shape_id, shape_pt_lat=17.3950, shape_pt_lon=78.4967, shape_pt_sequence=2),
            Shape(shape_id=shape_id, shape_pt_lat=17.4050, shape_pt_lon=78.5067, shape_pt_sequence=3),
        ])

        template_trip = Trip(
            bus_id=None,
            route_id=route.id,
            start_time=None,
            status="scheduled",
            service_id="WEEKDAY",
            gtfs_trip_id="gtfs-flow-1",
            trip_headsign="Destination Terminal",
            direction_id=0,
            shape_id=shape_id,
        )
        db.session.add(template_trip)
        db.session.flush()

        for index, stop in enumerate(stops, start=1):
            db.session.add(StopTime(
                trip_id=template_trip.id,
                stop_id=stop.id,
                arrival_time=stop.scheduled_arrival_time,
                departure_time=stop.scheduled_departure_time,
                stop_sequence=index,
            ))

        driver = User.query.filter_by(email=transpulse_app.SHARED_DRIVER_EMAIL, role="driver").one()
        bus = Bus(
            bus_number="FLOW-BUS-1",
            registration_number="FLOW-REG-1",
            capacity=42,
            assigned_driver_id=driver.id,
            assigned_driver_code="DTP-777",
            assigned_driver_name="DTP-777",
            route_id=route.id,
            is_active=False,
        )
        db.session.add(bus)
        db.session.commit()

        return {
            "bus_id": bus.id,
            "bus_number": bus.bus_number,
            "driver_code": bus.assigned_driver_code,
            "route_id": route.id,
            "route_code": route.route_code,
        }

    def _add_planned_assignment_on_different_route(self):
        route = Route(
            route_code="PLAN-2",
            name="Planned Assignment Route",
            origin="Planned Origin",
            destination="Planned Destination",
            distance_km=6.0,
            departure_time="10:00:00",
            arrival_time="10:20:00",
            is_operational=True,
        )
        db.session.add(route)
        db.session.flush()

        stops = [
            Stop(
                route_id=route.id,
                stop_name="Planned Origin",
                stop_order=1,
                eta_minutes=0,
                scheduled_arrival_time="10:00:00",
                scheduled_departure_time="10:00:00",
                stop_code="PLAN-A",
                stop_lat=17.5000,
                stop_lon=78.6000,
            ),
            Stop(
                route_id=route.id,
                stop_name="Planned Destination",
                stop_order=2,
                eta_minutes=20,
                scheduled_arrival_time="10:20:00",
                scheduled_departure_time="10:20:00",
                stop_code="PLAN-B",
                stop_lat=17.5100,
                stop_lon=78.6100,
            ),
        ]
        db.session.add_all(stops)
        db.session.flush()

        shape_id = "shape-plan-2"
        db.session.add_all([
            Shape(shape_id=shape_id, shape_pt_lat=17.5000, shape_pt_lon=78.6000, shape_pt_sequence=1),
            Shape(shape_id=shape_id, shape_pt_lat=17.5100, shape_pt_lon=78.6100, shape_pt_sequence=2),
        ])

        planned_trip = Trip(
            bus_id=self.fixture["bus_id"],
            route_id=route.id,
            start_time=None,
            status="assigned",
            service_id="WEEKDAY",
            gtfs_trip_id="gtfs-plan-2-assigned",
            trip_headsign="Planned Destination",
            direction_id=0,
            shape_id=shape_id,
        )
        db.session.add(planned_trip)
        db.session.flush()

        for index, stop in enumerate(stops, start=1):
            db.session.add(StopTime(
                trip_id=planned_trip.id,
                stop_id=stop.id,
                arrival_time=stop.scheduled_arrival_time,
                departure_time=stop.scheduled_departure_time,
                stop_sequence=index,
            ))

        bus = db.session.get(Bus, self.fixture["bus_id"])
        bus.route_id = route.id
        db.session.commit()
        transpulse_app._invalidate_fleet_snapshot_cache()
        return planned_trip.id

    def _login_driver(self):
        response = self.client.post(
            "/login",
            data={
                "email": transpulse_app.SHARED_DRIVER_EMAIL,
                "password": transpulse_app.DEFAULT_DRIVER_PASSWORD,
                "login_type": "driver",
                "driver_id": self.fixture["driver_code"],
            },
        )
        self.assertEqual(302, response.status_code, response.get_data(as_text=True))

    def test_start_trip_keeps_assigned_bus_connected_to_live_route(self):
        self._login_driver()

        with patch.object(
            transpulse_app,
            "_osrm_route_for_stop_sequence",
            side_effect=URLError("network disabled in test"),
        ):
            start_response = self.client.post("/api/driver/start-trip", json={"return_trip": False})
            self.assertEqual(200, start_response.status_code, start_response.get_data(as_text=True))
            start_payload = start_response.get_json()
            trip_id = start_payload["trip_id"]

            buses_response = self.client.get("/api/buses/live")
            self.assertEqual(200, buses_response.status_code, buses_response.get_data(as_text=True))
            buses_payload = buses_response.get_json()
            buses = buses_payload.get("buses", [])
            matching_buses = [
                bus for bus in buses
                if bus.get("bus_id") == self.fixture["bus_id"]
            ]
            self.assertEqual(1, len(matching_buses), buses_payload)

            live_bus = matching_buses[0]
            self.assertEqual(trip_id, live_bus.get("trip_id"))
            self.assertEqual("RUNNING", live_bus.get("trip_status"))
            self.assertEqual("Running", live_bus.get("bus_status"))
            self.assertEqual(self.fixture["route_id"], live_bus.get("route_id"))
            self.assertEqual(self.fixture["route_code"], live_bus.get("route_code"))
            self.assertEqual("Origin Terminal", live_bus.get("current_stop"))
            self.assertEqual("Midtown", live_bus.get("next_stop"))

            routes_response = self.client.get("/api/routes/live")
            self.assertEqual(200, routes_response.status_code, routes_response.get_data(as_text=True))
            routes_payload = routes_response.get_json()
            matching_routes = [
                route for route in routes_payload.get("routes", [])
                if route.get("route_id") == self.fixture["route_id"]
            ]
            self.assertEqual(1, len(matching_routes), routes_payload)
            self.assertEqual(1, matching_routes[0].get("active_bus_count"))
            self.assertEqual(live_bus.get("route_id"), matching_routes[0].get("route_id"))
            self.assertEqual(live_bus.get("route_code"), matching_routes[0].get("route_code"))

            tracking_response = self.client.get(f"/tracking/{self.fixture['bus_number']}")
            self.assertEqual(200, tracking_response.status_code, tracking_response.get_data(as_text=True))

    def test_active_trip_snapshot_wins_over_later_planned_assignment(self):
        self._login_driver()

        with patch.object(
            transpulse_app,
            "_osrm_route_for_stop_sequence",
            side_effect=URLError("network disabled in test"),
        ):
            start_response = self.client.post("/api/driver/start-trip", json={"return_trip": False})
            self.assertEqual(200, start_response.status_code, start_response.get_data(as_text=True))
            trip_id = start_response.get_json()["trip_id"]

        gps_response = self.client.post(
            "/api/driver/location",
            json={"lat": 17.3955, "lng": 78.4972, "speed_kmh": 0},
        )
        self.assertEqual(200, gps_response.status_code, gps_response.get_data(as_text=True))

        with self.app.app_context():
            planned_trip_id = self._add_planned_assignment_on_different_route()
            bus = db.session.get(Bus, self.fixture["bus_id"])
            active_trip = db.session.get(Trip, trip_id)
            planned_trip = db.session.get(Trip, planned_trip_id)
            self.assertTrue(bus.is_active)
            self.assertEqual("active", active_trip.status)
            self.assertEqual("assigned", planned_trip.status)

        for _ in range(3):
            buses_response = self.client.get("/api/buses/live")
            self.assertEqual(200, buses_response.status_code, buses_response.get_data(as_text=True))
            live_bus = next(
                bus for bus in buses_response.get_json().get("buses", [])
                if bus.get("bus_id") == self.fixture["bus_id"]
            )
            self.assertEqual(trip_id, live_bus.get("trip_id"))
            self.assertEqual("RUNNING", live_bus.get("trip_status"))
            self.assertEqual("Running", live_bus.get("bus_status"))
            self.assertNotEqual("WAITING_TO_DEPART", live_bus.get("trip_status"))
            self.assertAlmostEqual(17.3955, float(live_bus.get("current_lat")), places=4)
            self.assertAlmostEqual(78.4972, float(live_bus.get("current_lon")), places=4)

    def test_location_off_preserves_last_gps_for_active_trip(self):
        self._login_driver()

        with patch.object(
            transpulse_app,
            "_osrm_route_for_stop_sequence",
            side_effect=URLError("network disabled in test"),
        ):
            start_response = self.client.post("/api/driver/start-trip", json={"return_trip": False})
            self.assertEqual(200, start_response.status_code, start_response.get_data(as_text=True))
            trip_id = start_response.get_json()["trip_id"]

        gps_response = self.client.post(
            "/api/driver/location",
            json={"lat": 17.3960, "lng": 78.4980, "speed_kmh": 0},
        )
        self.assertEqual(200, gps_response.status_code, gps_response.get_data(as_text=True))

        off_response = self.client.post("/api/driver/location/off")
        self.assertEqual(200, off_response.status_code, off_response.get_data(as_text=True))
        self.assertTrue(off_response.get_json().get("last_known_gps_preserved"))

        with self.app.app_context():
            self.assertIn(self.fixture["bus_id"], transpulse_app.LIVE_GPS_DATA)
            bus = db.session.get(Bus, self.fixture["bus_id"])
            active_trip = db.session.get(Trip, trip_id)
            self.assertTrue(bus.is_active)
            self.assertEqual("active", active_trip.status)
            transpulse_app._invalidate_fleet_snapshot_cache()

        buses_response = self.client.get("/api/buses/live")
        self.assertEqual(200, buses_response.status_code, buses_response.get_data(as_text=True))
        live_bus = next(
            bus for bus in buses_response.get_json().get("buses", [])
            if bus.get("bus_id") == self.fixture["bus_id"]
        )
        self.assertEqual(trip_id, live_bus.get("trip_id"))
        self.assertEqual("RUNNING", live_bus.get("trip_status"))
        self.assertAlmostEqual(17.3960, float(live_bus.get("current_lat")), places=4)
        self.assertAlmostEqual(78.4980, float(live_bus.get("current_lon")), places=4)

    def test_routes_live_counts_assigned_bus_even_when_fleet_snapshot_is_empty(self):
        self._login_driver()

        with patch.object(
            transpulse_app,
            "_osrm_route_for_stop_sequence",
            side_effect=URLError("network disabled in test"),
        ):
            start_response = self.client.post("/api/driver/start-trip", json={"return_trip": False})
            self.assertEqual(200, start_response.status_code, start_response.get_data(as_text=True))

        with patch.object(transpulse_app, "_live_fleet_snapshot", return_value=[]):
            routes_response = self.client.get("/api/routes/live")
            self.assertEqual(200, routes_response.status_code, routes_response.get_data(as_text=True))
            matching_route = next(
                route for route in routes_response.get_json().get("routes", [])
                if route.get("route_id") == self.fixture["route_id"]
            )
            self.assertEqual(1, matching_route.get("active_bus_count"))


def tearDownModule():
    with transpulse_app.app.app_context():
        db.session.remove()
        db.engine.dispose()
    _TEMP_DB.cleanup()
