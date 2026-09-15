from models import Route, Stop, Shape, Trip, db
from sqlalchemy.orm import joinedload
import logging

logger = logging.getLogger(__name__)

class GTFSRouteService:
    @staticmethod
    def get_routes():
        # Optimization: Fetch routes without eager loading heavy relationships
        # if not needed for the basic list, or just load what's necessary.
        routes = Route.query.filter_by(is_operational=True).all()
        return routes

    @staticmethod
    def get_route_by_id(route_code):
        # We fetch the route by route_code, joinedload stops to prevent N+1 later if needed
        # But wait, stops are loaded in get_stops(). 
        return Route.query.filter_by(route_code=route_code).first()

    @staticmethod
    def get_stops(route_id):
        route = Route.query.filter_by(route_code=route_id).first()
        if not route:
            return []
        # Return stops associated with the route, sorted by stop_order
        return sorted(route.stops, key=lambda s: (s.stop_order or 0))

    @staticmethod
    def get_shape(route_id):
        # Try to find a trip for this route and return its shape
        route = Route.query.filter_by(route_code=route_id).first()
        if not route or not route.trips:
            return []
        
        first_trip = route.trips[0]
        if not first_trip.shape_id:
            return []
            
        shapes = Shape.query.filter_by(shape_id=first_trip.shape_id).order_by(Shape.shape_pt_sequence).all()
        return shapes

    @staticmethod
    def get_trips(route_id):
        route = Route.query.filter_by(route_code=route_id).first()
        if not route:
            return []
        return route.trips

    @staticmethod
    def get_overview(route_id):
        # Optimized query using joinedload to fetch Route and its Trips to avoid N+1
        route = Route.query.options(joinedload(Route.trips), joinedload(Route.stops)).filter_by(route_code=route_id).first()
        if not route:
            return None, None, None, None, None

        stops = sorted(route.stops, key=lambda s: (s.stop_order or 0))
        trips = route.trips
        
        shape_id = trips[0].shape_id if trips else None
        shapes = []
        if shape_id:
            shapes = Shape.query.filter_by(shape_id=shape_id).order_by(Shape.shape_pt_sequence).all()

        stats = {
            "distanceKm": route.distance_km,
            "totalStops": len(stops),
            "totalTrips": len(trips),
            "operator": "APSRTC",
            "districtsCovered": 2, # Placeholder
            "estimatedJourneyTime": "2h 15m" # Placeholder
        }
        
        return route, stops, shapes, trips, stats


class GTFSStopService:
    @staticmethod
    def get_stop_by_id(stop_code):
        return Stop.query.filter_by(stop_code=stop_code).first()

    @staticmethod
    def get_routes_for_stop(stop_code):
        stop = Stop.query.filter_by(stop_code=stop_code).first()
        if stop and stop.route:
            return [stop.route]
        return []
# TP-v2.0-Release
