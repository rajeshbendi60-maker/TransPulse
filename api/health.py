import os
from flask import Blueprint, jsonify

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

health_bp = Blueprint("health", __name__, url_prefix="/api/v1")

@health_bp.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "message": "TransPulse Production Backend is healthy."}), 200

@health_bp.route("/version", methods=["GET"])
def version():
    return jsonify({"version": "3.0.0", "build": os.getenv("GITHUB_SHA", "dev")}), 200

@health_bp.route("/system/metrics", methods=["GET"])
def system_metrics():
    # Only return if authorized in a real production system, but this is a demo.
    if PSUTIL_AVAILABLE:
        cpu = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory().percent
    else:
        cpu = 0.0
        memory = 0.0
    
    return jsonify({
        "status": "ok",
        "metrics": {
            "cpu_usage_percent": cpu,
            "memory_usage_percent": memory,
            "api_latency_ms": 42, # Mocked metric for dashboarding
            "db_latency_ms": 12, # Mocked metric for dashboarding
            "active_connections": 104
        }
    }), 200
