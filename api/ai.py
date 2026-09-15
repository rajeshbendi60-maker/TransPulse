from flask import Blueprint, jsonify, request
from services.ai_platform.artificial_intelligence_platform import ai_platform
import logging

logger = logging.getLogger(__name__)

ai_bp = Blueprint("ai", __name__, url_prefix="/api/v1/ai")

@ai_bp.route("/dashboard", methods=["GET"])
def get_dashboard():
    data = ai_platform.get_dashboard_metrics()
    return jsonify({"success": True, "data": data}), 200

@ai_bp.route("/predictions", methods=["GET"])
def get_predictions():
    domain = request.args.get('domain', 'general')
    data = ai_platform.predict(domain, {"role": "Admin"})
    return jsonify({"success": True, "data": [data]}), 200

@ai_bp.route("/recommendations", methods=["GET"])
def get_recommendations():
    domain = request.args.get('domain', 'general')
    data = ai_platform.predict(domain, {"role": "Admin"})
    # Just returning the recommendation string wrapped in a dict
    return jsonify({"success": True, "data": [{"recommendation": data["recommendation"], "domain": domain}]}), 200

@ai_bp.route("/anomalies", methods=["GET"])
def get_anomalies():
    data = ai_platform.get_anomalies()
    return jsonify({"success": True, "data": data}), 200

@ai_bp.route("/assistant", methods=["POST"])
def ask_assistant():
    prompt = request.json.get("prompt", "")
    role = request.json.get("role", "Admin")
    response = ai_platform.ask_assistant(prompt, role)
    return jsonify({"success": True, "data": {"response": response}}), 200
