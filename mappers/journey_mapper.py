from datetime import datetime

class JourneyMapper:
    @staticmethod
    def to_response(journey):
        def datetime_to_millis(dt):
            return int(dt.timestamp() * 1000) if dt else None

        def date_to_millis(d):
            if d:
                dt = datetime.combine(d, datetime.min.time())
                return int(dt.timestamp() * 1000)
            return None

        return {
            "id": journey.id,
            "routeId": journey.route_id,
            "tripId": journey.trip_id,
            "vehicleId": journey.vehicle_id,
            "driverId": journey.driver_id,
            "originStopId": journey.origin_stop_id,
            "destinationStopId": journey.destination_stop_id,
            "originStopName": journey.origin_stop_name,
            "destinationStopName": journey.destination_stop_name,
            "routeNumber": journey.route_number,
            "routeName": journey.route_name,
            "departureTime": datetime_to_millis(journey.departure_time),
            "arrivalTime": datetime_to_millis(journey.arrival_time),
            "travelDate": date_to_millis(journey.travel_date),
            "travelDuration": journey.travel_duration,
            "distanceKm": journey.distance_km,
            "fare": journey.fare,
            "journeyStatus": journey.journey_status,
            "etaDifference": journey.eta_difference,
            "travelMode": journey.travel_mode,
            "createdAt": datetime_to_millis(journey.created_at),
            "updatedAt": datetime_to_millis(journey.updated_at),
            "deviceId": journey.device_id
        }
