from flask import Blueprint, jsonify, request
from services.driver_operations_engine import driver_operations_engine
import logging

logger = logging.getLogger(__name__)

driver_bp = Blueprint("driver", __name__, url_prefix="/api/v1/driver")

@driver_bp.route("/assignments", methods=["GET"])
def get_assignments():
    # Mock assignments for Driver
    driver_id = 1 # Mock driver ID
    
    return jsonify({
        "success": True,
        "data": {
            "driverId": driver_id,
            "assignedBus": {"busId": 101, "busNumber": "TS09Z1234", "depot": "Secunderabad"},
            "sessionId": "mock_session_id",
            "shiftStatus": "OFF_DUTY",
            "assignedTrips": [
                {"tripId": "trip_001", "routeId": "205", "startTime": "08:00", "endTime": "09:30"}
            ]
        }
    }), 200

@driver_bp.route("/shift/status", methods=["POST"])
def update_shift_status():
    data = request.json
    try:
        session = driver_operations_engine.shift_engine.update_shift_status(
            session_id=data['sessionId'],
            new_status=data['status']
        )
        return jsonify({"success": True, "data": {"status": session.status}}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@driver_bp.route("/trip/status", methods=["POST"])
def update_trip_status():
    data = request.json
    try:
        trip_log = driver_operations_engine.trip_engine.update_trip_status(
            session_id=data['sessionId'],
            trip_id=data['tripId'],
            new_status=data['status']
        )
        return jsonify({"success": True, "data": {"status": trip_log.status}}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@driver_bp.route("/location", methods=["POST"])
def ingest_location():
    data = request.json
    try:
        driver_operations_engine.gps_engine.ingest_location(
            bus_id=data['busId'],
            lat=data['lat'],
            lon=data['lon'],
            heading=data.get('heading', 0),
            speed=data.get('speed', 0),
            accuracy=data.get('accuracy', 0)
        )
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@driver_bp.route("/sos", methods=["POST"])
def trigger_sos():
    data = request.json
    try:
        driver_operations_engine.sos_engine.trigger_sos(
            driver_id=data['driverId'],
            bus_id=data['busId'],
            lat=data['lat'],
            lon=data['lon']
        )
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@driver_bp.route("/inspection", methods=["POST"])
def submit_inspection():
    data = request.json
    try:
        driver_operations_engine.inspection_engine.submit_inspection(
            session_id=data['sessionId'],
            bus_id=data['busId'],
            data=data
        )
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@driver_bp.route("/incident", methods=["POST"])
def report_incident():
    data = request.json
    try:
        driver_operations_engine.incident_engine.report_incident(
            driver_id=data['driverId'],
            bus_id=data.get('busId'),
            category=data['category'],
            description=data['description'],
            lat=data.get('lat'),
            lon=data.get('lon')
        )
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400
# TP-v2.0-Release
