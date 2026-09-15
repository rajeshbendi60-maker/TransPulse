import math
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class Location:
    def __init__(self, lat, lon, name="Unknown"):
        self.lat = lat
        self.lon = lon
        self.name = name

class JourneySegmentType:
    WALK = "WALK"
    BUS = "BUS"
    TRANSFER = "TRANSFER"

class RecommendationType:
    BEST = "BEST"
    FASTEST = "FASTEST"
    LEAST_WALKING = "LEAST_WALKING"
    LEAST_TRANSFERS = "LEAST_TRANSFERS"
    ACCESSIBLE = "ACCESSIBLE"

# --- Pipeline Components ---

class LocationResolver:
    """Resolves arbitrary text or coordinates to a Location object"""
    def resolve(self, input_data):
        if isinstance(input_data, dict) and 'lat' in input_data and 'lon' in input_data:
            return Location(input_data['lat'], input_data['lon'], input_data.get('name', 'Custom Location'))
        # Mock geocoding
        return Location(17.3850, 78.4867, "Resolved Location")

class NearbyStopFinder:
    """Finds GTFS stops near a location"""
    def find_stops(self, location, radius_meters=1000):
        # Mock: return generic stops
        return [{"stop_id": "stop_1", "distance": 200, "lat": location.lat + 0.002, "lon": location.lon},
                {"stop_id": "stop_2", "distance": 500, "lat": location.lat - 0.004, "lon": location.lon}]

class WalkingEngine:
    """Calculates walking distance and time between two points"""
    def calculate(self, loc1, loc2):
        # Mock straight line distance + overhead
        # In future, integrate OSRM or similar road-network router here
        dist_x = loc1.lat - loc2.lat
        dist_y = loc1.lon - loc2.lon
        distance_meters = math.sqrt(dist_x**2 + dist_y**2) * 111000 # Rough approx
        
        # 1.4 m/s average walking speed
        time_seconds = distance_meters / 1.4
        return {"distance_meters": int(distance_meters), "time_seconds": int(time_seconds)}

class DirectRouteEngine:
    """Finds direct GTFS routes between origin stops and destination stops"""
    def search(self, origin_stops, dest_stops):
        # Mock direct route
        return [{
            "route_id": "route_205",
            "origin_stop": "stop_1",
            "dest_stop": "stop_100",
            "travel_time_seconds": 1800,
            "segments": [
                {"type": JourneySegmentType.BUS, "route_id": "route_205", "duration": 1800}
            ]
        }]

class TransferEngine:
    """Finds routes requiring 1-2 transfers"""
    def search(self, origin_stops, dest_stops):
        # Mock transfer route
        return [{
            "route_id": "route_complex",
            "origin_stop": "stop_2",
            "dest_stop": "stop_100",
            "travel_time_seconds": 2400,
            "segments": [
                {"type": JourneySegmentType.BUS, "route_id": "route_112", "duration": 1000},
                {"type": JourneySegmentType.TRANSFER, "stop_id": "stop_x", "duration": 300},
                {"type": JourneySegmentType.BUS, "route_id": "route_50", "duration": 1100}
            ]
        }]

class LiveTransitIntegrationEngine:
    """Attaches live vehicles to planned segments"""
    def integrate(self, routes):
        for route in routes:
            for seg in route['segments']:
                if seg['type'] == JourneySegmentType.BUS:
                    seg['live_vehicle_id'] = f"bus_{seg['route_id']}_live"
        return routes

class EtaIntegrationEngine:
    """Replaces scheduled times with live ETAs from EtaEngine"""
    def integrate(self, routes):
        for route in routes:
            # Mock confidence & ETA
            route['eta_confidence'] = 85
            for seg in route['segments']:
                if seg['type'] == JourneySegmentType.BUS:
                    seg['eta_seconds'] = seg['duration'] + 120 # simulated delay
        return routes

class JourneyScoringEngine:
    """Scores journeys based on weighted criteria"""
    def score(self, journey):
        # Travel Time 40%
        # Walking 20%
        # Transfers 20%
        # ETA Confidence 15%
        # Accessibility 5%
        
        time_score = max(0, 100 - (journey['total_travel_time'] / 60)) * 0.40
        walk_score = max(0, 100 - (journey['total_walking_distance'] / 10)) * 0.20
        transfer_score = max(0, 100 - (journey['transfer_count'] * 30)) * 0.20
        conf_score = journey.get('eta_confidence', 50) * 0.15
        acc_score = 100 * 0.05 # Mock highly accessible
        
        score = time_score + walk_score + transfer_score + conf_score + acc_score
        journey['score'] = min(100, max(0, int(score)))
        return journey

class RecommendationEngine:
    """Tags journeys with recommendation types based on their metrics"""
    def recommend(self, journeys):
        if not journeys:
            return []
            
        # Sort by score descending for BEST
        journeys.sort(key=lambda x: x['score'], reverse=True)
        journeys[0]['recommendation_type'] = RecommendationType.BEST
        
        # Sort by time
        journeys.sort(key=lambda x: x['total_travel_time'])
        if journeys[0]['recommendation_type'] is None:
             journeys[0]['recommendation_type'] = RecommendationType.FASTEST
             
        # Sort by walking
        journeys.sort(key=lambda x: x['total_walking_distance'])
        if journeys[0]['recommendation_type'] is None:
             journeys[0]['recommendation_type'] = RecommendationType.LEAST_WALKING
             
        # Sort by transfers
        journeys.sort(key=lambda x: x['transfer_count'])
        if journeys[0]['recommendation_type'] is None:
             journeys[0]['recommendation_type'] = RecommendationType.LEAST_TRANSFERS
             
        return sorted(journeys, key=lambda x: x['score'], reverse=True)

# --- Main Engine ---

class JourneyPlanningEngine:
    def __init__(self):
        self.loc_resolver = LocationResolver()
        self.stop_finder = NearbyStopFinder()
        self.walking_engine = WalkingEngine()
        self.direct_engine = DirectRouteEngine()
        self.transfer_engine = TransferEngine()
        self.live_engine = LiveTransitIntegrationEngine()
        self.eta_engine = EtaIntegrationEngine()
        self.scoring_engine = JourneyScoringEngine()
        self.recommendation_engine = RecommendationEngine()

    def plan_journey(self, origin_data, dest_data, preferences=None):
        logger.info(f"Planning journey from {origin_data} to {dest_data}")
        
        origin = self.loc_resolver.resolve(origin_data)
        dest = self.loc_resolver.resolve(dest_data)
        
        origin_stops = self.stop_finder.find_stops(origin)
        dest_stops = self.stop_finder.find_stops(dest)
        
        # 1. Find routes
        raw_routes = []
        raw_routes.extend(self.direct_engine.search(origin_stops, dest_stops))
        raw_routes.extend(self.transfer_engine.search(origin_stops, dest_stops))
        
        # 2. Build full journeys with walking
        journeys = []
        for route in raw_routes:
            # First walk
            walk_to = self.walking_engine.calculate(origin, Location(0,0)) # Mock stop loc
            # Last walk
            walk_from = self.walking_engine.calculate(Location(0,0), dest)
            
            segments = []
            segments.append({
                "type": JourneySegmentType.WALK,
                "distance_meters": walk_to['distance_meters'],
                "duration": walk_to['time_seconds']
            })
            segments.extend(route['segments'])
            segments.append({
                "type": JourneySegmentType.WALK,
                "distance_meters": walk_from['distance_meters'],
                "duration": walk_from['time_seconds']
            })
            
            total_time = sum(s['duration'] for s in segments)
            total_walk = walk_to['distance_meters'] + walk_from['distance_meters']
            transfers = len([s for s in segments if s['type'] == JourneySegmentType.TRANSFER])
            
            journeys.append({
                "id": f"journey_{len(journeys)}",
                "segments": segments,
                "total_travel_time": total_time,
                "total_walking_distance": total_walk,
                "transfer_count": transfers,
                "eta_confidence": 0,
                "recommendation_type": None
            })
            
        # 3. Enhance with Live Data
        journeys = self.live_engine.integrate(journeys)
        journeys = self.eta_engine.integrate(journeys)
        
        # 4. Score
        for j in journeys:
            self.scoring_engine.score(j)
            
        # 5. Recommend
        final_journeys = self.recommendation_engine.recommend(journeys)
        
        return {
            "origin": {"lat": origin.lat, "lon": origin.lon, "name": origin.name},
            "destination": {"lat": dest.lat, "lon": dest.lon, "name": dest.name},
            "journeys": final_journeys
        }

journey_planning_engine = JourneyPlanningEngine()
