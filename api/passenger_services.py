from flask import Blueprint, jsonify, request
from services.passenger_services_platform import passenger_services_platform
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

passenger_services_bp = Blueprint("passenger_services", __name__, url_prefix="/api/v1")

@passenger_services_bp.route("/complaints", methods=["POST"])
def create_complaint():
    # Support multipart/form-data
    user_id = request.form.get('user_id', type=int)
    category = request.form.get('category')
    description = request.form.get('description')
    route_id = request.form.get('route_id')
    bus_id = request.form.get('bus_id', type=int)
    
    files = request.files.getlist('files')
    
    try:
        complaint = passenger_services_platform.complaint_engine.create_complaint(
            user_id=user_id, category=category, description=description, 
            route_id=route_id, bus_id=bus_id, files=files
        )
        return jsonify({"success": True, "data": {"id": complaint.id}}), 200
    except Exception as e:
        logger.error(f"Complaint error: {e}")
        return jsonify({"success": False, "error": str(e)}), 400

@passenger_services_bp.route("/complaints/<string:complaint_id>/status", methods=["PATCH"])
def update_complaint_status(complaint_id):
    new_status = request.json.get('status')
    passenger_services_platform.complaint_engine.update_complaint_status(complaint_id, new_status)
    return jsonify({"success": True}), 200

@passenger_services_bp.route("/lost-found/lost", methods=["POST"])
def report_lost_item():
    user_id = request.form.get('user_id', type=int)
    category = request.form.get('category')
    date_lost = datetime.strptime(request.form.get('date_lost'), '%Y-%m-%d').date()
    color = request.form.get('color')
    brand = request.form.get('brand')
    file = request.files.get('file')
    
    item = passenger_services_platform.lost_found_engine.report_lost_item(
        user_id=user_id, category=category, date_lost=date_lost, color=color, brand=brand, file=file
    )
    return jsonify({"success": True, "data": {"id": item.id}}), 200

@passenger_services_bp.route("/feedback", methods=["POST"])
def submit_feedback():
    data = request.json
    passenger_services_platform.feedback_engine.submit_feedback(
        user_id=data.get('user_id'),
        overall=data['overall'],
        driver=data.get('driver'),
        vehicle=data.get('vehicle'),
        cleanliness=data.get('cleanliness'),
        safety=data.get('safety'),
        comfort=data.get('comfort'),
        punctuality=data.get('punctuality'),
        comments=data.get('comments')
    )
    return jsonify({"success": True}), 200

@passenger_services_bp.route("/emergency/contacts", methods=["GET"])
def get_emergency_contacts():
    contacts = passenger_services_platform.emergency_engine.get_hierarchical_contacts()
    return jsonify({"success": True, "data": [{"level": c.level, "name": c.name, "phone": c.phone_number} for c in contacts]}), 200
# TP-v2.0-Release
