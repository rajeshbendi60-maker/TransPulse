from flask import Blueprint, jsonify, request
from services.state_operations_platform import state_operations_platform
import logging

logger = logging.getLogger(__name__)

control_bp = Blueprint("control", __name__, url_prefix="/api/v1/control")

# Authentication / Role checking decorator mock
def require_state_admin(f):
    def wrap(*args, **kwargs):
        # In real code, check JWT role.
        auth_header = request.headers.get("Authorization")
        if not auth_header or "state_admin" not in auth_header:
            return jsonify({"success": False, "error": "Forbidden"}), 403
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__
    return wrap

@control_bp.route("/dashboard", methods=["GET"])
@require_state_admin
def get_dashboard():
    data = state_operations_platform.dashboard_engine.get_state_metrics()
    return jsonify({"success": True, "data": data}), 200

@control_bp.route("/districts", methods=["GET"])
@require_state_admin
def get_districts():
    data = state_operations_platform.district_aggregator.get_districts_overview()
    return jsonify({"success": True, "data": data}), 200

@control_bp.route("/fleet", methods=["GET"])
@require_state_admin
def get_fleet():
    # Large payload - could use GeoJSON directly, but returning list for now
    data = state_operations_platform.fleet_aggregator.get_live_state_fleet()
    return jsonify({"success": True, "data": data}), 200

@control_bp.route("/incidents", methods=["GET"])
@require_state_admin
def get_incidents():
    data = state_operations_platform.emergency_engine.get_sos_and_critical()
    return jsonify({"success": True, "data": data}), 200

@control_bp.route("/system-health", methods=["GET"])
@require_state_admin
def get_system_health():
    data = state_operations_platform.health_engine.capture_system_health()
    return jsonify({
        "success": True,
        "data": {
            "apiResponseTimeMs": data.api_response_time_ms,
            "dbLatencyMs": data.db_latency_ms,
            "gpsUploadRate": data.gps_upload_rate,
            "onlineDrivers": data.online_drivers,
            "onlineVehicles": data.online_vehicles,
            "liveTransitStatus": data.live_transit_status,
            "etaEngineStatus": data.eta_engine_status,
            "journeyPlannerStatus": data.journey_planner_status
        }
    }), 200

@control_bp.route("/broadcast", methods=["POST"])
@require_state_admin
def send_broadcast():
    data = request.json
    try:
        ip = request.remote_addr
        state_operations_platform.broadcast_engine.send_broadcast(
            admin_id=data['adminId'],
            target_type=data['targetType'],
            target_id=data.get('targetId'),
            message=data['message'],
            priority=data['priority'],
            ip_address=ip
        )
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@control_bp.route("/acknowledge", methods=["POST"])
@require_state_admin
def acknowledge_alert():
    data = request.json
    try:
        state_operations_platform.emergency_engine.resolve_alert(
            alert_id=data['alertId'],
            admin_id=data['adminId']
        )
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400
# TP-v2.0-Release
