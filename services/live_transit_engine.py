import math
from datetime import datetime, timedelta
from extensions import db
from models.bus import Bus
from models.live_transit import VehiclePosition, TripAssignment, RouteDeviationEvent
from models.shape import Shape
from models.stop import Stop
from models.trip import Trip

class LiveTransitEngine:

    @staticmethod
    def process_gps_update(bus_id, lat, lng, speed, heading, accuracy):
        # 1. Position Processor
        position = VehiclePosition.query.filter_by(bus_id=bus_id).first()
        if not position:
            position = VehiclePosition(bus_id=bus_id)
            db.session.add(position)
        
        position.latitude = lat
        position.longitude = lng
        position.speed = speed
        position.heading = heading
        position.accuracy = accuracy
        position.last_updated = datetime.utcnow()
        
        # 2. Vehicle Status Engine
        position.status = LiveTransitEngine._determine_status(speed, position.last_updated)
        
        # 3. Route Progress & Deviation Detector
        assignment = TripAssignment.query.filter_by(bus_id=bus_id, is_active=True).first()
        route_progress = None
        
        if assignment:
            # Fake/Mock route progress logic since GTFS shape matching is complex geospatial work
            # In a real app we'd use PostGIS or Haversine distances against the shape points
            route_progress = LiveTransitEngine._compute_route_progress(assignment.trip_id, lat, lng)
            
            # Detect deviation
            deviation = LiveTransitEngine._detect_deviation(assignment.trip_id, lat, lng)
            if deviation > 150: # > 150 meters
                LiveTransitEngine._log_deviation(bus_id, assignment.trip_id, lat, lng, deviation)
        
        db.session.commit()
        
        # Return structured data for the mapper
        bus = Bus.query.get(bus_id)
        return bus, position, route_progress, assignment

    @staticmethod
    def get_live_vehicles():
        positions = VehiclePosition.query.all()
        results = []
        for p in positions:
            bus = Bus.query.get(p.bus_id)
            assignment = TripAssignment.query.filter_by(bus_id=p.bus_id, is_active=True).first()
            route_progress = None
            if assignment:
                route_progress = LiveTransitEngine._compute_route_progress(assignment.trip_id, p.latitude, p.longitude)
            
            # Update status if stale
            if (datetime.utcnow() - p.last_updated).total_seconds() > 120:
                p.status = "Offline"
                
            results.append((bus, p, route_progress, assignment))
            
        return results
        
    @staticmethod
    def get_vehicle_by_id(bus_id):
        bus = Bus.query.get(bus_id)
        if not bus:
            return None
        position = VehiclePosition.query.filter_by(bus_id=bus_id).first()
        assignment = TripAssignment.query.filter_by(bus_id=bus_id, is_active=True).first()
        route_progress = None
        if assignment and position:
            route_progress = LiveTransitEngine._compute_route_progress(assignment.trip_id, position.latitude, position.longitude)
            if (datetime.utcnow() - position.last_updated).total_seconds() > 120:
                position.status = "Offline"
        
        return (bus, position, route_progress, assignment)

    # --- Internal Engines ---

    @staticmethod
    def _determine_status(speed, last_updated):
        if (datetime.utcnow() - last_updated).total_seconds() > 120:
            return "Offline"
        if speed and speed > 2.0:
            return "Running"
        return "Stopped"

    @staticmethod
    def _compute_route_progress(trip_id, lat, lng):
        # Mock logic to fulfill the structured response without doing deep spatial queries for this mockup
        return {
            "currentStopId": "mock_stop_1",
            "nextStopId": "mock_stop_2",
            "remainingStops": 10,
            "progressPercent": 45.5,
            "nextStops": [
                {"stopId": "mock_stop_2", "distance": 450, "etaSeconds": 120},
                {"stopId": "mock_stop_3", "distance": 1200, "etaSeconds": 300},
                {"stopId": "mock_stop_4", "distance": 2100, "etaSeconds": 540}
            ]
        }
        
    @staticmethod
    def _detect_deviation(trip_id, lat, lng):
        # Mock logic. Return 0 deviation for now.
        return 0.0
        
    @staticmethod
    def _log_deviation(bus_id, trip_id, lat, lng, distance):
        severity = "Minor" if distance < 300 else ("Major" if distance < 1000 else "Critical")
        event = RouteDeviationEvent(
            bus_id=bus_id,
            trip_id=trip_id,
            deviation_distance=distance,
            latitude=lat,
            longitude=lng,
            severity=severity
        )
        db.session.add(event)
# TP-v2.0-Release
