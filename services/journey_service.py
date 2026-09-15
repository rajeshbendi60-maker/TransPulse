from models.journey import Journey
from extensions import db
from datetime import datetime, timedelta
import uuid

class JourneyService:

    @staticmethod
    def get_journeys(user_id):
        return Journey.query.filter_by(user_id=user_id).order_by(Journey.travel_date.desc(), Journey.departure_time.desc()).all()

    @staticmethod
    def get_journey_by_id(journey_id, user_id):
        return Journey.query.filter_by(id=journey_id, user_id=user_id).first()

    @staticmethod
    def create_or_update_journey(user_id, data, mapper_class):
        journey_id = data.get("id")
        device_id = data.get("deviceId", "unknown_device")
        
        # Parse dates
        departure_time = None
        if data.get("departureTime"):
            try:
                departure_time = datetime.fromtimestamp(data["departureTime"] / 1000.0)
            except:
                pass
                
        arrival_time = None
        if data.get("arrivalTime"):
            try:
                arrival_time = datetime.fromtimestamp(data["arrivalTime"] / 1000.0)
            except:
                pass
                
        travel_date = datetime.utcnow().date()
        if data.get("travelDate"):
            try:
                travel_date = datetime.fromtimestamp(data["travelDate"] / 1000.0).date()
            except:
                pass

        if journey_id:
            existing = Journey.query.filter_by(id=journey_id, user_id=user_id).first()
            if existing:
                # Conflict resolution: updatedAt tiebreaker
                client_updated_at = None
                if data.get("updatedAt"):
                    try:
                        client_updated_at = datetime.fromtimestamp(data["updatedAt"] / 1000.0)
                    except:
                        pass
                
                if client_updated_at:
                    if existing.updated_at and client_updated_at < existing.updated_at:
                        # Server has newer version
                        if existing.device_id != device_id:
                            return existing, False # Reject update

                # Update fields
                existing.route_id = data.get("routeId", existing.route_id)
                existing.trip_id = data.get("tripId", existing.trip_id)
                existing.vehicle_id = data.get("vehicleId", existing.vehicle_id)
                existing.driver_id = data.get("driverId", existing.driver_id)
                existing.origin_stop_id = data.get("originStopId", existing.origin_stop_id)
                existing.destination_stop_id = data.get("destinationStopId", existing.destination_stop_id)
                existing.origin_stop_name = data.get("originStopName", existing.origin_stop_name)
                existing.destination_stop_name = data.get("destinationStopName", existing.destination_stop_name)
                existing.route_number = data.get("routeNumber", existing.route_number)
                existing.route_name = data.get("routeName", existing.route_name)
                
                if departure_time:
                    existing.departure_time = departure_time
                if arrival_time:
                    existing.arrival_time = arrival_time
                existing.travel_date = travel_date
                
                existing.travel_duration = data.get("travelDuration", existing.travel_duration)
                existing.distance_km = data.get("distanceKm", existing.distance_km)
                existing.fare = data.get("fare", existing.fare)
                existing.journey_status = data.get("journeyStatus", existing.journey_status)
                existing.eta_difference = data.get("etaDifference", existing.eta_difference)
                existing.travel_mode = data.get("travelMode", existing.travel_mode)
                
                existing.updated_at = datetime.utcnow()
                existing.device_id = device_id
                
                db.session.commit()
                return existing, True

        # Create new
        new_id = journey_id if journey_id else str(uuid.uuid4())
        new_journey = Journey(
            id=new_id,
            user_id=user_id,
            route_id=data.get("routeId"),
            trip_id=data.get("tripId"),
            vehicle_id=data.get("vehicleId"),
            driver_id=data.get("driverId"),
            origin_stop_id=data.get("originStopId"),
            destination_stop_id=data.get("destinationStopId"),
            origin_stop_name=data.get("originStopName"),
            destination_stop_name=data.get("destinationStopName"),
            route_number=data.get("routeNumber"),
            route_name=data.get("routeName"),
            departure_time=departure_time,
            arrival_time=arrival_time,
            travel_date=travel_date,
            travel_duration=data.get("travelDuration"),
            distance_km=data.get("distanceKm"),
            fare=data.get("fare"),
            journey_status=data.get("journeyStatus", "PLANNED"),
            eta_difference=data.get("etaDifference"),
            travel_mode=data.get("travelMode", "BUS"),
            device_id=device_id
        )
        
        db.session.add(new_journey)
        db.session.commit()
        return new_journey, True

    @staticmethod
    def delete_journey(journey_id, user_id):
        journey = Journey.query.filter_by(id=journey_id, user_id=user_id).first()
        if journey:
            db.session.delete(journey)
            db.session.commit()
            return True
        return False

    @staticmethod
    def get_statistics(user_id):
        journeys = Journey.query.filter_by(user_id=user_id).all()
        
        if not journeys:
            return {
                "totalTrips": 0,
                "totalDistance": 0.0,
                "totalDuration": 0,
                "longestJourneyDistance": 0.0,
                "shortestJourneyDistance": 0.0,
                "averageDistance": 0.0,
                "averageDuration": 0,
                "mostUsedRoute": None,
                "mostUsedStop": None,
                "tripsThisWeek": 0,
                "tripsThisMonth": 0,
                "favoriteDistrict": None,
                "travelStreak": 0
            }
            
        completed_journeys = [j for j in journeys if j.journey_status == "COMPLETED"]
        
        total_trips = len(journeys)
        distances = [j.distance_km for j in completed_journeys if j.distance_km is not None]
        durations = [j.travel_duration for j in completed_journeys if j.travel_duration is not None]
        
        total_distance = sum(distances)
        total_duration = sum(durations)
        
        avg_distance = total_distance / len(distances) if distances else 0.0
        avg_duration = total_duration / len(durations) if durations else 0
        
        longest = max(distances) if distances else 0.0
        shortest = min(distances) if distances else 0.0
        
        # Date calculations
        now = datetime.utcnow()
        week_ago = now.date() - timedelta(days=7)
        month_ago = now.date() - timedelta(days=30)
        
        trips_week = sum(1 for j in journeys if j.travel_date and j.travel_date >= week_ago)
        trips_month = sum(1 for j in journeys if j.travel_date and j.travel_date >= month_ago)
        
        # Route freq
        route_counts = {}
        for j in journeys:
            if j.route_number:
                route_counts[j.route_number] = route_counts.get(j.route_number, 0) + 1
        most_used_route = max(route_counts, key=route_counts.get) if route_counts else None
        
        # Stop freq (combining origin and destination)
        stop_counts = {}
        for j in journeys:
            if j.origin_stop_name:
                stop_counts[j.origin_stop_name] = stop_counts.get(j.origin_stop_name, 0) + 1
            if j.destination_stop_name:
                stop_counts[j.destination_stop_name] = stop_counts.get(j.destination_stop_name, 0) + 1
        most_used_stop = max(stop_counts, key=stop_counts.get) if stop_counts else None
        
        return {
            "totalTrips": total_trips,
            "totalDistance": round(total_distance, 2),
            "totalDuration": int(total_duration),
            "longestJourneyDistance": round(longest, 2),
            "shortestJourneyDistance": round(shortest, 2),
            "averageDistance": round(avg_distance, 2),
            "averageDuration": int(avg_duration),
            "mostUsedRoute": most_used_route,
            "mostUsedStop": most_used_stop,
            "tripsThisWeek": trips_week,
            "tripsThisMonth": trips_month,
            "favoriteDistrict": "Placeholder",
            "travelStreak": 1
        }
# TP-v2.0-Release
