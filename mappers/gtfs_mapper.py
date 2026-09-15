class GTFSMapper:
    @staticmethod
    def to_route_response(route):
        return {
            "route_id": route.route_code,
            "agency_id": "1",  # Hardcoded or map if we have it
            "route_short_name": route.route_code,
            "route_long_name": route.name,
            "route_desc": f"{route.origin} to {route.destination}",
            "route_type": route.route_type or 3,
            "route_color": route.route_color or "FFFFFF",
            "route_text_color": route.route_text_color or "000000",
            
            # Additional mobile-friendly fields requested by user
            "origin": route.origin,
            "destination": route.destination,
            "distanceKm": route.distance_km,
            "totalStops": len(route.stops) if route.stops else 0,
            "estimatedJourneyTime": "2h 15m" # Default placeholder, will compute if possible
        }

    @staticmethod
    def to_stop_response(stop):
        return {
            "stop_id": stop.stop_code or str(stop.id),
            "stop_code": stop.stop_code,
            "stop_name": stop.stop_name,
            "stop_desc": stop.stop_desc,
            "stop_lat": stop.stop_lat,
            "stop_lon": stop.stop_lon,
            "location_type": stop.location_type or 0
        }

    @staticmethod
    def to_shape_response(shape):
        return {
            "shape_id": shape.shape_id,
            "shape_pt_lat": shape.shape_pt_lat,
            "shape_pt_lon": shape.shape_pt_lon,
            "shape_pt_sequence": shape.shape_pt_sequence
        }

    @staticmethod
    def to_trip_response(trip):
        return {
            "route_id": trip.route.route_code if trip.route else "",
            "service_id": trip.service_id,
            "trip_id": trip.gtfs_trip_id,
            "trip_headsign": trip.trip_headsign,
            "direction_id": trip.direction_id,
            "shape_id": trip.shape_id
        }

    @staticmethod
    def to_overview_response(route, stops, shapes, trips, stats):
        return {
            "route": GTFSMapper.to_route_response(route),
            "stops": [GTFSMapper.to_stop_response(s) for s in stops],
            "shape": [GTFSMapper.to_shape_response(sh) for sh in shapes],
            "todayTrips": [GTFSMapper.to_trip_response(t) for t in trips],
            "statistics": stats
        }
