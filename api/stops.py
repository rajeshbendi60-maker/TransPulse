import math
from flask import Blueprint, request, jsonify
from flask_login import login_required
from models.stop import Stop

stops_bp = Blueprint("stops", __name__, url_prefix="/api/stops")

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371.0 # Earth radius in kilometers
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = math.sin(dLat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dLon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

@stops_bp.route("/nearby", methods=["GET"])
@login_required
def get_nearby_stops():
    try:
        lat_str = request.args.get("lat")
        lng_str = request.args.get("lng")
        
        if not lat_str or not lng_str:
            return jsonify({"success": False, "error": "Missing lat or lng"}), 400
            
        lat = float(lat_str)
        lng = float(lng_str)
        radius_km = float(request.args.get("radius", 5.0)) # Default 5km radius
        
        all_stops = Stop.query.filter(Stop.stop_lat.isnot(None), Stop.stop_lon.isnot(None)).all()
        
        nearby = []
        seen = set()
        for stop in all_stops:
            stop_key = f"{str(stop.stop_name).strip().upper()}_{round(stop.stop_lat, 4)}_{round(stop.stop_lon, 4)}"
            if stop_key in seen:
                continue
                
            dist = haversine_distance(lat, lng, stop.stop_lat, stop.stop_lon)
            if dist <= radius_km:
                seen.add(stop_key)
                nearby.append({
                    "id": stop.id,
                    "stop_name": stop.stop_name,
                    "stop_code": stop.stop_code,
                    "lat": stop.stop_lat,
                    "lng": stop.stop_lon,
                    "distance_km": round(dist, 2)
                })
                
        nearby.sort(key=lambda x: x["distance_km"])
        
        return jsonify({
            "success": True,
            "stops": nearby[:20]
        }), 200
        
    except ValueError:
        return jsonify({"success": False, "error": "Invalid coordinates format"}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
# TP-v2.0-Release
