from flask import Blueprint, jsonify, request
from services.business_intelligence_platform import bi_platform
import logging

logger = logging.getLogger(__name__)

analytics_bp = Blueprint("analytics", __name__, url_prefix="/api/v1/analytics")

@analytics_bp.route("/dashboard", methods=["GET"])
def get_dashboard():
    # Enforce role checks in real implementation
    data = bi_platform.kpi_engine.get_live_dashboard_metrics()
    return jsonify({"success": True, "data": data}), 200

@analytics_bp.route("/fleet", methods=["GET"])
def get_fleet_analytics():
    district_id = request.args.get('district_id')
    data = bi_platform.fleet_engine.get_fleet_metrics(district_id)
    return jsonify({"success": True, "data": data}), 200

@analytics_bp.route("/heatmaps/<string:map_type>", methods=["GET"])
def get_heatmap(map_type):
    data = bi_platform.heatmap_engine.get_density_data(map_type)
    return jsonify({"success": True, "data": data}), 200

@analytics_bp.route("/export/pdf", methods=["POST"])
def export_pdf():
    # Pass JSON metrics payload to export
    url = bi_platform.export_engine.export_pdf(request.json)
    return jsonify({"success": True, "url": url}), 200

@analytics_bp.route("/export/excel", methods=["POST"])
def export_excel():
    url = bi_platform.export_engine.export_excel(request.json)
    return jsonify({"success": True, "url": url}), 200

@analytics_bp.route("/export/csv", methods=["POST"])
def export_csv():
    url = bi_platform.export_engine.export_csv(request.json)
    return jsonify({"success": True, "url": url}), 200
# TP-v2.0-Release
