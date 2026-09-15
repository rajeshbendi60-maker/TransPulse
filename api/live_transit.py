from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from services.live_transit_engine import LiveTransitEngine
from mappers.live_transit_mapper import LiveTransitMapper
import logging

logger = logging.getLogger(__name__)

live_bp = Blueprint("live", __name__, url_prefix="/api/v1/live")

@live_bp.route("/vehicles", methods=["GET"])
def get_live_vehicles():
    try:
        vehicles = LiveTransitEngine.get_live_vehicles()
        data = [LiveTransitMapper.to_response(b, p, r, a) for b, p, r, a in vehicles]
        
        return jsonify({
            "success": True,
            "data": data
        }), 200
    except Exception as e:
        logger.error(f"Error fetching live vehicles: {str(e)}")
        return jsonify({"success": False, "error": "Internal server error"}), 500


@live_bp.route("/vehicles/<int:vehicle_id>", methods=["GET"])
def get_live_vehicle(vehicle_id):
    try:
        result = LiveTransitEngine.get_vehicle_by_id(vehicle_id)
        if not result:
            return jsonify({"success": False, "error": "Vehicle not found"}), 404
            
        b, p, r, a = result
        return jsonify({
            "success": True,
            "data": LiveTransitMapper.to_response(b, p, r, a)
        }), 200
    except Exception as e:
        logger.error(f"Error fetching live vehicle: {str(e)}")
        return jsonify({"success": False, "error": "Internal server error"}), 500


@live_bp.route("/location", methods=["POST"])
# @login_required (assuming driver/device auth needed, but omitted for testing Phase 3.7 flow)
def post_vehicle_location():
    try:
        data = request.get_json()
        if not data or 'busId' not in data or 'latitude' not in data or 'longitude' not in data:
            return jsonify({"success": False, "error": "Invalid payload"}), 400
            
        bus_id = data['busId']
        lat = data['latitude']
        lng = data['longitude']
        speed = data.get('speed', 0.0)
        heading = data.get('heading', 0.0)
        accuracy = data.get('accuracy', 0.0)
        
        b, p, r, a = LiveTransitEngine.process_gps_update(bus_id, lat, lng, speed, heading, accuracy)
        
        # Integrate SOS data capture with live vehicle context if SOS flag is present
        if data.get('isSOS'):
            # Trigger District Control Room notification logic here
            logger.warning(f"SOS triggered from bus {bus_id} at {lat}, {lng}")
            pass
            
        return jsonify({
            "success": True,
            "data": LiveTransitMapper.to_response(b, p, r, a)
        }), 200
    except Exception as e:
        logger.error(f"Error posting vehicle location: {str(e)}")
        return jsonify({"success": False, "error": "Internal server error"}), 500
# TP-v2.0-Release
