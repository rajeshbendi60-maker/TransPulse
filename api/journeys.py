from flask import Blueprint, request, jsonify
from flask_login import current_user, login_required
from services.journey_service import JourneyService
from mappers.journey_mapper import JourneyMapper
import logging

logger = logging.getLogger(__name__)

journeys_bp = Blueprint("journeys", __name__, url_prefix="/api/v1/journeys")

@journeys_bp.route("/history", methods=["GET"])
@login_required
def get_journey_history():
    try:
        journeys = JourneyService.get_journeys(current_user.id)
        return jsonify({
            "success": True,
            "data": [JourneyMapper.to_response(j) for j in journeys]
        }), 200
    except Exception as e:
        logger.error(f"Error fetching journeys: {str(e)}")
        return jsonify({"success": False, "error": "Internal server error"}), 500


@journeys_bp.route("/statistics", methods=["GET"])
@login_required
def get_journey_statistics():
    try:
        stats = JourneyService.get_statistics(current_user.id)
        return jsonify({
            "success": True,
            "data": stats
        }), 200
    except Exception as e:
        logger.error(f"Error fetching journey statistics: {str(e)}")
        return jsonify({"success": False, "error": "Internal server error"}), 500


@journeys_bp.route("", methods=["POST"])
@login_required
def create_journey():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Invalid payload"}), 400
            
        journey, _ = JourneyService.create_or_update_journey(current_user.id, data, JourneyMapper)
        
        return jsonify({
            "success": True,
            "data": JourneyMapper.to_response(journey)
        }), 201
    except Exception as e:
        logger.error(f"Error creating journey: {str(e)}")
        return jsonify({"success": False, "error": "Internal server error"}), 500


@journeys_bp.route("/<journey_id>", methods=["GET"])
@login_required
def get_journey(journey_id):
    try:
        journey = JourneyService.get_journey_by_id(journey_id, current_user.id)
        if not journey:
            return jsonify({"success": False, "error": "Journey not found"}), 404
            
        return jsonify({
            "success": True,
            "data": JourneyMapper.to_response(journey)
        }), 200
    except Exception as e:
        logger.error(f"Error fetching journey: {str(e)}")
        return jsonify({"success": False, "error": "Internal server error"}), 500


@journeys_bp.route("/<journey_id>", methods=["PATCH"])
@login_required
def update_journey(journey_id):
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Invalid payload"}), 400
            
        data["id"] = journey_id
        journey, updated = JourneyService.create_or_update_journey(current_user.id, data, JourneyMapper)
        
        return jsonify({
            "success": True,
            "data": JourneyMapper.to_response(journey)
        }), 200
    except Exception as e:
        logger.error(f"Error updating journey: {str(e)}")
        return jsonify({"success": False, "error": "Internal server error"}), 500


@journeys_bp.route("/<journey_id>", methods=["DELETE"])
@login_required
def delete_journey(journey_id):
    try:
        success = JourneyService.delete_journey(journey_id, current_user.id)
        if not success:
            return jsonify({"success": False, "error": "Journey not found or could not be deleted"}), 404
            
        return jsonify({"success": True, "message": "Journey deleted successfully"}), 200
    except Exception as e:
        logger.error(f"Error deleting journey: {str(e)}")
        return jsonify({"success": False, "error": "Internal server error"}), 500

@journeys_bp.route("", methods=["DELETE"])
@login_required
def delete_all_journeys():
    try:
        # Extra scope out of bounds to delete all histories, mock implementation for now
        return jsonify({"success": False, "error": "Not implemented"}), 501
    except Exception as e:
        logger.error(f"Error deleting all journeys: {str(e)}")
        return jsonify({"success": False, "error": "Internal server error"}), 500
