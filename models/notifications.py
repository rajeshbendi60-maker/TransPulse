from extensions import db
from datetime import datetime
import uuid

class NotificationCategory:
    ETA = "ETA"
    LIVE_TRANSIT = "LIVE_TRANSIT"
    JOURNEY = "JOURNEY"
    ROUTE_CHANGE = "ROUTE_CHANGE"
    EMERGENCY = "EMERGENCY"
    SOS = "SOS"
    DRIVER = "DRIVER"
    ADMIN = "ADMIN"
    STATE = "STATE"
    SYSTEM = "SYSTEM"
    MARKETING = "MARKETING"

class NotificationPriority:
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    NORMAL = "NORMAL"
    LOW = "LOW"

class NotificationStatus:
    CREATED = "CREATED"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    OPENED = "OPENED"
    READ = "READ"
    FAILED = "FAILED"

class Notification(db.Model):
    __tablename__ = 'system_notifications'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    category = db.Column(db.String(50), nullable=False)
    priority = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    body = db.Column(db.Text, nullable=False)
    deep_link = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class NotificationRecipient(db.Model):
    __tablename__ = 'notification_recipients'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    notification_id = db.Column(db.String(36), db.ForeignKey('system_notifications.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(50), default=NotificationStatus.CREATED)
    received_at = db.Column(db.DateTime, nullable=True)
    read_at = db.Column(db.DateTime, nullable=True)

class NotificationPreference(db.Model):
    __tablename__ = 'notification_preferences'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    enabled = db.Column(db.Boolean, default=True)

class NotificationDelivery(db.Model):
    __tablename__ = 'notification_deliveries'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    notification_id = db.Column(db.String(36), db.ForeignKey('system_notifications.id'), nullable=False)
    user_id = db.Column(db.Integer, nullable=True)
    fcm_message_id = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(50), nullable=False)
    error_message = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class NotificationTopic(db.Model):
    __tablename__ = 'notification_topics'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    topic = db.Column(db.String(255), nullable=False)

class NotificationAuditLog(db.Model):
    __tablename__ = 'notification_audit_logs'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    admin_id = db.Column(db.Integer, nullable=False)
    action = db.Column(db.String(100), nullable=False)
    target = db.Column(db.String(255), nullable=False)
    notification_id = db.Column(db.String(36), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
