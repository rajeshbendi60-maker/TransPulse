from flask import Blueprint, jsonify
from services.eta_engine import eta_engine
import logging

logger = logging.getLogger(__name__)

eta_bp = Blueprint("eta", __name__, url_prefix="/api/v1/eta")

@eta_bp.route("/vehicle/<int:vehicle_id>", methods=["GET"])
def get_vehicle_eta(vehicle_id):
    try:
        result = eta_engine.calculate_vehicle_eta(vehicle_id)
        if not result:
            return jsonify({"success": False, "error": "Vehicle not found or not active"}), 404
            
        return jsonify({
            "success": True,
            "data": result
        }), 200
    except Exception as e:
        logger.error(f"Error calculating ETA for vehicle {vehicle_id}: {str(e)}")
        return jsonify({"success": False, "error": "Internal server error"}), 500


@eta_bp.route("/stop/<string:stop_id>", methods=["GET"])
def get_stop_eta(stop_id):
    try:
        result = eta_engine.calculate_stop_eta(stop_id)
        return jsonify({
            "success": True,
            "data": result
        }), 200
    except Exception as e:
        logger.error(f"Error calculating ETA for stop {stop_id}: {str(e)}")
        return jsonify({"success": False, "error": "Internal server error"}), 500
# TP-v2.0-Release
