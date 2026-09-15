from flask import Blueprint, jsonify, request
from services.notification_engine import notification_engine
from models.notifications import NotificationRecipient, NotificationStatus, NotificationPreference, NotificationTopic
from extensions import db
import logging

logger = logging.getLogger(__name__)

notifications_bp = Blueprint("notifications", __name__, url_prefix="/api/v1/notifications")

@notifications_bp.route("", methods=["GET"])
def get_notifications():
    # In a real scenario, extract user_id from JWT. 
    user_id = request.args.get('user_id', type=int)
    since = request.args.get('since')
    if not user_id:
        return jsonify({"success": False, "error": "user_id required"}), 400
        
    history = notification_engine.history_engine.get_history(user_id, since)
    return jsonify({"success": True, "data": history}), 200

@notifications_bp.route("/<string:notification_id>/read", methods=["PATCH"])
def mark_as_read(notification_id):
    user_id = request.json.get('user_id')
    recp = NotificationRecipient.query.filter_by(notification_id=notification_id, user_id=user_id).first()
    if recp:
        recp.status = NotificationStatus.READ
        db.session.commit()
    return jsonify({"success": True}), 200

@notifications_bp.route("/send", methods=["POST"])
def send_notification():
    data = request.json
    success = notification_engine.send_targeted_notification(
        user_id=data['user_id'],
        token=data.get('token', 'mock_token'),
        category=data['category'],
        priority=data['priority'],
        title=data['title'],
        body=data['body'],
        deep_link=data.get('deep_link')
    )
    return jsonify({"success": success}), 200 if success else 400

@notifications_bp.route("/preferences", methods=["GET"])
def get_preferences():
    user_id = request.args.get('user_id')
    prefs = NotificationPreference.query.filter_by(user_id=user_id).all()
    return jsonify({
        "success": True,
        "data": [{"category": p.category, "enabled": p.enabled} for p in prefs]
    }), 200

@notifications_bp.route("/preferences", methods=["PATCH"])
def update_preferences():
    data = request.json
    user_id = data['user_id']
    for pref_data in data['preferences']:
        cat = pref_data['category']
        enabled = pref_data['enabled']
        pref = NotificationPreference.query.filter_by(user_id=user_id, category=cat).first()
        if not pref:
            pref = NotificationPreference(user_id=user_id, category=cat, enabled=enabled)
            db.session.add(pref)
        else:
            pref.enabled = enabled
    db.session.commit()
    return jsonify({"success": True}), 200
# TP-v2.0-Release
