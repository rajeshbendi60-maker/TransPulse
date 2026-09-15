from flask import Blueprint, jsonify, request
from services.district_operations_engine import district_operations_engine
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

district_admin_bp = Blueprint("district_admin", __name__, url_prefix="/api/v1/admin")

@district_admin_bp.route("/dashboard", methods=["GET"])
def get_dashboard():
    district_id = request.args.get('district_id', 1)
    
    fleet_metrics = district_operations_engine.fleet_engine.get_district_fleet_metrics(district_id)
    driver_metrics = district_operations_engine.driver_engine.get_driver_metrics(district_id)
    incident_metrics = district_operations_engine.incident_engine.get_incident_metrics(district_id)
    
    return jsonify({
        "success": True,
        "data": {
            "fleet": fleet_metrics,
            "drivers": driver_metrics,
            "incidents": incident_metrics
        }
    }), 200

@district_admin_bp.route("/fleet/live", methods=["GET"])
def get_live_fleet():
    depot_id = request.args.get('depot_id', 1)
    positions = district_operations_engine.fleet_engine.get_live_fleet_positions(depot_id)
    return jsonify({"success": True, "data": positions}), 200

@district_admin_bp.route("/assign", methods=["POST"])
def create_assignment():
    data = request.json
    try:
        scheduled_date = datetime.strptime(data['scheduledDate'], '%Y-%m-%d').date()
        assignment = district_operations_engine.assignment_engine.create_assignment(
            driver_id=data['driverId'],
            bus_id=data['busId'],
            route_id=data['routeId'],
            depot_id=data['depotId'],
            admin_id=data['adminId'],
            scheduled_date=scheduled_date
        )
        return jsonify({"success": True, "data": {"assignmentId": assignment.id}}), 200
    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        logger.error(f"Assignment error: {e}")
        return jsonify({"success": False, "error": "Internal server error"}), 500

@district_admin_bp.route("/incidents", methods=["GET"])
def get_incidents():
    # Mock incidents
    return jsonify({
        "success": True,
        "data": [
            {"id": "inc_1", "priority": "CRITICAL", "category": "SOS", "status": "OPEN", "driverId": 12, "busId": 101}
        ]
    }), 200

@district_admin_bp.route("/incidents/resolve", methods=["POST"])
def resolve_incident():
    data = request.json
    try:
        district_operations_engine.incident_engine.resolve_incident(
            incident_id=data['incidentId'],
            admin_id=data['adminId']
        )
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400
# TP-v2.0-Release
