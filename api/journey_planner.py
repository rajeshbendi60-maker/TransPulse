from flask import Blueprint, jsonify, request
from services.journey_planning_engine import journey_planning_engine
import logging

logger = logging.getLogger(__name__)

journey_planner_bp = Blueprint("journey_planner", __name__, url_prefix="/api/v1/journey")

@journey_planner_bp.route("/plan", methods=["POST"])
def plan_journey():
    data = request.json
    if not data or 'origin' not in data or 'destination' not in data:
        return jsonify({"success": False, "error": "Origin and destination required"}), 400
        
    try:
        result = journey_planning_engine.plan_journey(
            origin_data=data['origin'],
            dest_data=data['destination'],
            preferences=data.get('preferences')
        )
        return jsonify({"success": True, "data": result}), 200
    except Exception as e:
        logger.error(f"Journey plan error: {e}")
        return jsonify({"success": False, "error": "Internal server error"}), 500

@journey_planner_bp.route("/alternatives", methods=["POST"])
def alternatives():
    # Same as plan for now, could apply different filters
    return plan_journey()

@journey_planner_bp.route("/recent", methods=["GET"])
def recent_journeys():
    # Mock recent journeys for the user
    return jsonify({"success": True, "data": []}), 200

@journey_planner_bp.route("/favorite", methods=["POST"])
def favorite_journey():
    return jsonify({"success": True, "message": "Journey saved"}), 200
# TP-v2.0-Release
