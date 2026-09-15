from datetime import datetime

class LiveTransitMapper:

    @staticmethod
    def to_response(bus, position, route_progress, assignment):
        def datetime_to_millis(dt):
            return int(dt.timestamp() * 1000) if dt else None

        # 1. Vehicle block (Metadata)
        vehicle_block = None
        if bus:
            vehicle_block = {
                "id": str(bus.id),
                "vehicleNumber": bus.bus_number,
                "driverId": bus.assigned_driver_code,
                "driverName": bus.assigned_driver_name,
                "depot": "Main Depot", # Placeholder
            }
            
        # 2. Position block
        position_block = None
        if position:
            position_block = {
                "latitude": position.latitude,
                "longitude": position.longitude,
                "speed": position.speed,
                "heading": position.heading,
                "accuracy": position.accuracy,
                "bearing": position.bearing,
                "lastUpdated": datetime_to_millis(position.last_updated)
            }
            
        # 3. Status block
        status_block = None
        if position:
            status_block = {
                "status": position.status,
                "delaySeconds": 0, # Future placeholder
            }
            
        # 4. Route Progress block
        route_progress_block = route_progress if route_progress else None
        
        # Insert assignments to route_progress if they exist
        if assignment and not route_progress_block:
            route_progress_block = {
                "routeId": assignment.route_id,
                "tripId": assignment.trip_id
            }
        elif assignment and route_progress_block:
            route_progress_block["routeId"] = assignment.route_id
            route_progress_block["tripId"] = assignment.trip_id

        return {
            "vehicle": vehicle_block,
            "position": position_block,
            "routeProgress": route_progress_block,
            "status": status_block
        }
