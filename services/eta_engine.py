from datetime import datetime, timedelta
import math
from models.live_transit import VehiclePosition, TripAssignment
from models.bus import Bus
import logging

logger = logging.getLogger(__name__)

# Basic In-Memory Cache (Simple implementation for Phase 3.8)
_eta_cache = {}

class DelayCategory:
    EARLY = "EARLY"
    ON_TIME = "ON_TIME"
    MINOR_DELAY = "MINOR_DELAY"
    MAJOR_DELAY = "MAJOR_DELAY"
    UNKNOWN = "UNKNOWN"

    @staticmethod
    def categorize(delay_seconds):
        if delay_seconds is None:
            return DelayCategory.UNKNOWN
        if delay_seconds < -60: # more than 1 minute early
            return DelayCategory.EARLY
        if delay_seconds <= 120: # up to 2 minutes late
            return DelayCategory.ON_TIME
        if delay_seconds <= 600: # up to 10 minutes late
            return DelayCategory.MINOR_DELAY
        return DelayCategory.MAJOR_DELAY


class ConfidenceEngine:
    @staticmethod
    def calculate(position: VehiclePosition):
        if not position:
            return 35 # No GPS
        
        confidence = 100
        
        # GPS Age
        age = (datetime.utcnow() - position.last_updated).total_seconds()
        if age > 300: # 5 mins
            confidence -= 35
        elif age > 60:
            confidence -= 10
            
        # Vehicle Status
        if position.status in ["Offline", "Maintenance", "Out Of Service"]:
            confidence -= 40
            
        # Speed stability (simplified mock rule)
        if position.speed is None or position.speed < 1.0:
            confidence -= 10
            
        # Accuracy
        if position.accuracy and position.accuracy > 50:
            confidence -= 5
            
        return max(0, min(100, confidence))

class Predictor:
    def predict(self, distance_meters, current_speed_kmh, scheduled_eta=None):
        raise NotImplementedError

class DeterministicPredictor(Predictor):
    def predict(self, distance_meters, current_speed_kmh, scheduled_eta=None):
        # Fallback average speed in city if current speed is 0
        speed_ms = (current_speed_kmh * 1000 / 3600) if current_speed_kmh and current_speed_kmh > 0 else (15 * 1000 / 3600)
        time_seconds = distance_meters / speed_ms
        return int(time_seconds)

class EtaEnginePipeline:
    def __init__(self, predictor: Predictor):
        self.predictor = predictor

    def calculate_vehicle_eta(self, bus_id):
        # 1. Caching check
        cache_key = f"vehicle_eta_{bus_id}"
        if cache_key in _eta_cache:
            cached_time, cached_data = _eta_cache[cache_key]
            if (datetime.utcnow() - cached_time).total_seconds() < 30: # 30s TTL
                return cached_data

        # 2. Get Live State
        position = VehiclePosition.query.filter_by(bus_id=bus_id).first()
        assignment = TripAssignment.query.filter_by(bus_id=bus_id, is_active=True).first()
        
        if not position or not assignment:
            return None

        confidence = ConfidenceEngine.calculate(position)
        
        # 3. Route Progress & Distance (Mocked for Phase 3.8 until geospatial DB is connected)
        # Mocking 3 stops ahead
        stops = [
            {"stop_id": "stop_101", "distance_meters": 450, "scheduled_eta_seconds": 120},
            {"stop_id": "stop_102", "distance_meters": 1200, "scheduled_eta_seconds": 320},
            {"stop_id": "stop_103", "distance_meters": 2400, "scheduled_eta_seconds": 600}
        ]
        
        # 4. Predict
        etas = []
        for stop in stops:
            predicted_seconds = self.predictor.predict(
                distance_meters=stop['distance_meters'], 
                current_speed_kmh=position.speed,
                scheduled_eta=stop['scheduled_eta_seconds']
            )
            
            delay_seconds = predicted_seconds - stop['scheduled_eta_seconds']
            
            eta_timestamp = datetime.utcnow() + timedelta(seconds=predicted_seconds)
            
            etas.append({
                "stopId": stop['stop_id'],
                "etaSeconds": predicted_seconds,
                "etaTimestamp": int(eta_timestamp.timestamp() * 1000),
                "delaySeconds": delay_seconds,
                "delayCategory": DelayCategory.categorize(delay_seconds),
                "confidencePercent": confidence,
                "distanceMeters": stop['distance_meters']
            })
            
        result = {
            "vehicleId": str(bus_id),
            "tripId": assignment.trip_id,
            "routeId": assignment.route_id,
            "etas": etas
        }
        
        # Cache and trigger event
        _eta_cache[cache_key] = (datetime.utcnow(), result)
        self._publish_eta_event(bus_id, result)
        
        return result

    def calculate_stop_eta(self, stop_id):
        # 1. Caching check
        cache_key = f"stop_eta_{stop_id}"
        if cache_key in _eta_cache:
            cached_time, cached_data = _eta_cache[cache_key]
            if (datetime.utcnow() - cached_time).total_seconds() < 30:
                return cached_data
                
        # 2. Get approaching vehicles (Mocked for Phase 3.8)
        # In a real engine, we'd query RouteProgressEngine to find which vehicles have this stop as upcoming.
        approaching_vehicles = VehiclePosition.query.filter(VehiclePosition.status == 'Running').limit(2).all()
        
        vehicles_eta = []
        for pos in approaching_vehicles:
            assignment = TripAssignment.query.filter_by(bus_id=pos.bus_id, is_active=True).first()
            if not assignment:
                continue
                
            confidence = ConfidenceEngine.calculate(pos)
            
            # Mock distance 
            distance_meters = 800
            scheduled_eta = 200
            
            predicted_seconds = self.predictor.predict(distance_meters, pos.speed, scheduled_eta)
            delay_seconds = predicted_seconds - scheduled_eta
            eta_timestamp = datetime.utcnow() + timedelta(seconds=predicted_seconds)
            
            bus = Bus.query.get(pos.bus_id)
            
            vehicles_eta.append({
                "vehicleId": str(pos.bus_id),
                "vehicleNumber": bus.bus_number if bus else "Unknown",
                "routeId": assignment.route_id,
                "etaSeconds": predicted_seconds,
                "etaTimestamp": int(eta_timestamp.timestamp() * 1000),
                "delaySeconds": delay_seconds,
                "delayCategory": DelayCategory.categorize(delay_seconds),
                "confidencePercent": confidence,
                "distanceMeters": distance_meters
            })
            
        result = {
            "stopId": stop_id,
            "approachingVehicles": vehicles_eta
        }
        
        _eta_cache[cache_key] = (datetime.utcnow(), result)
        return result
        
    def _publish_eta_event(self, bus_id, eta_data):
        # Stub for Phase 7 (Notifications)
        # e.g., EventBus.publish("ETA_CHANGED", bus_id, eta_data)
        logger.debug(f"Event: ETA_CHANGED published for bus {bus_id}")


# Expose singleton engine using Deterministic Predictor
eta_engine = EtaEnginePipeline(DeterministicPredictor())
# TP-v2.0-Release
